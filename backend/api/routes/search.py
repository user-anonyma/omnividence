"""
backend/api/routes/search.py

The ONLY place in the backend that touches request/response JSON for the search
pipeline. Orchestrates:

    face service (detect + crop largest face)
      -> providers (fan out reverse-image-search of the cropped face)
      -> cache service (download each result thumbnail)
      -> face service (embed each downloaded thumbnail)
      -> ranking service (cosine -> 0-100 score, dedup, rank, bands)
      -> cache service (persist results + provider pagination cursors)

Routes:
    POST /api/search
    GET  /api/search/{search_id}/more
    GET  /api/search/{search_id}
    GET  /api/search/{search_id}/thumb/{result_id}
    GET  /api/search/{search_id}/query-face

Honesty/safety guarantees enforced here:
  * Never fabricates results. With no SERPAPI_KEY every provider returns [] plus a
    "provider not configured" note; the pipeline still runs and reports honestly.
  * No identity claims, never names people; only public URLs returned by providers.
  * The score is always a "face similarity score" in [0,100], never a match
    probability / identity confidence.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Optional

import numpy as np
from fastapi import APIRouter, File, Form, Path, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from config import (
    OMNI_MAX_RESULTS_PER_PAGE,
    OMNI_THUMB_CACHE_DIR,
    SERPAPI_KEY,
)
from providers import get_providers
from services import cache, face, ranking

router = APIRouter()

# Upload guard: ~10MB max as per contract.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Canonical provider names (request 'providers' subset is filtered against these).
KNOWN_PROVIDERS = {"google_lens", "yandex", "bing"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _providers_configured() -> list[str]:
    """Provider names that have a usable SERPAPI_KEY (for /health and metadata)."""
    return [p.name for p in get_providers(SERPAPI_KEY) if p.is_configured()]


def _parse_requested_providers(providers: Optional[str]) -> Optional[set[str]]:
    """Parse the optional comma-separated 'providers' form field.

    Returns None when nothing valid/explicit was requested (=> use all),
    otherwise the set of requested known provider names.
    """
    if not providers:
        return None
    wanted = {p.strip().lower() for p in providers.split(",") if p.strip()}
    wanted &= KNOWN_PROVIDERS
    return wanted or None


def _result_to_json(search_id: str, row: dict) -> dict:
    """Map a stored result row -> the public API result object shape.

    Adds 'thumb_url' (our cached-thumbnail route) and 'band_label' (from the
    single-source-of-truth score bands). Never emits identity wording.
    """
    score = row.get("score")
    band_key = row.get("band")
    band = ranking.band_for(score)
    # Prefer the persisted band, but always derive the label from the band dict
    # so backend and frontend agree verbatim.
    if not band_key:
        band_key = band["key"]
    band_label = band["label"]

    return {
        "image_url": row.get("image_url"),
        "thumbnail_url": row.get("thumbnail_url"),
        "thumb_url": f"/api/search/{search_id}/thumb/{row.get('id')}",
        "page_url": row.get("page_url"),
        "page_title": row.get("page_title"),
        "provider": row.get("provider"),
        "score": score,
        "band": band_key,
        "band_label": band_label,
        "rank": row.get("rank"),
    }


def _query_face_payload(search_id: str, search_row: dict) -> dict:
    """Build the query_face object from a persisted search row."""
    bbox = search_row.get("query_face_bbox")
    if isinstance(bbox, str):
        try:
            bbox = json.loads(bbox)
        except (ValueError, TypeError):
            bbox = None
    return {
        "detected": True,
        "bbox": bbox,
        "det_score": search_row.get("query_face_det"),
        "query_face_url": f"/api/search/{search_id}/query-face",
    }


def _decode_notes(raw) -> list[str]:
    """search.note is persisted as a JSON array string; decode defensively."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, list) else [raw]
        except (ValueError, TypeError):
            return [raw]
    return []


