/**
 * API Configuration
 * Centralizes all API endpoints and constants.
 *
 * Canonical backend (local-only Flask on :5000):
 *   - One-step search: POST /api/search (multipart 'image') -> { success, data: { results: [...] } }
 *   - /health is served at the ORIGIN root, NOT under /api.
 */

// Base URL is env-configurable. Default points at the local Flask backend.
// REACT_APP_API_URL may include or omit the trailing /api; we normalize both.
const RAW_API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

// API_BASE_URL always ends with /api. ORIGIN is API_BASE_URL minus the trailing /api.
const API_BASE_URL = RAW_API_URL.replace(/\/+$/, '').endsWith('/api')
  ? RAW_API_URL.replace(/\/+$/, '')
  : `${RAW_API_URL.replace(/\/+$/, '')}/api`;

export const ORIGIN = API_BASE_URL.replace(/\/api$/, '');

const API_TIMEOUT = 30000; // 30 seconds

export const API_ENDPOINTS = {
  SEARCH: `${API_BASE_URL}/search`,
  BATCH: `${API_BASE_URL}/batch`,
  INDEX: `${API_BASE_URL}/index`,
  RESULTS: `${API_BASE_URL}/results`,
  STATS: `${API_BASE_URL}/stats`,
  SOURCES: `${API_BASE_URL}/sources`,
  IMAGE: `${API_BASE_URL}/image`,
  // /health lives at the origin root, not under /api.
  HEALTH: `${ORIGIN}/health`,
};

/**
 * Absolute URL for a match's source image served by GET /api/image/<faiss_id>.
 * Optional helper — the backend already returns absolute thumbnail_url/image_url.
 */
export const getImageUrl = (faissId) => `${API_ENDPOINTS.IMAGE}/${faissId}`;

export const API_CONFIG = {
  BASE_URL: API_BASE_URL,
  ORIGIN,
  TIMEOUT: API_TIMEOUT,
  HEADERS: {
    'Content-Type': 'application/json',
  },
};

export const BATCH_LIMITS = {
  MAX_IMAGES: 50,
  MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB per image
  MAX_BATCH_SIZE: 500 * 1024 * 1024, // 500MB total batch
};

export const SIMILARITY_THRESHOLDS = {
  HIGH: 0.9,
  MEDIUM: 0.7,
  LOW: 0.5,
};

export const SORT_OPTIONS = {
  SIMILARITY_DESC: 'similarity_desc',
  SIMILARITY_ASC: 'similarity_asc',
  DATE_NEW: 'date_new',
  DATE_OLD: 'date_old',
  SOURCE_AZ: 'source_az',
  SOURCE_ZA: 'source_za',
};

export const SOURCE_TYPES = {
  SOCIAL_MEDIA: 'social_media',
  NEWS_SITES: 'news_sites',
  PUBLIC_DATABASES: 'public_databases',
  GOVERNMENT: 'government',
  OTHER: 'other',
};
