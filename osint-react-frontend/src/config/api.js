/**
 * API Configuration
 * Centralizes all API endpoints and constants
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';
const API_TIMEOUT = 30000; // 30 seconds

export const API_ENDPOINTS = {
  SEARCH: `${API_BASE_URL}/search`,
  SEARCH_BATCH: `${API_BASE_URL}/search/batch`,
  UPLOAD: `${API_BASE_URL}/upload`,
  RESULTS: `${API_BASE_URL}/results`,
  SOURCES: `${API_BASE_URL}/sources`,
  HEALTH: `${API_BASE_URL}/health`,
};

export const API_CONFIG = {
  BASE_URL: API_BASE_URL,
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
