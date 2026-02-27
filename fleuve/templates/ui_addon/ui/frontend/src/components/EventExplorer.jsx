import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import Table from './common/Table';
import JsonTree from './common/JsonTree';
import { format } from 'date-fns';

export default function EventExplorer() {
  const [events, setEvents] = useState([]);
  const [workflowTypes, setWorkflowTypes] = useState([]);
  const [eventTypes, setEventTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => ({
    workflow_type: searchParams.get('workflow_type') || '',
    workflow_id: searchParams.get('workflow_id') || '',
    event_type: searchParams.get('event_type') || '',
    created_after: searchParams.get('created_after') || '',
    created_before: searchParams.get('created_before') || '',
  }));
  const [pagination, setPagination] = useState({
    limit: 50,
    offset: 0,
  });
  const [selectedEvent, setSelectedEvent] = useState(null);

  const fetchWorkflowTypes = async () => {
    try {
      const types = await api.getWorkflowTypes();
      setWorkflowTypes(types.map((t) => t.workflow_type));
    } catch (err) {
      console.error('Failed to fetch workflow types:', err);
    }
  };

  const fetchEvents = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getEvents({
        ...filters,
        ...pagination,
      });
      setEvents(data);
      
      // Extract unique event types
      const uniqueTypes = [...new Set(data.map((e) => e.event_type))];
      setEventTypes(uniqueTypes);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkflowTypes();
  }, []);

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [filters, pagination]);

  useEffect(() => {
    const close = () => setSelectedEvent(null);
    window.addEventListener('fleuve:closeModal', close);
    return () => window.removeEventListener('fleuve:closeModal', close);
  }, []);

  useEffect(() => {
    setFilters({
      workflow_type: searchParams.get('workflow_type') || '',
      workflow_id: searchParams.get('workflow_id') || '',
      event_type: searchParams.get('event_type') || '',
      created_after: searchParams.get('created_after') || '',
      created_before: searchParams.get('created_before') || '',
    });
    setPagination((p) => ({ ...p, offset: parseInt(searchParams.get('offset') || '0', 10) }));
  }, [searchParams]);

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
    setPagination((p) => ({ ...p, offset: 0 }));
    const params = new URLSearchParams();
    if (newFilters.workflow_type) params.set('workflow_type', newFilters.workflow_type);
    if (newFilters.workflow_id) params.set('workflow_id', newFilters.workflow_id);
    if (newFilters.event_type) params.set('event_type', newFilters.event_type);
    if (newFilters.created_after) params.set('created_after', newFilters.created_after);
    if (newFilters.created_before) params.set('created_before', newFilters.created_before);
    setSearchParams(params, { replace: true });
  };

  const handlePageChange = (newOffset) => {
    setPagination((p) => ({ ...p, offset: newOffset }));
    const params = new URLSearchParams(searchParams);
    params.set('offset', String(newOffset));
    setSearchParams(params, { replace: true });
  };

  if (loading && events.length === 0) {
    return <Loading message="> loading events..." />;
  }

  if (error) {
    return <Error error={error} onRetry={fetchEvents} />;
  }

  const columns = [
    {
      key: 'global_id',
      label: 'id',
      render: (row) => (
        <span className="text-xs text-theme font-mono">#{row.global_id}</span>
      ),
    },
    {
      key: 'workflow_id',
      label: 'workflow',
      render: (row) => (
        <Link
          to={`/workflows/${row.workflow_id}`}
          className="text-theme hover:text-theme-accent font-mono text-xs"
        >
          {row.workflow_id.substring(0, 16)}...
        </Link>
      ),
    },
    {
      key: 'workflow_type',
      label: 'workflow_type',
      render: (row) => (
        <span className="text-xs text-theme font-mono">{row.workflow_type}</span>
      ),
    },
    {
      key: 'event_type',
      label: 'event_type',
      render: (row) => (
        <span className="text-xs font-mono text-theme">{row.event_type}</span>
      ),
    },
    {
      key: 'workflow_version',
      label: 'version',
      render: (row) => (
        <span className="text-xs text-theme font-mono">{row.workflow_version}</span>
      ),
    },
    {
      key: 'at',
      label: 'timestamp',
      render: (row) => (
        <span className="text-xs text-theme font-mono opacity-70">
          {format(new Date(row.at), 'MMM d, yyyy HH:mm:ss')}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-1">
      <div>
        <h2 className="text-sm font-mono text-theme">$ event_explorer</h2>
        <p className="mt-0 text-xs font-mono text-theme opacity-70">> browse and filter events across all workflows</p>
      </div>

      {/* Filters */}
      <div className="card p-2">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-2">
          <div>
            <label className="block text-xs font-mono text-theme mb-0">workflow_type:</label>
            <select
              value={filters.workflow_type}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_type: e.target.value })
              }
              className="w-full px-2 py-1 bg-theme border border-theme text-xs font-mono text-theme focus:outline-none focus:border-theme-accent"
            >
              <option value="">all types</option>
              {workflowTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono text-theme mb-0">
              workflow_id:
            </label>
            <input
              type="text"
              value={filters.workflow_id}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_id: e.target.value })
              }
              placeholder="filter by workflow id..."
              data-search-input
              className="w-full px-2 py-1 bg-theme border border-theme text-xs font-mono text-theme placeholder-[var(--fleuve-muted)] focus:outline-none focus:border-theme-accent"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-theme mb-0">event_type:</label>
            <select
              value={filters.event_type}
              onChange={(e) =>
                handleFilterChange({ ...filters, event_type: e.target.value })
              }
              className="w-full px-2 py-1 bg-theme border border-theme text-xs font-mono text-theme focus:outline-none focus:border-theme-accent"
            >
              <option value="">all event types</option>
              {eventTypes.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono text-theme mb-0">created_after:</label>
            <input
              type="datetime-local"
              value={filters.created_after ? filters.created_after.slice(0, 16) : ''}
              onChange={(e) =>
                handleFilterChange({
                  ...filters,
                  created_after: e.target.value ? new Date(e.target.value).toISOString() : '',
                })
              }
              className="w-full px-2 py-1 bg-theme border border-theme text-theme text-xs font-mono focus:outline-none focus:border-theme-accent"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-theme mb-0">created_before:</label>
            <input
              type="datetime-local"
              value={filters.created_before ? filters.created_before.slice(0, 16) : ''}
              onChange={(e) =>
                handleFilterChange({
                  ...filters,
                  created_before: e.target.value ? new Date(e.target.value).toISOString() : '',
                })
              }
              className="w-full px-2 py-1 bg-theme border border-theme text-theme text-xs font-mono focus:outline-none focus:border-theme-accent"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() =>
                handleFilterChange({
                  workflow_type: '', workflow_id: '', event_type: '',
                  created_after: '', created_before: '',
                })
              }
              className="px-2 py-1 bg-theme border border-theme text-theme text-xs font-mono hover:bg-[var(--fleuve-border-hover)]"
            >
              clear_filters
            </button>
          </div>
        </div>
      </div>

      {/* Events Table */}
      <div className="card overflow-hidden">
        <Table
          columns={columns}
          data={events}
          onRowClick={(row) => setSelectedEvent(row)}
          emptyMessage="no events found"
        />
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between card px-2 py-1">
        <div className="text-xs font-mono text-theme opacity-70">
          showing {pagination.offset + 1} to {pagination.offset + events.length} of{' '}
          {events.length === pagination.limit ? 'many' : events.length} events
        </div>
        <div className="flex space-x-1">
          <button
            onClick={() => handlePageChange(Math.max(0, pagination.offset - pagination.limit))}
            disabled={pagination.offset === 0}
            className="px-2 py-1 bg-theme border border-theme text-theme text-xs font-mono hover:bg-[var(--fleuve-border-hover)] disabled:opacity-30 disabled:cursor-not-allowed"
          >
            previous
          </button>
          <button
            onClick={() => handlePageChange(pagination.offset + pagination.limit)}
            disabled={events.length < pagination.limit}
            className="px-2 py-1 bg-theme border border-theme text-theme text-xs font-mono hover:bg-[var(--fleuve-border-hover)] disabled:opacity-30 disabled:cursor-not-allowed"
          >
            next
          </button>
        </div>
      </div>

      {/* Event Detail Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 bg-black/80 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-2 border border-theme w-11/12 md:w-3/4 lg:w-1/2 bg-black">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-mono text-theme">event_details:</h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-theme hover:text-theme-error font-mono text-xs border border-theme px-1 py-0"
              >
                [X]
              </button>
            </div>
            <div className="space-y-1">
              <div>
                <p className="text-xs font-mono text-theme opacity-70">global_id:</p>
                <p className="text-xs font-mono text-theme">#{selectedEvent.global_id}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-theme opacity-70">workflow_id:</p>
                <Link
                  to={`/workflows/${selectedEvent.workflow_id}`}
                  className="text-xs font-mono text-theme hover:text-theme-accent"
                >
                  {selectedEvent.workflow_id}
                </Link>
              </div>
              <div>
                <p className="text-xs font-mono text-theme opacity-70">event_type:</p>
                <p className="text-xs font-mono text-theme">{selectedEvent.event_type}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-theme opacity-70">workflow_version:</p>
                <p className="text-xs font-mono text-theme">{selectedEvent.workflow_version}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-theme opacity-70">timestamp:</p>
                <p className="text-xs font-mono text-theme">
                  {format(new Date(selectedEvent.at), 'MMM d, yyyy HH:mm:ss')}
                </p>
              </div>
              <div>
                <p className="text-xs font-mono text-theme opacity-70 mb-1">event_body:</p>
                <JsonTree data={selectedEvent.body} />
              </div>
              {Object.keys(selectedEvent.metadata || {}).length > 0 && (
                <div>
                  <p className="text-xs font-mono text-theme opacity-70 mb-1">metadata:</p>
                  <JsonTree data={selectedEvent.metadata} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
