function simpleLineDiff(str1, str2) {
  const lines1 = str1.split('\n');
  const lines2 = str2.split('\n');
  const result = [];
  let i = 0;
  let j = 0;
  while (i < lines1.length || j < lines2.length) {
    if (i < lines1.length && j < lines2.length && lines1[i] === lines2[j]) {
      result.push({ type: 'unchanged', value: lines1[i] });
      i++;
      j++;
    } else if (j < lines2.length && (i >= lines1.length || !lines1.slice(i).includes(lines2[j]))) {
      result.push({ type: 'added', value: lines2[j] });
      j++;
    } else if (i < lines1.length && (j >= lines2.length || !lines2.slice(j).includes(lines1[i]))) {
      result.push({ type: 'removed', value: lines1[i] });
      i++;
    } else if (i < lines1.length && j < lines2.length) {
      result.push({ type: 'removed', value: lines1[i] });
      result.push({ type: 'added', value: lines2[j] });
      i++;
      j++;
    } else if (i < lines1.length) {
      result.push({ type: 'removed', value: lines1[i] });
      i++;
    } else {
      result.push({ type: 'added', value: lines2[j] });
      j++;
    }
  }
  return result;
}

export default function StateDiff({ stateV1, stateV2, label1 = 'v1', label2 = 'v2' }) {
  const str1 = JSON.stringify(stateV1, null, 2);
  const str2 = JSON.stringify(stateV2, null, 2);
  const changes = simpleLineDiff(str1, str2);

  return (
    <div className="font-mono text-xs overflow-x-auto">
      <div className="flex gap-2 mb-1">
        <span className="text-theme-error">− {label1}</span>
        <span className="text-theme-accent">+ {label2}</span>
      </div>
      <pre className="bg-theme p-2 border border-theme overflow-x-auto">
        {changes.map((part, idx) => {
          if (part.type === 'added') {
            return (
              <span key={idx} className="bg-[color:rgba(0,255,0,0.2)] text-theme-accent block">
                +{part.value}
                {'\n'}
              </span>
            );
          }
          if (part.type === 'removed') {
            return (
              <span key={idx} className="bg-[color:rgba(255,0,0,0.2)] text-theme-error block">
                −{part.value}
                {'\n'}
              </span>
            );
          }
          return (
            <span key={idx} className="text-theme">
              {part.value}
              {'\n'}
            </span>
          );
        })}
      </pre>
    </div>
  );
}
