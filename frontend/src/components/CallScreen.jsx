const STATUS_LABELS = {
  connecting: 'Connecting…',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
};

export function CallScreen({ status, onEndCall }) {
  return (
    <div className="call-screen">
      <div className={`call-screen__avatar call-screen__avatar--${status}`}>🎙</div>
      <p className="call-screen__status">{STATUS_LABELS[status] || 'On call…'}</p>
      <button type="button" className="call-screen__end-button" onClick={onEndCall}>
        End Call
      </button>
    </div>
  );
}
