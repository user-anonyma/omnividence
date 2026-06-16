# API Integration Guide

Complete guide for integrating the React frontend with the Flask backend API.

## Overview

The React frontend communicates with the Flask backend through REST API calls. This guide covers the integration points and expected data formats.

## API Base URL

Set in `src/config/api.js` and environment variables:

```javascript
// src/config/api.js
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

// .env
REACT_APP_API_URL=http://localhost:5000/api
```

## Endpoints Reference

### 1. Upload Image

**Endpoint:** `POST /api/upload`

**Purpose:** Upload a single or multiple images

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body:
  ```
  image: File (single image upload)
  images: File[] (batch upload)
  ```

**Response (Success):**
```json
{
  "success": true,
  "data": {
    "image_id": "uuid-string",
    "thumbnail_url": "https://example.com/thumb.jpg",
    "uploaded_count": 1
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "File size exceeds limit"
}
```

**Implementation in Frontend:**
```javascript
// Single image
const response = await apiClient.uploadImage(file);

// Multiple images
const response = await apiClient.uploadBatch(files);
```

### 2. Search Image

**Endpoint:** `GET /api/search?image_id=<id>&similarity_threshold=<0-1>&sources=<source1>&sources=<source2>`

**Purpose:** Search for matches of an uploaded image

**Request:**
- Method: GET
- Query Parameters:
  - `image_id` (required): UUID of uploaded image
  - `similarity_threshold` (optional): 0-1, default 0.5
  - `sources` (optional): Source IDs (repeat for multiple)

**Response (Success):**
```json
{
  "success": true,
  "data": [
    {
      "id": "result-uuid",
      "image_url": "https://source.com/image.jpg",
      "thumbnail_url": "https://source.com/thumb.jpg",
      "similarity": 0.95,
      "source": "Facebook",
      "source_type": "social_media",
      "source_url": "https://facebook.com/profile/123",
      "metadata": {
        "date": "2024-01-15T10:30:00Z",
        "description": "Profile picture from 2024",
        "tags": ["profile", "verified"]
      }
    }
  ]
}
```

**Implementation in Frontend:**
```javascript
const results = await apiClient.searchImage('image-id-123', {
  similarity_threshold: 0.7,
  sources: ['facebook', 'twitter']
});
```

### 3. Batch Search

**Endpoint:** `POST /api/search/batch`

**Purpose:** Search multiple images concurrently

**Request:**
- Method: POST
- Content-Type: application/json
- Body:
  ```json
  {
    "image_ids": ["id1", "id2", "id3"],
    "similarity_threshold": 0.7,
    "sources": ["facebook", "twitter"]
  }
  ```

**Response (Success):**
```json
{
  "success": true,
  "data": [
    {
      "image_id": "id1",
      "matches": [
        {
          "id": "result-uuid",
          "image_url": "...",
          "similarity": 0.95,
          ...
        }
      ]
    },
    {
      "image_id": "id2",
      "matches": [...]
    }
  ]
}
```

**Implementation in Frontend:**
```javascript
const batchResults = await apiClient.searchBatch(['id1', 'id2'], {
  similarity_threshold: 0.7,
  sources: ['facebook']
});
```

### 4. Get Results

**Endpoint:** `GET /api/results/<search_id>`

**Purpose:** Retrieve search results by ID (optional endpoint)

**Request:**
- Method: GET
- URL Parameter: `search_id`

**Response:**
```json
{
  "success": true,
  "data": [...]
}
```

### 5. Get Sources

**Endpoint:** `GET /api/sources`

**Purpose:** Get available data sources for filtering

