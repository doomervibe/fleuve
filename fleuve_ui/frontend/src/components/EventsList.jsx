import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import JsonHighlight from './common/JsonHighlight';
import CopyButton from './common/CopyButton';
import RefreshButton from './common/RefreshButton';
import { SkeletonRow } from './common/Skeleton';
import PaginationBar from './common/PaginationBar';
import ColoredBadge from './common/ColoredBadge';
import { useResizableTableColumns } from '../hooks/useResizableTableColumns';
import { formatDate } from '../utils/format';
import { colorFor } from '../utils/colors';

const PAGE_SIZE = 50;

export default function EventsList({ onViewWorkflow }) {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedEventId, setExpandedEventId] = useState(null);
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [availableEventTypes, setAvailableEventTypes] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);

  useEffect(() => {
    setOffset(0);
    setExpandedEventId(null);
  }, [eventTypeFilter, tagFilter]);

  useEffect(() => {
    loadEvents();
    const interval = setInterval(loadEvents, 5000);
    return () => clearInterval(interval);
  }, [eventTypeFilter, tagFilter, offset]);

  async function loadEvents() {
    try {
      const params = { limit: PAGE_SIZE, offset };
      if (eventTypeFilter) params.event_type = eventTypeFilter;
      if (tagFilter) params.tag = tagFilter;
      const data = await api.events.list(params);
      const events = data.events || [];
      setEvents(events);
      setTotal(data.total ?? events.length);
      if (data.event_types) setAvailableEventTypes(data.event_types);
      const allTags = [
        ...new Set(
          (data.events || []).flatMap(
            (e) => e.metadata?.tags || e.metadata?.workflow_tags || e.tags || []
          )
        ),
      ];
      setAvailableTags(data.tags?.length ? data.tags : allTags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events');
    } finally {
      setLoading(false);
    }
  }

  const toggleExpanded = (eventId) => {
    setExpandedEventId((id) => (id === eventId ? null : eventId));
  };

  const getEventId = (e) => e.global_id ?? e.id ?? e.workflow_id + '-' + e.workflow_version;

  const eventColumns = [
    { key: 'id', label: 'id', defaultWidth: 140 },
    { key: 'workflow', label: 'workflow', defaultWidth: 140 },
    { key: 'type', label: 'type', defaultWidth: 100 },
    { key: 'eventNum', label: 'event #', defaultWidth: 60 },
    { key: 'eventType', label: 'event type', defaultWidth: 100 },
    { key: 'tags', label: 'tags', defaultWidth: 120 },
    { key: 'created', label: 'created', defaultWidth: 140 },
  ];
  const { TableHead } = useResizableTableColumns('fleuve-events-table', eventColumns);

  if (loading) {
    return (
      <>
        <div className="list-header">
          <h2>recent events</h2>
        </div>
        <div className="table-container">
          <div className="skeleton-table">
            {Array.from({ length: 10 }, (_, i) => (
              <SkeletonRow key={i} cols={7} />
            ))}
          </div>
        </div>
      </>
    );
  }

  if (error) {
    return (
      <div className="error">
        <p>Error: {error}</p>
        <button onClick={loadEvents}>Retry</button>
      </div>
    );
  }

  return (
    <>
      <div className="list-header">
        <h2>recent events</h2>
        <div className="list-controls">
          <select
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">all event types</option>
            {availableEventTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">all tags</option>
            {availableTags.map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
          <RefreshButton onRefresh={loadEvents} />
        </div>
      </div>

      {events.length === 0 ? (
        <div className="empty-state">
          <p>no events found</p>
        </div>
      ) : (
        <>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <TableHead columnKey="id" isLast={false}>id</TableHead>
                <TableHead columnKey="workflow" isLast={false}>workflow</TableHead>
                <TableHead columnKey="type" isLast={false}>type</TableHead>
                <TableHead columnKey="eventNum" isLast={false}>event #</TableHead>
                <TableHead columnKey="eventType" isLast={false}>event type</TableHead>
                <TableHead columnKey="tags" isLast={false}>tags</TableHead>
                <TableHead columnKey="created" isLast={true}>created</TableHead>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => {
                const eventId = getEventId(event);
                const tags = event.metadata?.tags || event.metadata?.workflow_tags || event.tags || [];
                return (
                  <React.Fragment key={eventId}>
                    <tr
                      key={eventId}
                      onClick={() => toggleExpanded(eventId)}
                      className={expandedEventId === eventId ? 'expanded' : ''}
                    >
                      <td className="cell-truncate" title={eventId}>{eventId}</td>
                      <td className="cell-truncate" title={event.workflow_id}>
                        {onViewWorkflow ? (
                          <button
                            className="event-workflow-link"
                            onClick={(e) => {
                              e.stopPropagation();
                              onViewWorkflow(event.workflow_id);
                            }}
                          >
                            {event.workflow_id}
                          </button>
                        ) : (
                          event.workflow_id
                        )}
                      </td>
                      <td className="cell-truncate" title={event.workflow_type}>
                        <ColoredBadge value={event.workflow_type} />
                      </td>
                      <td>{event.workflow_version ?? event.event_number ?? '—'}</td>
                      <td className="cell-truncate" title={event.body?.type ?? event.event_type ?? 'N/A'}>
                        <ColoredBadge value={event.body?.type ?? event.event_type ?? 'N/A'} />
                      </td>
                      <td className="tags-cell" title={tags.length > 0 ? tags.join(', ') : undefined}>
                        {tags.length > 0 ? (
                          tags.map((tag) => (
                            <button
                              key={tag}
                              className="tag-badge"
                              style={colorFor(tag) ? { '--badge-color': colorFor(tag) } : undefined}
                              onClick={(e) => {
                                e.stopPropagation();
                                setTagFilter(tag);
                              }}
                            >
                              {tag}
                            </button>
                          ))
                        ) : (
                          <span className="no-tags">—</span>
                        )}
                      </td>
                      <td className="cell-truncate" title={formatDate(event.at ?? event.created_at)}>{formatDate(event.at ?? event.created_at)}</td>
                    </tr>
                    {expandedEventId === eventId && (
                      <tr key={eventId + '-detail'} className="event-detail-row">
                        <td colSpan={7}>
                          <div className="event-detail-cell">
                            <div className="event-detail-actions">
                              <CopyButton text={eventId} title="copy event id" />
                            </div>
                            <JsonHighlight data={event.body || event} className="event-body-json" copyable />
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        <PaginationBar
          offset={offset}
          limit={PAGE_SIZE}
          total={total}
          onPageChange={setOffset}
        />
        </>
      )}
    </>
  );
}
