import { useState } from 'react';

export default function RefreshButton({ onRefresh, label = 'refresh' }) {
  const [spinning, setSpinning] = useState(false);

  async function handleClick() {
    if (spinning) return;
    setSpinning(true);
    try {
      await onRefresh();
    } finally {
      setSpinning(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`refresh-btn ${spinning ? 'refresh-btn--spinning' : ''}`}
      disabled={spinning}
      aria-label={label}
    >
      <span className="refresh-btn-icon" aria-hidden>↻</span>
      <span className="refresh-btn-text">{label}</span>
    </button>
  );
}
