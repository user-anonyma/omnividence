# Component Documentation

Detailed documentation for all React components in the OSINT Face Search frontend.

## Table of Contents

1. [ImageUploader](#imageuploader)
2. [SearchResults](#searchresults)
3. [FilterBar](#filterbar)
4. [SortControls](#sortcontrols)
5. [BatchProcessor](#batchprocessor)
6. [API Client](#api-client)
7. [Custom Hooks](#custom-hooks)

---

## ImageUploader

**Location:** `src/components/ImageUploader/ImageUploader.jsx`

### Purpose
Handles single image upload with drag-and-drop support, file validation, and preview.

### Props

```typescript
interface ImageUploaderProps {
  onUploadSuccess?: (data: UploadData) => void
  onUploadError?: (error: string) => void
  onLoading?: (isLoading: boolean) => void
}

interface UploadData {
  image_id: string
  thumbnail_url: string
}
```

### Features

- Drag-and-drop upload zone
- Click to browse files
- File validation (type, size)
- Image preview
- Progress tracking
- Error messages
- Clear button
- Keyboard accessible

### Usage

```jsx
import ImageUploader from './components/ImageUploader/ImageUploader';

<ImageUploader
  onUploadSuccess={handleSuccess}
  onUploadError={handleError}
  onLoading={setLoading}
/>
```

### State Management

```javascript
- preview: string | null // Data URL of preview image
- fileName: string // Name of uploaded file
- uploadProgress: number // 0-100
- isUploading: boolean // Upload in progress
- error: string | null // Error message
```

### File Validation

- File type must be image/*
- Maximum file size: 10MB (configurable in api.js)
- Accepts: JPG, PNG, GIF, WebP

### Accessibility

- ARIA labels on all interactive elements
- Keyboard navigation support
- Focus indicators
- Error announcements via role="alert"
- Screen reader friendly

---

## SearchResults

**Location:** `src/components/SearchResults/SearchResults.jsx`

### Purpose
Displays matched faces in a responsive grid with detailed information and modal view.

### Props

```typescript
interface SearchResultsProps {
  results?: SearchResult[]
  loading?: boolean
  error?: string | null
}

interface SearchResult {
  id: string
  image_url: string
  thumbnail_url: string
  similarity: number // 0-1
  source: string
  source_type: string
  source_url: string
  metadata?: {
    date?: string
    description?: string
    tags?: string[]
  }
}
```

### Features

- Responsive grid layout (auto-fill columns)
- Similarity badges with percentages
- Source attribution
- Clickable cards for detail view
- Modal with full image and metadata
- Loading spinner
- Empty state message
- Error state handling

### Grid Behavior

- Desktop (1200px+): 4+ columns
- Tablet (768px-1199px): 3-4 columns
- Mobile (480px-767px): 2-3 columns
- Small mobile (<480px): 1-2 columns

### Usage

```jsx
import SearchResults from './components/SearchResults/SearchResults';

<SearchResults
  results={searchResults}
  loading={isSearching}
  error={searchError}
/>
```

### Sub-Components

#### SearchResultCard
Individual result card with thumbnail and metadata.

- Click to open detail modal
- Keyboard accessible
- Hover effects
- Link to original source

#### ResultDetailModal
Full-screen modal with detailed information.

- Image viewer
- Complete metadata
- Tags display
- External link
- Close button
- Click outside to close

---

## FilterBar

**Location:** `src/components/FilterBar/FilterBar.jsx`

### Purpose
Filter search results by source, similarity threshold, and other criteria.

### Props

```typescript
interface FilterBarProps {
  onFiltersChange?: (filters: FilterOptions) => void
  onLoading?: (isLoading: boolean) => void
}

interface FilterOptions {
  sources?: string[]
  similarity_threshold?: number
}
```

### Features

- Similarity threshold slider (0-100%)
- Source checkboxes with counts
- Active filters display
- Clear filters button
- Dynamic source loading
- Visual feedback

### Slider Behavior

- Range: 0 to 1 (displayed as 0-100%)
- Step: 0.05 (5%)
- Color gradient background
- Touch-friendly on mobile

### Source Loading

- Fetches available sources on mount
- Shows loading state
- Handles errors gracefully
- Displays result counts

### Usage

```jsx
import FilterBar from './components/FilterBar/FilterBar';

<FilterBar
  onFiltersChange={handleFiltersChange}
  onLoading={setLoading}
/>
```

### State Management

```javascript
- sources: Source[] // Available sources
- selectedSources: string[] // Selected source IDs
- similarityThreshold: number // 0-1
- loadingSourcesState: boolean
- error: string | null
```

### Accessibility

- Proper labels for all inputs
- ARIA labels
- Keyboard navigation
- Focus indicators
- Role="region" for active filters

---

## SortControls

**Location:** `src/components/SortControls/SortControls.jsx`

### Purpose
Sort search results by multiple criteria.

### Props

```typescript
interface SortControlsProps {
  currentSort?: string
  onSortChange?: (sortMethod: string) => void
}
```

### Sort Options

1. `similarity_desc` - Highest Similarity (default)
2. `similarity_asc` - Lowest Similarity
3. `date_new` - Newest First
4. `date_old` - Oldest First
5. `source_az` - Source (A-Z)
6. `source_za` - Source (Z-A)

### Usage

```jsx
import SortControls from './components/SortControls/SortControls';

<SortControls
  currentSort={currentSort}
  onSortChange={handleSortChange}
/>
```

### Implementation Details

The sort logic is implemented in the parent component (App.jsx):

```javascript
const sortResultsData = useCallback((data, sortMethod) => {
  const sorted = [...data];
  
  switch (sortMethod) {
    case SORT_OPTIONS.SIMILARITY_DESC:
      return sorted.sort((a, b) => b.similarity - a.similarity);
    // ... other cases
  }
}, []);
```

### Accessibility

- Semantic HTML select element
- ARIA labels
- Keyboard accessible
- Clear option labels

---

## BatchProcessor

**Location:** `src/components/BatchProcessor/BatchProcessor.jsx`

### Purpose
Upload and process multiple images for concurrent searching.

### Props

```typescript
interface BatchProcessorProps {
  onBatchSuccess?: (data: BatchUploadData) => void
  onBatchError?: (error: string) => void
  onLoading?: (isLoading: boolean) => void
}

interface BatchUploadData {
  image_ids: string[]
  uploaded_count: number
}
```

### Features

- Multi-file drag-and-drop
- File list management
- File removal
- Batch validation
- Size limits enforcement
- Progress tracking
- Loading states
- Error handling

### Limits

- Maximum 50 images per batch (configurable)
- 10MB per image
- 500MB total batch size

### File List Management

- Display selected files
- Individual file removal
- Total size calculation
- Remove all button
- Dynamic button labels

### Usage

```jsx
import BatchProcessor from './components/BatchProcessor/BatchProcessor';

<BatchProcessor
  onBatchSuccess={handleSuccess}
  onBatchError={handleError}
  onLoading={setLoading}
/>
```

### Validation

```javascript
validateFiles(filesToValidate):
- Check file count <= MAX_IMAGES
- Validate each file type
- Check individual file size
- Calculate total size
- Verify total <= MAX_BATCH_SIZE
```

### State Management

```javascript
- files: File[] // Selected files
- uploadProgress: object // Per-file progress
- isProcessing: boolean
- error: string | null
- successMessage: string | null
```

### Accessibility

- Proper labels
- ARIA labels on all buttons
- Keyboard navigation
- Focus indicators
- Error announcements

---

## API Client

**Location:** `src/services/apiClient.js`

### Purpose
Centralized service for all API requests with error handling and request management.

### Methods

#### `uploadImage(file: File): Promise<UploadResponse>`

Upload a single image.

```javascript
const response = await apiClient.uploadImage(file);
// Returns: { success: boolean, data: { image_id, thumbnail_url } }
```

#### `uploadBatch(files: File[]): Promise<BatchUploadResponse>`

Upload multiple images.

```javascript
const response = await apiClient.uploadBatch(files);
// Returns: { success: boolean, data: { image_ids, uploaded_count } }
```

#### `searchImage(imageId: string, filters?: FilterOptions): Promise<SearchResponse>`

Search for matches by image.

```javascript
const response = await apiClient.searchImage(imageId, {
  similarity_threshold: 0.7,
  sources: ['facebook', 'twitter']
});
// Returns: { success: boolean, data: SearchResult[] }
```

#### `searchBatch(imageIds: string[], filters?: FilterOptions): Promise<BatchSearchResponse>`

Batch search multiple images.

```javascript
const response = await apiClient.searchBatch(['id1', 'id2'], filters);
// Returns: { success: boolean, data: { image_results } }
```

#### `getSources(): Promise<SourcesResponse>`

Get available sources for filtering.

```javascript
const response = await apiClient.getSources();
// Returns: { success: boolean, data: Source[] }
```

#### `healthCheck(): Promise<HealthResponse>`

Check API availability.

```javascript
const response = await apiClient.healthCheck();
```

### Error Handling

```javascript
// Throws APIError
class APIError extends Error {
  constructor(message, status, originalError)
  - message: string
  - status: number | null
  - originalError: Error | null
}
```

### Request Features

- Automatic timeout (30s, configurable)
- Request cancellation
- Error status handling
- JSON parsing
- Header management
- Custom headers support

---

## Custom Hooks

**Location:** `src/hooks/useAsync.js`

### useAsync

Manages async operations with loading, data, and error states.

```typescript
interface UseAsyncOptions {
  asyncFunction: (...args: any[]) => Promise<any>
  immediate?: boolean
}

interface UseAsyncReturn {
  loading: boolean
  data: any
  error: Error | null
  execute: (...args: any[]) => Promise<any>
}
```

### Usage

```javascript
import useAsync from './hooks/useAsync';

const { loading, data, error, execute } = useAsync(
  async () => {
    const response = await apiClient.getSources();
    return response.data;
  },
  true // immediate execution
);
```

### Features

- Auto-execute on mount (optional)
- Manual execution via `execute()`
- State reset before requests
- Error capture
- Return data on success
- Type-safe with generics

---

## Configuration

**Location:** `src/config/api.js`

### API Endpoints

```javascript
API_ENDPOINTS = {
  SEARCH: '/search',
  SEARCH_BATCH: '/search/batch',
  UPLOAD: '/upload',
  RESULTS: '/results',
  SOURCES: '/sources',
  HEALTH: '/health'
}
```

### Batch Limits

```javascript
BATCH_LIMITS = {
  MAX_IMAGES: 50,
  MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
  MAX_BATCH_SIZE: 500 * 1024 * 1024 // 500MB
}
```

### Sort Options

```javascript
SORT_OPTIONS = {
  SIMILARITY_DESC: 'similarity_desc',
  SIMILARITY_ASC: 'similarity_asc',
  DATE_NEW: 'date_new',
  DATE_OLD: 'date_old',
  SOURCE_AZ: 'source_az',
  SOURCE_ZA: 'source_za'
}
```

### Similarity Thresholds

```javascript
SIMILARITY_THRESHOLDS = {
  HIGH: 0.9,
  MEDIUM: 0.7,
  LOW: 0.5
}
```

---

## Best Practices

### Component Design

1. Keep components focused and single-responsibility
2. Use prop drilling sparingly
3. Extract complex logic to custom hooks
4. Use callbacks for parent-child communication
5. Memoize callbacks with useCallback

### API Integration

1. Always handle errors gracefully
2. Show loading states for async operations
3. Validate data before use
4. Use centralized API client
5. Implement request cancellation

### Accessibility

1. Always include ARIA labels
2. Use semantic HTML
3. Ensure keyboard navigation
4. Test with screen readers
5. Verify color contrast

### Performance

1. Lazy load images
2. Memoize expensive computations
3. Avoid unnecessary re-renders
4. Optimize CSS selectors
5. Use proper image formats

---

## Testing

### Component Testing

```javascript
import { render, screen } from '@testing-library/react';
import ImageUploader from './ImageUploader';

describe('ImageUploader', () => {
  it('renders upload zone', () => {
    render(<ImageUploader />);
    expect(screen.getByText(/drag image/i)).toBeInTheDocument();
  });
});
```

### API Client Testing

```javascript
import apiClient from './apiClient';

describe('APIClient', () => {
  it('handles network errors', async () => {
    expect(() => apiClient.uploadImage(invalidFile))
      .rejects.toThrow(APIError);
  });
});
```

---

## Troubleshooting

### Common Issues

1. **API Connection Errors**
   - Check `.env` API URL
   - Verify backend is running
   - Check CORS configuration

2. **File Upload Fails**
   - Verify file size limits
   - Check file type validation
   - Ensure multipart/form-data headers

3. **Results Not Displaying**
   - Check API response format
   - Verify data structure
   - Check browser console for errors

4. **Styling Issues**
   - Clear browser cache
   - Check CSS specificity
   - Verify responsive breakpoints

---

## Performance Tips

1. Use React DevTools Profiler to identify slow renders
2. Memoize large lists with React.memo
3. Use code splitting for large components
4. Optimize images before upload
5. Enable gzip compression on server

---

## Security Considerations

1. Validate all file uploads on server
2. Sanitize user input
3. Use HTTPS in production
4. Implement CSRF protection
5. Secure API endpoints with authentication