def _process_batch(
    search_id: str,
    query_embedding: np.ndarray,
    provider_results: list[dict],
) -> None:
    """Download + embed + score a batch of raw provider results, then persist.

    provider_results items are normalized ProviderResult dicts (image_url,
    thumbnail_url, page_url, page_title, provider). For each:
      1) download a thumbnail to the on-disk cache (never raises),
      2) embed the largest face in that thumbnail,
      3) cosine(query, result) -> 0-100 score (None if no face / no thumb),
      4) attach band.
    Then dedup+rank the batch and store. A full re-rank over ALL results of the
    search happens afterwards in the caller.
    """
    scored_rows: list[dict] = []
    for r in provider_results:
        image_url = r.get("image_url")
        if not image_url:
            continue

        thumb_path = cache.get_or_download_thumbnail(
            image_url, r.get("thumbnail_url")
        )

        score: Optional[int] = None
        if thumb_path:
            emb = face.embed_face(thumb_path)
            if emb is not None:
                cos = ranking.cosine(query_embedding, emb)
                score = ranking.to_score(cos)

        band = ranking.band_for(score)
        scored_rows.append(
            {
                "image_url": image_url,
                "thumbnail_url": r.get("thumbnail_url"),
                "thumb_path": thumb_path,
                "page_url": r.get("page_url"),
                "page_title": r.get("page_title"),
                "provider": r.get("provider"),
                "score": score,
                "band": band["key"],
                "returned": 0,
            }
        )

    if not scored_rows:
        return

    # Dedup + rank within this batch (a global re-rank follows in the caller).
    ranked = ranking.rank_and_dedup(scored_rows)
    cache.store_results(search_id, ranked)


def _fan_out_first_page(
    face_path: str,
    requested: Optional[set[str]],
    query_embedding: np.ndarray,
    search_id: str,
) -> tuple[list[str], list[str]]:
    """First-page fan-out across providers for an already-created search.

    Persists provider cursors and processes the downloaded batch. Returns
    (providers_used, notes).
    """
    providers_used: list[str] = []
    notes: list[str] = []
    batch: list[dict] = []

    for provider in get_providers(SERPAPI_KEY):
        if requested is not None and provider.name not in requested:
            continue
        providers_used.append(provider.name)

        page = provider.search(face_path, cursor=None)
        note = page.get("note")
        if note:
            notes.append(note)

        next_cursor = page.get("next_cursor")
        cache.upsert_cursor(
            search_id,
            provider.name,
            next_cursor=next_cursor,
            page_index=1,
            exhausted=next_cursor is None,
        )

        for res in page.get("results", []) or []:
            res.setdefault("provider", provider.name)
            batch.append(res)

    if batch:
        _process_batch(search_id, query_embedding, batch)

    return providers_used, notes


