import { useMemo } from 'react';
import { format } from 'date-fns';

function getStatusClass(status) {
  const normalized = (status || '').toLowerCase().replace(/\s+/g, '_');
  return `workflow-timeline-status--${normalized || 'none'}`;
}

export default function WorkflowTimeline({
  events,
  activities,
  delays,
  onEventClick,
  selectedEventIndex,
}) {
  const { items, minTime, maxTime } = useMemo(() => {
    const now = Date.now();
    const all = [];

    (events || []).forEach((event, index) => {
      const at = new Date(event.at).getTime();
      all.push({
        type: 'event',
        id: `event-${event.global_id}`,
        label: event.event_type,
        eventNumber: event.workflow_version,
        status: 'recorded',
        start: at,
        end: at,
        index,
        data: event,
      });
    });

    (activities || []).forEach((activity) => {
      const start = new Date(activity.started_at || activity.created_at || now).getTime();
      const end = activity.finished_at ? new Date(activity.finished_at).getTime() : now;
      all.push({
        type: 'activity',
        id: `activity-${activity.workflow_id}-${activity.event_number}`,
        label: `activity #${activity.event_number}`,
        eventNumber: activity.event_number,
        status: activity.status,
        start,
        end,
      });
    });

    (delays || []).forEach((delay) => {
      const start = new Date(delay.created_at || delay.delay_until).getTime();
      const end = new Date(delay.delay_until).getTime();
      all.push({
        type: 'delay',
        id: `delay-${delay.workflow_id}-${delay.event_version}`,
        label: `until ${format(end, 'HH:mm:ss')}`,
        eventNumber: delay.event_version,
        status: end > now ? 'pending' : 'completed',
        start,
        end,
      });
    });

    const min = all.length ? Math.min(...all.map((item) => item.start)) : now;
    const max = all.length ? Math.max(...all.map((item) => item.end), now) : now;
    const range = Math.max(max - min, 1000);

    const timelineItems = all
      .map((item) => {
        const left = ((item.start - min) / range) * 100;
        const width = Math.max(((item.end - item.start) / range) * 100, item.type === 'event' ? 0.6 : 1.2);
        return { ...item, left, width };
      })
      .sort((a, b) => {
        if (a.start !== b.start) return b.start - a.start;
        if (a.type !== b.type) return a.type.localeCompare(b.type);
        return 0;
      });

    return { items: timelineItems, minTime: min, maxTime: max };
  }, [events, activities, delays]);

  if (!items.length) return null;

  return (
    <div className="workflow-timeline mb-2 border border-theme">
      <div className="workflow-timeline-header">
        <span className="workflow-timeline-title">timeline</span>
        <span className="workflow-timeline-range">
          {format(minTime, 'HH:mm:ss')} → {format(maxTime, 'HH:mm:ss')}
        </span>
      </div>

      <div className="workflow-timeline-grid">
        <div className="workflow-timeline-row workflow-timeline-row--header">
          <span>type</span>
          <span>label</span>
          <span>ev#</span>
          <span>status</span>
          <span>time</span>
        </div>

        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => item.type === 'event' && onEventClick?.(item.data, item.index)}
            className={`workflow-timeline-row ${
              item.type === 'event' ? 'workflow-timeline-row--clickable' : ''
            } ${item.type === 'event' && selectedEventIndex === item.index ? 'workflow-timeline-row--selected' : ''}`}
          >
            <span className={`workflow-timeline-type workflow-timeline-type--${item.type}`}>
              {item.type}
            </span>
            <span className="workflow-timeline-label" title={item.label}>
              {item.label}
            </span>
            <span>{item.eventNumber ?? '-'}</span>
            <span className={getStatusClass(item.status)}>{item.status || '-'}</span>
            <span className="workflow-timeline-bar-cell">
              <span
                className={`workflow-timeline-bar workflow-timeline-bar--${item.type}`}
                style={{ left: `${item.left}%`, width: `${item.width}%` }}
                title={`${format(item.start, 'HH:mm:ss')} - ${format(item.end, 'HH:mm:ss')}`}
              />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
