import { colorFor } from '../../utils/colors';

/**
 * Badge with deterministic color based on value (tag, event type, workflow type).
 * Same value always gets the same color.
 */
export default function ColoredBadge({ value, as: Component = 'span', className = '', ...props }) {
  const color = colorFor(value);
  const Tag = Component;
  return (
    <Tag
      className={`colored-badge ${className}`.trim()}
      style={color ? { '--badge-color': color } : undefined}
      {...props}
    >
      {value}
    </Tag>
  );
}
