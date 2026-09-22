// Matches `[label](url)`, a bare `http(s)://...` URL, or `**bold**` text, so
// renderFormatted can turn all three into real markup in one pass.
const FORMAT_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s)]+)|\*\*([^*]+)\*\*/g;

function renderFormatted(text) {
  const parts = [];
  let lastIndex = 0;
  let match;
  let key = 0;

  while ((match = FORMAT_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const [, linkLabel, linkUrl, bareUrl, boldText] = match;
    if (boldText !== undefined) {
      parts.push(<strong key={key++}>{boldText}</strong>);
    } else {
      const label = linkLabel || bareUrl;
      const url = linkUrl || bareUrl;
      parts.push(
        <a key={key++} href={url} target="_blank" rel="noopener noreferrer">
          {label}
        </a>,
      );
    }
    lastIndex = FORMAT_RE.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

export function ChatMessage({ role, text, pending, demoActions, viaVoice }) {
  return (
    <div className={`chat-message chat-message--${role}`}>
      <div className="chat-message__bubble">
        {viaVoice && <span className="chat-message__voice-tag">via call</span>}
        {renderFormatted(text)}
        {pending && <span className="chat-message__pending">…</span>}
        {demoActions?.length > 0 && (
          <div className="chat-message__demo-badges">
            {demoActions.map((action, i) => (
              <span key={i} className="chat-message__demo-badge" title={action.note}>
                Demo action — {action.tool === 'send_email' ? 'no real email sent' : 'no real invite sent'}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
