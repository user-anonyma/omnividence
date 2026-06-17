"""
Omnividence - Flask Backend API
================================

Local-only face-recognition reverse-image-search REST backend.

Canonical data flow:
    image -> face_engine (InsightFace buffalo_l detect + ArcFace embed, 512-d
    float32 L2-normalized)
          -> faiss_index (IndexFlatIP exact cosine search + SQLite metadata)
          -> app.py (this file: Flask REST)
          -> React frontend.

Key contract points honored here:
  * face_engine.extract_faces() returns a FaceExtractionResult OBJECT
    (.status, .faces), NOT a bare list. We read result.faces.
  * faiss_index is FAISSIndex with a FLAT IP API. Scores from .search() are
    cosine similarity in [-1, 1] DIRECTLY (NO "1 - dist" conversion).
  * ONE-STEP search flow: POST /api/search with a multipart image returns a
    FLAT results array at response.data.results.
  * Fixed on-disk persistence under <repo>/data/ (FAISS index + SQLite) so the
    index survives restarts.
  * External reverse search is an explicit no-op stub (never fabricated).
  * Detection forensics are EXPERIMENTAL, optional (?detect=true), and wrapped
    so they can never block or fail the search path.

Envelope:
    success_response -> {success:true, message, data, timestamp}
    error_response   -> {success:false, error, error_code, timestamp}

Local only: binds 127.0.0.1:5000. No Docker.

Author: Omnividence
License: MIT
"""

import os
import json
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

# Face recognition modules (sole producers of the contract interfaces).
try:
    from face_engine import FaceEngine, Face, FaceDetectionStatus  # noqa: F401
    from faiss_index import FAISSIndex
except ImportError as exc:  # pragma: no cover - import guard
    print(f"Error importing face recognition modules: {exc}")
    raise

# ============================================================================
# Flask application setup
# ============================================================================

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50MB max upload
    JSON_SORT_KEYS=False,
    JSONIFY_PRETTYPRINT_REGULAR=False,
)

# CORS for the local React dev server (both localhost and 127.0.0.1).
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "max_age": 3600,
        },
        r"/health": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
            "methods": ["GET", "OPTIONS"],
        },
    },
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/omnividence_api.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================================
# Constants & persistence paths
# ============================================================================

# DATA_DIR is fixed under the repo (NOT /tmp) so the index + DB survive restarts.
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Uploads and result cache are ephemeral and may live in /tmp.
UPLOAD_FOLDER = Path("/tmp/omnividence_uploads")
CACHE_FOLDER = Path("/tmp/omnividence_cache")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
CACHE_FOLDER.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp"}
DEFAULT_THRESHOLD = 0.35  # LFW cross-photo same-identity often 0.4-0.7.
MAX_RESULTS = 100
DEFAULT_TOP_K = 10
MAX_BATCH = 100
CACHE_EXPIRY_HOURS = 24

EMBEDDING_DIM = 512

# ============================================================================
# Lazy singletons
# ============================================================================

_face_engine: Optional[FaceEngine] = None
_faiss_index: Optional[FAISSIndex] = None


def get_face_engine() -> FaceEngine:
    """Lazily construct the InsightFace engine (CPU-only by default)."""
    global _face_engine
    if _face_engine is None:
        logger.info("Initializing FaceEngine...")
        _face_engine = FaceEngine(use_gpu=False)
        logger.info("FaceEngine initialized.")
    return _face_engine


def get_faiss_index() -> FAISSIndex:
    """Lazily construct the FAISS index (rehydrates from disk on first use)."""
    global _faiss_index
    if _faiss_index is None:
        logger.info("Initializing FAISSIndex...")
        _faiss_index = FAISSIndex(
            embedding_dim=EMBEDDING_DIM,
            index_path=str(DATA_DIR / "faiss.index"),
        )
        logger.info("FAISSIndex initialized (size=%d).", _faiss_index.size)
    return _faiss_index


# ============================================================================
# Response helpers
# ============================================================================

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def success_response(data: Any, status_code: int = 200, message: str = "Success"):
    """Standard success envelope: {success:true, message, data, timestamp}."""
    return (
        jsonify(
            {
                "success": True,
                "message": message,
                "data": data,
                "timestamp": _now_iso(),
            }
        ),
        status_code,
    )


def error_response(error: str, status_code: int = 400, error_code: str = "ERROR"):
    """Standard error envelope: {success:false, error, error_code, timestamp}."""
    return (
        jsonify(
            {
                "success": False,
                "error": error,
                "error_code": error_code,
                "timestamp": _now_iso(),
            }
        ),
        status_code,
    )


