import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import Loading from './common/Loading';
import Error from './common/Error';
import Table from './common/Table';
import { format } from 'date-fns';

function CopyButton({ text, className = '' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className={`inline-flex items-center gap-1 px-1 py-0 text-xs font-mono text-theme hover:text-theme-accent border border-theme ${className}`}
      title="Copy workflow ID"
    >
      {copied ? '[OK]' : '[CP]'}
    </button>
  );
}

function parseFiltersFromSearchParams(searchParams) {
  return {
    workflow_type: searchParams.get('workflow_type') || '',
    search: searchParams.get('search') || '',
    created_after: searchParams.get('created_after') || '',
    created_before: searchParams.get('created_before') || '',
  };
}

export default function WorkflowList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [workflows, setWorkflows] = useState([]);
  const [workflowTypes, setWorkflowTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState(() => parseFiltersFromSearchParams(searchParams));
  const [pagination, setPagination] = useState({
    limit: 50,
    offset: parseInt(searchParams.get('offset') || '0', 10),
  });
  const [selectedIds, setSelectedIds] = useState([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState(null);

  useEffect(() => {
    setFilters(parseFiltersFromSearchParams(searchParams));
    setPagination((p) => ({ ...p, offset: parseInt(searchParams.get('offset') || '0', 10) }));
  }, [searchParams]);

  const fetchWorkflowTypes = async () => {
    try {
      const types = await api.getWorkflowTypes();
      setWorkflowTypes(types.map((t) => t.workflow_type));
    } catch (err) {
      console.error('Failed to fetch workflow types:', err);
    }
  };

  const fetchWorkflows = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getWorkflows({
        ...filters,
        ...pagination,
      });
      setWorkflows(data);
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
    fetchWorkflows();
    const interval = setInterval(fetchWorkflows, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [filters, pagination]);

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
    setPagination((p) => ({ ...p, offset: 0 }));
    const params = new URLSearchParams();
    if (newFilters.workflow_type) params.set('workflow_type', newFilters.workflow_type);
    if (newFilters.search) params.set('search', newFilters.search);
    if (newFilters.created_after) params.set('created_after', newFilters.created_after);
    if (newFilters.created_before) params.set('created_before', newFilters.created_before);
    setSearchParams(params, { replace: true });
  };

  const handlePageChange = (newOffset) => {
    setPagination((p) => ({ ...p, offset: newOffset }));
    const params = new URLSearchParams(searchParams);
    params.set('offset', String(newOffset));
    setSearchParams(params, { replace: true });
    setSelectedIds([]);
  };

  const handleBatchCancel = async () => {
    if (selectedIds.length === 0) return;
    setBatchLoading(true);
    setBatchError(null);
    try {
      await api.batchCancel(selectedIds);
      setSelectedIds([]);
      fetchWorkflows();
    } catch (err) {
      setBatchError(err);
    } finally {
      setBatchLoading(false);
    }
  };

  const handleBatchReplay = async () => {
    if (selectedIds.length === 0) return;
    setBatchLoading(true);
    setBatchError(null);
    try {
      await api.batchReplay(selectedIds);
      setSelectedIds([]);
      fetchWorkflows();
    } catch (err) {
      setBatchError(err);
    } finally {
      setBatchLoading(false);
    }
  };

  if (loading && workflows.length === 0) {
    return <Loading message="> loading workflows..." />;
  }

  if (error) {
    return <Error error={error} onRetry={fetchWorkflows} />;
  }

  const columns = [
    {
      key: 'workflow_id',
      label: 'workflow id',
      render: (row) => (
        <div className="flex items-center gap-1">
          <Link
            to={`/workflows/${row.workflow_id}`}
            className="text-theme hover:text-theme-accent font-mono text-xs"
          >
            {row.workflow_id.substring(0, 16)}...
          </Link>
          <CopyButton text={row.workflow_id} />
        </div>
      ),
    },
    {
      key: 'workflow_type',
      label: 'type',
      render: (row) => (
        <span className="text-xs font-mono text-theme">{row.workflow_type}</span>
      ),
    },
    {
      key: 'version',
      label: 'version',
      render: (row) => (
        <span className="text-xs font-mono text-theme">{row.version}</span>
      ),
    },
    {
      key: 'state',
      label: 'state_preview',
      render: (row) => {
        const stateKeys = Object.keys(row.state || {}).slice(0, 3);
        return (
          <div className="text-xs font-mono text-theme opacity-70">
            {stateKeys.length > 0
              ? stateKeys.map((key) => (
                  <span key={key} className="mr-2">
                    {key}: {String(row.state[key]).substring(0, 20)}
                  </span>
                ))
              : 'no state'}
          </div>
        );
      },
    },
    {
      key: 'created_at',
      label: 'created',
      render: (row) => (
        <span className="text-xs font-mono text-theme opacity-70">
          {row.created_at
            ? format(new Date(row.created_at), 'MMM d, yyyy HH:mm')
            : 'N/A'}
        </span>
      ),
    },
    {
      key: 'updated_at',
      label: 'updated',
      render: (row) => (
        <span className="text-xs font-mono text-theme opacity-70">
          {row.updated_at
            ? format(new Date(row.updated_at), 'MMM d, yyyy HH:mm')
            : 'N/A'}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-1">
      <div>
        <h2 className="text-sm font-mono text-theme">$ workflows</h2>
        <p className="mt-0 text-xs font-mono text-theme opacity-70">> browse and search all workflows</p>
      </div>

      {/* Filters */}
      <div className="card p-2">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-2">
          <div>
            <label className="block text-xs font-mono text-theme mb-0">workflow_type:</label>
            <select
              value={filters.workflow_type}
              onChange={(e) =>
                handleFilterChange({ ...filters, workflow_type: e.target.value })
              }
              className="w-full px-2 py-1 bg-theme border border-theme text-theme text-xs font-mono focus:outline-none focus:border-theme-accent"
            >
              <option value="">all types</option>
              {workflowTypes.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono text-theme mb-0">search_workflow_id:</label>
            <input
              type="text"
              value={filters.search}
              onChange={(e) =>
                handleFilterChange({ ...filters, search: e.target.value })
              }
              placeholder="search by workflow id..."
              data-search-input
              className="w-full px-2 py-1 bg-theme border border-theme text-theme placeholder-[var(--fleuve-muted)] text-xs font-mono focus:outline-none focus:border-theme-accent"
            />
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
              onClick={() => handleFilterChange({
                workflow_type: '', search: '', created_after: '', created_before: '',
              })}
              className="px-2 py-1 bg-theme border border-theme text-theme hover:bg-[var(--fleuve-border-hover)] text-xs font-mono"
            >
              clear_filters
            </button>
          </div>
        </div>
      </div>

      {/* Bulk actions bar */}
      {selectedIds.length > 0 && (
        <div className="card p-2 flex items-center justify-between gap-2">
          <span className="text-xs font-mono text-theme">
            {selectedIds.length} selected
          </span>
          <div className="flex items-center gap-2">
            {batchError && (
              <span className="text-xs font-mono text-red-500">{batchError.message}</span>
            )}
            <button
              onClick={handleBatchCancel}
              disabled={batchLoading}
              className="px-2 py-1 bg-theme border border-theme text-theme hover:bg-[var(--fleuve-border-hover)] disabled:opacity-50 text-xs font-mono"
            >
              {batchLoading ? '...' : 'cancel selected'}
            </button>
            <button
              onClick={handleBatchReplay}
              disabled={batchLoading}
              className="px-2 py-1 bg-theme border border-theme text-theme hover:bg-[var(--fleuve-border-hover)] disabled:opacity-50 text-xs font-mono"
            >
              {batchLoading ? '...' : 'replay selected'}
            </button>
            <button
              onClick={() => setSelectedIds([])}
              className="px-2 py-1 text-theme opacity-70 hover:opacity-100 text-xs font-mono"
            >
              clear
            </button>
          </div>
        </div>
      )}

      {/* Workflows Table */}
      <div className="card overflow-hidden">
        <Table
          columns={columns}
          data={workflows}
          rowKey="workflow_id"
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onRowClick={(row) => {
            window.location.href = `/workflows/${row.workflow_id}`;
          }}
          emptyMessage="no workflows found"
        />
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between card px-2 py-1">
        <div className="text-xs font-mono text-theme opacity-70">
          showing {pagination.offset + 1} to {pagination.offset + workflows.length} of{' '}
          {workflows.length === pagination.limit ? 'many' : workflows.length} workflows
        </div>
        <div className="flex space-x-1">
          <button
            onClick={() => handlePageChange(Math.max(0, pagination.offset - pagination.limit))}
            disabled={pagination.offset === 0}
            className="px-2 py-1 bg-theme border border-theme text-theme hover:bg-[var(--fleuve-border-hover)] disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-theme text-xs font-mono"
          >
            previous
          </button>
          <button
            onClick={() => handlePageChange(pagination.offset + pagination.limit)}
            disabled={workflows.length < pagination.limit}
            className="px-2 py-1 bg-theme border border-theme text-theme hover:bg-[var(--fleuve-border-hover)] disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-theme text-xs font-mono"
          >
            next
          </button>
        </div>
      </div>
    </div>
  );
}
