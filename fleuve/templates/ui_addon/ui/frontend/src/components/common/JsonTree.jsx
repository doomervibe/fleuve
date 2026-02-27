import { useState, useCallback } from 'react';

function ValueDisplay({ value, depth }) {
  if (value === null) {
    return <span className="text-theme-error">null</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="text-theme-warning">{String(value)}</span>;
  }
  if (typeof value === 'number') {
    return <span className="text-theme-accent">{String(value)}</span>;
  }
  if (typeof value === 'string') {
    return (
      <span className="text-theme">
        &quot;{String(value).replace(/"/g, '\\"')}&quot;
      </span>
    );
  }
  return null;
}

function TreeNode({ keyName, value, depth, defaultExpanded = false, expandAll }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isExpanded = expandAll !== undefined ? expandAll : expanded;
  const isExpandable =
    typeof value === 'object' &&
    value !== null &&
    (Array.isArray(value) ? value.length > 0 : Object.keys(value).length > 0);

  if (value === null || typeof value !== 'object') {
    return (
      <div className="flex flex-wrap gap-x-1 font-mono text-xs" style={{ paddingLeft: `${depth * 12}px` }}>
        {keyName !== null && (
          <>
            <span className="text-theme opacity-70">&quot;{keyName}&quot;</span>
            <span className="text-theme opacity-70">:</span>
          </>
        )}
        <ValueDisplay value={value} depth={depth} />
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries = isArray ? value.map((v, i) => [String(i), v]) : Object.entries(value);

  return (
    <div className="font-mono text-xs">
      <div
        className="flex items-start gap-x-1 cursor-pointer select-none hover:opacity-80"
        style={{ paddingLeft: `${depth * 12}px` }}
        onClick={() => isExpandable && expandAll === undefined && setExpanded((e) => !e)}
      >
        {keyName !== null && (
          <>
            <span className="text-theme opacity-70">&quot;{keyName}&quot;</span>
            <span className="text-theme opacity-70">:</span>
          </>
        )}
        <span className="text-theme">
          {isArray ? '[' : '{'}
          {entries.length > 0 && (
            <span className="text-theme-accent ml-1">
              {isExpanded ? '−' : '+'}
            </span>
          )}
          {entries.length === 0 && (
            <span className="text-theme">{isArray ? ']' : '}'}</span>
          )}
        </span>
      </div>
      {isExpanded && entries.length > 0 &&
        entries.map(([k, v]) => (
          <TreeNode
            key={k}
            keyName={isArray ? null : k}
            value={v}
            depth={depth + 1}
            defaultExpanded={defaultExpanded}
            expandAll={expandAll}
          />
        ))}
      {isExpanded && entries.length > 0 && (
        <div style={{ paddingLeft: `${depth * 12}px` }} className="text-theme">
          {isArray ? ']' : '}'}
        </div>
      )}
    </div>
  );
}

export default function JsonTree({
  data,
  defaultExpanded = false,
  maxDepth = 10,
  className = '',
  showCopy = true,
}) {
  const [copied, setCopied] = useState(false);
  const [expandAll, setExpandAll] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      const str = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
      await navigator.clipboard.writeText(str);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  }, [data]);

  let parsed;
  try {
    parsed = typeof data === 'string' ? JSON.parse(data) : data;
  } catch {
    return (
      <pre className={`bg-theme p-2 border border-theme overflow-x-auto text-xs font-mono text-theme ${className}`}>
        {String(data)}
      </pre>
    );
  }

  return (
    <div className={`bg-theme p-2 border border-theme overflow-x-auto ${className}`}>
      <div className="flex items-center justify-between gap-2 mb-1 pb-1 border-b border-theme">
        <div className="flex gap-1">
          {typeof parsed === 'object' && parsed !== null && (
            <>
              <button
                type="button"
                onClick={() => setExpandAll((e) => !e)}
                className="px-1 py-0 text-xs font-mono text-theme border border-theme hover:bg-[var(--fleuve-border-hover)]"
              >
                {expandAll ? 'collapse' : 'expand'}
              </button>
            </>
          )}
          {showCopy && (
            <button
              type="button"
              onClick={handleCopy}
              className="px-1 py-0 text-xs font-mono text-theme border border-theme hover:bg-[var(--fleuve-border-hover)]"
            >
              {copied ? '[OK]' : '[CP]'}
            </button>
          )}
        </div>
      </div>
      <div className="font-mono text-xs">
        <TreeNode
          keyName={null}
          value={parsed}
          depth={0}
          defaultExpanded={false}
          expandAll={expandAll ? true : undefined}
        />
      </div>
    </div>
  );
}
