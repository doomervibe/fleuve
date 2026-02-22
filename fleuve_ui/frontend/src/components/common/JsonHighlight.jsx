import CopyButton from './CopyButton';

/**
 * Lightweight JSON syntax highlighter.
 * Renders JSON with colored tokens (keys, strings, numbers, booleans, null).
 */

export default function JsonHighlight({ data, className = '', copyable }) {
  if (data == null) return <pre className={`json-highlight ${className}`}><code>null</code></pre>;
  const str = typeof data === 'string' ? data : JSON.stringify(data, null, 2);

  const tokens = [];
  let i = 0;

  const patterns = [
    { regex: /^\s+/, type: 'whitespace' },
    { regex: /^"(?:[^"\\]|\\.)*"(?=\s*:)/, type: 'key' },
    { regex: /^"(?:[^"\\]|\\.)*"/, type: 'string' },
    { regex: /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/, type: 'number' },
    { regex: /^(true|false)\b/, type: 'boolean' },
    { regex: /^null\b/, type: 'null' },
    { regex: /^[{}\[\],:]/, type: 'punctuation' },
  ];

  while (i < str.length) {
    let matched = false;
    for (const { regex, type } of patterns) {
      const m = str.slice(i).match(regex);
      if (m) {
        tokens.push({ type, value: m[0] });
        i += m[0].length;
        matched = true;
        break;
      }
    }
    if (!matched) {
      tokens.push({ type: 'plain', value: str[i] });
      i++;
    }
  }

  return (
    <div className={`json-highlight-wrap ${copyable ? 'json-highlight-wrap--copyable' : ''}`}>
      {copyable && (
        <div className="json-highlight-actions">
          <CopyButton text={str} label="copy json" title="copy raw json" />
        </div>
      )}
      <pre className={`json-highlight ${className}`}>
        <code>
          {tokens.map((t, idx) => (
            <span key={idx} className={`json-token json-token-${t.type}`}>
              {t.value}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
