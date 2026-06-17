"""Central configuration for the Omnividence backend.

Reads all OMNI_* environment variables, computes the data / cache / model paths,
and ensures the required directories exist. Import `config` anywhere in the
backend to read settings; nothing here is mutated at runtime.

Providers use Scrapling's browser automation (no API key), so there is no secret
to configure here — a blocked engine just reports "blocked" and the pipeline
still runs honestly.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- semantic version (also reported by /health and /version) -----------------
VERSION = "1.0.0"


def _read_version() -> str:
    """Prefer the repo-root VERSION file so /health matches the project version.

    Falls back to the hard-coded VERSION constant if the file is missing.
    """
    try:
        version_file = Path(__file__).resolve().parent.parent / "VERSION"
        if version_file.is_file():
            text = version_file.read_text(encoding="utf-8").strip()
            if text:
                return text
    except Exception:
        pass
    return VERSION


def _env(name: str, default: str) -> str:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return val


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


# --- version ------------------------------------------------------------------
VERSION = _read_version()

# Providers use Scrapling's browser automation (no API key). Nothing to configure
# here for them — an engine that gets CAPTCHA-walled just reports "blocked".

# --- base data directory ------------------------------------------------------
# Default ./backend/data resolved relative to this file so it is stable
# regardless of the process working directory.
_DEFAULT_DATA_DIR = str(Path(__file__).resolve().parent / "data")
DATA_DIR: str = os.path.abspath(_env("OMNI_DATA_DIR", _DEFAULT_DATA_DIR))

# --- derived paths ------------------------------------------------------------
DB_PATH: str = os.path.abspath(
    _env("OMNI_DB_PATH", os.path.join(DATA_DIR, "omnividence.db"))
)
THUMB_CACHE_DIR: str = os.path.abspath(
    _env("OMNI_THUMB_CACHE_DIR", os.path.join(DATA_DIR, "thumbs"))
)
INSIGHTFACE_ROOT: str = os.path.abspath(
    _env("OMNI_INSIGHTFACE_ROOT", os.path.join(DATA_DIR, "models"))
)

# --- tunables -----------------------------------------------------------------
MAX_RESULTS_PER_PAGE: int = _env_int("OMNI_MAX_RESULTS_PER_PAGE", 20)
THUMB_TIMEOUT_SEC: int = _env_int("OMNI_THUMB_TIMEOUT_SEC", 10)

# Minimum face-similarity score (0-100) to KEEP a result. Reverse-image engines
# (esp. Bing/Google Lens) return whole-image matches — objects with no face, and
# unrelated strangers. We drop anything with no detectable face and anything
# scoring below this floor, so the grid shows real face matches only.
MIN_SCORE: int = _env_int("OMNI_MIN_SCORE", 50)

# Hard upper bound on an accepted upload (~10MB) — enforced in the route.
MAX_UPLOAD_BYTES: int = _env_int("OMNI_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)

# --- CORS ---------------------------------------------------------------------
_DEFAULT_CORS = "http://localhost:3000"
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in _env("OMNI_CORS_ORIGINS", _DEFAULT_CORS).split(",")
    if o.strip()
]


# --- OMNI_-prefixed aliases ---------------------------------------------------
# api/routes/search.py imports these by their OMNI_* names (matching the env var
# names in the build contract), while services/cache.py and services/face.py use
# the short names above. Expose both so every importer resolves regardless of
# which convention it picked. They are the SAME values — plain aliases.
OMNI_DATA_DIR = DATA_DIR
OMNI_DB_PATH = DB_PATH
OMNI_THUMB_CACHE_DIR = THUMB_CACHE_DIR
OMNI_INSIGHTFACE_ROOT = INSIGHTFACE_ROOT
OMNI_MAX_RESULTS_PER_PAGE = MAX_RESULTS_PER_PAGE
OMNI_THUMB_TIMEOUT_SEC = THUMB_TIMEOUT_SEC
OMNI_MIN_SCORE = MIN_SCORE
OMNI_MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES
OMNI_CORS_ORIGINS = CORS_ORIGINS


def ensure_dirs() -> None:
    """Create the data, thumbnail cache, and model directories if missing.

    Idempotent. Called on startup (and safe to call again). The DB's parent
    directory is also ensured so a custom OMNI_DB_PATH works out of the box.
    """
    for path in (DATA_DIR, THUMB_CACHE_DIR, INSIGHTFACE_ROOT):
        os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)


# Ensure directories exist at import time so any module that reads paths
# (cache.py, face.py) can rely on them being present.
ensure_dirs()
