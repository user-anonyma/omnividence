/**
 * FilterBar Component
 * Filter search results by source and other criteria
 * Accessible and responsive
 */

import React, { useState, useEffect } from 'react';
import apiClient, { APIError } from '../../services/apiClient';
import './FilterBar.css';

export const FilterBar = ({ onFiltersChange, onLoading = null }) => {
  const [sources, setSources] = useState([]);
  const [selectedSources, setSelectedSources] = useState([]);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.5);
  const [loadingSourcesState, setLoadingSourcesState] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSources();
  }, []);

  const fetchSources = async () => {
    setLoadingSourcesState(true);
    setError(null);
    try {
      const response = await apiClient.getSources();
      if (response.success && response.data) {
        setSources(response.data);
      } else {
        throw new Error('Failed to load sources');
      }
    } catch (err) {
      const errorMessage =
        err instanceof APIError ? err.message : err.message;
      setError(errorMessage);
    } finally {
      setLoadingSourcesState(false);
      onLoading?.(false);
    }
  };

  const handleSourceToggle = (source) => {
    const updated = selectedSources.includes(source)
      ? selectedSources.filter((s) => s !== source)
      : [...selectedSources, source];

    setSelectedSources(updated);
    notifyChanges(updated, similarityThreshold);
  };

  const handleSimilarityChange = (value) => {
    const numValue = parseFloat(value);
    setSimilarityThreshold(numValue);
    notifyChanges(selectedSources, numValue);
  };

  const handleClearFilters = () => {
    setSelectedSources([]);
    setSimilarityThreshold(0.5);
    notifyChanges([], 0.5);
  };

  const notifyChanges = (sources, threshold) => {
    onFiltersChange?.({
      sources,
      similarity_threshold: threshold,
    });
  };

  const isFilterActive = selectedSources.length > 0 || similarityThreshold > 0.5;

  return (
    <div className="filter-bar">
      <div className="filter-section">
        <h3 className="filter-title">Filters</h3>

        {error && (
          <div className="filter-error" role="alert">
            {error}
          </div>
        )}

        {/* Similarity Threshold Filter */}
        <div className="filter-group">
          <label htmlFor="similarity-slider" className="filter-label">
            Minimum Similarity
          </label>
          <div className="slider-container">
            <input
              id="similarity-slider"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={similarityThreshold}
              onChange={(e) => handleSimilarityChange(e.target.value)}
              className="slider"
              aria-label="Minimum similarity threshold"
            />
            <span className="slider-value">
              {(similarityThreshold * 100).toFixed(0)}%
            </span>
          </div>
        </div>

        {/* Sources Filter */}
        <div className="filter-group">
          <label className="filter-label">Sources</label>
          {loadingSourcesState ? (
            <div className="loading-sources">Loading sources...</div>
          ) : sources.length > 0 ? (
            <div className="checkbox-group">
              {sources.map((source) => (
                <div key={source.value} className="checkbox-item">
                  <input
                    type="checkbox"
                    id={`source-${source.value}`}
                    checked={selectedSources.includes(source.value)}
                    onChange={() => handleSourceToggle(source.value)}
                    className="checkbox-input"
                    aria-label={`Filter by ${source.label}`}
                  />
                  <label htmlFor={`source-${source.value}`} className="checkbox-label">
                    <span className="source-name">{source.label}</span>
                    {source.count !== undefined && (
                      <span className="source-count">({source.count})</span>
                    )}
                  </label>
                </div>
              ))}
            </div>
          ) : (
            <p className="no-sources">No sources available</p>
          )}
        </div>

        {/* Clear Filters Button */}
        {isFilterActive && (
          <button
            className="clear-filters-button"
            onClick={handleClearFilters}
            aria-label="Clear all filters"
          >
            Clear Filters
          </button>
        )}
      </div>

      {/* Active Filters Summary */}
      {isFilterActive && (
        <div className="active-filters" role="region" aria-label="Active filters">
          <h4>Active Filters</h4>
          <div className="filter-tags">
            {similarityThreshold > 0.5 && (
              <span className="filter-tag">
                Similarity {(similarityThreshold * 100).toFixed(0)}%+
              </span>
            )}
            {selectedSources.map((sourceValue) => {
              const source = sources.find((s) => s.value === sourceValue);
              return source ? (
                <span key={sourceValue} className="filter-tag">
                  {source.label}
                </span>
              ) : null;
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default FilterBar;
