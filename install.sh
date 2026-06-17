#!/usr/bin/env bash
# Omnividence installer — LOCAL install only (no Docker anywhere).
#
# Sets up:
#   * the FastAPI backend  -> Python venv at backend/.venv + pip deps
#   * the Next.js frontend -> npm install
#   * env files            -> copies .env.example -> .env and
#                             frontend/.env.local.example -> frontend/.env.local
#
# Re-runnable: skips work that is already done. After it finishes, see the
# printed run commands (or the README) to start the two dev servers.

set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Resolve the repo root (directory containing this script) so the script works
# from anywhere.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "Omnividence installer (local)"
echo "============================="
echo "School face-similarity search demo. Local install only, no Docker."
echo ""

# --- Prerequisites ------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.10+ first." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node not found. Install Node.js 18+ first." >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm not found. Install Node.js (includes npm) first." >&2
  exit 1
fi

echo "python3: $(python3 --version)"
echo "node:    $(node --version)"
echo "npm:     $(npm --version)"
echo ""

# --- Backend: Python venv + pip ----------------------------------------------
echo "[1/3] Backend: creating venv and installing requirements..."
if [ ! -d "backend/.venv" ]; then
  python3 -m venv backend/.venv
fi
# shellcheck disable=SC1091
source backend/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
deactivate
echo "      backend dependencies installed (backend/.venv)"
echo ""

# --- Frontend: npm ------------------------------------------------------------
echo "[2/3] Frontend: installing npm packages..."
( cd frontend && npm install )
echo "      frontend dependencies installed"
echo ""

# --- Env files ----------------------------------------------------------------
echo "[3/3] Env files..."
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  cp .env.example .env
  echo "      created .env from .env.example (set SERPAPI_KEY to enable providers)"
else
  echo "      .env already present (or no .env.example) — left untouched"
fi
if [ -f "frontend/.env.local.example" ] && [ ! -f "frontend/.env.local" ]; then
  cp frontend/.env.local.example frontend/.env.local
  echo "      created frontend/.env.local from example (NEXT_PUBLIC_API_URL)"
else
  echo "      frontend/.env.local already present (or no example) — left untouched"
fi
echo ""

VERSION="$(cat VERSION 2>/dev/null || echo unknown)"
echo "Omnividence v${VERSION} installed locally."
echo ""
echo "Run it (two terminals):"
echo "  1) Backend:  source backend/.venv/bin/activate && cd backend && python main.py"
echo "               -> http://localhost:8000   (buffalo_l model downloads on first run)"
echo "  2) Frontend: cd frontend && npm run dev"
echo "               -> http://localhost:3000"
echo ""
echo "Then open http://localhost:3000 in your browser."
echo ""
echo "No SERPAPI_KEY? It still runs: every provider reports 'not configured',"
echo "results come back empty, and the pipeline reports that honestly."
