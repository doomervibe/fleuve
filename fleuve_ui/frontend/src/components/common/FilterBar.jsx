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
    <div className="filter-bar">
      <div className="filter-bar-grid">
        {filters && Object.keys(filters).map((key) => (
          <div key={key} className="filter-bar-field">
            <label className="stat-label">
              {key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, '_')}:
            </label>
            <input
              type="text"
              value={localFilters[key] || ''}
              onChange={(e) => handleChange(key, e.target.value)}
              placeholder={`filter by ${key}`}
              className="search-input"
            />
          </div>
        ))}
        <div className="filter-bar-actions">
          <button
            onClick={handleClear}
            className="refresh-btn"
          >
            clear
          </button>
        </div>
      </div>
    </div>
  );
}
