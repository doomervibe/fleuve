import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function RunnersList() {
  const [runners, setRunners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [workflowTypeFilter, setWorkflowTypeFilter] = useState('');
  const [workflowTypes, setWorkflowTypes] = useState([]);

  useEffect(() => {
    loadRunners();
    const interval = setInterval(loadRunners, 5000);
    return () => clearInterval(interval);
  }, [workflowTypeFilter]);

  async function loadRunners() {
    try {
      const params = workflowTypeFilter
        ? { workflow_type: workflowTypeFilter }
        : {};
      const data = await api.runners.list(params);
      const runnersList = data.runners || [];
      setRunners(runnersList);

      const types = [...new Set(runnersList.map((r) => r.workflow_type))];
      if (types.length > workflowTypes.length) {
        setWorkflowTypes(types);
      }

      setError(null);
    } catch (err) {
      setRunners([]);
      setError(null);
    } finally {
      setLoading(false);
    }
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString();
  };

  const getLagClass = (lag) => {
    if (lag < 10) return 'lag-healthy';
    if (lag < 100) return 'lag-warning';
    return 'lag-critical';
  };

  const getLagLabel = (lag) => {
    if (lag < 10) return 'healthy';
    if (lag < 100) return 'catching up';
    return 'falling behind';
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>loading runners...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error">
        <p>Error: {error}</p>
        <button onClick={loadRunners}>Retry</button>
      </div>
    );
  }

  return (
    <>
      <div className="list-header">
        <h2>runners</h2>
        <div className="list-controls">
          <select
            value={workflowTypeFilter}
            onChange={(e) => setWorkflowTypeFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">all workflow types</option>
            {workflowTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <button onClick={loadRunners} className="refresh-btn">
            refresh
          </button>
        </div>
      </div>

      {runners.length === 0 ? (
        <div className="empty-state">
          <p>No runners found</p>
          <p className="hint">
            Runners will appear here once they start processing events
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>reader name</th>
                <th>workflow type</th>
                <th>partition</th>
                <th>last event</th>
                <th>max event</th>
                <th>lag</th>
                <th>status</th>
                <th>updated</th>
              </tr>
            </thead>
            <tbody>
              {runners.map((runner) => (
                <tr key={runner.reader_name + '-' + (runner.partition_id ?? 'single')}>
                  <td>{runner.reader_name}</td>
                  <td>{runner.workflow_type}</td>
                  <td>
                    {runner.partition_id !== undefined &&
                    runner.partition_id !== null ? (
                      <span className="partition-badge">
                        P{runner.partition_id}
                      </span>
                    ) : (
                      <span className="partition-badge single">single</span>
                    )}
                  </td>
                  <td>{runner.last_event_id?.toLocaleString() ?? '—'}</td>
                  <td>{runner.max_event_id?.toLocaleString() ?? '—'}</td>
                  <td>{runner.lag?.toLocaleString() ?? '—'}</td>
                  <td>
                    <span
                      className={`status-indicator ${getLagClass(
                        runner.lag ?? 0
                      )}`}
                    >
                      {getLagLabel(runner.lag ?? 0)}
                    </span>
                  </td>
                  <td>{formatDate(runner.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
