export default function Error({ error, onRetry }) {
  return (
    <div className="error">
      <p>ERROR: {error?.message || 'an error occurred'}</p>
      {onRetry && (
        <button onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}
