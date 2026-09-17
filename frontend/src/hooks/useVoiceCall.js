import { useCallback, useRef, useState } from 'react';
import { PcmAudioPlayer } from '../audio/audio-player';

const BACKEND_WS_URL = import.meta.env.VITE_BACKEND_WS_URL || 'ws://localhost:8000';

// Owns the mic capture, the /voice websocket, and the playback queue for one
// continuous call. Talks to the backend in the app's own wire protocol:
// binary frames both ways are PCM16 audio; JSON frames carry
// user_partial/user_final/assistant_text/interrupt/error.
export function useVoiceCall({ sessionId, onUserPartial, onUserFinal, onAssistantText, onError }) {
  const [isCallActive, setIsCallActive] = useState(false);
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const workletNodeRef = useRef(null);
  const micStreamRef = useRef(null);
  const playerRef = useRef(null);

  const startCall = useCallback(async () => {
    const wsUrl = `${BACKEND_WS_URL}/voice?session_id=${encodeURIComponent(sessionId)}`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    const player = new PcmAudioPlayer(16000);
    playerRef.current = player;

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        const msg = JSON.parse(event.data);
        if (msg.type === 'user_partial') onUserPartial?.(msg.text);
        else if (msg.type === 'user_final') onUserFinal?.(msg.text);
        else if (msg.type === 'assistant_text') onAssistantText?.(msg.text, msg.demo_actions);
        else if (msg.type === 'interrupt') player.clear();
        else if (msg.type === 'error') onError?.(msg.message);
      } else {
        player.enqueue(event.data);
      }
    };

    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = () => reject(new Error(`voice websocket failed to connect (${wsUrl})`));
      ws.onclose = (event) => {
        reject(new Error(`voice websocket closed before opening (code ${event.code}: ${event.reason || 'no reason given'}) -- url ${wsUrl}`));
      };
    });
    ws.onclose = null;

    // Explicit constraints rather than relying on browser defaults: without
    // echo cancellation, the mic picks up the bot's own voice from your
    // speakers, which Sarvam's VAD reads as you interrupting -- cutting the
    // reply off mid-sentence even though you never spoke. Doesn't fully
    // replace using headphones, but helps a lot on speakers.
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    micStreamRef.current = stream;

    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    audioContextRef.current = audioContext;
    await audioContext.audioWorklet.addModule('/pcm-recorder-worklet.js');

    const source = audioContext.createMediaStreamSource(stream);
    const workletNode = new AudioWorkletNode(audioContext, 'pcm-recorder-processor', {
      processorOptions: { targetSampleRate: 16000 },
    });
    workletNodeRef.current = workletNode;

    workletNode.port.onmessage = (event) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(event.data);
      }
    };

    source.connect(workletNode);
    // The worklet has no meaningful audio output, but some browsers only pump
    // process() while the node is connected somewhere in the graph.
    const silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    workletNode.connect(silentGain);
    silentGain.connect(audioContext.destination);

    setIsCallActive(true);
  }, [sessionId, onUserPartial, onUserFinal, onAssistantText, onError]);

  const endCall = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
    }
    wsRef.current?.close();
    wsRef.current = null;

    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;

    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;

    audioContextRef.current?.close();
    audioContextRef.current = null;

    playerRef.current?.close();
    playerRef.current = null;

    setIsCallActive(false);
  }, []);

  return { isCallActive, startCall, endCall };
}
