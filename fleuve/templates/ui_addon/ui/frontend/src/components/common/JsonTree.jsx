import { useState, useCallback, useMemo, useEffect } from 'react';

function ValueDisplay({ value }) {
  if (value === null) {
    return <span className="json-token-null">null</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="json-token-boolean">{String(value)}</span>;
  }
  if (typeof value === 'number') {
    return <span className="json-token-number">{String(value)}</span>;
  }
  if (typeof value === 'string') {
    const escaped = String(value).replace(/"/g, '\\"');
    return (
      <>
        <span className="json-token-punctuation">&quot;</span>
        <span className="json-token-string">{escaped}</span>
        <span className="json-token-punctuation">&quot;</span>
      </>
    );
  }
  return null;
}

function TreeNode({ keyName, value, depth, defaultExpanded = false, expandAll, maxDepth }) {
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
            <span className="json-token-punctuation">&quot;</span>
            <span className="json-token-key">{keyName}</span>
            <span className="json-token-punctuation">&quot;:</span>
          </>
        )}
        <ValueDisplay value={value} />
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries = isArray ? value.map((v, i) => [String(i), v]) : Object.entries(value);
  const reachedMaxDepth = depth >= maxDepth;

  if (reachedMaxDepth) {
    return (
      <div className="flex flex-wrap gap-x-1 font-mono text-xs" style={{ paddingLeft: `${depth * 12}px` }}>
        {keyName !== null && (
          <>
            <span className="json-token-punctuation">&quot;</span>
            <span className="json-token-key">{keyName}</span>
            <span className="json-token-punctuation">&quot;:</span>
          </>
        )}
        <span className="json-token-punctuation">{isArray ? '[...]' : '{...}'}</span>
      </div>
    );
  }

  return (
    <div className="font-mono text-xs">
      <div
        className="flex items-start gap-x-1 cursor-pointer select-none hover:opacity-80"
        style={{ paddingLeft: `${depth * 12}px` }}
        onClick={() => isExpandable && expandAll === undefined && setExpanded((e) => !e)}
      >
        {keyName !== null && (
          <>
            <span className="json-token-punctuation">&quot;</span>
            <span className="json-token-key">{keyName}</span>
            <span className="json-token-punctuation">&quot;:</span>
          </>
        )}
        <span className="json-token-punctuation">
          {isArray ? '[' : '{'}
          {entries.length > 0 && (
            <span className="text-theme-accent ml-1">
              {isExpanded ? '-' : '+'}
            </span>
          )}
          {entries.length === 0 && (
            <span className="json-token-punctuation">{isArray ? ']' : '}'}</span>
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
            maxDepth={maxDepth}
          />
        ))}
      {isExpanded && entries.length > 0 && (
        <div style={{ paddingLeft: `${depth * 12}px` }} className="json-token-punctuation">
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
  previewLineLimit = 10,
}) {
  const [copied, setCopied] = useState(false);
  const [expandAll, setExpandAll] = useState(false);

  const rawJson = useMemo(() => {
    if (typeof data === 'string') {
      return data;
    }
    try {
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  }, [data]);
  const rawJsonLines = useMemo(() => rawJson.split('\n'), [rawJson]);
  const exceedsPreviewLimit = rawJsonLines.length > previewLineLimit;
  const [isExpanded, setIsExpanded] = useState(defaultExpanded || !exceedsPreviewLimit);

  useEffect(() => {
    setIsExpanded(defaultExpanded || !exceedsPreviewLimit);
    setExpandAll(false);
  }, [defaultExpanded, exceedsPreviewLimit, rawJson]);

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
          {exceedsPreviewLimit && (
            <button
              type="button"
              onClick={() => setIsExpanded((expanded) => !expanded)}
              className="px-1 py-0 text-xs font-mono text-theme border border-theme hover:bg-[var(--fleuve-border-hover)]"
            >
              {isExpanded ? 'preview' : 'expand'}
            </button>
          )}
          {typeof parsed === 'object' && parsed !== null && (
            <>
              <button
                type="button"
                onClick={() => setExpandAll((e) => !e)}
                disabled={!isExpanded}
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
      {!isExpanded && exceedsPreviewLimit ? (
        <pre
          className="font-mono text-xs text-theme cursor-pointer"
          onClick={() => setIsExpanded(true)}
          title="Click to expand"
        >
          {rawJsonLines.slice(0, previewLineLimit).join('\n')}
        </pre>
      ) : (
        <div className="font-mono text-xs">
          <TreeNode
            keyName={null}
            value={parsed}
            depth={0}
            defaultExpanded={true}
            expandAll={expandAll ? true : undefined}
            maxDepth={maxDepth}
          />
        </div>
      )}
    </div>
  );
}
