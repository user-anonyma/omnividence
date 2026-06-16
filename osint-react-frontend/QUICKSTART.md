# Quick Start Guide

Get the OSINT React frontend up and running in 5 minutes.

## Prerequisites

- Node.js 14+ (`node --version`)
- npm 6+ (`npm --version`)
- Flask backend running on `http://localhost:5000`

## Step 1: Install

```bash
cd osint-react-frontend
npm install
```

Takes ~2-3 minutes depending on internet speed.

## Step 2: Configure

```bash
cp .env.example .env
```

Edit `.env` and ensure:
```env
REACT_APP_API_URL=http://localhost:5000/api
```

## Step 3: Start

```bash
npm start
```

Browser opens automatically to `http://localhost:3000`

## Step 4: Test

1. **Single Image Search:**
   - Click "Single Image" tab
   - Drag an image into the upload zone or click to browse
   - Wait for results to appear

2. **Batch Upload:**
   - Click "Batch Upload" tab
   - Drag multiple images or click to select
   - Click "Upload N Images"
   - Results appear when ready

3. **Filter Results:**
   - Use similarity slider to filter
   - Select sources with checkboxes
   - Results update automatically

4. **Sort Results:**
   - Click dropdown to change sort
   - Options: Similarity, Date, Source

## Common Commands

```bash
npm start          # Start development server
npm run build      # Create production build
npm test           # Run tests
npm run eject      # Eject from Create React App (one-way!)
```

## Troubleshooting

### "Cannot find module" error
```bash
rm -rf node_modules package-lock.json
npm install
```

### Port 3000 already in use
```bash
PORT=3001 npm start
```

### API connection fails
1. Check backend running: `curl http://localhost:5000/api/health`
2. Check `.env` has correct URL
3. Check browser console for CORS errors

### Blank screen
1. Hard refresh: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)
2. Check browser DevTools console for errors
3. Restart dev server: Stop and run `npm start` again

## What's Included

### 5 Components
1. **ImageUploader** - Drag-drop image upload with preview
2. **SearchResults** - Grid display with detail modal
3. **FilterBar** - Filter by source and similarity
4. **SortControls** - Sort by 6 different criteria
5. **BatchProcessor** - Upload multiple images

### Features
- Fully responsive (mobile to desktop)
- Accessible (WCAG 2.1 AA)
- Error handling throughout
- Loading states for all operations
- Dark mode support
- No external CSS framework

## File Structure

```
src/
├── components/         # 5 React components
├── config/            # API configuration
├── hooks/             # Custom React hooks
├── services/          # API client
├── App.jsx            # Main orchestration
└── App.css            # Main styles
```

## API Integration

The frontend automatically connects to:
- `POST /api/upload` - Upload images
- `GET /api/search` - Search by image
- `POST /api/search/batch` - Batch search
- `GET /api/sources` - Get available sources

## Next Steps

1. **Explore Components**
   - Each component is self-contained
   - Check `src/components/` for examples

2. **Customize Styling**
   - Each component has its own CSS file
   - No CSS framework - pure CSS

3. **Add Features**
   - See `COMPONENT_DOCUMENTATION.md` for API details
   - Use existing patterns as template

4. **Deploy**
   - Build: `npm run build`
   - Deploy `build/` folder to Vercel, Netlify, or your host

## Documentation

- **README.md** - Project overview and features
- **SETUP_GUIDE.md** - Detailed installation and config
- **COMPONENT_DOCUMENTATION.md** - Component API reference
- **INTEGRATION_GUIDE.md** - Backend API integration
- **DELIVERABLES.md** - Complete file inventory

## Development Tips

### Hot Reload
Changes to files automatically reload in browser.

### Browser DevTools
Open DevTools to:
- Check Network tab for API calls
- View Console for errors
- Use React DevTools extension

### Component Testing
Test individual components by:
1. Uploading test images
2. Verifying results display
3. Testing filters and sorts
4. Trying different screen sizes

## Performance

App is optimized for:
- Quick startup (~3s from cold)
- Fast interactions (no lag)
- Responsive UI (smooth animations)
- Mobile performance

## Browser Support

Works in:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
- Mobile browsers

## Getting Help

1. Check error message in console
2. Review relevant documentation file
3. Check component comments in source
4. Review COMPONENT_DOCUMENTATION.md

## What's NOT Included

- CSS framework (pure CSS for simplicity)
- Test files (ready for React Testing Library)
- TypeScript (plain JavaScript for simplicity)
- Redux/Context (uses React hooks)
- Build optimizations (Create React App handles)

## Production Deployment

```bash
# Build optimized bundle
npm run build

# Test production build locally
npx serve -s build

# Deploy 'build' folder to:
# - Vercel: via GitHub integration
# - Netlify: via GitHub integration
# - Static host: upload build/ contents
```

## Security Notes

- Always use HTTPS in production
- Validate file uploads on server
- Never commit `.env` with real tokens
- Use environment variables for secrets
- Implement authentication if needed

## Need More Help?

1. **Setup Issues** → See `SETUP_GUIDE.md`
2. **Component Details** → See `COMPONENT_DOCUMENTATION.md`
3. **API Integration** → See `INTEGRATION_GUIDE.md`
4. **Feature Overview** → See `README.md`
5. **Complete Inventory** → See `DELIVERABLES.md`

---

You're ready to go! Start with `npm start` and explore the app.
