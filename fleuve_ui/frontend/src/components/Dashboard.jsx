import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function Dashboard({ onViewWorkflow }) {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('');
  const [searchId, setSearchId] = useState('');
  const [searchError, setSearchError] = useState(null);

  useEffect(() => {
    loadWorkflows();
    const interval = setInterval(loadWorkflows, 5000);
    return () => clearInterval(interval);
  }, [filter, searchId]);

  async function loadWorkflows() {
    try {
      const params = {};
      if (filter) params.workflow_type = filter;
      if (searchId.trim()) params.workflow_id = searchId.trim();
      const data = await api.workflows.list(
        Object.keys(params).length ? params : undefined
      );
      setWorkflows(data.workflows || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflows');
    } finally {
      setLoading(false);
    }
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString();
  };

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
      <div className="loading">
        <div className="spinner" />
        <p>loading workflows...</p>
      </div>
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
          <button onClick={loadWorkflows} className="refresh-btn">
            refresh
          </button>
        </div>
      </div>

      {searchError && (
        <p className="search-error">{searchError}</p>
      )}

      {workflows.length === 0 ? (
        <div className="empty-state">
          <p>
            {searchId.trim()
              ? `No workflows match "${searchId.trim()}"`
              : 'No workflows found'}
          </p>
          <p className="hint">
            {searchId.trim()
              ? 'Try a different ID or clear the search to see all.'
              : 'Run an example to create workflows:'}
          </p>
          {!searchId.trim() && (
            <pre>make run-example</pre>
          )}
        </div>
      ) : (
        <div className="workflows-grid">
          {workflows.map((workflow) => (
            <div
              key={workflow.workflow_id}
              className="workflow-card"
              onClick={() => onViewWorkflow(workflow.workflow_id)}
            >
              <div className="workflow-card-header">
                <h3>{workflow.workflow_id}</h3>
                <span className="workflow-type">{workflow.workflow_type}</span>
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
                    {workflow.updated_at
                      ? formatDate(workflow.updated_at)
                      : '—'}
                  </span>
                </div>
              </div>
              <div className="workflow-card-footer">
                Updated: {formatDate(workflow.updated_at)}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
