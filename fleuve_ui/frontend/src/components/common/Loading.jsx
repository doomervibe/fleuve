export default function Loading({ message = 'loading...' }) {
  return (
    <div className="loading">
      <div className="spinner" />
      <p>{message}</p>
    </div>
  );
}
