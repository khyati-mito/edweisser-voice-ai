import { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';
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
  const [partialText, setPartialText] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const el = chatLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, partialText]);

  // Typed messages and voice-transcribed messages both land in this one
  // array — that's what makes voice feel like another input mode for the
  // same chat, rather than a separate bolted-on feature.
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

  const handleUserPartial = useCallback((text) => setPartialText(text), []);
  const handleUserFinal = useCallback(
    (text) => {
      setPartialText('');
      appendMessage('user', text);
    },
    [appendMessage],
  );
  const handleAssistantText = useCallback(
    (text, demoActions) => appendMessage('assistant', text, demoActions),
    [appendMessage],
  );
  const handleVoiceError = useCallback(
    (message) => appendMessage('assistant', `Voice error: ${message}`),
    [appendMessage],
  );

  const { isCallActive, startCall, endCall } = useVoiceCall({
    sessionId: sessionIdRef.current,
    onUserPartial: handleUserPartial,
    onUserFinal: handleUserFinal,
    onAssistantText: handleAssistantText,
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
      startCall().catch((err) => {
        console.error('Failed to start voice call', err);
        appendMessage('assistant', `Could not start the voice call — ${err.name || 'Error'}: ${err.message || err}`);
      });
    }
  }, [isCallActive, startCall, endCall, appendMessage]);

  return (
    <div className="app">
      <header className="app__header">
        <h1>Edweisser</h1>
        <p>Type or talk — same conversation either way.</p>
      </header>

      <main className="chat-log" ref={chatLogRef}>
        {messages.map((m) => (
          <ChatMessage key={m.id} role={m.role} text={m.text} demoActions={m.demoActions} />
        ))}
        {partialText && <ChatMessage role="user" text={partialText} pending />}
      </main>

      <form className="composer" onSubmit={handleSend}>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message…"
          disabled={isCallActive}
        />
        <button type="submit" disabled={isCallActive || sending}>
          Send
        </button>
        <MicButton isActive={isCallActive} onClick={handleMicClick} />
      </form>
    </div>
  );
}

export default App;