# ============================================================================
# Utilities
# ============================================================================

def allowed_file(filename: Optional[str]) -> bool:
    return bool(filename) and "." in filename and \
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_request_id() -> str:
    return f"{uuid.uuid4().hex[:16]}_{int(datetime.utcnow().timestamp() * 1000)}"


def save_uploaded_file(file) -> Tuple[str, str]:
    """
    Persist an uploaded FileStorage to UPLOAD_FOLDER.

    Returns (file_path, file_hash). Raises BadRequest on invalid input.
    """
    if not file or file.filename == "":
        raise BadRequest("No file provided")
    if not allowed_file(file.filename):
        raise BadRequest(
            f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    content = file.read()
    file.seek(0)
    if not content:
        raise BadRequest("Uploaded file is empty")

    file_hash = hashlib.md5(content).hexdigest()
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    safe_name = f"{name}_{file_hash[:8]}{ext}"
    file_path = UPLOAD_FOLDER / safe_name
    with open(file_path, "wb") as fh:
        fh.write(content)

    logger.info("File saved: %s (hash=%s)", file_path, file_hash[:8])
    return str(file_path), file_hash


def parse_threshold(default: float = DEFAULT_THRESHOLD) -> float:
    value = float(request.form.get("threshold", default))
    if not 0.0 <= value <= 1.0:
        raise BadRequest("threshold must be between 0 and 1")
    return value


def parse_top_k(default: int = DEFAULT_TOP_K) -> int:
    value = int(request.form.get("top_k", default))
    if not 1 <= value <= MAX_RESULTS:
        raise BadRequest(f"top_k must be between 1 and {MAX_RESULTS}")
    return value


def cache_result(request_id: str, data: Dict[str, Any]) -> None:
    cache_file = CACHE_FOLDER / f"{request_id}.json"
    payload = {
        "timestamp": _now_iso(),
        "data": data,
        "expires_at": (datetime.utcnow() + timedelta(hours=CACHE_EXPIRY_HOURS)).isoformat(),
    }
    try:
        with open(cache_file, "w") as fh:
            json.dump(payload, fh)
    except Exception as exc:  # pragma: no cover - non-fatal
        logger.warning("Failed to cache %s: %s", request_id, exc)


def load_cached_result(request_id: str) -> Optional[Dict[str, Any]]:
    cache_file = CACHE_FOLDER / f"{request_id}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r") as fh:
            payload = json.load(fh)
        if datetime.utcnow() > datetime.fromisoformat(payload["expires_at"]):
            cache_file.unlink(missing_ok=True)
            return None
        return payload["data"]
    except Exception as exc:
        logger.error("Error loading cache %s: %s", request_id, exc)
        return None


def count_cache_entries() -> int:
    try:
        return len(list(CACHE_FOLDER.glob("*.json")))
    except Exception:
        return 0


def external_block() -> Dict[str, Any]:
    """
    External reverse-search stub. NEVER fabricates results.

    Returns an empty result set with a note. Only labels itself as configured
    (experimental) when OMNIVIDENCE_SERPAPI_KEY is set; even then we return no
    fabricated matches (true external integration is out of scope for v1).
    """
    configured = bool(os.getenv("OMNIVIDENCE_SERPAPI_KEY"))
    return {
        "configured": configured,
        "note": (
            "experimental external results (no external matches produced in v1)"
            if configured
            else "external reverse search not configured"
        ),
        "results": [],
    }


def run_forensics(image_path: str) -> Optional[Dict[str, Any]]:
    """
    Optional, EXPERIMENTAL image forensics. Wrapped so it can never raise into
    the search path. Returns None on any failure or if the module is absent.
    """
    try:
        from detection import DetectionEngine
    except Exception as exc:
        logger.info("Detection module unavailable: %s", exc)
        return None
    try:
        summary = DetectionEngine().get_summary(image_path)
        if isinstance(summary, dict):
            summary.setdefault("experimental", True)
        return summary
    except Exception as exc:
        logger.warning("Forensics failed (non-fatal): %s", exc)
        return {
            "experimental": True,
            "reliability": "low",
            "error": str(exc),
            "disclaimer": (
                "Heuristic forensics — low confidence, not court-grade, "
                "do not rely on for decisions."
            ),
        }


