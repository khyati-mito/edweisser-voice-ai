import { useCallback, useRef, useState } from 'react';
import { PcmAudioPlayer } from '../audio/audio-player';

const BACKEND_WS_URL = import.meta.env.VITE_BACKEND_WS_URL || 'ws://localhost:8000';

// Owns the mic capture, the /voice websocket, and the playback queue for one
// continuous, voice-only call -- like a phone call, nothing is rendered
// live from this while the call is up. Talks to the backend in the app's
// own wire protocol: binary frames both ways are PCM16 audio; JSON frames
// carry user_partial/user_final/assistant_text_delta/assistant_done/
// interrupt/error. Beyond deriving a coarse call status ('listening' |
// 'thinking' | 'speaking'), each finalized turn (user_final, assistant_done)
// is also handed to onTranscript so the caller can fold the call into the
// same chat log used for typed messages once it's over -- the shared
// backend conversation history already includes it either way, so this is
// just making that visible.
export function useVoiceCall({ sessionId, onStatusChange, onError, onTranscript }) {
  const [isCallActive, setIsCallActive] = useState(false);
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const workletNodeRef = useRef(null);
  const micStreamRef = useRef(null);
  const playerRef = useRef(null);
  // Set right before we close the websocket ourselves, so the onclose
  // handler below can tell "the user ended the call" apart from "the
  // connection died out from under us" (Sarvam STT inactivity timeout, a
  // network blip, a backend restart, ...). Without this distinction, an
  // unexpected close left isCallActive stuck true forever.
  const intentionalCloseRef = useRef(false);

  const teardown = useCallback(() => {
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

  const startCall = useCallback(async () => {
    intentionalCloseRef.current = false;
    const wsUrl = `${BACKEND_WS_URL}/voice?session_id=${encodeURIComponent(sessionId)}`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    const player = new PcmAudioPlayer(16000);
    playerRef.current = player;

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        const msg = JSON.parse(event.data);
        if (msg.type === 'user_partial') onStatusChange?.('listening');
        else if (msg.type === 'user_final') {
          onStatusChange?.('thinking');
          if (msg.text?.trim()) onTranscript?.({ role: 'user', text: msg.text });
        } else if (msg.type === 'assistant_text_delta') onStatusChange?.('speaking');
        else if (msg.type === 'assistant_done') {
          onStatusChange?.('listening');
          if (msg.text?.trim()) {
            onTranscript?.({ role: 'assistant', text: msg.text, demoActions: msg.demo_actions });
          }
        } else if (msg.type === 'interrupt') {
          player.clear();
          onStatusChange?.('listening');
        } else if (msg.type === 'error') onError?.(msg.message);
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
    // Once connected, keep listening for a close we didn't ask for -- the
    // server can drop the connection at any point during a call (STT
    // inactivity timeout, network blip, backend restart), and without this
    // the UI would just look like a live call forever.
    ws.onclose = (event) => {
      if (intentionalCloseRef.current) return;
      onError?.(`voice call disconnected unexpectedly (code ${event.code}: ${event.reason || 'no reason given'})`);
      teardown();
    };

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

    onStatusChange?.('listening');
    setIsCallActive(true);
  }, [sessionId, onStatusChange, onError, teardown]);

  const endCall = useCallback(() => {
    intentionalCloseRef.current = true;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
    }
    wsRef.current?.close();
    teardown();
  }, [teardown]);

  return { isCallActive, startCall, endCall };
}
