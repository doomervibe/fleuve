import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function ActivitiesList({ onViewWorkflow }) {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    loadActivities();
    const interval = setInterval(loadActivities, 5000);
    return () => clearInterval(interval);
  }, [statusFilter]);

  async function loadActivities() {
    try {
      const params = statusFilter
        ? { status: statusFilter, limit: 50 }
        : { limit: 50 };
      const data = await api.activities.list(params);
      setActivities(data.activities || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load activities');
    } finally {
      setLoading(false);
    }
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString();
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>loading activities...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error">
        <p>Error: {error}</p>
        <button onClick={loadActivities}>Retry</button>
      </div>
    );
  }

  return (
    <>
      <div className="list-header">
        <h2>activities</h2>
        <div className="list-controls">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">all statuses</option>
            <option value="pending">pending</option>
            <option value="running">in progress</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
          </select>
          <button onClick={loadActivities} className="refresh-btn">
            refresh
          </button>
        </div>
      </div>

      {activities.length === 0 ? (
        <div className="empty-state">
          <p>No activities found</p>
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
                <th>status</th>
                <th>retries</th>
                <th>updated</th>
              </tr>
            </thead>
            <tbody>
              {activities.map((activity) => (
                <tr
                  key={activity.workflow_id + '-' + activity.event_number}
                  onClick={() =>
                    onViewWorkflow && onViewWorkflow(activity.workflow_id)
                  }
                >
                  <td>{activity.workflow_id + '-' + activity.event_number}</td>
                  <td>
                    {onViewWorkflow ? (
                      <button
                        className="event-workflow-link"
                        onClick={(e) => {
                          e.stopPropagation();
                          onViewWorkflow(activity.workflow_id);
                        }}
                      >
                        {activity.workflow_id}
                      </button>
                    ) : (
                      activity.workflow_id
                    )}
                  </td>
                  <td>{activity.workflow_type || '—'}</td>
                  <td>{activity.event_number}</td>
                  <td>
                    <span
                      className={`status-badge ${(activity.status || '')
                        .toLowerCase()
                        .replace(' ', '_')}`}
                    >
                      {activity.status}
                    </span>
                  </td>
                  <td>{activity.retry_count ?? 0}</td>
                  <td>
                    {formatDate(
                      activity.finished_at || activity.started_at || activity.last_attempt_at
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
