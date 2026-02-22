import { useState } from 'react';

export default function CopyButton({ text, label, title = 'copy', compact }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy(e) {
    e.stopPropagation();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }

  const displayLabel = copied ? 'copied' : (label ?? 'copy');
  return (
    <button
      type="button"
      className={`copy-btn ${compact ? 'copy-btn--compact' : ''}`}
      onClick={handleCopy}
      title={title}
      disabled={!text}
    >
      {compact ? (copied ? '✓' : '⎘') : displayLabel}
    </button>
  );
}
