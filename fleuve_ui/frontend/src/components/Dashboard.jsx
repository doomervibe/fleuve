import { useState, useEffect } from 'react';
import { api } from '../api/client';
import RefreshButton from './common/RefreshButton';
import PaginationBar from './common/PaginationBar';
import ColoredBadge from './common/ColoredBadge';
import { SkeletonCard } from './common/Skeleton';
import { formatDate } from '../utils/format';

const PAGE_SIZE = 24;

export default function Dashboard({ onViewWorkflow }) {
  const [workflows, setWorkflows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('');
  const [searchId, setSearchId] = useState('');
  const [searchError, setSearchError] = useState(null);

  useEffect(() => {
    setOffset(0);
  }, [filter, searchId]);

  useEffect(() => {
    loadWorkflows();
    const interval = setInterval(loadWorkflows, 5000);
    return () => clearInterval(interval);
  }, [filter, searchId, offset]);

  async function loadWorkflows() {
    try {
      const params = { limit: PAGE_SIZE, offset };
      if (filter) params.workflow_type = filter;
      if (searchId.trim()) params.workflow_id = searchId.trim();
      const data = await api.workflows.list(params);
      setWorkflows(data.workflows || []);
      setTotal(data.total ?? data.workflows?.length ?? 0);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflows');
    } finally {
      setLoading(false);
    }
  }

  const getWorkflowTypes = () => {
    const types = new Set(workflows.map((w) => w.workflow_type));
    return Array.from(types);
  };

  async function handleSearchById(e) {
    e.preventDefault();
    const id = searchId.trim();
    if (!id) return;
    setSearchError(null);
    try {
      await api.workflows.get(id);
      onViewWorkflow(id);
    } catch {
      setSearchError('Workflow not found');
    }
  }

  if (loading) {
    return (
      <>
        <div className="list-header">
          <h2>workflows</h2>
        </div>
        <div className="workflows-grid">
          {Array.from({ length: 8 }, (_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </>
    );
  }

  if (error) {
    return (
      <div className="error">
        <p>Error: {error}</p>
        <button onClick={loadWorkflows}>Retry</button>
      </div>
    );
  }

  return (
    <>
      <div className="list-header">
        <h2>workflows</h2>
        <div className="list-controls">
          <form
            className="search-workflow-form"
            onSubmit={handleSearchById}
          >
            <input
              type="text"
              value={searchId}
              onChange={(e) => {
                setSearchId(e.target.value);
                setSearchError(null);
              }}
              className="search-input"
              placeholder="workflow id"
            />
            <button type="submit" className="search-btn">
              go
            </button>
          </form>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">all types</option>
            {getWorkflowTypes().map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <RefreshButton onRefresh={loadWorkflows} />
        </div>
      </div>

      {searchError && (
        <p className="search-error">{searchError}</p>
      )}

      {workflows.length === 0 ? (
        <div className="empty-state">
          <p>
            {searchId.trim()
              ? `no workflows match "${searchId.trim()}"`
              : 'no workflows found'}
          </p>
          <p className="hint">
            {searchId.trim()
              ? 'try a different id or clear the search to see all.'
              : 'run an example to create workflows:'}
          </p>
          {!searchId.trim() && (
            <pre>make run-example</pre>
          )}
        </div>
      ) : (
        <>
        <div className="workflows-grid">
          {workflows.map((workflow) => (
            <div
              key={workflow.workflow_id}
              className="workflow-card"
              onClick={() => onViewWorkflow(workflow.workflow_id)}
            >
              <div className="workflow-card-header">
                <h3 title={workflow.workflow_id}>{workflow.workflow_id}</h3>
                <ColoredBadge value={workflow.workflow_type} className="workflow-type" title={workflow.workflow_type} />
              </div>
              <div className="workflow-card-body">
                <div className="workflow-stat">
                  <span className="stat-label">events</span>
                  <span className="stat-value">
                    {workflow.version ?? '—'}
                  </span>
                </div>
                <div className="workflow-stat">
                  <span className="stat-label">last event</span>
                  <span className="stat-value">
                    {formatDate(workflow.updated_at)}
                  </span>
                </div>
                {workflow.runner_id && (
                  <div className="workflow-stat">
                    <span className="stat-label">runner</span>
                    <span className="stat-value" title={workflow.runner_id}>
                      {workflow.runner_id}
                    </span>
                  </div>
                )}
              </div>
              <div className="workflow-card-footer">
                updated: {formatDate(workflow.updated_at)}
              </div>
            </div>
          ))}
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
