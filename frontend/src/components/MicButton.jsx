export function MicButton({ isActive, onClick }) {
  return (
    <button
      type="button"
      className={`mic-button${isActive ? ' mic-button--active' : ''}`}
      onClick={onClick}
      aria-label={isActive ? 'End voice call' : 'Start voice call'}
    >
      {isActive ? '● End call' : '🎙 Talk'}
    </button>
  );
}
