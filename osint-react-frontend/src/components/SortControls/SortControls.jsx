/**
 * SortControls Component
 * Sort search results by various criteria
 * Accessible and responsive
 */

import React from 'react';
import { SORT_OPTIONS } from '../../config/api';
import './SortControls.css';

export const SortControls = ({ currentSort = SORT_OPTIONS.SIMILARITY_DESC, onSortChange }) => {
  const sortOptions = [
    { value: SORT_OPTIONS.SIMILARITY_DESC, label: 'Highest Similarity' },
    { value: SORT_OPTIONS.SIMILARITY_ASC, label: 'Lowest Similarity' },
    { value: SORT_OPTIONS.DATE_NEW, label: 'Newest First' },
    { value: SORT_OPTIONS.DATE_OLD, label: 'Oldest First' },
    { value: SORT_OPTIONS.SOURCE_AZ, label: 'Source (A-Z)' },
    { value: SORT_OPTIONS.SOURCE_ZA, label: 'Source (Z-A)' },
  ];

  return (
    <div className="sort-controls">
      <label htmlFor="sort-select" className="sort-label">
        Sort by:
      </label>
      <select
        id="sort-select"
        value={currentSort}
        onChange={(e) => onSortChange?.(e.target.value)}
        className="sort-select"
        aria-label="Sort search results"
      >
        {sortOptions.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
};

export default SortControls;
