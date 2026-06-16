/**
 * API Client Service
 * Handles all API requests with error handling and request/response management
 */

import { API_ENDPOINTS, API_CONFIG } from '../config/api';

class APIClient {
  /**
   * Make a fetch request with timeout and error handling
   */
  async request(url, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          ...API_CONFIG.HEADERS,
          ...options.headers,
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new APIError(
          `HTTP ${response.status}: ${response.statusText}`,
          response.status,
          response
        );
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof APIError) {
        throw error;
      }

      if (error.name === 'AbortError') {
        throw new APIError('Request timeout', 408);
      }

      throw new APIError(
        error.message || 'Network request failed',
        null,
        error
      );
    }
  }

  /**
   * Upload image(s) for face search
   */
  async uploadImage(file) {
    const formData = new FormData();
    formData.append('image', file);

    return this.request(API_ENDPOINTS.UPLOAD, {
      method: 'POST',
      body: formData,
      headers: {}, // Remove Content-Type to allow browser to set multipart/form-data
    });
  }

  /**
   * Upload multiple images for batch processing
   */
  async uploadBatch(files) {
    const formData = new FormData();
    files.forEach((file, index) => {
      formData.append(`images`, file);
    });

    return this.request(API_ENDPOINTS.UPLOAD, {
      method: 'POST',
      body: formData,
      headers: {},
    });
  }

  /**
   * Search for matches by image
   */
  async searchImage(imageId, filters = {}) {
    const params = new URLSearchParams();
    params.append('image_id', imageId);

    if (filters.similarity_threshold) {
      params.append('similarity_threshold', filters.similarity_threshold);
    }
    if (filters.sources && filters.sources.length) {
      filters.sources.forEach(source => {
        params.append('sources', source);
      });
    }

    return this.request(`${API_ENDPOINTS.SEARCH}?${params.toString()}`, {
      method: 'GET',
    });
  }

  /**
   * Batch search multiple images
   */
  async searchBatch(imageIds, filters = {}) {
    const body = {
      image_ids: imageIds,
      ...filters,
    };

    return this.request(API_ENDPOINTS.SEARCH_BATCH, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  /**
   * Get search results
   */
  async getResults(searchId) {
    return this.request(`${API_ENDPOINTS.RESULTS}/${searchId}`, {
      method: 'GET',
    });
  }

  /**
   * Get available sources/websites for filtering
   */
  async getSources() {
    return this.request(API_ENDPOINTS.SOURCES, {
      method: 'GET',
    });
  }

  /**
   * Health check
   */
  async healthCheck() {
    return this.request(API_ENDPOINTS.HEALTH, {
      method: 'GET',
    });
  }
}

/**
 * Custom API Error class
 */
export class APIError extends Error {
  constructor(message, status = null, originalError = null) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.originalError = originalError;
  }
}

export default new APIClient();
