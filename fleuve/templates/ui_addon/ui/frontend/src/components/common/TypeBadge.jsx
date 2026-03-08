function hashString(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function getTypeBadgeStyle(value, kind) {
  const normalized = String(value || 'unknown');
  const baseHash = hashString(normalized.toLowerCase());
  const hueOffset = kind === 'event' ? 37 : 0;
  const hue = (baseHash + hueOffset) % 360;
  const saturation = kind === 'event' ? 85 : 75;
  const textLightness = kind === 'event' ? 72 : 68;
  const borderLightness = kind === 'event' ? 58 : 54;

  return {
    color: `hsl(${hue} ${saturation}% ${textLightness}%)`,
    borderColor: `hsla(${hue} ${saturation}% ${borderLightness}% / 0.8)`,
    backgroundColor: `hsla(${hue} ${saturation}% 40% / 0.12)`,
  };
}

export default function TypeBadge({ value, kind = 'workflow', className = '' }) {
  return (
    <span
      className={`inline-flex items-center px-1 py-0 text-xs font-mono border ${className}`}
      style={getTypeBadgeStyle(value, kind)}
    >
      {value || 'unknown'}
    </span>
  );
}
