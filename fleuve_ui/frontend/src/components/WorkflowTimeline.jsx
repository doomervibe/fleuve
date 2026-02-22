/**
 * Network-panel style timeline for a single workflow.
 * Shows events, activities, and delays on a unified time axis.
 * Column widths are resizable via drag handles.
 */
import { useState, useCallback, useEffect } from 'react';
import { formatDate, formatDuration } from '../utils/format';
import ColoredBadge from './common/ColoredBadge';

const STORAGE_KEY = 'fleuve-workflow-timeline-columns';
const MIN_COL = 24;

function getStoredWidths() {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

export default function WorkflowTimeline({ events = [], activities = [], delays = [], formatDate: formatDateProp }) {
  const fmt = formatDateProp || formatDate;
  const stored = getStoredWidths();
  const [colWidths, setColWidths] = useState({
    type: stored?.type ?? 48,
    label: stored?.label ?? 120,
    ev: stored?.ev ?? 40,
    status: stored?.status ?? 70,
  });
  const [resizing, setResizing] = useState(null);

  const persist = useCallback((w) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(w));
    } catch {}
  }, []);

  const handleResizeStart = (key, e) => {
    e.preventDefault();
    setResizing({ key, startX: e.clientX, startW: colWidths[key] });
  };

  const handleMove = useCallback(
    (e) => {
      if (!resizing) return;
      const d = e.clientX - resizing.startX;
      const w = Math.max(MIN_COL, resizing.startW + d);
      setColWidths((prev) => {
        const next = { ...prev, [resizing.key]: w };
        persist(next);
        return next;
      });
    },
    [resizing, persist]
  );

  const handleUp = useCallback(() => setResizing(null), []);

  useEffect(() => {
    if (!resizing) return;
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [resizing, handleMove, handleUp]);

  const now = Date.now();
  const MIN_BAR_MS = 500;

  const items = [];

  // Events: instant (point in time)
  (events || []).forEach((e) => {
    const t = new Date(e.created_at || e.at || now).getTime();
    const eventType = e.body?.type || e.event_type;
    items.push({
      type: 'event',
      id: e.id || `ev-${e.event_number}`,
      label: eventType || `event #${e.event_number}`,
      eventType,
      eventNumber: e.event_number,
      start: t,
      end: t,
      duration: 0,
      raw: e,
    });
  });

  // Activities: bars with duration
  (activities || []).forEach((a) => {
    const start = new Date(a.created_at || a.started_at || a.updated_at || now).getTime();
    const end = a.updated_at || a.finished_at
      ? new Date(a.updated_at || a.finished_at).getTime()
      : Math.max(start + MIN_BAR_MS, now);
    const duration = end - start;
    const inProgress = ['running', 'pending', 'in_progress'].includes((a.status || '').toLowerCase());
    items.push({
      type: 'activity',
      id: a.id || `act-${a.event_number}`,
      label: `activity #${a.event_number}`,
      eventNumber: a.event_number,
      status: a.status,
      start,
      end,
      duration,
      inProgress,
      raw: a,
    });
  });

  // Delays: from created to delay_until (waiting period)
  (delays || []).forEach((d) => {
    const end = new Date(d.delay_until || now).getTime();
    const start = d.created_at
      ? new Date(d.created_at).getTime()
      : end - 3600000; // fallback: 1h before delay_until
    const duration = Math.max(end - start, 0);
    items.push({
      type: 'delay',
      id: d.id || `delay-${d.event_number}`,
      label: `delay #${d.event_number}`,
      eventNumber: d.event_number,
      start,
      end,
      duration,
      delayUntil: d.delay_until,
      raw: d,
    });
  });

  if (items.length === 0) {
    return (
      <div className="empty-state">
        <p>no events, activities, or delays to display</p>
      </div>
    );
  }

  const minTime = Math.min(...items.map((i) => i.start));
  const maxTime = Math.max(...items.map((i) => i.end), now);
  // Ensure non-zero range: when all items at same time, add 1h padding
  const rangeMs = Math.max(maxTime - minTime, 3600000);

  const toWidth = (start, end) => Math.max(((end - start) / rangeMs) * 100, 0.3);
  const toLeft = (t) => ((t - minTime) / rangeMs) * 100;

  const nowLeft = toLeft(now);
  const showNowLine = now >= minTime && now <= maxTime;

  // Sort by start time descending (latest first), then by type order
  const typeOrder = { event: 0, activity: 1, delay: 2 };
  items.sort((a, b) => {
    if (a.start !== b.start) return b.start - a.start;
    return (typeOrder[a.type] ?? 3) - (typeOrder[b.type] ?? 3);
  });

  const barClass = (item) => {
    if (item.type === 'event') return 'workflow-timeline-bar--event';
    if (item.type === 'delay') return 'workflow-timeline-bar--delay';
    const k = (item.status || '').toLowerCase().replace(' ', '_');
    return `workflow-timeline-bar--activity activity-bar--${k}`;
  };

  return (
    <div className="workflow-timeline activities-timeline">
      <div className="timeline-ruler">
        <span className="timeline-ruler-label">{fmt(minTime)}</span>
        <span className="timeline-ruler-label timeline-ruler-label--end">
          {fmt(maxTime)}
        </span>
      </div>

      <div
        className="timeline-viewport timeline-viewport--grid"
        style={{
          '--timeline-labels-width': `${colWidths.type + colWidths.label + colWidths.ev + colWidths.status + 32}px`,
          ...(showNowLine && { '--timeline-now-left': `${nowLeft}%` }),
        }}
      >
        <div
          className="timeline-grid-row timeline-grid-row--header"
          style={{
            gridTemplateColumns: `${colWidths.type}px ${colWidths.label}px ${colWidths.ev}px ${colWidths.status}px 1fr`,
          }}
        >
          <div className="timeline-col-header">
            <span>type</span>
            <div
              className="timeline-col-resizer"
              onMouseDown={(e) => {
                e.stopPropagation();
                handleResizeStart('type', e);
              }}
            />
          </div>
          <div className="timeline-col-header">
            <span>label</span>
            <div
              className="timeline-col-resizer"
              onMouseDown={(e) => {
                e.stopPropagation();
                handleResizeStart('label', e);
              }}
            />
          </div>
          <div className="timeline-col-header">
            <span>ev#</span>
            <div
              className="timeline-col-resizer"
              onMouseDown={(e) => {
                e.stopPropagation();
                handleResizeStart('ev', e);
              }}
            />
          </div>
          <div className="timeline-col-header">
            <span>status</span>
          </div>
          <div className="timeline-bar-cell timeline-bar-cell--header">
            {showNowLine && <div className="timeline-now-line" />}
          </div>
        </div>
        {items.map((item) => {
          const left = toLeft(item.start);
          const width = toWidth(item.start, item.end);
          return (
            <div
              key={item.id}
              className="timeline-grid-row"
              style={{
                gridTemplateColumns: `${colWidths.type}px ${colWidths.label}px ${colWidths.ev}px ${colWidths.status}px 1fr`,
              }}
            >
              <span className={`timeline-col-type workflow-timeline-type--${item.type}`}>
                {item.type}
              </span>
              <span className="timeline-col-name" title={item.label}>
                {item.type === 'event' && item.eventType ? (
                  <ColoredBadge value={item.eventType} />
                ) : (
                  item.label
                )}
              </span>
              <span className="timeline-col-event">{item.eventNumber}</span>
              <span className="timeline-col-status">
                {item.type === 'activity' && item.status ? (
                  <span className={`status-badge activity-bar--${(item.status || '').toLowerCase().replace(' ', '_')}`}>
                    {item.status}
                  </span>
                ) : (
                  '—'
                )}
              </span>
              <div className="timeline-bar-cell">
                {showNowLine && <div className="timeline-now-line" />}
                <div
                  className={`activity-bar workflow-timeline-bar ${barClass(item)} ${item.inProgress ? 'activity-bar--in-progress' : ''}`}
                  style={{
                    left: `${left}%`,
                    width: `${width}%`,
                  }}
                  title={
                    item.type === 'event'
                      ? fmt(item.start)
                      : `${fmt(item.start)} – ${item.type === 'delay' ? fmt(item.delayUntil) : fmt(item.end)}${item.duration ? ` (${formatDuration(item.duration)})` : ''}`
                  }
                >
                  {width > 6 && item.duration > 0 && (
                    <span className="activity-bar-duration">
                      {formatDuration(item.duration)}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
