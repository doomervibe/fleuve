import { useState, useEffect } from 'react';
import { api } from '../api/client';
import RefreshButton from './common/RefreshButton';
import PaginationBar from './common/PaginationBar';
import ActivitiesTimeline from './ActivitiesTimeline';
import ColoredBadge from './common/ColoredBadge';
import CopyButton from './common/CopyButton';
import { SkeletonRow } from './common/Skeleton';
import { useResizableTableColumns } from '../hooks/useResizableTableColumns';
import { formatDate } from '../utils/format';

const PAGE_SIZE = 50;

export default function ActivitiesList({ onViewWorkflow }) {
  const [activities, setActivities] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'timeline'

  useEffect(() => {
    setOffset(0);
  }, [statusFilter]);

  useEffect(() => {
    loadActivities();
    const interval = setInterval(loadActivities, 5000);
    return () => clearInterval(interval);
  }, [statusFilter, offset]);

  async function loadActivities() {
    try {
      const params = { limit: PAGE_SIZE, offset };
      if (statusFilter) params.status = statusFilter;
      const data = await api.activities.list(params);
      setActivities(data.activities || []);
      setTotal(data.total ?? data.activities?.length ?? 0);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load activities');
    } finally {
      setLoading(false);
    }
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
  const { TableHead } = useResizableTableColumns('fleuve-activities-table', activityColumns);

  if (loading) {
    return (
      <>
        <div className="list-header">
          <h2>activities</h2>
        </div>
        <div className="table-container">
          <div className="skeleton-table">
            {Array.from({ length: 10 }, (_, i) => (
              <SkeletonRow key={i} cols={8} />
            ))}
          </div>
        </div>
      </>
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
          <div className="view-toggle">
            <button
              className={viewMode === 'table' ? 'active' : ''}
              onClick={() => setViewMode('table')}
            >
              table
            </button>
            <button
              className={viewMode === 'timeline' ? 'active' : ''}
              onClick={() => setViewMode('timeline')}
            >
              timeline
            </button>
          </div>
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
          <RefreshButton onRefresh={loadActivities} />
        </div>
      </div>

      {activities.length === 0 ? (
        <div className="empty-state">
          <p>no activities found</p>
        </div>
      ) : viewMode === 'timeline' ? (
        <ActivitiesTimeline
          activities={activities}
          onActivityClick={onViewWorkflow}
          formatDate={formatDate}
        />
      ) : (
        <>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <TableHead columnKey="id" isLast={false}>id</TableHead>
                <TableHead columnKey="workflow" isLast={false}>workflow</TableHead>
                <TableHead columnKey="type" isLast={false}>type</TableHead>
                <TableHead columnKey="eventNum" isLast={false}>event #</TableHead>
                <TableHead columnKey="status" isLast={false}>status</TableHead>
                <TableHead columnKey="runner" isLast={false}>runner</TableHead>
                <TableHead columnKey="retries" isLast={false}>retries</TableHead>
                <TableHead columnKey="updated" isLast={true}>updated</TableHead>
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
                  <td className="cell-truncate" title={activity.workflow_id + '-' + activity.event_number}>
                    <span className="id-with-copy">
                      {activity.workflow_id + '-' + activity.event_number}
                      <CopyButton
                        text={activity.workflow_id + '-' + activity.event_number}
                        compact
                        title="copy activity id"
                      />
                    </span>
                  </td>
                  <td className="cell-truncate" title={activity.workflow_id}>
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
                  <td className="cell-truncate" title={formatDate(
                    activity.finished_at || activity.started_at || activity.last_attempt_at
                  )}>{formatDate(
                    activity.finished_at || activity.started_at || activity.last_attempt_at
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {viewMode === 'table' && (
          <PaginationBar
            offset={offset}
            limit={PAGE_SIZE}
            total={total}
            onPageChange={setOffset}
          />
        )}
        </>
      )}
    </>
  );
}