**Request:**
- Method: GET
- No parameters

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "facebook",
      "name": "Facebook",
      "type": "social_media",
      "count": 5000
    },
    {
      "id": "twitter",
      "name": "Twitter",
      "type": "social_media",
      "count": 3200
    },
    {
      "id": "linkedin",
      "name": "LinkedIn",
      "type": "professional",
      "count": 2100
    }
  ]
}
```

**Implementation in Frontend:**
```javascript
const sources = await apiClient.getSources();
```

### 6. Health Check

**Endpoint:** `GET /api/health`

**Purpose:** Check API availability

**Request:**
- Method: GET
- No parameters

**Response:**
```json
{
  "success": true,
  "status": "healthy",
  "version": "1.0.0"
}
```

**Implementation in Frontend:**
```javascript
await apiClient.healthCheck();
```

## Data Models

### SearchResult

```typescript
interface SearchResult {
  id: string                    // Unique result ID
  image_url: string             // Full size image URL
  thumbnail_url: string         // Thumbnail image URL
  similarity: number            // 0-1 similarity score
  source: string                // Source name (Facebook, Twitter, etc)
  source_type: string           // Type (social_media, news, etc)
  source_url: string            // URL to original source
  metadata?: {
    date?: string               // ISO 8601 date string
    description?: string        // Optional description
    tags?: string[]             // Optional tags
  }
}
```

### Source

```typescript
interface Source {
  id: string                    // Source ID (unique identifier)
  name: string                  // Display name
  type?: string                 // Source type
  count?: number                // Number of records from this source
}
```

### UploadResponse

```typescript
interface UploadResponse {
  success: boolean
  data: {
    image_id: string            // ID for uploaded image
    thumbnail_url?: string      // Optional thumbnail
    uploaded_count?: number     // For batch uploads
  }
  error?: string                // Error message if unsuccessful
}
```

## Error Handling

### HTTP Status Codes

- `200` - Success
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (authentication required)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `413` - Payload Too Large
- `500` - Internal Server Error
- `503` - Service Unavailable

### Error Response Format

```json
{
  "success": false,
  "error": "Error description",
  "details": "Optional additional details"
}
```

### Frontend Error Handling

```javascript
try {
  const results = await apiClient.searchImage(imageId, filters);
  setResults(results.data);
} catch (error) {
  if (error instanceof APIError) {
    if (error.status === 413) {
      setError('File too large');
    } else if (error.status === 400) {
      setError('Invalid request');
    } else {
      setError(error.message);
    }
  } else {
    setError('Network error');
  }
}
```

## CORS Configuration

The frontend runs on a different port than the backend during development. Ensure CORS is properly configured in Flask:

```python
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
```

Or for specific origins:

```python
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000"],
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type"]
    }
})
```

## Authentication

If your API requires authentication:

1. Add token to API client:

```javascript
// src/services/apiClient.js
async request(url, options = {}) {
  const token = localStorage.getItem('authToken');
  return fetch(url, {
    ...options,
    headers: {
      ...API_CONFIG.HEADERS,
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
    signal: controller.signal,
  });
}
```

2. Handle 401 responses:

```javascript
if (response.status === 401) {
  // Redirect to login
  window.location.href = '/login';
}
```

## Rate Limiting

If the API implements rate limiting:

1. Check `Retry-After` header:

```javascript
if (response.status === 429) {
  const retryAfter = response.headers.get('Retry-After');
  setTimeout(() => {
    // Retry request
  }, retryAfter * 1000);
}
```

2. Implement exponential backoff in frontend

## Testing API Integration

### Using cURL

```bash
# Health check
curl http://localhost:5000/api/health

# Upload image
curl -F "image=@image.jpg" http://localhost:5000/api/upload

# Search
curl "http://localhost:5000/api/search?image_id=123&similarity_threshold=0.7"

# Get sources
curl http://localhost:5000/api/sources
```

### Using Postman

1. Import collection from API documentation
2. Set environment variables (API_URL, image_id, etc)
3. Test each endpoint
4. Check response format

### Using Frontend Dev Tools

```javascript
// Open browser console
const apiClient = window.apiClient;

// Test API
await apiClient.healthCheck();
await apiClient.getSources();
```

## Performance Optimization

### Caching

Implement caching for sources:

```javascript
const [sources, setSources] = useState(null);

useEffect(() => {
  const cached = localStorage.getItem('osint_sources');
  if (cached) {
    setSources(JSON.parse(cached));
  } else {
    fetchSources();
  }
}, []);

const fetchSources = async () => {
  const response = await apiClient.getSources();
  localStorage.setItem('osint_sources', JSON.stringify(response.data));
  setSources(response.data);
};
```

### Pagination

For large result sets:

```javascript
// Search with pagination
const response = await apiClient.searchImage(imageId, {
  page: 1,
  per_page: 20
});
```

## Monitoring

### API Metrics to Track

1. Request/response times
2. Error rates
3. Most common errors
4. Slowest endpoints
5. Cache hit rates

### Logging

```javascript
// Enable debug logging
if (process.env.REACT_APP_DEBUG) {
  console.log('API Request:', method, url);
  console.log('Response:', data);
}
```

## Troubleshooting

### Connection Errors

```bash
# Test connectivity
curl -v http://localhost:5000/api/health

# Check network tab in DevTools
# Look for CORS errors
```

### Data Format Issues

1. Verify JSON structure matches expected format
2. Check API documentation
3. Log response in console
4. Use Postman to test API directly

### Performance Issues

1. Check network tab for slow requests
2. Monitor API logs for slow queries
3. Implement pagination for large datasets
4. Cache results when appropriate

## Migration Guide

If changing API endpoints:

1. Update `src/config/api.js`
2. Update environment variables
3. Test each endpoint
4. Update error handling if needed
5. Test in production environment

## Backend Implementation Checklist

- [ ] Implement upload endpoint (POST /api/upload)
- [ ] Implement search endpoint (GET /api/search)
- [ ] Implement batch search (POST /api/search/batch)
- [ ] Implement sources endpoint (GET /api/sources)
- [ ] Implement health check (GET /api/health)
- [ ] Add CORS headers
- [ ] Add input validation
- [ ] Add error handling
- [ ] Add logging
- [ ] Add rate limiting
- [ ] Add authentication (if needed)
- [ ] Test with frontend

## References

- Flask Documentation: https://flask.palletsprojects.com/
- Flask-CORS: https://flask-cors.readthedocs.io/
- REST API Best Practices: https://restfulapi.net/
- HTTP Status Codes: https://httpwg.org/specs/rfc7231.html#status.codes
