import { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';
import { CallScreen } from './components/CallScreen';
import { ChatMessage } from './components/ChatMessage';
import { MicButton } from './components/MicButton';
import { useVoiceCall } from './hooks/useVoiceCall';

const BACKEND_HTTP_URL = import.meta.env.VITE_BACKEND_HTTP_URL || 'http://localhost:8000';

function App() {
  const sessionIdRef = useRef(crypto.randomUUID());
  const startedRef = useRef(false);
  const chatLogRef = useRef(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  // startCall() is async (websocket connect -> mic permission -> audio
  // worklet setup); isConnecting covers that window so the UI can show
  // "Connecting..." before the call is actually live.
  const [isConnecting, setIsConnecting] = useState(false);
  const [callStatus, setCallStatus] = useState('listening');
  const [voiceError, setVoiceError] = useState(null);

  useEffect(() => {
    const el = chatLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const appendMessage = useCallback((role, text, demoActions) => {
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role, text, demoActions }]);
  }, []);

  // Edweisser greets first, before the user says anything.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    fetch(`${BACKEND_HTTP_URL}/chat/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionIdRef.current }),
    })
      .then((res) => res.json())
      .then((data) => appendMessage('assistant', data.reply))
      .catch(() => appendMessage('assistant', "Hi, I'm Edweisser. (Couldn't reach the backend just now.)"));
  }, [appendMessage]);

  const handleStatusChange = useCallback((status) => setCallStatus(status), []);
  const handleVoiceError = useCallback((message) => setVoiceError(message), []);

  const { isCallActive, startCall, endCall } = useVoiceCall({
    sessionId: sessionIdRef.current,
    onStatusChange: handleStatusChange,
    onError: handleVoiceError,
  });

  const handleSend = useCallback(
    async (event) => {
      event.preventDefault();
      const text = draft.trim();
      if (!text || sending) return;
      setDraft('');
      appendMessage('user', text);
      setSending(true);
      try {
        const res = await fetch(`${BACKEND_HTTP_URL}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionIdRef.current, text }),
        });
        if (!res.ok) throw new Error(`backend returned ${res.status}`);
        const data = await res.json();
        appendMessage('assistant', data.reply, data.demo_actions);
      } catch {
        appendMessage('assistant', 'Sorry, something went wrong reaching the advisor.');
      } finally {
        setSending(false);
      }
    },
    [draft, sending, appendMessage],
  );

  const handleMicClick = useCallback(() => {
    if (isCallActive) {
      endCall();
    } else {
      setVoiceError(null);
      setCallStatus('listening');
      setIsConnecting(true);
      startCall()
        .catch((err) => {
          console.error('Failed to start voice call', err);
          setVoiceError(`Could not start the voice call — ${err.name || 'Error'}: ${err.message || err}`);
        })
        .finally(() => setIsConnecting(false));
    }
  }, [isCallActive, startCall, endCall]);

  const onCall = isCallActive || isConnecting;

  return (
    <div className="app">
      <header className="app__header">
        <h1>Edweisser</h1>
        <p>Type or talk — same conversation either way.</p>
      </header>

      {voiceError && <div className="error-banner">{voiceError}</div>}

      {onCall ? (
        <CallScreen status={isConnecting ? 'connecting' : callStatus} onEndCall={endCall} />
      ) : (
        <>
          <main className="chat-log" ref={chatLogRef}>
            {messages.map((m) => (
              <ChatMessage key={m.id} role={m.role} text={m.text} demoActions={m.demoActions} />
            ))}
          </main>

          <form className="composer" onSubmit={handleSend}>
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type a message…"
              disabled={sending}
            />
            <button type="submit" disabled={sending}>
              Send
            </button>
            <MicButton isActive={false} onClick={handleMicClick} />
          </form>
        </>
      )}
    </div>
  );
}

export default App;
