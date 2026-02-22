import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function WorkflowDetail({ workflowId, onBack }) {
  const [workflow, setWorkflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('events');

  useEffect(() => {
    loadWorkflow();
    const interval = setInterval(loadWorkflow, 5000);
    return () => clearInterval(interval);
  }, [workflowId]);

  async function loadWorkflow() {
    try {
      const data = await api.workflows.get(workflowId);
      setWorkflow(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflow');
    } finally {
      setLoading(false);
    }
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString();
  };

  const formatJSON = (obj) => {
    return JSON.stringify(obj, null, 2);
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>loading workflow...</p>
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <div className="error">
        <p>Error: {error || 'Workflow not found'}</p>
        <button onClick={onBack}>← back</button>
      </div>
    );
  }

  return (
    <div className="workflow-detail">
      <div className="detail-header">
        <button className="back-btn" onClick={onBack}>
          ← back
        </button>
        <div className="detail-title">
          <h2>{workflow.workflow_id}</h2>
          <span className="workflow-type">{workflow.workflow_type}</span>
        </div>
        <div className="detail-stats">
          <div className="stat">
            <span className="stat-label">events</span>
            <span className="stat-value">{workflow.event_count}</span>
          </div>
          <div className="stat">
            <span className="stat-label">activities</span>
            <span className="stat-value">{workflow.activities?.length ?? 0}</span>
          </div>
          <div className="stat">
            <span className="stat-label">delays</span>
            <span className="stat-value">{workflow.delays?.length ?? 0}</span>
          </div>
        </div>
      </div>

      <div className="tabs">
        <button
          className={activeTab === 'events' ? 'active' : ''}
          onClick={() => setActiveTab('events')}
        >
          events ({workflow.events?.length ?? 0})
        </button>
        <button
          className={activeTab === 'activities' ? 'active' : ''}
          onClick={() => setActiveTab('activities')}
        >
          activities ({workflow.activities?.length ?? 0})
        </button>
        <button
          className={activeTab === 'delays' ? 'active' : ''}
          onClick={() => setActiveTab('delays')}
        >
          delays ({workflow.delays?.length ?? 0})
        </button>
      </div>

      {activeTab === 'events' && (
        <div className="events-timeline">
          {(workflow.events || []).map((event) => (
            <div key={event.id} className="timeline-item">
              <span className="timeline-marker">#{event.event_number}</span>
              <div className="timeline-content">
                <div className="timeline-header">
                  <span>{event.body?.type || 'Event'}</span>
                  <small>{formatDate(event.created_at)}</small>
                </div>
                <pre className="json-view">{formatJSON(event.body)}</pre>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'activities' && (
        <div>
          {(workflow.activities || []).length === 0 ? (
            <div className="empty-state">
              <p>No activities</p>
            </div>
          ) : (
            (workflow.activities || []).map((activity) => (
              <div key={activity.id} className="activity-item">
                <div className="activity-header">
                  <span
                    className={`status-badge ${activity.status
                      .toLowerCase()
                      .replace(' ', '_')}`}
                  >
                    {activity.status}
                  </span>
                  <span>Event #{activity.event_number}</span>
                  {activity.retry_count > 0 && (
                    <span className="retry-badge">
                      Retries: {activity.retry_count}
                    </span>
                  )}
                </div>
                <p className="workflow-card-footer">
                  Updated: {formatDate(activity.updated_at)}
                </p>
                {activity.resulting_command && (
                  <details>
                    <summary>Resulting Command</summary>
                    <pre className="json-view">
                      {formatJSON(activity.resulting_command)}
                    </pre>
                  </details>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'delays' && (
        <div>
          {(workflow.delays || []).length === 0 ? (
            <div className="empty-state">
              <p>No scheduled delays</p>
            </div>
          ) : (
            (workflow.delays || []).map((delay) => (
              <div key={delay.id} className="delay-item">
                <div className="delay-header">
                  <span>Delay #{delay.id}</span>
                  <span>Event #{delay.event_number}</span>
                </div>
                <p className="workflow-card-footer">
                  Execute at: {formatDate(delay.delay_until)}
                </p>
                <details>
                  <summary>Next Command</summary>
                  <pre className="json-view">
                    {formatJSON(delay.next_command)}
                  </pre>
                </details>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
