/**
 * SearchResults Component
 * Grid display of matched faces with metadata
 * Accessible and responsive
 */

import React, { useState, useMemo } from 'react';
import './SearchResults.css';

export const SearchResults = ({ results = [], loading = false, error = null }) => {
  const [selectedResult, setSelectedResult] = useState(null);

  if (error) {
    return (
      <div className="search-results" role="region" aria-label="Search results">
        <div className="error-state" role="alert">
          <p className="error-title">Error Loading Results</p>
          <p className="error-message">{error}</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="search-results" role="region" aria-label="Search results">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Searching for matches...</p>
        </div>
      </div>
    );
  }

  if (!results || results.length === 0) {
    return (
      <div className="search-results" role="region" aria-label="Search results">
        <div className="empty-state">
          <p>No results yet. Upload an image to get started.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="search-results" role="region" aria-label="Search results">
      <div className="results-header">
        <h2>Found {results.length} match{results.length !== 1 ? 'es' : ''}</h2>
      </div>

      <div className="results-grid">
        {results.map((result, index) => (
          <SearchResultCard
            key={result.id || index}
            result={result}
            isSelected={selectedResult?.id === result.id}
            onSelect={() => setSelectedResult(result)}
          />
        ))}
      </div>

      {selectedResult && (
        <ResultDetailModal
          result={selectedResult}
          onClose={() => setSelectedResult(null)}
        />
      )}
    </div>
  );
};

/**
 * Individual search result card
 */
const SearchResultCard = ({ result, isSelected, onSelect }) => {
  return (
    <div
      className={`result-card ${isSelected ? 'selected' : ''}`}
      onClick={onSelect}
      role="button"
      tabIndex="0"
      aria-label={`Result: ${result.source} with ${(result.similarity * 100).toFixed(1)}% similarity`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onSelect();
        }
      }}
    >
      <div className="card-thumbnail">
        <img
          src={result.thumbnail_url}
          alt={`Match from ${result.source}`}
          className="thumbnail-image"
          loading="lazy"
        />
      </div>

      <div className="card-content">
        <div className="similarity-badge">
          <span className="similarity-value">
            {(result.similarity * 100).toFixed(1)}%
          </span>
          <span className="similarity-label">Similarity</span>
        </div>

        <div className="source-info">
          <p className="source-name">{result.source}</p>
          <p className="source-type">{result.source_type}</p>
        </div>

        <a
          href={result.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="visit-link"
          aria-label={`Visit original on ${result.source}`}
        >
          View Original
        </a>
      </div>
    </div>
  );
};

/**
 * Detailed view modal for selected result
 */
const ResultDetailModal = ({ result, onClose }) => {
  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Result details"
    >
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="modal-close"
          onClick={onClose}
          aria-label="Close modal"
        >
          &times;
        </button>

        <div className="modal-body">
          <div className="modal-image-container">
            <img
              src={result.image_url}
              alt={`Full image from ${result.source}`}
              className="modal-image"
            />
          </div>

          <div className="modal-info">
            <div className="info-section">
              <h3>Match Details</h3>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">Similarity</span>
                  <span className="info-value">
                    {(result.similarity * 100).toFixed(2)}%
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">Source</span>
                  <span className="info-value">{result.source}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Type</span>
                  <span className="info-value">{result.source_type}</span>
                </div>
                {result.metadata?.date && (
                  <div className="info-item">
                    <span className="info-label">Date</span>
                    <span className="info-value">
                      {new Date(result.metadata.date).toLocaleDateString()}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {result.metadata?.description && (
              <div className="info-section">
                <h3>Description</h3>
                <p className="description-text">{result.metadata.description}</p>
              </div>
            )}

            {result.metadata?.tags && result.metadata.tags.length > 0 && (
              <div className="info-section">
                <h3>Tags</h3>
                <div className="tags-container">
                  {result.metadata.tags.map((tag, index) => (
                    <span key={index} className="tag">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="info-section">
              <a
                href={result.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="primary-button"
              >
                Open in {result.source}
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SearchResults;
