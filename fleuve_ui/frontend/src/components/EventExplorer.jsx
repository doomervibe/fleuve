import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import Table from './common/Table';
import { format } from 'date-fns';

export default function EventExplorer() {
  const [events, setEvents] = useState([]);
  const [workflowTypes, setWorkflowTypes] = useState([]);
  const [eventTypes, setEventTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    workflow_type: '',
    workflow_id: '',
    event_type: '',
  });
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

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
    setPagination({ ...pagination, offset: 0 });
  };

  const handlePageChange = (newOffset) => {
    setPagination({ ...pagination, offset: newOffset });
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
        <span className="text-xs text-[#00ff00] font-mono">#{row.global_id}</span>
      ),
    },
    {
      key: 'workflow_id',
      label: 'workflow',
      render: (row) => (
        <Link
          to={`/workflows/${row.workflow_id}`}
          className="text-[#00ff00] hover:text-[#00ffff] font-mono text-xs"
        >
          {row.workflow_id.substring(0, 16)}...
        </Link>
      ),
    },
    {
      key: 'workflow_type',
      label: 'workflow_type',
      render: (row) => (
        <span className="text-xs text-[#00ff00] font-mono">{row.workflow_type}</span>
      ),
    },
    {
      key: 'event_type',
      label: 'event_type',
      render: (row) => (
        <span className="text-xs font-mono text-[#00ff00]">{row.event_type}</span>
      ),
    },
    {
      key: 'workflow_version',
      label: 'version',
      render: (row) => (
        <span className="text-xs text-[#00ff00] font-mono">{row.workflow_version}</span>
      ),
    },
    {
      key: 'at',
      label: 'timestamp',
      render: (row) => (
        <span className="text-xs text-[#00ff00] font-mono opacity-70">
          {format(new Date(row.at), 'MMM d, yyyy HH:mm:ss')}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-1">
      <div>
        <h2 className="text-sm font-mono text-[#00ff00]">$ event_explorer</h2>
        <p className="mt-0 text-xs font-mono text-[#00ff00] opacity-70">> browse and filter events across all workflows</p>
      </div>

      {/* Filters */}
      <div className="card p-2">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <div>
            <label className="block text-xs font-mono text-[#00ff00] mb-0">
              workflow_type:
            </label>
            <select
              value={filters.workflow_type}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_type: e.target.value })
              }
              className="w-full px-2 py-1 bg-black border border-[#00ff00] text-xs font-mono text-[#00ff00] focus:outline-none focus:border-[#00ffff]"
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
            <label className="block text-xs font-mono text-[#00ff00] mb-0">
              workflow_id:
            </label>
            <input
              type="text"
              value={filters.workflow_id}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_id: e.target.value })
              }
              placeholder="filter by workflow id..."
              className="w-full px-2 py-1 bg-black border border-[#00ff00] text-xs font-mono text-[#00ff00] placeholder-[#004400] focus:outline-none focus:border-[#00ffff]"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-[#00ff00] mb-0">
              event_type:
            </label>
            <select
              value={filters.event_type}
              onChange={(e) =>
                handleFilterChange({ ...filters, event_type: e.target.value })
              }
              className="w-full px-2 py-1 bg-black border border-[#00ff00] text-xs font-mono text-[#00ff00] focus:outline-none focus:border-[#00ffff]"
            >
              <option value="">all event types</option>
              {eventTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={() =>
                handleFilterChange({ workflow_type: '', workflow_id: '', event_type: '' })
              }
              className="px-2 py-1 bg-black border border-[#00ff00] text-[#00ff00] text-xs font-mono hover:bg-[#001100]"
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
        <div className="text-xs font-mono text-[#00ff00] opacity-70">
          showing {pagination.offset + 1} to {pagination.offset + events.length} of{' '}
          {events.length === pagination.limit ? 'many' : events.length} events
        </div>
        <div className="flex space-x-1">
          <button
            onClick={() => handlePageChange(Math.max(0, pagination.offset - pagination.limit))}
            disabled={pagination.offset === 0}
            className="px-2 py-1 bg-black border border-[#00ff00] text-[#00ff00] text-xs font-mono hover:bg-[#001100] disabled:opacity-30 disabled:cursor-not-allowed"
          >
            previous
          </button>
          <button
            onClick={() => handlePageChange(pagination.offset + pagination.limit)}
            disabled={events.length < pagination.limit}
            className="px-2 py-1 bg-black border border-[#00ff00] text-[#00ff00] text-xs font-mono hover:bg-[#001100] disabled:opacity-30 disabled:cursor-not-allowed"
          >
            next
          </button>
        </div>
      </div>

      {/* Event Detail Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 bg-black bg-opacity-80 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-2 border border-[#00ff00] w-11/12 md:w-3/4 lg:w-1/2 bg-black">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-mono text-[#00ff00]">event_details:</h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-[#00ff00] hover:text-[#ff0000] font-mono text-xs border border-[#00ff00] px-1 py-0"
              >
                [X]
              </button>
            </div>
            <div className="space-y-1">
              <div>
                <p className="text-xs font-mono text-[#00ff00] opacity-70">global_id:</p>
                <p className="text-xs font-mono text-[#00ff00]">#{selectedEvent.global_id}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-[#00ff00] opacity-70">workflow_id:</p>
                <Link
                  to={`/workflows/${selectedEvent.workflow_id}`}
                  className="text-xs font-mono text-[#00ff00] hover:text-[#00ffff]"
                >
                  {selectedEvent.workflow_id}
                </Link>
              </div>
              <div>
                <p className="text-xs font-mono text-[#00ff00] opacity-70">event_type:</p>
                <p className="text-xs font-mono text-[#00ff00]">{selectedEvent.event_type}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-[#00ff00] opacity-70">workflow_version:</p>
                <p className="text-xs font-mono text-[#00ff00]">{selectedEvent.workflow_version}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-[#00ff00] opacity-70">timestamp:</p>
                <p className="text-xs font-mono text-[#00ff00]">
                  {format(new Date(selectedEvent.at), 'MMM d, yyyy HH:mm:ss')}
                </p>
              </div>
              <div>
                <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-1">event_body:</p>
                <pre className="bg-black p-2 border border-[#00ff00] overflow-x-auto text-xs font-mono text-[#00ff00]">
                  {JSON.stringify(selectedEvent.body, null, 2)}
                </pre>
              </div>
              {Object.keys(selectedEvent.metadata || {}).length > 0 && (
                <div>
                  <p className="text-xs font-mono text-[#00ff00] opacity-70 mb-1">metadata:</p>
                  <pre className="bg-black p-2 border border-[#00ff00] overflow-x-auto text-xs font-mono text-[#00ff00]">
                    {JSON.stringify(selectedEvent.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
