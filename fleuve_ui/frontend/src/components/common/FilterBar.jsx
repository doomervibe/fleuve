import { useState } from 'react';

export default function FilterBar({ filters, onFilterChange }) {
  const [localFilters, setLocalFilters] = useState(filters || {});

  const handleChange = (key, value) => {
    const newFilters = { ...localFilters, [key]: value };
    setLocalFilters(newFilters);
    onFilterChange(newFilters);
  };

  const handleClear = () => {
    const cleared = {};
    setLocalFilters(cleared);
    onFilterChange(cleared);
  };

  return (
    <div className="p-2 mb-1">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
        {filters && Object.keys(filters).map((key) => (
          <div key={key}>
            <label className="block text-xs font-mono mb-0 stat-label">
              {key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, '_')}:
            </label>
            <input
              type="text"
              value={localFilters[key] || ''}
              onChange={(e) => handleChange(key, e.target.value)}
              placeholder={`filter by ${key}`}
              className="w-full px-2 py-1 search-input text-xs font-mono"
            />
          </div>
        ))}
        <div className="flex items-end">
          <button
            onClick={handleClear}
            className="px-2 py-1 refresh-btn text-xs font-mono"
          >
            clear
          </button>
        </div>
      </div>
    </div>
  );
}
