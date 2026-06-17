#!/usr/bin/env bash
# Omnividence installer - local install (no Docker)
# Sets up the Python backend (venv + deps) and the React frontend (npm deps).

set -e
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

echo "📥 Omnividence Installer (local)"
echo "================================"
echo ""

# --- Prerequisites ---
if ! command -v python3 &> /dev/null; then
  echo "❌ python3 not found. Install Python 3.10+ first."
  exit 1
fi

if ! command -v node &> /dev/null; then
  echo "❌ node not found. Install Node.js 16+ first."
  exit 1
fi

if ! command -v npm &> /dev/null; then
  echo "❌ npm not found. Install Node.js (includes npm) first."
  exit 1
fi

echo "✅ python3: $(python3 --version)"
echo "✅ node:    $(node --version)"
echo ""

# --- Backend setup ---
echo "🐍 Setting up Python backend..."
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Backend dependencies installed"
echo ""

# --- Frontend setup ---
echo "⚛️  Setting up React frontend..."
cd osint-react-frontend
npm install
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  cp .env.example .env
  echo "   created .env from .env.example (set REACT_APP_API_URL if needed)"
fi
cd ..
echo "✅ Frontend dependencies installed"
echo ""

VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
echo "✅ Omnividence v$VERSION installed locally!"
echo ""
echo "To run it (two terminals):"
echo "  1) Backend:  source venv/bin/activate && python app.py     # http://localhost:5000"
echo "  2) Frontend: cd osint-react-frontend && npm start          # http://localhost:3000"
echo ""
echo "Then open http://localhost:3000 in your browser."
