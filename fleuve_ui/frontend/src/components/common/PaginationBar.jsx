/**
 * Compact pagination bar for tables/lists.
 */
export default function PaginationBar({ offset, limit, total, onPageChange }) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  if (total <= limit && offset === 0) return null;

  return (
    <div className="pagination-bar">
      <span className="pagination-info">
        {total === 0 ? 'no items' : `showing ${from}–${to} of ${total}`}
      </span>
      <div className="pagination-controls">
        <button
          type="button"
          className="pagination-btn"
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          disabled={!hasPrev}
        >
          ← prev
        </button>
        <button
          type="button"
          className="pagination-btn"
          onClick={() => onPageChange(offset + limit)}
          disabled={!hasNext}
        >
          next →
        </button>
      </div>
    </div>
  );
}
