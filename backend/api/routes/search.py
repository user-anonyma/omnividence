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
  * Never fabricates results. A provider that can't run (browser unavailable,
    blocked by a CAPTCHA/anti-bot wall, or no hits) returns [] plus an honest
    note; the pipeline still runs and reports that state truthfully.
  * No identity claims, never names people; only public URLs returned by providers.
  * The score is always a "face similarity score" in [0,100], never a match
    probability / identity confidence.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import uuid
from typing import Optional

import numpy as np
from fastapi import APIRouter, File, Form, Path, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from config import (
    OMNI_MAX_RESULTS_PER_PAGE,
    OMNI_MIN_SCORE,
    OMNI_THUMB_CACHE_DIR,
)
from providers import get_providers
from services import cache, face, ranking

router = APIRouter()

# Upload guard: ~10MB max as per contract.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Canonical provider names (request 'providers' subset is filtered against these).
KNOWN_PROVIDERS = {"yandex"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _providers_configured() -> list[str]:
    """Provider names that can run (Playwright available) — for /health/metadata."""
    return [p.name for p in get_providers() if p.is_configured()]


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

    page_url = row.get("page_url")
    return {
        "image_url": row.get("image_url"),
        "thumbnail_url": row.get("thumbnail_url"),
        "thumb_url": f"/api/search/{search_id}/thumb/{row.get('id')}",
        "page_url": page_url,
        "page_title": row.get("page_title"),
        "provider": row.get("provider"),
        # Real source of the matched image (derived from the source URL):
        "source_domain": ranking.source_domain(page_url),
        "source_label": ranking.source_label(page_url),
        "source_category": ranking.source_category(page_url),  # instagram/linkedin/.../other
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
    def _score_one(r: dict) -> Optional[dict]:
        image_url = r.get("image_url")
        if not image_url:
            return None
        thumb_path = cache.get_or_download_thumbnail(image_url, r.get("thumbnail_url"))
        score: Optional[int] = None
        if thumb_path:
            emb = face.embed_face(thumb_path)
            if emb is not None:
                score = ranking.to_score(ranking.cosine(query_embedding, emb))
        band = ranking.band_for(score)
        return {
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

    # Download + embed + score with a SMALL pool (2 workers). Downloads are
    # I/O-bound and onnxruntime inference is thread-safe; 2 workers matches a
    # typical small box's core count and roughly halves the embed pass without
    # the thrash a larger pool caused alongside the browsers.
    scored_rows: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for row in ex.map(_score_one, provider_results):
            if row is None:
                continue
            # Keep only real face matches: drop results with no detectable face
            # (objects from whole-image engines) and unrelated strangers below
            # the similarity floor.
            score = row.get("score")
            if score is None or score < OMNI_MIN_SCORE:
                continue
            scored_rows.append(row)

    if not scored_rows:
        return

    # Dedup + rank within this batch (a global re-rank follows in the caller).
    ranked = ranking.rank_and_dedup(scored_rows)
    cache.store_results(search_id, ranked)


def _run_search_bg(
    search_id: str,
    face_path: str,
    requested: Optional[set[str]],
    query_embedding: np.ndarray,
) -> None:
    """Background worker: fan out across providers CONCURRENTLY and write each
    provider's results as soon as it finishes, so the frontend (polling
    GET /api/search/{id}) sees results stream in and a progress bar climb.

    Sequential fan-out costs ~sum of providers (a minute-plus). Concurrent costs
    ~the slowest single provider, and the fast/accurate one (Yandex) lands first.
    Always marks the search 'done' (progress 100) at the end, even on error.
    """
    providers = [
        p for p in get_providers() if requested is None or p.name in requested
    ]
    total = len(providers) or 1
    notes: list[str] = []
    done = 0
    try:
        if providers:
            # Cap concurrency: each provider drives a headless browser, and on a
            # small box (e.g. 2 cores) running 3 at once thrashes and stalls.
            # 2 in flight keeps it responsive; the rest queue.
            max_workers = min(2, len(providers))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futs = {ex.submit(p.search, face_path, None): p for p in providers}
                for fut in concurrent.futures.as_completed(futs):
                    p = futs[fut]
                    try:
                        page = fut.result()
                    except Exception as exc:  # one provider must not break the rest
                        page = {
                            "results": [],
                            "next_cursor": None,
                            "note": f"{p.name}: error ({type(exc).__name__})",
                        }
                    note = page.get("note")
                    if note:
                        notes.append(note)
                    next_cursor = page.get("next_cursor")
                    cache.upsert_cursor(
                        search_id,
                        p.name,
                        next_cursor=next_cursor,
                        page_index=1,
                        exhausted=next_cursor is None,
                    )
                    results = page.get("results") or []
                    for res in results:
                        res.setdefault("provider", p.name)
                    if results:
                        _process_batch(search_id, query_embedding, results)
                        cache.rerank_search(search_id)
                    done += 1
                    # Cap running progress below 100 so 'done' is the only 100%.
                    prog = min(95, round(done / total * 95))
                    cache.set_search_status(
                        search_id, "running", note=notes, progress=prog
                    )
    finally:
        cache.set_search_status(search_id, "done", note=notes, progress=100)


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
        for p in get_providers()
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

    # --- persist the search row as 'running' (cache owns the uuid) ---
    search_id = cache.create_search(
        query_embedding=query_embedding,
        query_face_bbox=bbox,
        query_face_det=det_score,
        query_thumb_path=query_thumb_path,
        providers_used=planned,
        note=[],
        status="running",
        progress=5,
    )

    # --- kick off the provider fan-out in the BACKGROUND and return now ---
    # The browser scraping takes a while; we don't hold the HTTP request open
    # for it (that timed out behind proxies/tunnels). The frontend polls
    # GET /api/search/{id} for streaming results + progress. Send the cropped
    # face JPEG to providers; fall back to a fresh crop if the persist failed.
    face_path = query_thumb_path or _write_temp_face(raw, bbox)
    threading.Thread(
        target=_run_search_bg,
        args=(search_id, face_path, requested, query_embedding),
        daemon=True,
    ).start()

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
            "results": [],
            "providers_used": planned,
            "status": "running",
            "progress": 5,
            "has_more": False,
            "note": [],
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

    for provider in get_providers():
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

    status = search_row.get("status") or "done"
    progress = search_row.get("progress")
    if progress is None:
        progress = 100 if status == "done" else 5

    return JSONResponse(
        status_code=200,
        content={
            "search_id": search_id,
            "created_at": search_row.get("created_at"),
            "query_face": _query_face_payload(search_id, search_row),
            "results": results,
            "providers_used": providers_used,
            "status": status,
            "progress": int(progress),
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
