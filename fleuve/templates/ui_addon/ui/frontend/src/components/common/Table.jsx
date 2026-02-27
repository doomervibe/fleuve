export default function Table({
  columns,
  data,
  onRowClick,
  emptyMessage = '> no data available',
  rowKey,
  selectedIds = [],
  onSelectionChange,
}) {
  const selectable = Boolean(rowKey && onSelectionChange);
  const allSelected = selectable && data.length > 0 && data.every((r) => selectedIds.includes(r[rowKey]));
  const someSelected = selectable && selectedIds.length > 0;

  const toggleRow = (e, row) => {
    e.stopPropagation();
    const id = row[rowKey];
    const next = selectedIds.includes(id)
      ? selectedIds.filter((x) => x !== id)
      : [...selectedIds, id];
    onSelectionChange(next);
  };

  const toggleAll = (e) => {
    e.stopPropagation();
    if (allSelected) {
      onSelectionChange([]);
    } else {
      onSelectionChange(data.map((r) => r[rowKey]));
    }
  };

  if (data.length === 0) {
    return (
      <div className="text-center py-4 text-theme opacity-50 text-xs font-mono">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto border border-theme">
      <table className="min-w-full divide-y divide-[color:var(--fleuve-border)] font-mono text-xs">
        <thead className="bg-theme">
          <tr>
            {selectable && (
              <th
                className="w-8 px-1 py-1 text-left border-b border-theme"
                onClick={toggleAll}
              >
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => el && (el.indeterminate = someSelected && !allSelected)}
                  onChange={() => {}}
                  className="cursor-pointer"
                />
              </th>
            )}
            {columns.map((col) => (
              <th
                key={col.key}
                className="px-2 py-1 text-left text-xs font-mono text-theme border-b border-theme"
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-theme divide-y divide-[color:var(--fleuve-border)]">
          {data.map((row, idx) => (
            <tr
              key={row[rowKey] ?? idx}
              onClick={() => onRowClick && onRowClick(row)}
              className={onRowClick ? 'cursor-pointer hover:bg-[var(--fleuve-border-hover)]' : ''}
            >
              {selectable && (
                <td
                  className="w-8 px-1 py-1 text-theme"
                  onClick={(e) => toggleRow(e, row)}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(row[rowKey])}
                    onChange={() => {}}
                    className="cursor-pointer"
                  />
                </td>
              )}
              {columns.map((col) => (
                <td key={col.key} className="px-2 py-1 whitespace-nowrap text-xs text-theme">
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
