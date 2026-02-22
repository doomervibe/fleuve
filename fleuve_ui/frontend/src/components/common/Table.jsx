import { useResizableTableColumns } from '../../hooks/useResizableTableColumns';

export default function Table({ columns, data, onRowClick, emptyMessage = 'no data available', storageKey = 'fleuve-table' }) {
  const colConfig = columns.map((c) => ({
    key: c.key,
    label: c.label,
    defaultWidth: c.defaultWidth ?? 120,
  }));
  const { TableHead } = useResizableTableColumns(storageKey, colConfig);

  if (data.length === 0) {
    return (
      <div className="empty-state table-empty">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="table-container">
      <table className="data-table table-component">
        <thead>
          <tr>
            {columns.map((col, i) => (
              <TableHead key={col.key} columnKey={col.key} isLast={i === columns.length - 1}>
                {col.label}
              </TableHead>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr
              key={idx}
              onClick={() => onRowClick && onRowClick(row)}
              className={onRowClick ? 'clickable-row workflow-card' : ''}
            >
              {columns.map((col) => {
                const value = col.render ? col.render(row) : row[col.key];
                const titleStr = col.title ? col.title(row) : (row[col.key] != null ? String(row[col.key]) : null);
                return (
                  <td key={col.key} className="cell-truncate" title={titleStr}>
                    {value}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
