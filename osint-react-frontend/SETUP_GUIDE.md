# React Frontend Setup Guide

Complete setup instructions for the OSINT Face Search React frontend.

## Prerequisites

- Node.js 14+ or 16+
- npm 6+ or yarn 1.22+
- A running backend API server

## Quick Start

### 1. Installation

```bash
# Clone repository
git clone <repository-url>
cd osint-react-frontend

# Install dependencies
npm install
```

### 2. Environment Setup

```bash
# Copy example env file
cp .env.example .env

# Edit .env to set your API URL
# REACT_APP_API_URL=http://localhost:5000/api
nano .env
```

### 3. Start Development Server

```bash
npm start
```

The app will open at `http://localhost:3000`

## Detailed Setup Instructions

### Node.js Installation

#### macOS (using Homebrew)
```bash
brew install node
```

#### Ubuntu/Debian
```bash
curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -
sudo apt-get install -y nodejs
```

#### Windows
Download from https://nodejs.org/

#### Verify Installation
```bash
node --version
npm --version
```

### Project Setup

#### Clone Repository

```bash
git clone <repository-url>
cd osint-react-frontend
```

#### Install Dependencies

```bash
# Using npm
npm install

# Or using yarn
yarn install
```

This creates a `node_modules` directory with all dependencies.

#### Verify Installation

```bash
npm list react react-dom
```

### Environment Configuration

#### Create .env File

```bash
cp .env.example .env
```

#### Edit Environment Variables

```bash
# .env
REACT_APP_API_URL=http://localhost:5000/api
REACT_APP_DEBUG=false
```

#### Available Variables

- `REACT_APP_API_URL` - Backend API endpoint (required)
- `REACT_APP_DEBUG` - Enable debug logging (optional)
- `PORT` - Development server port (default: 3000)

### Development Workflow

#### Start Development Server

```bash
npm start
```

- Automatically opens browser at http://localhost:3000
- Hot reload on file changes
- Shows compilation errors in browser

#### Build for Production

```bash
npm run build
```

Creates optimized build in `build/` directory:
- Minified JavaScript
- Optimized CSS
- Images optimized
- Ready for deployment

#### Run Tests

```bash
npm test
```

Runs tests in watch mode.

### Project Structure After Installation

```
osint-react-frontend/
├── node_modules/          # Installed dependencies
├── public/
│   └── index.html         # HTML template
├── src/
│   ├── components/        # React components
│   ├── config/            # Configuration files
│   ├── hooks/             # Custom React hooks
│   ├── services/          # API client
│   ├── App.jsx            # Main app component
│   ├── App.css            # App styles
│   └── index.js           # Entry point
├── .env                   # Environment variables
├── .gitignore             # Git ignore rules
├── package.json           # Dependencies and scripts
└── README.md              # Documentation
```

## API Backend Configuration

### Required Backend Setup

Ensure the Flask backend is running:

```bash
# From the parent directory with Flask app
python app.py
```

Backend should be available at `http://localhost:5000`

### API Endpoints Expected

The frontend expects these endpoints:

```
POST   /api/upload              # Upload image
POST   /api/search              # Search image
POST   /api/search/batch        # Batch search
GET    /api/results/{id}        # Get results
GET    /api/sources             # Get sources
GET    /api/health              # Health check
```

See Flask backend documentation for implementation details.

## Troubleshooting

### Port Already in Use

If port 3000 is already in use:

```bash
# Use a different port
PORT=3001 npm start

# Or kill the process on port 3000
# macOS/Linux
lsof -i :3000 | grep LISTEN | awk '{print $2}' | xargs kill

# Windows
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

### Module Not Found Errors

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

### API Connection Fails

1. Check backend is running: `curl http://localhost:5000/api/health`
2. Verify .env has correct API URL
3. Check CORS is enabled on backend
4. Verify firewall rules

### Blank Screen on Startup

1. Check browser console for errors
2. Verify Node version: `node --version` (should be 14+)
3. Clear browser cache and hard refresh (Ctrl+Shift+R)

### Hot Reload Not Working

```bash
# Restart development server
npm start

# Or check file watcher limit
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

## IDE Configuration

### Visual Studio Code

1. Install extensions:
   - ES7+ React/Redux/React-Native snippets
   - Prettier - Code formatter
   - ESLint

2. Create `.vscode/settings.json`:
```json
{
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  }
}
```

### WebStorm

1. Open project
2. Enable "Use npm from node_modules folder"
3. Configure run configuration for `npm start`

## Deployment

### Deploy to Vercel

1. Push code to GitHub
2. Connect repository to Vercel
3. Set environment variables:
   - `REACT_APP_API_URL` = production backend URL
4. Deploy

### Deploy to Netlify

1. Build locally: `npm run build`
2. Connect `build/` folder to Netlify
3. Set environment variables in Netlify dashboard
4. Deploy

### Deploy to Static Host

```bash
# Build production bundle
npm run build

# Upload build/ directory to your host
# Configure server to serve index.html for all routes
```

### Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM node:16-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY src ./src
COPY public ./public

ENV REACT_APP_API_URL=http://api:5000/api

RUN npm run build

FROM nginx:alpine
COPY --from=0 /app/build /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

Build and run:

```bash
docker build -t osint-frontend .
docker run -p 80:80 osint-frontend
```

## Performance Optimization

### Code Splitting

The app uses dynamic imports for code splitting.

### Image Optimization

- Compress images before upload
- Use WebP format when possible
- Implement lazy loading

### Bundle Analysis

```bash
npm install -g source-map-explorer
npm run build
source-map-explorer 'build/static/js/*.js'
```

## Security Checklist

- [ ] Set secure API endpoint in production
- [ ] Enable HTTPS
- [ ] Validate all file uploads on server
- [ ] Implement rate limiting
- [ ] Use secure headers (CSP, X-Frame-Options, etc.)
- [ ] Keep dependencies updated
- [ ] Use environment variables for secrets
- [ ] Implement authentication if needed

## Development Tools

### Useful npm Scripts

```bash
npm start          # Start dev server
npm run build      # Production build
npm test           # Run tests
npm run eject      # Eject from Create React App
```

### Browser DevTools

1. React DevTools extension
2. Redux DevTools (if using Redux)
3. Network tab for API debugging
4. Console for error tracking

## Maintenance

### Update Dependencies

```bash
# Check outdated packages
npm outdated

# Update all packages
npm update

# Update to latest major versions
npm install -g npm-check-updates
ncu -u
npm install
```

### Code Quality

```bash
# ESLint
npm run lint

# Format code
npm run format

# Type checking (if using TypeScript)
npm run type-check
```

## Common Commands

```bash
# View installed version
npm list react

# Install specific version
npm install react@18.2.0

# Remove package
npm uninstall package-name

# Clear npm cache
npm cache clean --force

# Check for security vulnerabilities
npm audit

# Fix security vulnerabilities
npm audit fix
```

## Getting Help

1. Check the README.md
2. See COMPONENT_DOCUMENTATION.md for component details
3. Review API integration guide
4. Check browser console for errors
5. Check backend logs for API errors

## Next Steps

1. Update .env with your API endpoint
2. Start development server: `npm start`
3. Make changes and see hot reload in action
4. Test with different screen sizes
5. Build for production when ready

## Additional Resources

- React Documentation: https://react.dev
- Create React App: https://create-react-app.dev
- npm Documentation: https://docs.npmjs.com
- JavaScript MDN: https://developer.mozilla.org
