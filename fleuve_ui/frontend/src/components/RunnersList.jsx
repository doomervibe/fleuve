import { useState, useEffect } from 'react';
import ColoredBadge from './common/ColoredBadge';
import CopyButton from './common/CopyButton';
import { SkeletonRow } from './common/Skeleton';
import { api } from '../api/client';
import RefreshButton from './common/RefreshButton';
import { useResizableTableColumns } from '../hooks/useResizableTableColumns';
import { formatDate } from '../utils/format';

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

  const runnerColumns = [
    { key: 'readerName', label: 'reader name', defaultWidth: 140 },
    { key: 'workflowType', label: 'workflow type', defaultWidth: 120 },
    { key: 'partition', label: 'partition', defaultWidth: 70 },
    { key: 'lastEvent', label: 'last event', defaultWidth: 80 },
    { key: 'maxEvent', label: 'max event', defaultWidth: 80 },
    { key: 'lag', label: 'lag', defaultWidth: 60 },
    { key: 'status', label: 'status', defaultWidth: 90 },
    { key: 'updated', label: 'updated', defaultWidth: 140 },
  ];
  const { TableHead } = useResizableTableColumns('fleuve-runners-table', runnerColumns);

  if (loading) {
    return (
      <>
        <div className="list-header">
          <h2>runners</h2>
        </div>
        <div className="table-container">
          <div className="skeleton-table">
            {Array.from({ length: 8 }, (_, i) => (
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
          <RefreshButton onRefresh={loadRunners} />
        </div>
      </div>

      {runners.length === 0 ? (
        <div className="empty-state">
          <p>no runners found</p>
          <p className="hint">
            runners will appear here once they start processing events
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <TableHead columnKey="readerName" isLast={false}>reader name</TableHead>
                <TableHead columnKey="workflowType" isLast={false}>workflow type</TableHead>
                <TableHead columnKey="partition" isLast={false}>partition</TableHead>
                <TableHead columnKey="lastEvent" isLast={false}>last event</TableHead>
                <TableHead columnKey="maxEvent" isLast={false}>max event</TableHead>
                <TableHead columnKey="lag" isLast={false}>lag</TableHead>
                <TableHead columnKey="status" isLast={false}>status</TableHead>
                <TableHead columnKey="updated" isLast={true}>updated</TableHead>
              </tr>
            </thead>
            <tbody>
              {runners.map((runner) => (
                <tr key={runner.reader_name + '-' + (runner.partition_id ?? 'single')}>
                  <td className="cell-truncate" title={runner.reader_name}>
                    <span className="id-with-copy">
                      {runner.reader_name}
                      <CopyButton
                        text={runner.reader_name + (runner.partition_id != null ? `-P${runner.partition_id}` : '')}
                        compact
                        title="copy runner id"
                      />
                    </span>
                  </td>
                  <td className="cell-truncate" title={runner.workflow_type}>
                    <ColoredBadge value={runner.workflow_type} />
                  </td>
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
                  <td className="cell-truncate" title={formatDate(runner.updated_at)}>{formatDate(runner.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
