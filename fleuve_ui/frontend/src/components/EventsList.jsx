import React, { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function EventsList({ onViewWorkflow }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedEventId, setExpandedEventId] = useState(null);
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [availableEventTypes, setAvailableEventTypes] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);

  useEffect(() => {
    loadEvents();
    const interval = setInterval(loadEvents, 5000);
    return () => clearInterval(interval);
  }, [eventTypeFilter, tagFilter]);

  async function loadEvents() {
    try {
      const params = { limit: 100 };
      if (eventTypeFilter) params.event_type = eventTypeFilter;
      const data = await api.events.list(params);
      let events = data.events || [];
      if (tagFilter) {
        events = events.filter((e) => {
          const tags = e.metadata?.tags || e.metadata?.workflow_tags || e.tags || [];
          return tags.includes(tagFilter);
        });
      }
      setEvents(events);
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

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString();
  };

  const toggleExpanded = (eventId) => {
    setExpandedEventId((id) => (id === eventId ? null : eventId));
  };

  const getEventId = (e) => e.global_id ?? e.id ?? e.workflow_id + '-' + e.workflow_version;

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>loading events...</p>
      </div>
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
          <button onClick={loadEvents} className="refresh-btn">
            refresh
          </button>
        </div>
      </div>

      {events.length === 0 ? (
        <div className="empty-state">
          <p>no events found</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>id</th>
                <th>workflow</th>
                <th>type</th>
                <th>event #</th>
                <th>event type</th>
                <th>tags</th>
                <th>created</th>
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
                      <td>{eventId}</td>
                      <td>
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
                      <td>{event.workflow_type}</td>
                      <td>{event.workflow_version ?? event.event_number ?? '—'}</td>
                      <td>{event.body?.type ?? event.event_type ?? 'N/A'}</td>
                      <td className="tags-cell">
                        {tags.length > 0 ? (
                          tags.map((tag) => (
                            <button
                              key={tag}
                              className="tag-badge"
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
                      <td>{formatDate(event.at ?? event.created_at)}</td>
                    </tr>
                    {expandedEventId === eventId && (
                      <tr key={eventId + '-detail'} className="event-detail-row">
                        <td colSpan={7}>
                          <div className="event-detail-cell">
                            <pre className="event-body-json">
                              {JSON.stringify(event.body || event, null, 2)}
                            </pre>
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
      )}
    </>
  );
}
