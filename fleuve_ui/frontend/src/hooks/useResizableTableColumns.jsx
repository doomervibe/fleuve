/**
 * Hook for resizable table columns with localStorage persistence.
 * @param {string} storageKey - localStorage key for persisting widths
 * @param {Array<{key: string, label: string, defaultWidth?: number}>} columns
 * @returns {{ widths: Object, startResize: Function, TableHead: Function }}
 */
import { useState, useCallback, useEffect } from 'react';

const MIN_COL_WIDTH = 40;

function getStored(storageKey) {
  try {
    const s = localStorage.getItem(storageKey);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

function persist(storageKey, widths) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(widths));
  } catch {}
}

export function useResizableTableColumns(storageKey, columns) {
  const stored = getStored(storageKey);
  const [widths, setWidths] = useState(() => {
    const w = {};
    columns.forEach((c) => {
      w[c.key] = stored?.[c.key] ?? c.defaultWidth ?? 120;
    });
    return w;
  });
  const [resizing, setResizing] = useState(null);

  const startResize = useCallback(
    (key, e) => {
      e.preventDefault();
      e.stopPropagation();
      setResizing({ key, startX: e.clientX, startW: widths[key] });
    },
    [widths]
  );

  const handleMove = useCallback(
    (e) => {
      if (!resizing) return;
      const d = e.clientX - resizing.startX;
      const w = Math.max(MIN_COL_WIDTH, resizing.startW + d);
      setWidths((prev) => {
        const next = { ...prev, [resizing.key]: w };
        persist(storageKey, next);
        return next;
      });
    },
    [resizing, storageKey]
  );

  const handleUp = useCallback(() => setResizing(null), []);

  useEffect(() => {
    if (!resizing) return;
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [resizing, handleMove, handleUp]);

  const TableHead = useCallback(
    ({ columnKey, children, isLast }) => (
      <th style={{ width: widths[columnKey], minWidth: MIN_COL_WIDTH }}>
        <div className="table-th-content">
          {children}
          {!isLast && (
            <div
              className="table-col-resizer"
              onMouseDown={(e) => startResize(columnKey, e)}
            />
          )}
        </div>
      </th>
    ),
    [widths, startResize]
  );

  return { widths, startResize, TableHead };
}
