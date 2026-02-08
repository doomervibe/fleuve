export default function Table({ columns, data, onRowClick, emptyMessage = '> no data available' }) {
  if (data.length === 0) {
    return (
      <div className="text-center py-4 text-[#00ff00] opacity-50 text-xs font-mono">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto border border-[#00ff00]">
      <table className="min-w-full divide-y divide-[#00ff00] font-mono text-xs">
        <thead className="bg-black">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className="px-2 py-1 text-left text-xs font-mono text-[#00ff00] border-b border-[#00ff00]"
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-black divide-y divide-[#00ff00]">
          {data.map((row, idx) => (
            <tr
              key={idx}
              onClick={() => onRowClick && onRowClick(row)}
              className={onRowClick ? 'cursor-pointer hover:bg-[#001100]' : ''}
            >
              {columns.map((col) => (
                <td key={col.key} className="px-2 py-1 whitespace-nowrap text-xs text-[#00ff00]">
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
