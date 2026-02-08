export default function Error({ error, onRetry }) {
  return (
    <div className="bg-black border border-[#ff0000] p-2">
      <div className="flex">
        <div className="flex-shrink-0">
          <span className="text-[#ff0000] font-mono text-sm">[ERROR]</span>
        </div>
        <div className="ml-2">
          <h3 className="text-xs font-mono text-[#ff0000]">error</h3>
          <div className="mt-0 text-xs font-mono text-[#ff0000] opacity-80">
            <p>{error?.message || 'an error occurred'}</p>
          </div>
          {onRetry && (
            <div className="mt-2">
              <button
                onClick={onRetry}
                className="bg-black border border-[#ff0000] text-[#ff0000] px-2 py-1 text-xs font-mono hover:bg-[#330000]"
              >
                retry
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
