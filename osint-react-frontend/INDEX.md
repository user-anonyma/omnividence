# OSINT React Frontend - Complete Index

## Quick Navigation

Start here based on your needs:

### Getting Started (5 minutes)
- **QUICKSTART.md** - Run the app in 5 minutes
  1. Install: `npm install`
  2. Config: `cp .env.example .env`
  3. Start: `npm start`

### Learning the Project
- **README.md** - Project overview, features, structure
- **PROJECT_SUMMARY.txt** - Complete technical summary

### Setup & Installation
- **SETUP_GUIDE.md** - Detailed installation for all OS
  - Node.js setup
  - Project configuration
  - Development workflow
  - Troubleshooting

### Development & Components
- **COMPONENT_DOCUMENTATION.md** - All components explained
  - ImageUploader (drag-drop upload)
  - SearchResults (grid + modal)
  - FilterBar (source + similarity)
  - SortControls (6 sort options)
  - BatchProcessor (multi-image)
  - API Client Service
  - Custom Hooks

### Backend Integration
- **INTEGRATION_GUIDE.md** - Connect to Flask API
  - Endpoint specifications
  - Request/response formats
  - Error handling
  - Testing API
  - Troubleshooting

### Reference
- **DELIVERABLES.md** - Complete file inventory
  - All files listed
  - Feature checklist
  - Code statistics
  - Quality metrics

---

## Project Structure

```
osint-react-frontend/
├── src/
│   ├── components/        (5 components)
│   │   ├── ImageUploader/   (drag-drop upload)
│   │   ├── SearchResults/   (grid + modal)
│   │   ├── FilterBar/       (filters)
│   │   ├── SortControls/    (sorting)
│   │   └── BatchProcessor/  (batch upload)
│   ├── config/api.js        (API config)
│   ├── hooks/useAsync.js    (custom hook)
│   ├── services/apiClient.js (API client)
│   ├── App.jsx              (main app)
│   └── index.js             (entry point)
├── public/index.html
├── package.json
├── .env.example
└── [Documentation files]
```

---

## Essential Files

### For Running the App
- `package.json` - Install dependencies
- `.env.example` → `.env` - Configure API endpoint
- `npm start` - Start development server

### For Development
- `src/App.jsx` - Main orchestration
- `src/components/` - All 5 components
- `src/services/apiClient.js` - API calls

### For Styling
- `src/App.css` - Main layout
- `src/components/*/Component.css` - Component styles
- Mobile-first responsive design
- Dark mode support

### For Integration
- `src/config/api.js` - API configuration
- `src/services/apiClient.js` - API client methods
- Expected backend endpoints documented

---

## Component Overview

### 1. ImageUploader
- Single image upload
- Drag-and-drop support
- File preview and validation
- Progress tracking

**Usage:**
```jsx
<ImageUploader
  onUploadSuccess={handleSuccess}
  onUploadError={handleError}
  onLoading={setLoading}
/>
```

### 2. SearchResults
- Responsive grid of results
- Similarity badges
- Detail modal view
- Loading and error states

**Usage:**
```jsx
<SearchResults
  results={results}
  loading={isSearching}
  error={error}
/>
```

### 3. FilterBar
- Similarity slider
- Source checkboxes
- Active filters display
- Clear button

**Usage:**
```jsx
<FilterBar
  onFiltersChange={handleFilters}
  onLoading={setLoading}
/>
```

### 4. SortControls
- 6 sort options dropdown
- Similarity, date, source

**Usage:**
```jsx
<SortControls
  currentSort={sort}
  onSortChange={handleSort}
/>
```

### 5. BatchProcessor
- Multi-file upload
- File list management
- Batch validation

**Usage:**
```jsx
<BatchProcessor
  onBatchSuccess={handleSuccess}
  onBatchError={handleError}
  onLoading={setLoading}
/>
```

---

## API Integration

### Endpoints
```
POST /api/upload              # Upload images
GET  /api/search              # Search image
POST /api/search/batch        # Batch search
GET  /api/sources             # Get sources
GET  /api/health              # Health check
```

### API Client Methods
```javascript
apiClient.uploadImage(file)
apiClient.uploadBatch(files)
apiClient.searchImage(imageId, filters)
apiClient.searchBatch(imageIds, filters)
apiClient.getSources()
apiClient.healthCheck()
```

See **INTEGRATION_GUIDE.md** for full details.

---

## State Management

**Main App State:**
- `currentImageId` - Image being searched
- `results` - Search results
- `sortedResults` - Sorted results
- `currentSort` - Sort method
- `filters` - Active filters
- `isSearching` - Search in progress
- `activeTab` - Single or batch mode

---

## Styling Features

- Mobile-first responsive design
- 3+ breakpoints (480px, 768px, 1200px)
- Dark mode support (`prefers-color-scheme`)
- Reduced motion support (`prefers-reduced-motion`)
- WCAG AA color contrast
- Pure CSS (no framework)
- CSS Grid and Flexbox layout

---

## Accessibility

- WCAG 2.1 AA compliant
- ARIA labels
- Semantic HTML
- Keyboard navigation
- Focus indicators
- Screen reader friendly
- Error announcements

---

## Key Features

✓ Single image search
✓ Batch image processing
✓ Advanced filtering
✓ Multiple sort options
✓ Responsive design (mobile to desktop)
✓ Full accessibility
✓ Error handling
✓ Loading states
✓ Dark mode
✓ Production ready

---

## Installation Steps

1. **Install Node dependencies**
   ```bash
   npm install
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env to set API URL
   ```

3. **Start development**
   ```bash
   npm start
   ```

4. **Build for production**
   ```bash
   npm run build
   ```

---

## Documentation Files

| File | Purpose |
|------|---------|
| **QUICKSTART.md** | 5-minute quick start |
| **README.md** | Project overview |
| **SETUP_GUIDE.md** | Detailed installation |
| **COMPONENT_DOCUMENTATION.md** | Component API reference |
| **INTEGRATION_GUIDE.md** | Backend API integration |
| **DELIVERABLES.md** | File inventory & checklist |
| **PROJECT_SUMMARY.txt** | Technical summary |

---

## Troubleshooting

### App won't start
- Check Node version: `node --version` (need 14+)
- Clear cache: `rm -rf node_modules package-lock.json && npm install`
- Check .env configuration

### API connection fails
- Verify backend running: `curl http://localhost:5000/api/health`
- Check .env has correct API URL
- Review browser console for errors

### Port already in use
```bash
PORT=3001 npm start
```

### Blank screen
- Hard refresh: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
- Check browser DevTools console
- Restart dev server

---

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
- Mobile browsers (iOS Safari, Chrome Mobile)

---

## Next Steps

1. **Quick Start**: Read QUICKSTART.md
2. **Install & Run**: `npm install && npm start`
3. **Explore Components**: Check src/components/
4. **Test Features**: Try upload, filter, sort
5. **Configure API**: Update .env with backend URL
6. **Build**: `npm run build` when ready

---

## Support

- **Setup issues** → SETUP_GUIDE.md
- **Component questions** → COMPONENT_DOCUMENTATION.md
- **API integration** → INTEGRATION_GUIDE.md
- **Complete reference** → DELIVERABLES.md

---

## Statistics

- **5 Components** (production-ready)
- **1,500+ LOC** (React components)
- **1,200+ LOC** (Stylesheets)
- **800+ LOC** (Services/config)
- **2,000+ LOC** (Documentation)
- **~5,500+ total lines**

---

**Location:** `/home/anonym/osint-react-frontend`

**Status:** Complete and production-ready

**Last Updated:** 2024