def build_match(
    idx: int,
    score: float,
    faiss_index: FAISSIndex,
    query_face_idx: int,
    host_url: str,
) -> Dict[str, Any]:
    """
    Build a single FLAT match object joining FAISS position -> SQLite metadata.

    score is cosine similarity in [-1, 1] taken DIRECTLY from IndexFlatIP.
    thumbnail_url / image_url are ABSOLUTE so SearchResults <img> renders.
    """
    meta = faiss_index.get_metadata(int(idx)) or {}
    image_url = f"{host_url}api/image/{int(idx)}"
    return {
        "id": int(idx),
        "similarity": float(score),
        "match_score": float(score * 100.0),
        "source": meta.get("source") or "local",
        "source_type": meta.get("source_type") or "public_databases",
        "source_url": meta.get("source_url"),
        "thumbnail_url": image_url,
        "image_url": image_url,
        "label": meta.get("label"),
        "query_face_idx": int(query_face_idx),
        "metadata": meta.get("metadata") or {},
    }


def search_one_image(
    file_path: str,
    threshold: float,
    top_k: int,
    host_url: str,
    sources_filter: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    """
    Core search for a single image. Returns (flat_matches, query_face_count, note).

    note is one of: None, 'no_faces_detected', 'index_empty'.
    Matches across ALL query faces are flattened, filtered by threshold and the
    optional source bucket filter, sorted by similarity desc, and sliced to top_k.
    """
    engine = get_face_engine()
    result = engine.extract_faces(file_path)

    if result.status != FaceDetectionStatus.SUCCESS or not result.faces:
        return [], 0, "no_faces_detected"

    faiss_index = get_faiss_index()
    if faiss_index.size == 0:
        return [], len(result.faces), "index_empty"

    k = min(top_k, faiss_index.size)
    collected: List[Dict[str, Any]] = []

    for face_idx, face in enumerate(result.faces):
        scores, indices = faiss_index.search(face.embedding.reshape(1, -1), k=k)
        for score, idx in zip(scores[0], indices[0]):
            if int(idx) == -1:
                continue
            if float(score) < threshold:
                continue
            match = build_match(int(idx), float(score), faiss_index, face_idx, host_url)
            if sources_filter and match["source"] not in sources_filter:
                continue
            collected.append(match)

    collected.sort(key=lambda m: m["similarity"], reverse=True)
    return collected[:top_k], len(result.faces), None


# ============================================================================
# Health
# ============================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Liveness + component readiness. Served at ORIGIN root /health."""
    status = "healthy"
    components = {"api": "ok", "face_engine": "checking", "faiss_index": "checking"}

    try:
        get_face_engine()
        components["face_engine"] = "ok"
    except Exception as exc:
        components["face_engine"] = f"error: {exc}"
        status = "degraded"

    try:
        get_faiss_index()
        components["faiss_index"] = "ok"
    except Exception as exc:
        components["faiss_index"] = f"error: {exc}"
        status = "degraded"

    body = {
        "status": status,
        "components": components,
        "version": _version(),
        "timestamp": _now_iso(),
    }
    return jsonify(body), (200 if status == "healthy" else 503)


def _version() -> str:
    try:
        return (Path(__file__).resolve().parent / "VERSION").read_text().strip()
    except Exception:
        return "0.0.0"


# ============================================================================
# POST /api/search  (PRIMARY one-step endpoint)
# ============================================================================

@app.route("/api/search", methods=["POST"])
def search():
    request_id = generate_request_id()
    start = datetime.utcnow()
    try:
        if "image" not in request.files:
            raise BadRequest("No image file provided (field 'image')")

        file = request.files["image"]
        threshold = parse_threshold()
        top_k = parse_top_k()
        detect = request.form.get("detect", "false").lower() == "true"
        sources_filter = request.form.getlist("sources") or None

        file_path, file_hash = save_uploaded_file(file)
        logger.info(
            "[%s] search: threshold=%.3f top_k=%d detect=%s",
            request_id, threshold, top_k, detect,
        )

        results, query_face_count, note = search_one_image(
            file_path, threshold, top_k, request.host_url, sources_filter
        )

        forensics = run_forensics(file_path) if detect else None

        elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000.0
        data = {
            "request_id": request_id,
            "query_face_count": query_face_count,
            "results": results,
            "external": external_block(),
            "forensics": forensics,
            "query_time_ms": round(elapsed_ms, 2),
        }
        if note:
            data["note"] = note

        cache_result(request_id, data)
        message = note or "Search completed"
        return success_response(data, message=message)

    except BadRequest as exc:
        return error_response(str(exc), 400, "INVALID_REQUEST")
    except RequestEntityTooLarge:
        return error_response("File too large (max 50MB)", 413, "FILE_TOO_LARGE")
    except Exception as exc:
        logger.error("[%s] search error: %s", request_id, exc, exc_info=True)
        return error_response(f"Search failed: {exc}", 500, "SEARCH_ERROR")


# ============================================================================
# POST /api/batch
# ============================================================================

@app.route("/api/batch", methods=["POST"])
def batch():
    batch_id = generate_request_id()
    start = datetime.utcnow()
    try:
        files = request.files.getlist("images")
        if not files:
            raise BadRequest("No images provided (field 'images')")
        if len(files) > MAX_BATCH:
            raise BadRequest(f"Maximum {MAX_BATCH} images per batch")

        threshold = parse_threshold()
        top_k = parse_top_k()

        results: List[Dict[str, Any]] = []
        processed = 0
        failed = 0

        for file in files:
            name = file.filename or "unknown"
            try:
                if not allowed_file(file.filename):
                    results.append(
                        {"image_name": name, "status": "error",
                         "matches": [], "error": "Invalid file type"}
                    )
                    failed += 1
                    continue

                file_path, _ = save_uploaded_file(file)
                matches, _, note = search_one_image(
                    file_path, threshold, top_k, request.host_url
                )

                if note == "no_faces_detected":
                    results.append(
                        {"image_name": name, "status": "no_faces",
                         "matches": [], "error": None}
                    )
                    processed += 1
                elif note == "index_empty":
                    results.append(
                        {"image_name": name, "status": "index_empty",
                         "matches": [], "error": None}
                    )
                    processed += 1
                else:
                    results.append(
                        {"image_name": name, "status": "success",
                         "matches": matches, "error": None}
                    )
                    processed += 1
            except Exception as exc:
                logger.error("[%s] batch item %s error: %s", batch_id, name, exc)
                results.append(
                    {"image_name": name, "status": "error",
                     "matches": [], "error": str(exc)}
                )
                failed += 1

        elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000.0
        data = {
            "batch_id": batch_id,
            "total_images": len(files),
            "processed": processed,
            "failed": failed,
            "results": results,
            "batch_time_ms": round(elapsed_ms, 2),
        }
        cache_result(batch_id, data)
        return success_response(data, message="Batch completed")

    except BadRequest as exc:
        return error_response(str(exc), 400, "INVALID_REQUEST")
    except Exception as exc:
        logger.error("[%s] batch error: %s", batch_id, exc, exc_info=True)
        return error_response(f"Batch failed: {exc}", 500, "BATCH_ERROR")


# ============================================================================
# POST /api/index  (runtime indexing)
# ============================================================================

@app.route("/api/index", methods=["POST"])
def index_faces():
    batch_id = generate_request_id()
    try:
        files = request.files.getlist("images")
        if not files:
            raise BadRequest("No images provided (field 'images')")
        if len(files) > MAX_BATCH:
            raise BadRequest(f"Maximum {MAX_BATCH} images per batch")

        label = request.form.get("label")
        source_url = request.form.get("source_url")
        source = request.form.get("source", "local")
        source_type = request.form.get("source_type", "public_databases")

        engine = get_face_engine()
        faiss_index = get_faiss_index()

        results: List[Dict[str, Any]] = []
        indexed_faces = 0
        failed = 0

        for file in files:
            name = file.filename or "unknown"
            try:
                if not allowed_file(file.filename):
                    results.append(
                        {"image_name": name, "face_count": 0,
                         "indexed_ids": [], "error": "Invalid file type"}
                    )
                    failed += 1
                    continue

                file_path, file_hash = save_uploaded_file(file)
                extraction = engine.extract_faces(file_path)

                if extraction.status != FaceDetectionStatus.SUCCESS or not extraction.faces:
                    results.append(
                        {"image_name": name, "face_count": 0,
                         "indexed_ids": [], "error": "No faces detected"}
                    )
                    failed += 1
                    continue

                indexed_ids: List[int] = []
                for face in extraction.faces:
                    bb = face.bounding_box
                    new_id = faiss_index.add_vector(
                        face.embedding,
                        metadata={
                            "label": label,
                            "image_path": os.path.abspath(file_path),
                            "source_url": source_url,
                            "source": source,
                            "source_type": source_type,
                            "det_score": float(face.confidence),
                            "bbox": (bb.x1, bb.y1, bb.x2, bb.y2),
                            "file_hash": file_hash,
                            "timestamp": _now_iso(),
                        },
                    )
                    indexed_ids.append(int(new_id))
                    indexed_faces += 1

                results.append(
                    {"image_name": name, "face_count": len(extraction.faces),
                     "indexed_ids": indexed_ids, "error": None}
                )
            except Exception as exc:
                logger.error("[%s] index item %s error: %s", batch_id, name, exc)
                results.append(
                    {"image_name": name, "face_count": 0,
                     "indexed_ids": [], "error": str(exc)}
                )
                failed += 1

        # Persist once after the whole batch (perf).
        faiss_index.save()

        data = {
            "batch_id": batch_id,
            "total_images": len(files),
            "indexed_faces": indexed_faces,
            "failed": failed,
            "index_size": faiss_index.size,
            "results": results,
        }
        return success_response(data, status_code=201, message="Indexing completed")

    except BadRequest as exc:
        return error_response(str(exc), 400, "INVALID_REQUEST")
    except Exception as exc:
        logger.error("[%s] index error: %s", batch_id, exc, exc_info=True)
        return error_response(f"Indexing failed: {exc}", 500, "INDEXING_ERROR")


# ============================================================================
# GET /api/results/<request_id>
# ============================================================================

@app.route("/api/results/<request_id>", methods=["GET"])
def get_results(request_id: str):
    cached = load_cached_result(request_id)
    if cached is None:
        return error_response("Results not found", 404, "NOT_FOUND")
    return success_response(cached, message="Results retrieved")


# ============================================================================
# GET /api/stats
# ============================================================================

@app.route("/api/stats", methods=["GET"])
def get_stats():
    try:
        faiss_index = get_faiss_index()
        index_stats = faiss_index.get_stats()
        data = {
            "index_size": index_stats.get("index_size", faiss_index.size),
            "total_faces": index_stats.get("total_faces", faiss_index.size),
            "embedding_dim": index_stats.get("embedding_dim", EMBEDDING_DIM),
            "index_type": index_stats.get("index_type", "IndexFlatIP"),
            "metric": index_stats.get("metric", "cosine"),
            "distinct_labels": index_stats.get("distinct_labels", 0),
            "cache_entries": count_cache_entries(),
            "data_dir": str(DATA_DIR),
        }
        return success_response(data, message="Statistics retrieved")
    except Exception as exc:
        logger.error("stats error: %s", exc, exc_info=True)
        return error_response(f"Failed to retrieve stats: {exc}", 500, "STATS_ERROR")


# ============================================================================
# GET /api/sources
# ============================================================================

@app.route("/api/sources", methods=["GET"])
def get_sources():
    try:
        faiss_index = get_faiss_index()
        return success_response(faiss_index.get_sources(), message="Sources retrieved")
    except Exception as exc:
        logger.error("sources error: %s", exc, exc_info=True)
        return error_response(f"Failed to retrieve sources: {exc}", 500, "SOURCES_ERROR")


# ============================================================================
# GET /api/image/<faiss_id>
# ============================================================================

@app.route("/api/image/<int:faiss_id>", methods=["GET"])
def get_image(faiss_id: int):
    try:
        faiss_index = get_faiss_index()
        meta = faiss_index.get_metadata(int(faiss_id))
        if not meta:
            return error_response("Image not found", 404, "NOT_FOUND")
        image_path = meta.get("image_path")
        if not image_path or not os.path.exists(image_path):
            return error_response("Source image file missing", 404, "FILE_MISSING")
        return send_file(image_path)
    except Exception as exc:
        logger.error("image %s error: %s", faiss_id, exc, exc_info=True)
        return error_response(f"Failed to serve image: {exc}", 500, "IMAGE_ERROR")


# ============================================================================
# Error handlers (consistent envelope)
# ============================================================================

@app.errorhandler(404)
def _not_found(_error):
    return error_response("Endpoint not found", 404, "NOT_FOUND")


@app.errorhandler(405)
def _method_not_allowed(_error):
    return error_response("Method not allowed", 405, "METHOD_NOT_ALLOWED")


@app.errorhandler(413)
def _too_large(_error):
    return error_response("File too large (max 50MB)", 413, "FILE_TOO_LARGE")


@app.errorhandler(500)
def _internal(error):
    logger.error("Internal server error: %s", error, exc_info=True)
    return error_response("Internal server error", 500, "INTERNAL_ERROR")


# ============================================================================
# Entry point (local only)
# ============================================================================

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Omnividence Flask backend")
    logger.info("Data dir (persistent): %s", DATA_DIR)
    logger.info("Upload dir (ephemeral): %s", UPLOAD_FOLDER)
    logger.info("Default threshold: %.2f", DEFAULT_THRESHOLD)
    logger.info("=" * 70)

    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=debug_mode,
        threaded=True,
        use_reloader=debug_mode,
    )
