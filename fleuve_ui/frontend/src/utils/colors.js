/**
 * Deterministic colors for tags and event types.
 * Same string always maps to the same color for visual consistency.
 */

const PALETTE = [
  '#4ec9b0', // green
  '#5eb3f6', // blue
  '#dcdcaa', // yellow
  '#9cdcfe', // cyan
  '#c586c0', // purple
  '#d7ba7d', // gold
  '#ce9178', // orange
  '#6a9955', // darker green
  '#569cd6', // steel blue
  '#f14c4c', // red
  '#b5cea8', // sage
  '#d4a373', // tan
];

function hashString(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export function colorFor(str) {
  if (!str || typeof str !== 'string') return null;
  const h = hashString(str);
  return PALETTE[h % PALETTE.length];
}
