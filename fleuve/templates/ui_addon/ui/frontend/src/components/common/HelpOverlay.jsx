export default function HelpOverlay({ shortcuts, onClose, open }) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80"
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        className="bg-theme border border-theme p-4 max-w-md w-full mx-2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-mono text-theme">keyboard_shortcuts</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-theme hover:text-theme-accent font-mono text-xs border border-theme px-1 py-0"
          >
            [X]
          </button>
        </div>
        <div className="space-y-2 font-mono text-xs">
          {shortcuts.map((s) => (
            <div key={s.keys} className="flex justify-between gap-4">
              <kbd className="px-1 py-0 border border-theme text-theme-accent">{s.keys}</kbd>
              <span className="text-theme opacity-90">{s.label}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs font-mono text-theme opacity-50">
          Press ? to close
        </p>
      </div>
    </div>
  );
}
