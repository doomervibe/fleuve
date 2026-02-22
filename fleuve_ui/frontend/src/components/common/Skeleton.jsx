/**
 * Skeleton loaders for loading states.
 */

export function Skeleton({ className = '', style = {} }) {
  return <div className={`skeleton ${className}`} style={style} />;
}

export function SkeletonText({ width = '60%', className = '' }) {
  return <Skeleton className={`skeleton-text ${className}`} style={{ width }} />;
}

export function SkeletonRow({ cols = 5, className = '' }) {
  return (
    <div className={`skeleton-row ${className}`}>
      {Array.from({ length: cols }, (_, i) => (
        <Skeleton key={i} className="skeleton-cell" style={{ flex: i === 0 ? 1.5 : 1 }} />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = '' }) {
  return (
    <div className={`skeleton-card ${className}`}>
      <SkeletonText width="70%" />
      <SkeletonText width="40%" />
      <SkeletonText width="55%" />
    </div>
  );
}
