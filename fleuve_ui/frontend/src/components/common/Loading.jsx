export default function Loading({ message = 'loading...' }) {
  return (
    <div className="loading">
      <div className="spinner" />
      <p className="mt-2 font-mono text-xs" style={{ color: 'var(--muted)' }}>{message}</p>
    </div>
  );
}
