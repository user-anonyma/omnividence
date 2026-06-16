# OSINT Face Search - React Frontend

A comprehensive React application for facial recognition and image matching with OSINT capabilities. Built with modern React patterns, accessibility-first design, and full responsiveness.

## Features

- **Single Image Search**: Upload and search for matches on a single face
- **Batch Processing**: Upload multiple images for concurrent searching
- **Advanced Filtering**: Filter results by source, similarity threshold, and more
- **Smart Sorting**: Sort results by similarity, date, source, and other criteria
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile
- **Accessibility**: WCAG 2.1 AA compliant with proper ARIA labels and keyboard navigation
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Loading States**: Visual feedback for all async operations

## Project Structure

```
osint-react-frontend/
├── public/
│   └── index.html
├── src/
│   ├── components/
│   │   ├── ImageUploader/
│   │   │   ├── ImageUploader.jsx
│   │   │   └── ImageUploader.css
│   │   ├── SearchResults/
│   │   │   ├── SearchResults.jsx
│   │   │   └── SearchResults.css
│   │   ├── FilterBar/
│   │   │   ├── FilterBar.jsx
│   │   │   └── FilterBar.css
│   │   ├── SortControls/
│   │   │   ├── SortControls.jsx
│   │   │   └── SortControls.css
│   │   └── BatchProcessor/
│   │       ├── BatchProcessor.jsx
│   │       └── BatchProcessor.css
│   ├── config/
│   │   └── api.js
│   ├── hooks/
│   │   └── useAsync.js
│   ├── services/
│   │   └── apiClient.js
│   ├── App.jsx
│   ├── App.css
│   └── index.js
├── .env.example
├── package.json
└── README.md
```

## Installation

1. Clone the repository
```bash
git clone <repository-url>
cd osint-react-frontend
```

2. Install dependencies
```bash
npm install
```

3. Set up environment variables
```bash
cp .env.example .env
# Edit .env to configure API endpoint
```

## Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
REACT_APP_API_URL=http://localhost:5000/api
REACT_APP_DEBUG=false
```

### API Configuration

Update `src/config/api.js` to configure:

- API endpoints
- Batch processing limits
- Similarity thresholds
- Sort options
- Source types

## Running the Application

### Development Mode

```bash
npm start
```

The app will open at `http://localhost:3000`

### Production Build

```bash
npm run build
```

Creates optimized production build in the `build/` directory.

## Components Overview

### ImageUploader
Handles single image upload with drag-and-drop support.

**Features:**
- Drag-and-drop upload
- File validation
- Progress tracking
- Image preview
- Error handling

**Props:**
- `onUploadSuccess(data)` - Called when upload succeeds
- `onUploadError(error)` - Called on upload error
- `onLoading(isLoading)` - Loading state callback

### SearchResults
Grid display of matched faces with detailed information.

**Features:**
- Responsive grid layout
- Similarity badges
- Source attribution
- Modal detail view
- Loading and empty states
- Error handling

**Props:**
- `results` - Array of search results
- `loading` - Loading state
- `error` - Error message

### FilterBar
Filter results by source and similarity threshold.

**Features:**
- Similarity slider
- Source checkboxes
- Active filters display
- Clear filters button
- Dynamic source loading

**Props:**
- `onFiltersChange(filters)` - Called when filters change
- `onLoading(isLoading)` - Loading state callback

### SortControls
Sort results by multiple criteria.

**Features:**
- 6 sort options
- Accessible dropdown
- Responsive design

**Props:**
- `currentSort` - Current sort method
- `onSortChange(sortMethod)` - Sort change callback

### BatchProcessor
Upload and process multiple images.

**Features:**
- Multi-file selection
- Drag-and-drop support
- File list management
- Progress tracking
- Batch validation

**Props:**
- `onBatchSuccess(data)` - Called on batch success
- `onBatchError(error)` - Called on batch error
- `onLoading(isLoading)` - Loading state callback

## API Integration

The frontend communicates with the backend API through `src/services/apiClient.js`:

### Available Methods

```javascript
// Upload single image
apiClient.uploadImage(file)

// Upload multiple images
apiClient.uploadBatch(files)

// Search for matches
apiClient.searchImage(imageId, filters)

// Batch search
apiClient.searchBatch(imageIds, filters)

// Get results
apiClient.getResults(searchId)

// Get available sources
apiClient.getSources()

// Health check
apiClient.healthCheck()
```

## State Management

The app uses React's built-in hooks for state management:

- `useState` - Component state
- `useEffect` - Side effects and lifecycle
- `useCallback` - Memoized callbacks
- `useRef` - DOM references
- `useAsync` - Custom hook for async operations

## Accessibility

The application is built with accessibility as a core feature:

- WCAG 2.1 AA compliant
- Proper ARIA labels and roles
- Keyboard navigation support
- Focus indicators
- Semantic HTML
- Color contrast compliance
- Reduced motion support

## Styling

No external CSS framework is used. Styling is done with plain CSS:

- Mobile-first approach
- Responsive breakpoints: 768px, 480px
- CSS Grid and Flexbox for layout
- Smooth transitions
- Dark mode support via `prefers-color-scheme`

## Error Handling

Comprehensive error handling throughout:

- Network error messages
- File validation errors
- API error responses
- User-friendly error displays
- Proper error boundaries

## Performance

- Lazy loading images
- Memoized callbacks
- Efficient state updates
- CSS optimization
- Responsive image handling

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## API Response Format

Expected API response format:

```javascript
// Upload response
{
  success: true,
  data: {
    image_id: "uuid",
    thumbnail_url: "url"
  }
}

// Search response
{
  success: true,
  data: [
    {
      id: "result_id",
      image_url: "url",
      thumbnail_url: "url",
      similarity: 0.95,
      source: "source_name",
      source_type: "social_media",
      source_url: "url",
      metadata: {
        date: "2024-01-01",
        description: "text",
        tags: ["tag1", "tag2"]
      }
    }
  ]
}

// Sources response
{
  success: true,
  data: [
    {
      id: "source_id",
      name: "Source Name",
      count: 1000
    }
  ]
}
```

## Development

### Code Style

- Clean, readable code
- Clear component naming
- Proper prop documentation
- Comments for complex logic

### Adding New Components

1. Create component directory under `src/components/`
2. Create `Component.jsx` and `Component.css`
3. Export from component file
4. Import and use in parent component

## Testing

Add tests using Jest and React Testing Library:

```bash
npm test
```

## Deployment

### Building for Production

```bash
npm run build
```

### Environment Configuration

Update `.env` with production API endpoint:

```env
REACT_APP_API_URL=https://api.example.com/api
```

## License

Copyright 2024. All rights reserved.

## Support

For issues or questions, contact the development team.
