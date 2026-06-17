"""Omnividence backend — FastAPI application entrypoint.

School FACE-SIMILARITY SEARCH demo (NOT identity / surveillance). This module:

  * builds the FastAPI app and configures CORS for the Next.js origin,
  * runs startup init (cache.init_db() + face.init_model()),
  * mounts the search router (api/routes/search.py) and the optional/
    experimental forensics router (api/routes/forensics.py),
  * mounts the on-disk thumbnail cache as static files (convenience mount;
    the API also serves thumbnails via /api/search/{id}/thumb/{result_id}),
  * exposes /health and /version,
  * binds 127.0.0.1:8000 when run directly. Local-only, no Docker.

HONESTY: providers drive real public pages via Scrapling's browser (no API key).
If one is blocked by a CAPTCHA/anti-bot wall it reports "blocked" and the
pipeline still runs and reports honestly. Scores are always a "face similarity
score" (0-100), never a match/identity probability.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import config

logger = logging.getLogger("omnividence")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Omnividence",
    version=config.VERSION,
    description=(
        "School face-similarity search demo. Results are approximate visual "
        "similarity matches and do not confirm identity."
    ),
)

# --- CORS: allow only the configured Next.js origin(s) ------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- startup: ensure dirs, init DB, lazy-load the face model ------------------
@app.on_event("startup")
def _on_startup() -> None:
    config.ensure_dirs()

    # Imported lazily so the module imports cleanly even if a sibling file is
    # still being written by a parallel agent; startup will surface real errors.
    try:
        from services import cache

        cache.init_db()
        logger.info("SQLite initialized at %s", config.DB_PATH)
    except Exception:  # pragma: no cover - defensive startup logging
        logger.exception("Failed to initialize the database")
        raise

    try:
        from services import face

        face.init_model()
        logger.info("InsightFace model ready (root=%s)", config.INSIGHTFACE_ROOT)
    except Exception:  # pragma: no cover
        # Do not crash the whole app if the model pack download/load fails;
        # the search route will report the failure honestly per-request.
        logger.exception("Face model failed to load at startup (will retry lazily)")


# --- routers ------------------------------------------------------------------
# search.py is the ONLY place that touches request/response JSON for the search
# pipeline (POST /api/search, /more, GET /api/search/{id}, /thumb, /query-face).
from api.routes import search as search_routes  # noqa: E402

app.include_router(search_routes.router)

# forensics.py is OPTIONAL + EXPERIMENTAL and wrapped so it can never block or
# fail the search path. Mount it defensively: if the module is unavailable the
# rest of the app still serves.
try:
    from api.routes import forensics as forensics_routes  # noqa: E402

    app.include_router(forensics_routes.router)
except Exception:  # pragma: no cover
    logger.exception("Forensics router unavailable; continuing without it")


# --- static thumbnail cache (convenience mount) -------------------------------
# Files are stored as <sha256(image_url)>.jpg under OMNI_THUMB_CACHE_DIR. The
# canonical way to fetch a result thumbnail is the API route
# /api/search/{id}/thumb/{result_id}; this static mount exposes the raw cache
# directory for debugging / direct access and never overlaps the /api routes.
os.makedirs(config.THUMB_CACHE_DIR, exist_ok=True)
app.mount(
    "/static/thumbs",
    StaticFiles(directory=config.THUMB_CACHE_DIR, check_dir=False),
    name="thumbs",
)


# --- health / version ---------------------------------------------------------
def _providers_configured() -> list[str]:
    """Names of providers that can run (Scrapling's browser is available).

    Imported lazily and guarded so /health stays up even mid-build.
    """
    try:
        from providers import get_providers

        return [p.name for p in get_providers() if p.is_configured()]
    except Exception:
        return []


def _model_loaded() -> bool:
    try:
        from services import face

        getter = getattr(face, "is_loaded", None)
        if callable(getter):
            return bool(getter())
        # Fall back to probing a module-level model handle if exposed.
        for attr in ("_model", "MODEL", "model"):
            if getattr(face, attr, None) is not None:
                return True
    except Exception:
        return False
    return False


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": config.VERSION,
            "model_loaded": _model_loaded(),
            "providers_configured": _providers_configured(),
        }
    )


@app.get("/version")
def version() -> JSONResponse:
    return JSONResponse({"version": config.VERSION})


if __name__ == "__main__":
    import uvicorn

    # Local-only bind. No Docker. Reload off by default for a clean demo run.
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=bool(os.environ.get("OMNI_RELOAD")),
    )