# --------------------------------------------------------------------------- #
# POST /api/search
# --------------------------------------------------------------------------- #
@router.post("/api/search")
async def post_search(
    image: UploadFile = File(...),
    providers: Optional[str] = Form(default=None),
):
    # --- read + validate upload ---
    try:
        raw = await image.read()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_image", "message": "Could not read the uploaded file."},
        )

    if not raw:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_image", "message": "The uploaded file was empty."},
        )
    if len(raw) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_image",
                "message": "Image is too large (max 10MB).",
            },
        )

    # --- detect the largest face in the upload ---
    try:
        detected = face.detect_largest_face(raw)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_image",
                "message": "The uploaded file could not be processed as an image.",
            },
        )

    if detected is None:
        return JSONResponse(
            status_code=422,
            content={
                "error": "no_face_detected",
                "message": "No face was detected in the uploaded image.",
                "query_face": {"detected": False},
            },
        )

    bbox = [int(v) for v in detected["bbox"]]
    det_score = float(detected["det_score"])
    query_embedding = np.asarray(detected["embedding"], dtype=np.float32)

    requested = _parse_requested_providers(providers)

    # Determine which providers we'll actually query (for providers_used metadata
    # in the searches row).
    planned = [
        p.name
        for p in get_providers(SERPAPI_KEY)
        if requested is None or p.name in requested
    ]

    # --- crop the largest face to a JPEG; this same image is sent to providers
    #     AND saved as the search's query_thumb_path. Use a unique filename
    #     (the search_id is owned by cache.create_search). ---
    query_thumb_path = os.path.join(
        OMNI_THUMB_CACHE_DIR, f"query_{uuid.uuid4().hex}.jpg"
    )
    try:
        face.crop_face_jpeg(raw, bbox, query_thumb_path)
    except Exception:
        query_thumb_path = None  # honest: query-face image just won't be available

    # --- persist the search row (cache owns the uuid) ---
    search_id = cache.create_search(
        query_embedding=query_embedding,
        query_face_bbox=bbox,
        query_face_det=det_score,
        query_thumb_path=query_thumb_path,
        providers_used=planned,
        note=[],
    )

    # --- fan out across providers, download/embed/score, persist ---
    # Send the cropped face JPEG to providers; fall back to a fresh crop if the
    # persisted one is unavailable.
    face_path = query_thumb_path or _write_temp_face(raw, bbox)
    providers_used, notes = _fan_out_first_page(
        face_path,
        requested,
        query_embedding,
        search_id,
    )

    # --- global re-rank across everything stored for this search ---
    cache.rerank_search(search_id)

    # --- collect this page of (unreturned) results ---
    rows = cache.get_results(
        search_id, only_unreturned=True, limit=OMNI_MAX_RESULTS_PER_PAGE
    )
    cache.mark_returned(search_id, [row["id"] for row in rows if row.get("id") is not None])

    results = [_result_to_json(search_id, row) for row in rows]
    has_more = cache.any_more_available(search_id)

    return JSONResponse(
        status_code=200,
        content={
            "search_id": search_id,
            "query_face": {
                "detected": True,
                "bbox": bbox,
                "det_score": det_score,
                "query_face_url": f"/api/search/{search_id}/query-face",
            },
            "results": results,
            "providers_used": providers_used,
            "has_more": has_more,
            "note": notes,
        },
    )


def _write_temp_face(raw: bytes, bbox: list[int]) -> str:
    """Fallback crop path if the primary query-face crop failed to persist.

    Returns a path to a cropped face JPEG suitable for sending to providers.
    """
    tmp_path = os.path.join(OMNI_THUMB_CACHE_DIR, f"query_tmp_{uuid.uuid4().hex}.jpg")
    try:
        face.crop_face_jpeg(raw, bbox, tmp_path)
        return tmp_path
    except Exception:
        return tmp_path  # providers handle missing/unreadable file by returning [] + note


# --------------------------------------------------------------------------- #
# GET /api/search/{search_id}/more
# --------------------------------------------------------------------------- #
@router.get("/api/search/{search_id}/more")
async def get_more(search_id: str = Path(...)):
    search_row = cache.get_search(search_id)
    if search_row is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Unknown search_id."},
        )

    query_embedding = np.asarray(search_row["query_embedding"], dtype=np.float32)
    face_path = search_row.get("query_thumb_path")

    cursors = cache.get_cursors(search_id)
    providers_used: list[str] = []
    notes: list[str] = []
    batch: list[dict] = []

    for provider in get_providers(SERPAPI_KEY):
        state = cursors.get(provider.name)
        if state is None:
            # Provider was never part of this search; skip it.
            continue
        if state.get("exhausted"):
            continue

        providers_used.append(provider.name)
        saved_cursor = state.get("next_cursor")

        page = provider.search(face_path, cursor=saved_cursor)
        note = page.get("note")
        if note:
            notes.append(note)

        next_cursor = page.get("next_cursor")
        page_index = int(state.get("page_index", 0)) + 1
        cache.upsert_cursor(
            search_id,
            provider.name,
            next_cursor=next_cursor,
            page_index=page_index,
            exhausted=next_cursor is None,
        )

        for res in page.get("results", []) or []:
            res.setdefault("provider", provider.name)
            batch.append(res)

    if batch:
        _process_batch(search_id, query_embedding, batch)

    # Re-rank the WHOLE search so the new batch interleaves correctly.
    cache.rerank_search(search_id)

    rows = cache.get_results(
        search_id, only_unreturned=True, limit=OMNI_MAX_RESULTS_PER_PAGE
    )
    cache.mark_returned(search_id, [row["id"] for row in rows if row.get("id") is not None])

    results = [_result_to_json(search_id, row) for row in rows]
    has_more = cache.any_more_available(search_id)

    return JSONResponse(
        status_code=200,
        content={
            "search_id": search_id,
            "results": results,
            "has_more": has_more,
            "providers_used": providers_used,
            "note": notes,
        },
    )


