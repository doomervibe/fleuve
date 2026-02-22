/**
 * Network-panel style timeline view for activities.
 * Each activity is a horizontal bar on a time axis (waterfall).
 * Column widths are resizable via drag handles.
 */
import { useState, useCallback, useEffect } from 'react';
import { formatDate, formatDuration } from '../utils/format';

const STORAGE_KEY = 'fleuve-activities-timeline-columns';
const MIN_COL = 24;

function getStoredWidths() {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

export default function ActivitiesTimeline({ activities, onActivityClick, formatDate: formatDateProp }) {
  const fmt = formatDateProp || formatDate;
  const stored = getStoredWidths();
  const [colWidths, setColWidths] = useState({
    workflow: stored?.workflow ?? 140,
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

  if (!activities?.length) return null;

  const now = Date.now();
  const MIN_BAR_MS = 2000; // minimum bar width for very short activities

  const withTiming = activities.map((a) => {
    const start = new Date(a.started_at || a.last_attempt_at || now).getTime();
    const end = a.finished_at
      ? new Date(a.finished_at).getTime()
      : Math.max(start + MIN_BAR_MS, now);
    const duration = end - start;
    return { ...a, start, end, duration };
  });

  const minTime = Math.min(...withTiming.map((a) => a.start));
  const maxTime = Math.max(...withTiming.map((a) => a.end), now);
  // Ensure non-zero range: when all items are at same time, add 1h padding
  const rangeMs = Math.max(maxTime - minTime, 3600000);

  const toWidth = (start, end) => Math.max(((end - start) / rangeMs) * 100, 0.5);
  const toLeft = (t) => ((t - minTime) / rangeMs) * 100;

  const nowLeft = toLeft(now);
  const showNowLine = now >= minTime && now <= maxTime;

  const statusClass = (s) => {
    const k = (s || '').toLowerCase().replace(' ', '_');
    return `activity-bar--${k}`;
  };

  return (
    <div className="activities-timeline">
      <div className="timeline-ruler">
        <span className="timeline-ruler-label">{fmt(minTime)}</span>
        <span className="timeline-ruler-label timeline-ruler-label--end">
          {fmt(maxTime)}
        </span>
      </div>

      <div
        className="timeline-viewport timeline-viewport--grid"
        style={{
          '--timeline-labels-width': `${colWidths.workflow + colWidths.ev + colWidths.status + 24}px`,
          ...(showNowLine && { '--timeline-now-left': `${nowLeft}%` }),
        }}
      >
        <div
          className="timeline-grid-row timeline-grid-row--header"
          style={{
            gridTemplateColumns: `${colWidths.workflow}px ${colWidths.ev}px ${colWidths.status}px 1fr`,
          }}
        >
          <div className="timeline-col-header">
            <span>workflow</span>
            <div
              className="timeline-col-resizer"
              onMouseDown={(e) => {
                e.stopPropagation();
                handleResizeStart('workflow', e);
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
        {withTiming.map((a, idx) => {
          const left = toLeft(a.start);
          const width = toWidth(a.start, a.end);
          const inProgress = !a.finished_at;
          return (
            <div
              key={(a.workflow_id ?? '') + '-' + (a.event_number ?? idx)}
              className={`timeline-grid-row ${onActivityClick ? 'clickable' : ''}`}
              style={{
                gridTemplateColumns: `${colWidths.workflow}px ${colWidths.ev}px ${colWidths.status}px 1fr`,
              }}
              onClick={() => a.workflow_id && onActivityClick?.(a.workflow_id)}
            >
              <span className="timeline-col-name" title={a.workflow_id ?? ''}>
                {a.workflow_id ?? '—'}
              </span>
              <span className="timeline-col-event">{a.event_number}</span>
              <span className={`timeline-col-status status-badge ${statusClass(a.status)}`}>
                {a.status}
              </span>
              <div className="timeline-bar-cell">
                {showNowLine && <div className="timeline-now-line" />}
                <div
                  className={`activity-bar ${statusClass(a.status)} ${inProgress ? 'activity-bar--in-progress' : ''}`}
                  style={{
                    left: `${left}%`,
                    width: `${width}%`,
                  }}
                  title={`${fmt(a.start)} – ${a.finished_at ? fmt(a.end) : 'in progress'} (${formatDuration(a.duration)})`}
                >
                  {width > 8 && (
                    <span className="activity-bar-duration">
                      {formatDuration(a.duration)}
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
