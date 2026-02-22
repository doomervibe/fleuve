import { useState, useEffect } from 'react';
import { api } from '../api/client';
import RefreshButton from './common/RefreshButton';
import PaginationBar from './common/PaginationBar';
import ColoredBadge from './common/ColoredBadge';
import CopyButton from './common/CopyButton';
import { SkeletonRow } from './common/Skeleton';
import { useResizableTableColumns } from '../hooks/useResizableTableColumns';
import { formatDate } from '../utils/format';

const PAGE_SIZE = 50;

export default function DelaysList({ onViewWorkflow }) {
  const [delays, setDelays] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDelays();
    const interval = setInterval(loadDelays, 5000);
    return () => clearInterval(interval);
  }, [offset]);

  async function loadDelays() {
    try {
      const data = await api.delays.list({ limit: PAGE_SIZE, offset });
      setDelays(data.delays || []);
      setTotal(data.total ?? data.delays?.length ?? 0);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load delays');
    } finally {
      setLoading(false);
    }
  }

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

  const getDelayId = (d) =>
    d.id ?? d.workflow_id + '-' + (d.event_version ?? d.event_number ?? '');

  const delayColumns = [
    { key: 'id', label: 'id', defaultWidth: 140 },
    { key: 'workflow', label: 'workflow', defaultWidth: 140 },
    { key: 'type', label: 'type', defaultWidth: 100 },
    { key: 'eventNum', label: 'event #', defaultWidth: 60 },
    { key: 'executeAt', label: 'execute at', defaultWidth: 140 },
    { key: 'timeRemaining', label: 'time remaining', defaultWidth: 100 },
  ];
  const { TableHead } = useResizableTableColumns('fleuve-delays-table', delayColumns);

  if (loading) {
    return (
      <>
        <div className="list-header">
          <h2>scheduled delays</h2>
        </div>
        <div className="table-container">
          <div className="skeleton-table">
            {Array.from({ length: 10 }, (_, i) => (
              <SkeletonRow key={i} cols={6} />
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
        <button onClick={loadDelays}>Retry</button>
      </div>
    );
  }

  return (
    <>
      <div className="list-header">
        <h2>scheduled delays</h2>
        <div className="list-controls">
          <RefreshButton onRefresh={loadDelays} />
        </div>
      </div>

      {delays.length === 0 ? (
        <div className="empty-state">
          <p>no scheduled delays</p>
        </div>
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
                <TableHead columnKey="executeAt" isLast={false}>execute at</TableHead>
                <TableHead columnKey="timeRemaining" isLast={true}>time remaining</TableHead>
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
                  <td className="cell-truncate" title={getDelayId(delay)}>
                    <span className="id-with-copy">
                      {getDelayId(delay)}
                      <CopyButton text={getDelayId(delay)} compact title="copy delay id" />
                    </span>
                  </td>
                  <td className="cell-truncate" title={delay.workflow_id}>
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
                  <td className="cell-truncate" title={delay.workflow_type}>
                    <ColoredBadge value={delay.workflow_type} />
                  </td>
                  <td>{delay.event_version ?? delay.event_number ?? '—'}</td>
                  <td className="cell-truncate" title={formatDate(delay.delay_until)}>{formatDate(delay.delay_until)}</td>
                  <td>{getTimeRemaining(delay.delay_until)}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
