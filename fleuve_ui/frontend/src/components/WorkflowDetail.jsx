import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import JsonHighlight from './common/JsonHighlight';
import WorkflowTimeline from './WorkflowTimeline';
import CausationGraph from './CausationGraph';
import ActivitiesTimeline from './ActivitiesTimeline';
import ColoredBadge from './common/ColoredBadge';
import CopyButton from './common/CopyButton';
import RefreshButton from './common/RefreshButton';
import { Skeleton, SkeletonText } from './common/Skeleton';
import { useResizableTableColumns } from '../hooks/useResizableTableColumns';
import { formatDate } from '../utils/format';

export default function WorkflowDetail({ onBack }) {
  const { id: workflowId } = useParams();
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('events');
  const [activitiesViewMode, setActivitiesViewMode] = useState('table');
  const [activitiesStatusFilter, setActivitiesStatusFilter] = useState('');

  useEffect(() => {
    if (!workflowId) {
      navigate('/');
      return;
    }
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

  function getTimeRemaining(delayUntil) {
    const now = new Date();
    const target = new Date(delayUntil);
    const diff = target.getTime() - now.getTime();
    if (diff < 0) return 'Overdue';
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    }
    return `${hours}h ${minutes}m`;
  }

  const activityColumns = [
    { key: 'id', label: 'id', defaultWidth: 140 },
    { key: 'workflow', label: 'workflow', defaultWidth: 140 },
    { key: 'type', label: 'type', defaultWidth: 100 },
    { key: 'eventNum', label: 'event #', defaultWidth: 60 },
    { key: 'status', label: 'status', defaultWidth: 80 },
    { key: 'runner', label: 'runner', defaultWidth: 120 },
    { key: 'retries', label: 'retries', defaultWidth: 60 },
    { key: 'updated', label: 'updated', defaultWidth: 140 },
  ];
  const delayColumns = [
    { key: 'id', label: 'id', defaultWidth: 140 },
    { key: 'workflow', label: 'workflow', defaultWidth: 140 },
    { key: 'type', label: 'type', defaultWidth: 100 },
    { key: 'eventNum', label: 'event #', defaultWidth: 60 },
    { key: 'executeAt', label: 'execute at', defaultWidth: 140 },
    { key: 'timeRemaining', label: 'time remaining', defaultWidth: 100 },
  ];
  const { TableHead: ActivityTableHead } = useResizableTableColumns(
    'workflow-activities-table',
    activityColumns
  );
  const { TableHead: DelayTableHead } = useResizableTableColumns(
    'workflow-delays-table',
    delayColumns
  );

  const filteredActivities = useMemo(() => {
    const list = workflow?.activities || [];
    if (!activitiesStatusFilter) return list;
    return list.filter(
      (a) =>
        (a.status || '').toLowerCase() === activitiesStatusFilter.toLowerCase()
    );
  }, [workflow?.activities, activitiesStatusFilter]);

  if (loading) {
    return (
      <div className="workflow-detail">
        <div className="detail-header">
          <Skeleton style={{ width: 60, height: 24 }} />
          <div className="detail-title">
            <SkeletonText width="200px" />
            <SkeletonText width="120px" />
          </div>
          <div className="detail-stats">
            {[1, 2, 3].map((i) => (
              <div key={i} className="stat">
                <SkeletonText width="40px" />
                <SkeletonText width="24px" />
              </div>
            ))}
          </div>
        </div>
        <div className="tabs">
          {['timeline', 'events', 'activities', 'delays', 'graph'].map((tab) => (
            <Skeleton key={tab} style={{ width: 80, height: 28 }} />
          ))}
        </div>
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
          <CopyButton text={workflow.workflow_id} compact title="copy workflow id" />
          <ColoredBadge value={workflow.workflow_type} className="workflow-type" />
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
          className={activeTab === 'timeline' ? 'active' : ''}
          onClick={() => setActiveTab('timeline')}
        >
          timeline
        </button>
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
        <button
          className={activeTab === 'graph' ? 'active' : ''}
          onClick={() => setActiveTab('graph')}
        >
          graph
        </button>
      </div>

      {activeTab === 'timeline' && (
        <WorkflowTimeline
          events={workflow.events}
          activities={workflow.activities}
          delays={workflow.delays}
          formatDate={formatDate}
        />
      )}

      {activeTab === 'events' && (
        <div className="events-timeline">
          {[...(workflow.events || [])]
            .sort((a, b) => {
              const ta = new Date(a.created_at || a.at || 0).getTime();
              const tb = new Date(b.created_at || b.at || 0).getTime();
              return tb - ta;
            })
            .map((event) => (
            <div key={event.id} className="timeline-item">
              <span className="timeline-marker">#{event.event_number}</span>
              <div className="timeline-content">
                <div className="timeline-header">
                  <ColoredBadge value={event.body?.type || 'Event'} />
                  <small>{formatDate(event.created_at)}</small>
                </div>
                <JsonHighlight data={event.body} className="json-view" copyable />
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'activities' && (
        <>
          <div className="list-header">
            <h2>activities</h2>
            <div className="list-controls">
              <div className="view-toggle">
                <button
                  className={activitiesViewMode === 'table' ? 'active' : ''}
                  onClick={() => setActivitiesViewMode('table')}
                >
                  table
                </button>
                <button
                  className={activitiesViewMode === 'timeline' ? 'active' : ''}
                  onClick={() => setActivitiesViewMode('timeline')}
                >
                  timeline
                </button>
              </div>
              <select
                value={activitiesStatusFilter}
                onChange={(e) => setActivitiesStatusFilter(e.target.value)}
                className="filter-select"
              >
                <option value="">all statuses</option>
                <option value="pending">pending</option>
                <option value="running">in progress</option>
                <option value="completed">completed</option>
                <option value="failed">failed</option>
              </select>
              <RefreshButton onRefresh={loadWorkflow} />
            </div>
          </div>
          {filteredActivities.length === 0 ? (
            <div className="empty-state">
              <p>no activities found</p>
            </div>
          ) : activitiesViewMode === 'timeline' ? (
            <ActivitiesTimeline
              activities={filteredActivities}
              formatDate={formatDate}
            />
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <ActivityTableHead columnKey="id" isLast={false}>id</ActivityTableHead>
                    <ActivityTableHead columnKey="workflow" isLast={false}>workflow</ActivityTableHead>
                    <ActivityTableHead columnKey="type" isLast={false}>type</ActivityTableHead>
                    <ActivityTableHead columnKey="eventNum" isLast={false}>event #</ActivityTableHead>
                    <ActivityTableHead columnKey="status" isLast={false}>status</ActivityTableHead>
                    <ActivityTableHead columnKey="runner" isLast={false}>runner</ActivityTableHead>
                    <ActivityTableHead columnKey="retries" isLast={false}>retries</ActivityTableHead>
                    <ActivityTableHead columnKey="updated" isLast={true}>updated</ActivityTableHead>
                  </tr>
                </thead>
                <tbody>
                  {filteredActivities.map((activity) => (
                    <tr key={activity.id ?? activity.workflow_id + '-' + activity.event_number}>
                      <td className="cell-truncate" title={activity.id ?? activity.workflow_id + '-' + activity.event_number}>
                        <span className="id-with-copy">
                          {activity.id ?? activity.workflow_id + '-' + activity.event_number}
                          <CopyButton
                            text={activity.id ?? activity.workflow_id + '-' + activity.event_number}
                            compact
                            title="copy activity id"
                          />
                        </span>
                      </td>
                      <td className="cell-truncate" title={activity.workflow_id}>
                        {activity.workflow_id}
                      </td>
                      <td className="cell-truncate" title={activity.workflow_type || '—'}>
                        {activity.workflow_type ? (
                          <ColoredBadge value={activity.workflow_type} />
                        ) : (
                          '—'
                        )}
                      </td>
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
                      <td className="cell-truncate" title={activity.runner_id || '—'}>
                        {activity.runner_id || '—'}
                      </td>
                      <td>{activity.retry_count ?? 0}</td>
                      <td className="cell-truncate" title={formatDate(activity.updated_at)}>
                        {formatDate(activity.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {activeTab === 'graph' && (
        <CausationGraph
          events={workflow.events}
          activities={workflow.activities}
          delays={workflow.delays}
        />
      )}

      {activeTab === 'delays' && (
        <>
          <div className="list-header">
            <h2>scheduled delays</h2>
            <div className="list-controls">
              <RefreshButton onRefresh={loadWorkflow} />
            </div>
          </div>
          {(workflow.delays || []).length === 0 ? (
            <div className="empty-state">
              <p>no scheduled delays</p>
            </div>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <DelayTableHead columnKey="id" isLast={false}>id</DelayTableHead>
                    <DelayTableHead columnKey="workflow" isLast={false}>workflow</DelayTableHead>
                    <DelayTableHead columnKey="type" isLast={false}>type</DelayTableHead>
                    <DelayTableHead columnKey="eventNum" isLast={false}>event #</DelayTableHead>
                    <DelayTableHead columnKey="executeAt" isLast={false}>execute at</DelayTableHead>
                    <DelayTableHead columnKey="timeRemaining" isLast={true}>time remaining</DelayTableHead>
                  </tr>
                </thead>
                <tbody>
                  {(workflow.delays || []).map((delay) => {
                    const delayId = delay.id ?? delay.workflow_id + '-' + (delay.event_version ?? delay.event_number ?? '');
                    return (
                      <tr key={delayId}>
                        <td className="cell-truncate" title={delayId}>
                          <span className="id-with-copy">
                            {delayId}
                            <CopyButton text={delayId} compact title="copy delay id" />
                          </span>
                        </td>
                        <td className="cell-truncate" title={delay.workflow_id}>
                          {delay.workflow_id}
                        </td>
                        <td className="cell-truncate" title={delay.workflow_type}>
                          <ColoredBadge value={delay.workflow_type} />
                        </td>
                        <td>{delay.event_number ?? delay.event_version ?? '—'}</td>
                        <td className="cell-truncate" title={formatDate(delay.delay_until)}>
                          {formatDate(delay.delay_until)}
                        </td>
                        <td>{getTimeRemaining(delay.delay_until)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
