export default function Loading({ message = '> loading...' }) {
  return (
    <div className="flex items-center justify-center p-8">
      <div className="text-center">
        <div className="inline-block font-mono text-[#00ff00] text-sm animate-pulse">
          <span className="inline-block">[</span>
          <span className="inline-block animate-pulse">...</span>
          <span className="inline-block">]</span>
        </div>
        <p className="mt-2 text-[#00ff00] font-mono text-xs">{message}</p>
      </div>
    </div>
  );
}
