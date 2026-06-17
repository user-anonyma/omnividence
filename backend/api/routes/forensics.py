"""
backend/api/routes/forensics.py

POST /api/forensics — EXPERIMENTAL, OPTIONAL, never on the search path.

Thin HTTP wrapper around ``services/detection.py``'s ``analyze()`` heuristics.
The whole handler is wrapped so it can NEVER 5xx: on any failure (unreadable
upload, missing dependency, internal error) it returns a clean, honest
``200`` payload with every check labelled ``"unavailable"`` and a note explaining
it could not run. It is mounted defensively in ``main.py`` so even an import
problem here can never affect the search pipeline.

Honesty rules (mirrored from the build contract):
  * Experimental, low-confidence heuristics — NOT evidence, NOT a detector.
  * No identity claims, never names a person, never asserts a verdict as fact.
  * Always returns 200 with the documented shape, even on internal failure.

Response shape (passes ``services.detection.analyze`` through verbatim):

    {
      "experimental": true,
      "confidence": "low",
      "checks": {
        "ai_generated":     {"score": <float 0..1>, "label": <str>},
        "manipulation_ela": {"score": <float 0..1>, "label": <str>},
        "deepfake":         {"score": <float 0..1>, "label": <str>}
      },
      "note": <str>
    }
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()


# Same ~10MB guard as the search upload path; an oversized/empty body just yields
# an honest "unavailable" payload rather than an error.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _unavailable(reason: Optional[str] = None) -> dict:
    """Honest fallback payload (200-shaped) when nothing could be computed."""
    note = (
        "Experimental forensics could not run on this image "
        "(unreadable image or missing dependency). No conclusions drawn."
    )
    if reason:
        note = f"{note} ({reason})"
    return {
        "experimental": True,
        "confidence": "low",
        "checks": {
            "ai_generated": {"score": 0.0, "label": "unavailable"},
            "manipulation_ela": {"score": 0.0, "label": "unavailable"},
            "deepfake": {"score": 0.0, "label": "unavailable"},
        },
        "note": note,
    }


@router.post("/api/forensics")
async def post_forensics(image: UploadFile = File(...)) -> JSONResponse:
    # Read the upload defensively — any failure degrades to a clean payload.
    try:
        raw = await image.read()
    except Exception:
        return JSONResponse(status_code=200, content=_unavailable("could not read upload"))

    if not raw:
        return JSONResponse(status_code=200, content=_unavailable("empty upload"))
    if len(raw) > _MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=200, content=_unavailable("image too large"))

    # Run the experimental heuristics. analyze() never raises, but wrap it anyway
    # so this route can never reach the client as a 5xx.
    try:
        from services import detection

        payload = detection.analyze(raw)
        if not isinstance(payload, dict):
            payload = _unavailable("unexpected heuristics output")
    except Exception:
        payload = _unavailable("unexpected internal error")

    return JSONResponse(status_code=200, content=payload)
