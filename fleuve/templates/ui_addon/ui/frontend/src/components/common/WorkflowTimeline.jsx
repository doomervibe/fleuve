import { useMemo } from 'react';
import { format } from 'date-fns';

const EVENT_COLORS = [
  'var(--fleuve-text)',
  'var(--fleuve-accent)',
  'var(--fleuve-warning)',
  '#00ff88',
  '#88ff00',
  '#ff00ff',
];

function hashEventType(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export default function WorkflowTimeline({ events, activities, delays, onEventClick, eventRefs }) {
  const { items, minTime, maxTime } = useMemo(() => {
    const all = [];
    const times = [];

    events.forEach((e, idx) => {
      const t = new Date(e.at).getTime();
      times.push(t);
      all.push({
        type: 'event',
        id: `e-${e.global_id}`,
        time: t,
        label: e.event_type,
        eventType: e.event_type,
        data: e,
        index: idx,
      });
    });

    activities.forEach((a) => {
      const start = new Date(a.started_at).getTime();
      const end = a.finished_at
        ? new Date(a.finished_at).getTime()
        : Date.now();
      times.push(start, end);
      all.push({
        type: 'activity',
        id: `a-${a.workflow_id}-${a.event_number}`,
        start,
        end,
        label: `#${a.event_number} ${a.status}`,
        status: a.status,
        data: a,
      });
    });

    delays.forEach((d) => {
      const created = new Date(d.created_at || d.delay_until).getTime();
      const until = new Date(d.delay_until).getTime();
      times.push(created, until);
      all.push({
        type: 'delay',
        id: `d-${d.workflow_id}-${d.event_version}`,
        start: created,
        end: until,
        label: `until ${format(until, 'HH:mm')}`,
        data: d,
      });
    });

    const minT = times.length ? Math.min(...times) : Date.now();
    const maxT = times.length ? Math.max(...times) : Date.now();
    const range = maxT - minT || 1;

    return {
      items: all.map((item) => {
        if (item.type === 'event') {
          return {
            ...item,
            x: ((item.time - minT) / range) * 100,
          };
        }
        return {
          ...item,
          xStart: ((item.start - minT) / range) * 100,
          xEnd: ((item.end - minT) / range) * 100,
        };
      }),
      minTime: minT,
      maxTime: maxT,
    };
  }, [events, activities, delays]);

  if (items.length === 0) return null;

  const width = 600;
  const height = 80;

  return (
    <div className="mb-2">
      <div className="text-xs font-mono text-theme opacity-70 mb-1">timeline</div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full max-w-full border border-theme"
        style={{ minHeight: 60 }}
      >
        {/* Time axis line */}
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="var(--fleuve-border)"
          strokeWidth={1}
        />

        {items.map((item) => {
          if (item.type === 'event') {
            const x = (item.x / 100) * width;
            const color =
              EVENT_COLORS[hashEventType(item.eventType) % EVENT_COLORS.length];
            return (
              <g key={item.id}>
                <circle
                  cx={x}
                  cy={height / 2}
                  r={5}
                  fill={color}
                  stroke="var(--fleuve-border)"
                  strokeWidth={1}
                  className="cursor-pointer hover:r-7"
                  style={{ cursor: 'pointer' }}
                  onClick={() => onEventClick?.(item.data, item.index)}
                />
                <title>{item.label} @ {format(item.time, 'HH:mm:ss')}</title>
              </g>
            );
          }
          if (item.type === 'activity') {
            const x1 = (item.xStart / 100) * width;
            const x2 = (item.xEnd / 100) * width;
            const w = Math.max(x2 - x1, 4);
            const color =
              item.status === 'completed'
                ? 'var(--fleuve-text)'
                : item.status === 'failed'
                ? 'var(--fleuve-error)'
                : 'var(--fleuve-warning)';
            return (
              <rect
                key={item.id}
                x={x1}
                y={height / 2 - 6}
                width={w}
                height={12}
                fill={color}
                fillOpacity={0.4}
                stroke={color}
                strokeWidth={1}
                className="cursor-pointer"
                style={{ cursor: 'pointer' }}
              >
                <title>{item.label}</title>
              </rect>
            );
          }
          if (item.type === 'delay') {
            const x1 = (item.xStart / 100) * width;
            const x2 = (item.xEnd / 100) * width;
            return (
              <line
                key={item.id}
                x1={x1}
                y1={height / 2}
                x2={x2}
                y2={height / 2}
                stroke="var(--fleuve-warning)"
                strokeWidth={2}
                strokeDasharray="4 2"
                opacity={0.7}
              >
                <title>{item.label}</title>
              </line>
            );
          }
          return null;
        })}
      </svg>
      <div className="flex justify-between text-[10px] font-mono text-theme opacity-50 mt-0">
        <span>{format(minTime, 'HH:mm:ss')}</span>
        <span>{format(maxTime, 'HH:mm:ss')}</span>
      </div>
    </div>
  );
}
