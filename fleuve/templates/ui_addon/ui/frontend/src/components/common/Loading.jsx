export default function Loading({ message = '$ connecting...' }) {
  return (
    <div className="loading">
      <div className="spinner" />
      <p>{message}</p>
    </div>
  );
}
