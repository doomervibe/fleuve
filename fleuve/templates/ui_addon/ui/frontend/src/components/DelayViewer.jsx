import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import Table from './common/Table';
import { format, formatDistanceToNow } from 'date-fns';

function CronScheduleInfo({ delay }) {
  if (!delay.cron_expression) return null;
  return (
    <div className="mt-1 text-xs font-mono text-theme opacity-70">
      <span className="text-theme-accent">cron:</span> {delay.cron_expression}
      {delay.cron_timezone && (
        <span className="ml-1">({delay.cron_timezone})</span>
      )}
      {delay.next_fire_times && delay.next_fire_times.length > 0 && (
        <div className="mt-0.5">
          next: {delay.next_fire_times.slice(0, 5).map((t, i) => (
            <span key={i} className="mr-2">
              {format(new Date(t), 'MMM d HH:mm')}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DelayViewer() {
  const [delays, setDelays] = useState([]);
  const [workflowTypes, setWorkflowTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    workflow_type: '',
    workflow_id: '',
  });
  const [pagination, setPagination] = useState({
    limit: 50,
    offset: 0,
  });
  const [now, setNow] = useState(new Date());

  const fetchWorkflowTypes = async () => {
    try {
      const types = await api.getWorkflowTypes();
      setWorkflowTypes(types.map((t) => t.workflow_type));
    } catch (err) {
      console.error('Failed to fetch workflow types:', err);
    }
  };

  const fetchDelays = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getDelays({
        ...filters,
        ...pagination,
      });
      setDelays(data);
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
    fetchDelays();
    const interval = setInterval(fetchDelays, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [filters, pagination]);

  // Update time every second for countdown timers
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
    setPagination({ ...pagination, offset: 0 });
  };

  const handlePageChange = (newOffset) => {
    setPagination({ ...pagination, offset: newOffset });
  };

  const getTimeRemaining = (delayUntil) => {
    const delayDate = new Date(delayUntil);
    const diff = delayDate - now;
    if (diff <= 0) return 'completed';
    
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (days > 0) return `${days}d ${hours % 24}h`;
    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  };

  const isActive = (delayUntil) => {
    return new Date(delayUntil) > now;
  };

  if (loading && delays.length === 0) {
    return <Loading message="> loading delays..." />;
  }

  if (error) {
    return <Error error={error} onRetry={fetchDelays} />;
  }

  const columns = [
    {
      key: 'workflow_id',
      label: 'workflow',
      render: (row) => (
        <Link
          to={`/workflows/${row.workflow_id}`}
          className="text-theme hover:text-theme-accent font-mono text-xs font-mono"
        >
          {row.workflow_id.substring(0, 16)}...
        </Link>
      ),
    },
    {
      key: 'workflow_type',
      label: 'workflow type',
      render: (row) => (
        <span className="text-xs font-mono text-theme font-mono text-xs">{row.workflow_type}</span>
      ),
    },
    {
      key: 'delay_until',
      label: 'delay until',
      render: (row) => (
        <span className="text-xs font-mono text-theme font-mono text-xs">
          {format(new Date(row.delay_until), 'MMM d, yyyy HH:mm:ss')}
        </span>
      ),
    },
    {
      key: 'time_remaining',
      label: 'time remaining',
      render: (row) => {
        const active = isActive(row.delay_until);
        return (
          <span
            className={`text-xs font-mono font-medium ${
              active ? 'text-theme-warning' : 'text-theme opacity-70'
            }`}
          >
            {active ? getTimeRemaining(row.delay_until) : 'completed'}
          </span>
        );
      },
    },
    {
      key: 'event_version',
      label: 'event version',
      render: (row) => (
        <span className="text-xs font-mono text-theme font-mono text-xs">{row.event_version}</span>
      ),
    },
    {
      key: 'created_at',
      label: 'created',
      render: (row) => (
        <span className="text-xs font-mono text-theme font-mono text-xs opacity-70">
          {format(new Date(row.created_at), 'MMM d, yyyy HH:mm:ss')}
        </span>
      ),
    },
    {
      key: 'schedule',
      label: 'schedule',
      render: (row) => (
        <div>
          {row.cron_expression ? (
            <span className="text-xs font-mono text-theme-accent" title={row.cron_timezone || 'UTC'}>
              cron: {row.cron_expression}
            </span>
          ) : (
            <span className="text-xs font-mono text-theme opacity-50">one-shot</span>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-sm font-mono font-bold text-theme font-mono">delay viewer</h2>
        <p className="mt-0.5 text-xs font-mono text-theme font-mono text-xs opacity-70">view scheduled delays and countdown timers</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="card p-3">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="w-8 h-8 bg-theme border border-theme-warning  flex items-center justify-center">
                <span className="text-theme text-xs font-mono font-bold">A</span>
              </div>
            </div>
            <div className="ml-4">
              <p className="text-xs font-mono font-medium text-theme font-mono text-xs opacity-70">active delays</p>
              <p className="text-sm font-mono font-bold text-theme font-mono">
                {delays.filter((d) => isActive(d.delay_until)).length}
              </p>
            </div>
          </div>
        </div>
        <div className="card p-3">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="w-8 h-8 bg-theme border border-theme  flex items-center justify-center">
                <span className="text-theme text-xs font-mono font-bold">T</span>
              </div>
            </div>
            <div className="ml-4">
              <p className="text-xs font-mono font-medium text-theme font-mono text-xs opacity-70">total delays</p>
              <p className="text-sm font-mono font-bold text-theme font-mono">{delays.length}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="card p-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-mono font-medium text-theme font-mono text-xs mb-1">
              workflow type
            </label>
            <select
              value={filters.workflow_type}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_type: e.target.value })
              }
              className="w-full px-3 py-2 bg-theme border border-theme text-theme font-mono text-xs focus:outline-none focus:ring-2 focus:ring-theme-accent"
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
            <label className="block text-xs font-mono font-medium text-theme font-mono text-xs mb-1">
              workflow id
            </label>
            <input
              type="text"
              value={filters.workflow_id}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_id: e.target.value })
              }
              placeholder="filter by workflow id..."
              data-search-input
              className="w-full px-3 py-2 bg-theme border border-theme text-theme font-mono text-xs focus:outline-none focus:ring-2 focus:ring-theme-accent"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() => handleFilterChange({ workflow_type: '', workflow_id: '' })}
              className="px-4 py-2 bg-[var(--fleuve-surface-hover)] text-theme font-mono text-xs  hover:bg-[var(--fleuve-border-hover)]"
            >
              clear filters
            </button>
          </div>
        </div>
      </div>

      {/* Delays Table */}
      <div className="card overflow-hidden">
        <Table
          columns={columns}
          data={delays}
          onRowClick={(row) => {
            window.location.href = `/workflows/${row.workflow_id}`;
          }}
          emptyMessage="no delays found"
        />
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between card px-4 py-2">
        <div className="text-xs font-mono text-theme font-mono text-xs">
          showing {pagination.offset + 1} to {pagination.offset + delays.length} of{' '}
          {delays.length === pagination.limit ? 'many' : delays.length} delays
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => handlePageChange(Math.max(0, pagination.offset - pagination.limit))}
            disabled={pagination.offset === 0}
            className="px-4 py-2 bg-[var(--fleuve-surface-hover)] text-theme font-mono text-xs  hover:bg-[var(--fleuve-border-hover)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            previous
          </button>
          <button
            onClick={() => handlePageChange(pagination.offset + pagination.limit)}
            disabled={delays.length < pagination.limit}
            className="px-4 py-2 bg-[var(--fleuve-surface-hover)] text-theme font-mono text-xs  hover:bg-[var(--fleuve-border-hover)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            next
          </button>
        </div>
      </div>

      {/* Active Delays List */}
      {delays.filter((d) => isActive(d.delay_until)).length > 0 && (
        <div className="card p-3">
          <h3 className="text-base font-bold text-theme font-mono mb-3">active delays</h3>
          <div className="space-y-3">
            {delays
              .filter((d) => isActive(d.delay_until))
              .map((delay, idx) => (
                <div
                  key={idx}
                  className="border-l-4 border-theme-warning pl-4 py-2 bg-[var(--fleuve-surface)] rounded-r-md"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <Link
                        to={`/workflows/${delay.workflow_id}`}
                        className="text-theme hover:text-theme-accent font-mono text-xs font-mono"
                      >
                        {delay.workflow_id.substring(0, 16)}...
                      </Link>
                      <p className="text-xs font-mono text-theme font-mono text-xs mt-0.5">
                        {format(new Date(delay.delay_until), 'MMM d, yyyy HH:mm:ss')}
                      </p>
                      <CronScheduleInfo delay={delay} />
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold text-theme-warning">
                        {getTimeRemaining(delay.delay_until)}
                      </p>
                      <p className="text-xs text-theme font-mono text-xs opacity-70">
                        {formatDistanceToNow(new Date(delay.delay_until), { addSuffix: true })}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
