/**
 * Main App Component
 * Orchestrates all OSINT search functionality
 */

import React, { useState, useEffect, useCallback } from 'react';
import ImageUploader from './components/ImageUploader/ImageUploader';
import SearchResults from './components/SearchResults/SearchResults';
import FilterBar from './components/FilterBar/FilterBar';
import SortControls from './components/SortControls/SortControls';
import BatchProcessor from './components/BatchProcessor/BatchProcessor';
import apiClient, { APIError } from './services/apiClient';
import { SORT_OPTIONS } from './config/api';
import './App.css';

function App() {
  const [results, setResults] = useState([]);
  const [sortedResults, setSortedResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [currentSort, setCurrentSort] = useState(SORT_OPTIONS.SIMILARITY_DESC);
  const [filters, setFilters] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [appError, setAppError] = useState(null);
  const [activeTab, setActiveTab] = useState('single');

  // Health check on mount
  useEffect(() => {
    checkApiHealth();
  }, []);

  const checkApiHealth = async () => {
    try {
      await apiClient.healthCheck();
    } catch (error) {
      const errorMessage =
        error instanceof APIError ? error.message : 'API connection failed';
      setAppError(errorMessage);
    }
  };

  // Sort results when they change or sort method changes
  useEffect(() => {
    setSortedResults(sortResultsData(results, currentSort));
  }, [results, currentSort]);

  const sortResultsData = useCallback((data, sortMethod) => {
    if (!data || data.length === 0) return [];

    const sorted = [...data];

    switch (sortMethod) {
      case SORT_OPTIONS.SIMILARITY_DESC:
        return sorted.sort((a, b) => b.similarity - a.similarity);
      case SORT_OPTIONS.SIMILARITY_ASC:
        return sorted.sort((a, b) => a.similarity - b.similarity);
      case SORT_OPTIONS.DATE_NEW:
        return sorted.sort(
          (a, b) =>
            new Date(b.metadata?.date || 0) -
            new Date(a.metadata?.date || 0)
        );
      case SORT_OPTIONS.DATE_OLD:
        return sorted.sort(
          (a, b) =>
            new Date(a.metadata?.date || 0) -
            new Date(b.metadata?.date || 0)
        );
      case SORT_OPTIONS.SOURCE_AZ:
        return sorted.sort((a, b) => a.source.localeCompare(b.source));
      case SORT_OPTIONS.SOURCE_ZA:
        return sorted.sort((a, b) => b.source.localeCompare(a.source));
      default:
        return sorted;
    }
  }, []);

  const handleImageUploadSuccess = useCallback((uploadData) => {
    // One-step flow: the uploaded image IS the query, so the ranked matches
    // are already present at uploadData.results (response.data.results).
    setSearchError(null);
    setIsSearching(false);
    setResults(Array.isArray(uploadData?.results) ? uploadData.results : []);
  }, []);

  const handleImageUploadError = useCallback((error) => {
    setSearchError(error);
    setResults([]);
  }, []);

  const handleBatchUploadSuccess = useCallback((uploadData) => {
    // One-step flow: /api/batch already returns per-image matches.
    // Flatten data.results[].matches into a single ranked list.
    setSearchError(null);
    setIsSearching(false);

    const perImage = Array.isArray(uploadData?.results)
      ? uploadData.results
      : [];
    const allMatches = perImage.reduce(
      (acc, image) =>
        Array.isArray(image?.matches) ? [...acc, ...image.matches] : acc,
      []
    );
    setResults(allMatches);
  }, []);

  const handleBatchUploadError = useCallback((error) => {
    setSearchError(error);
    setResults([]);
  }, []);

  const handleFiltersChange = useCallback((newFilters) => {
    // One-step backend has no stateful re-query; the image IS the query.
    // Source/threshold filtering is applied server-side at upload time, so
    // here we just record the selection (re-upload to apply server filters).
    setFilters(newFilters);
  }, []);

  const handleSortChange = useCallback((newSort) => {
    setCurrentSort(newSort);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <h1>OSINT Face Search</h1>
          <p>Advanced facial recognition and image matching</p>
        </div>
        {appError && (
          <div className="connection-error" role="alert">
            {appError}
          </div>
        )}
      </header>

      <main className="app-main">
        <div className="tabs">
          <button
            className={`tab-button ${activeTab === 'single' ? 'active' : ''}`}
            onClick={() => setActiveTab('single')}
            aria-selected={activeTab === 'single'}
            aria-label="Single image search"
          >
            Single Image
          </button>
          <button
            className={`tab-button ${activeTab === 'batch' ? 'active' : ''}`}
            onClick={() => setActiveTab('batch')}
            aria-selected={activeTab === 'batch'}
            aria-label="Batch image search"
          >
            Batch Upload
          </button>
        </div>

        <div className="tab-content">
          {activeTab === 'single' && (
            <div className="single-search-container">
              <ImageUploader
                onUploadSuccess={handleImageUploadSuccess}
                onUploadError={handleImageUploadError}
                onLoading={setIsLoading}
              />

              {results.length > 0 && (
                <div className="results-controls">
                  <FilterBar
                    onFiltersChange={handleFiltersChange}
                    onLoading={setIsLoading}
                  />
                  <SortControls
                    currentSort={currentSort}
                    onSortChange={handleSortChange}
                  />
                </div>
              )}

              <SearchResults
                results={sortedResults}
                loading={isSearching || isLoading}
                error={searchError}
              />
            </div>
          )}

          {activeTab === 'batch' && (
            <div className="batch-search-container">
              <BatchProcessor
                onBatchSuccess={handleBatchUploadSuccess}
                onBatchError={handleBatchUploadError}
                onLoading={setIsLoading}
              />

              {results.length > 0 && (
                <div className="results-controls">
                  <FilterBar
                    onFiltersChange={handleFiltersChange}
                    onLoading={setIsLoading}
                  />
                  <SortControls
                    currentSort={currentSort}
                    onSortChange={handleSortChange}
                  />
                </div>
              )}

              <SearchResults
                results={sortedResults}
                loading={isSearching || isLoading}
                error={searchError}
              />
            </div>
          )}
        </div>
      </main>

      <footer className="app-footer">
        <p>OSINT Face Search &copy; 2024. All rights reserved.</p>
      </footer>
    </div>
  );
}

export default App;
