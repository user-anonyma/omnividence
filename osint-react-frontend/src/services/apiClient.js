/**
 * API Client Service
 * Handles all API requests with timeout + error handling.
 *
 * The backend uses a ONE-STEP search flow: the uploaded image IS the query.
 *   uploadImage(file) -> POST multipart 'image' to /api/search
 *   The ranked matches are already at response.data.results (flat array).
 *
 * Standard envelope: { success, message, data, timestamp }.
 */

import { API_ENDPOINTS, API_CONFIG, getImageUrl } from '../config/api';

class APIClient {
  /**
   * Make a fetch request with timeout and error handling.
   * For multipart bodies (FormData) pass headers:{} so the browser sets the
   * Content-Type boundary itself; otherwise JSON headers are applied.
   */
  async request(url, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);

    const isFormData = options.body instanceof FormData;

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: isFormData
          ? { ...options.headers }
          : { ...API_CONFIG.HEADERS, ...options.headers },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        // Try to surface a structured backend error message if present.
        let message = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const body = await response.json();
          if (body && body.error) {
            message = body.error;
          }
        } catch (_) {
          // non-JSON error body; keep the status-based message
        }
        throw new APIError(message, response.status, response);
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

      throw new APIError(error.message || 'Network request failed', null, error);
    }
  }

  /**
   * One-step face search. Uploads the image and returns the parsed envelope;
   * the caller reads the ranked matches at response.data.results.
   *
   * @param {File} file
   * @param {{threshold?:number, top_k?:number, detect?:boolean, sources?:string[]}} [options]
   */
  async uploadImage(file, options = {}) {
    const formData = new FormData();
    formData.append('image', file);

    if (options.threshold != null) {
      formData.append('threshold', options.threshold);
    }
    if (options.top_k != null) {
      formData.append('top_k', options.top_k);
    }
    if (options.detect) {
      formData.append('detect', 'true');
    }
    if (options.sources && options.sources.length) {
      options.sources.forEach((source) => formData.append('sources', source));
    }

    return this.request(API_ENDPOINTS.SEARCH, {
      method: 'POST',
      body: formData,
      headers: {}, // let the browser set multipart/form-data boundary
    });
  }

  /**
   * Batch process multiple images. POSTs repeatable 'images' to /api/batch.
   *
   * @param {File[]} files
   * @param {{threshold?:number, top_k?:number}} [options]
   */
  async uploadBatch(files, options = {}) {
    const formData = new FormData();
    files.forEach((file) => formData.append('images', file));

    if (options.threshold != null) {
      formData.append('threshold', options.threshold);
    }
    if (options.top_k != null) {
      formData.append('top_k', options.top_k);
    }

    return this.request(API_ENDPOINTS.BATCH, {
      method: 'POST',
      body: formData,
      headers: {},
    });
  }

  // ---- Backwards-compatible aliases (one-step flow) -----------------------
  // The legacy two-step flow (uploadImage -> image_id -> searchImage) is gone.
  // These aliases keep older callers working: the image IS the query.

  /** @deprecated use uploadImage — kept as a one-step alias. */
  async searchImage(file, options = {}) {
    return this.uploadImage(file, options);
  }

  /** @deprecated use uploadBatch — kept as a one-step alias. */
  async searchBatch(files, options = {}) {
    return this.uploadBatch(files, options);
  }

  /**
   * Fetch a cached prior search/batch result by request_id.
   */
  async getResults(requestId) {
    return this.request(`${API_ENDPOINTS.RESULTS}/${requestId}`, {
      method: 'GET',
    });
  }

  /**
   * Index statistics (index_size, total_faces, embedding_dim, ...).
   */
  async getStats() {
    return this.request(API_ENDPOINTS.STATS, {
      method: 'GET',
    });
  }

  /**
   * Available source buckets for filtering -> [{ value, label, count }].
   */
  async getSources() {
    return this.request(API_ENDPOINTS.SOURCES, {
      method: 'GET',
    });
  }

  /**
   * Liveness + component readiness. Hits /health at the origin root.
   */
  async healthCheck() {
    return this.request(API_ENDPOINTS.HEALTH, {
      method: 'GET',
    });
  }

  /**
   * Absolute URL for a match's source image (GET /api/image/<faiss_id>).
   * Backend already returns absolute thumbnail_url/image_url; this is a helper.
   */
  getImageUrl(faissId) {
    return getImageUrl(faissId);
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
