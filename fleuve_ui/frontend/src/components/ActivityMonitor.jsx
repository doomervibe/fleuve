import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import Table from './common/Table';
import { format } from 'date-fns';

export default function ActivityMonitor() {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    workflow_id: '',
    status: '',
  });
  const [pagination, setPagination] = useState({
    limit: 50,
    offset: 0,
  });
  const [selectedActivity, setSelectedActivity] = useState(null);

  const fetchActivities = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getActivities({
        ...filters,
        ...pagination,
      });
      setActivities(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchActivities();
    const interval = setInterval(fetchActivities, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [filters, pagination]);

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
    setPagination({ ...pagination, offset: 0 });
  };

  const handlePageChange = (newOffset) => {
    setPagination({ ...pagination, offset: newOffset });
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed':
        return 'bg-black text-[#00ff00] border border-[#00ff00]';
      case 'failed':
        return 'bg-black text-[#ff0000] border border-[#ff0000]';
      case 'running':
        return 'bg-black text-[#00ffff] border border-[#00ffff]';
      case 'retrying':
        return 'bg-black text-[#ffbf00] border border-[#ffbf00]';
      case 'pending':
        return 'bg-black text-[#00ff00] border border-[#00ff00] opacity-50';
      default:
        return 'bg-black text-[#00ff00] border border-[#00ff00] opacity-50';
    }
  };

  const calculateDuration = (started, finished) => {
    if (!started) return '-';
    const start = new Date(started);
    const end = finished ? new Date(finished) : new Date();
    const diff = Math.floor((end - start) / 1000);
    if (diff < 60) return `${diff}s`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`;
    return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
  };

  if (loading && activities.length === 0) {
    return <Loading message="> loading activities..." />;
  }

  if (error) {
    return <Error error={error} onRetry={fetchActivities} />;
  }

  const columns = [
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
      key: 'event_number',
      label: 'event #',
      render: (row) => (
        <span className="text-xs text-[#00ff00] font-mono">{row.event_number}</span>
      ),
    },
    {
      key: 'status',
      label: 'status',
      render: (row) => (
        <span className={`px-1 py-0 text-xs font-mono border ${getStatusColor(row.status)}`}>
          {row.status}
        </span>
      ),
    },
    {
      key: 'retry_count',
      label: 'retries',
      render: (row) => (
        <span className="text-xs font-mono text-[#00ff00] font-mono text-xs">
          {row.retry_count} / {row.max_retries}
        </span>
      ),
    },
    {
      key: 'started_at',
      label: 'started',
      render: (row) => (
        <span className="text-xs font-mono text-[#00ff00] font-mono text-xs opacity-70">
          {format(new Date(row.started_at), 'MMM d, HH:mm:ss')}
        </span>
      ),
    },
    {
      key: 'duration',
      label: 'duration',
      render: (row) => (
        <span className="text-xs font-mono text-[#00ff00] font-mono text-xs">
          {calculateDuration(row.started_at, row.finished_at)}
        </span>
      ),
    },
    {
      key: 'error',
      label: 'error',
      render: (row) =>
        row.error_message ? (
          <span
            className="text-xs font-mono text-red-600 cursor-pointer"
            onClick={() => setSelectedActivity(row)}
            title="click to view details"
          >
            {row.error_message.substring(0, 30)}...
          </span>
        ) : (
          <span className="text-xs font-mono text-[#00ff00] font-mono text-xs opacity-70">-</span>
        ),
    },
  ];

  const statusOptions = ['pending', 'running', 'completed', 'failed', 'retrying'];

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-xl font-bold text-gray-100">activity monitor</h2>
        <p className="mt-0.5 text-xs font-mono text-[#00ff00] font-mono text-xs opacity-70">monitor action execution and retries</p>
      </div>

      {/* Filters */}
      <div className="card p-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-mono font-medium text-gray-300 mb-1">
              workflow id
            </label>
            <input
              type="text"
              value={filters.workflow_id}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_id: e.target.value })
              }
              placeholder="filter by workflow id..."
              className="w-full px-3 py-2 bg-black border border-[#00ff00] text-[#00ff00] font-mono text-xs focus:outline-none focus:ring-2 focus:ring-[#FF6B35]"
            />
          </div>
          <div>
            <label className="block text-xs font-mono font-medium text-gray-300 mb-1">
              status
            </label>
            <select
              value={filters.status}
              onChange={(e) =>
                handleFilterChange({ ...filters, status: e.target.value })
              }
              className="w-full px-3 py-2 bg-black border border-[#00ff00] text-[#00ff00] font-mono text-xs focus:outline-none focus:ring-2 focus:ring-[#FF6B35]"
            >
              <option value="">all statuses</option>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={() => handleFilterChange({ workflow_id: '', status: '' })}
              className="px-4 py-2 bg-[#242424] text-[#00ff00] font-mono text-xs rounded-md hover:bg-[#2a2a2a]"
            >
              clear filters
            </button>
          </div>
        </div>
      </div>

      {/* Activities Table */}
      <div className="card overflow-hidden">
        <Table
          columns={columns}
          data={activities}
          onRowClick={(row) => setSelectedActivity(row)}
          emptyMessage="no activities found"
        />
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between card px-4 py-2">
        <div className="text-xs font-mono text-gray-300">
          showing {pagination.offset + 1} to {pagination.offset + activities.length} of{' '}
          {activities.length === pagination.limit ? 'many' : activities.length} activities
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => handlePageChange(Math.max(0, pagination.offset - pagination.limit))}
            disabled={pagination.offset === 0}
            className="px-4 py-2 bg-[#242424] text-[#00ff00] font-mono text-xs rounded-md hover:bg-[#2a2a2a] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            previous
          </button>
          <button
            onClick={() => handlePageChange(pagination.offset + pagination.limit)}
            disabled={activities.length < pagination.limit}
            className="px-4 py-2 bg-[#242424] text-[#00ff00] font-mono text-xs rounded-md hover:bg-[#2a2a2a] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            next
          </button>
        </div>
      </div>

      {/* Activity Detail Modal */}
      {selectedActivity && (
        <div className="fixed inset-0 bg-black bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border border-[#2a2a2a] w-11/12 md:w-3/4 lg:w-1/2 shadow-sm rounded-md bg-[#1a1a1a]">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold text-gray-100">activity details</h3>
              <button
                onClick={() => setSelectedActivity(null)}
                className="text-[#00ff00] font-mono text-xs opacity-70 hover:text-[#00ff00] font-mono text-xs"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70">workflow id</p>
                  <Link
                    to={`/workflows/${selectedActivity.workflow_id}`}
                    className="text-xs font-mono text-[#00ff00] hover:text-[#FF7B45] font-mono"
                  >
                    {selectedActivity.workflow_id}
                  </Link>
                </div>
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70">event number</p>
                  <p className="text-xs font-mono text-[#00ff00] font-mono text-xs">{selectedActivity.event_number}</p>
                </div>
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70">status</p>
                  <span
                    className={`inline-block px-2 py-1 text-xs rounded ${getStatusColor(
                      selectedActivity.status
                    )}`}
                  >
                    {selectedActivity.status}
                  </span>
                </div>
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70">retries</p>
                  <p className="text-xs font-mono text-[#00ff00] font-mono text-xs">
                    {selectedActivity.retry_count} / {selectedActivity.max_retries}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70">started</p>
                  <p className="text-xs font-mono text-[#00ff00] font-mono text-xs">
                    {format(new Date(selectedActivity.started_at), 'MMM d, yyyy HH:mm:ss')}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70">finished</p>
                  <p className="text-xs font-mono text-[#00ff00] font-mono text-xs">
                    {selectedActivity.finished_at
                      ? format(new Date(selectedActivity.finished_at), 'MMM d, yyyy HH:mm:ss')
                      : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70">duration</p>
                  <p className="text-xs font-mono text-[#00ff00] font-mono text-xs">
                    {calculateDuration(selectedActivity.started_at, selectedActivity.finished_at)}
                  </p>
                </div>
              </div>
              {selectedActivity.error_message && (
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70 mb-2">error</p>
                  <div className="bg-red-900/30 border border-red-500/30 rounded-md p-3">
                    <p className="text-xs font-mono font-medium text-red-400">
                      {selectedActivity.error_type}
                    </p>
                    <p className="text-xs font-mono text-red-300 mt-0.5">{selectedActivity.error_message}</p>
                  </div>
                </div>
              )}
              {Object.keys(selectedActivity.checkpoint || {}).length > 0 && (
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70 mb-2">checkpoint</p>
                  <pre className="bg-[#0a0a0a] p-3 rounded-md overflow-x-auto text-xs font-mono text-[#00ff00] font-mono text-xs border border-[#2a2a2a]">
                    {JSON.stringify(selectedActivity.checkpoint, null, 2)}
                  </pre>
                </div>
              )}
              {selectedActivity.resulting_command && (
                <div>
                  <p className="text-xs font-mono font-medium text-[#00ff00] font-mono text-xs opacity-70 mb-2">resulting command</p>
                  <pre className="bg-[#0a0a0a] p-3 rounded-md overflow-x-auto text-xs font-mono text-[#00ff00] font-mono text-xs border border-[#2a2a2a]">
                    {JSON.stringify(selectedActivity.resulting_command, null, 2)}
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