# --------------------------------------------------------------------------- #
# GET /api/search/{search_id}
# --------------------------------------------------------------------------- #
@router.get("/api/search/{search_id}")
async def get_search(
    search_id: str = Path(...),
    provider: Optional[str] = Query(default=None),
    band: Optional[str] = Query(default=None),
    sort: str = Query(default="score_desc"),
):
    search_row = cache.get_search(search_id)
    if search_row is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Unknown search_id."},
        )

    rows = cache.get_results(search_id, only_unreturned=False)

    # --- client-mirroring filters (provider, band) ---
    if provider and provider != "all":
        rows = [r for r in rows if r.get("provider") == provider]
    if band and band != "all":
        rows = [r for r in rows if (r.get("band") or ranking.band_for(r.get("score"))["key"]) == band]

    # --- sort (default score_desc); rows already come rank-ordered (score desc) ---
    if sort == "score_asc":
        rows = sorted(
            rows,
            key=lambda r: (
                r.get("score") if r.get("score") is not None else 10**9,
                r.get("provider") or "",
                r.get("image_url") or "",
            ),
        )
    # score_desc => keep rank order from cache.get_results (rank asc == score desc).

    results = [_result_to_json(search_id, row) for row in rows]

    providers_used = search_row.get("providers_used")
    if isinstance(providers_used, str):
        try:
            providers_used = json.loads(providers_used)
        except (ValueError, TypeError):
            providers_used = [providers_used] if providers_used else []
    providers_used = providers_used or []

    return JSONResponse(
        status_code=200,
        content={
            "search_id": search_id,
            "created_at": search_row.get("created_at"),
            "query_face": _query_face_payload(search_id, search_row),
            "results": results,
            "providers_used": providers_used,
            "has_more": cache.any_more_available(search_id),
            "note": _decode_notes(search_row.get("note")),
        },
    )


# --------------------------------------------------------------------------- #
# GET /api/search/{search_id}/thumb/{result_id}
# --------------------------------------------------------------------------- #
@router.get("/api/search/{search_id}/thumb/{result_id}")
async def get_thumb(search_id: str = Path(...), result_id: int = Path(...)):
    if cache.get_search(search_id) is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Unknown search_id."},
        )

    rows = cache.get_results(search_id, only_unreturned=False)
    row = next((r for r in rows if r.get("id") == result_id), None)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Unknown result."},
        )

    thumb_path = row.get("thumb_path")
    if thumb_path and os.path.isfile(thumb_path):
        return FileResponse(thumb_path, media_type="image/jpeg")

    # Not cached on disk -> fall back to the provider thumbnail URL if present.
    thumbnail_url = row.get("thumbnail_url")
    if thumbnail_url:
        return RedirectResponse(url=thumbnail_url, status_code=302)

    return JSONResponse(
        status_code=404,
        content={"error": "not_found", "message": "Thumbnail not available."},
    )


# --------------------------------------------------------------------------- #
# GET /api/search/{search_id}/query-face
# --------------------------------------------------------------------------- #
@router.get("/api/search/{search_id}/query-face")
async def get_query_face(search_id: str = Path(...)):
    search_row = cache.get_search(search_id)
    if search_row is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Unknown search_id."},
        )

    thumb_path = search_row.get("query_thumb_path")
    if thumb_path and os.path.isfile(thumb_path):
        return FileResponse(thumb_path, media_type="image/jpeg")

    return JSONResponse(
        status_code=404,
        content={"error": "not_found", "message": "Query face image not available."},
    )
