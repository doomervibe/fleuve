export default function Error({ error, onRetry }) {
  return (
    <div className="error">
      <p style={{ color: 'var(--red)' }}>error: {error?.message || 'an error occurred'}</p>
      {onRetry && (
        <button onClick={onRetry} className="back-btn">
          retry
        </button>
      )}
    </div>
  );
}
