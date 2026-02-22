export default function Table({ columns, data, onRowClick, emptyMessage = 'no data available' }) {
  if (data.length === 0) {
    return (
      <div className="text-center py-4 empty-state text-xs font-mono">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full font-mono text-xs data-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} className="px-2 py-1 text-left text-xs font-mono">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr
              key={idx}
              onClick={() => onRowClick && onRowClick(row)}
              className={onRowClick ? 'cursor-pointer workflow-card' : ''}
            >
              {columns.map((col) => (
                <td key={col.key} className="px-2 py-1 whitespace-nowrap text-xs">
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
