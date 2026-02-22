/**
 * Safe formatting utilities that handle null/undefined/invalid values.
 */

export function formatDate(value) {
  if (value == null || value === '') return '—';
  const d = typeof value === 'number' ? new Date(value) : new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

/**
 * Human-readable duration from milliseconds (e.g. "2d 5h 30m", "1h 15m", "45s", "500ms").
 */
export function formatDuration(ms) {
  if (ms == null || ms < 0 || !Number.isFinite(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const sec = Math.floor(ms / 1000);
  const min = Math.floor(sec / 60);
  const hr = Math.floor(min / 60);
  const day = Math.floor(hr / 24);
  const parts = [];
  if (day > 0) parts.push(`${day}d`);
  if (hr % 24 > 0) parts.push(`${hr % 24}h`);
  if (min % 60 > 0 && day === 0) parts.push(`${min % 60}m`);
  if (sec % 60 > 0 && hr === 0 && day === 0) parts.push(`${sec % 60}s`);
  return parts.length ? parts.join(' ') : '0s';
}
