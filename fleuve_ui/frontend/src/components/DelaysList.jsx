import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function DelaysList({ onViewWorkflow }) {
  const [delays, setDelays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDelays();
    const interval = setInterval(loadDelays, 5000);
    return () => clearInterval(interval);
  }, []);

  async function loadDelays() {
    try {
      const data = await api.delays.list({ limit: 50 });
      setDelays(data.delays || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load delays');
    } finally {
      setLoading(false);
    }
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString();
  };

  const getTimeRemaining = (delayUntil) => {
    const now = new Date();
    const target = new Date(delayUntil);
    const diff = target.getTime() - now.getTime();

    if (diff < 0) return 'Overdue';

    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor(
      (diff % (1000 * 60 * 60)) / (1000 * 60)
    );

    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    }

    return `${hours}h ${minutes}m`;
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>loading delays...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error">
        <p>Error: {error}</p>
        <button onClick={loadDelays}>Retry</button>
      </div>
    );
  }

  const getDelayId = (d) =>
    d.id ?? d.workflow_id + '-' + (d.event_version ?? d.event_number ?? '');

  return (
    <>
      <div className="list-header">
        <h2>scheduled delays</h2>
        <div className="list-controls">
          <button onClick={loadDelays} className="refresh-btn">
            refresh
          </button>
        </div>
      </div>

      {delays.length === 0 ? (
        <div className="empty-state">
          <p>No scheduled delays</p>
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
                <th>execute at</th>
                <th>time remaining</th>
              </tr>
            </thead>
            <tbody>
              {delays.map((delay) => (
                <tr
                  key={getDelayId(delay)}
                  onClick={() =>
                    onViewWorkflow && onViewWorkflow(delay.workflow_id)
                  }
                >
                  <td>{getDelayId(delay)}</td>
                  <td>
                    {onViewWorkflow ? (
                      <button
                        className="event-workflow-link"
                        onClick={(e) => {
                          e.stopPropagation();
                          onViewWorkflow(delay.workflow_id);
                        }}
                      >
                        {delay.workflow_id}
                      </button>
                    ) : (
                      delay.workflow_id
                    )}
                  </td>
                  <td>{delay.workflow_type}</td>
                  <td>{delay.event_version ?? delay.event_number ?? '—'}</td>
                  <td>{formatDate(delay.delay_until)}</td>
                  <td>{getTimeRemaining(delay.delay_until)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
