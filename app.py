"""
OSINT Face Search - Flask Backend API
Provides REST API endpoints for face recognition and OSINT searching.

Endpoints:
- POST /api/search - Search for face matches in indexed database
- POST /api/batch - Batch process multiple images
- GET /api/results/<id> - Retrieve cached search results
- POST /api/index - Add new faces to search index
- GET /api/stats - Get index statistics
- GET /health - Health check endpoint

Features:
- CORS support for frontend integration
- Request validation and error handling
- JSON response formatting
- Comprehensive logging
- Results caching
- Batch processing support
- Optional Celery task queue integration

Author: OSINT Face Search Team
License: MIT
"""

import os
import logging
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from functools import wraps
from io import BytesIO

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest, NotFound, RequestEntityTooLarge
import numpy as np

# Import face recognition modules
try:
    from face_engine import FaceEngine, Face, FaceDetectionStatus
    from faiss_index import FAISSIndex
except ImportError as e:
    print(f"Error importing face recognition modules: {e}")
    raise

# ============================================================================
# Flask Application Setup
# ============================================================================

app = Flask(__name__)

# Configuration
app.config.update(
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50MB max upload
    JSON_SORT_KEYS=False,
    JSONIFY_PRETTYPRINT_REGULAR=False,
)

# Enable CORS
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
        "max_age": 3600,
    }
})

# ============================================================================
# Logging Setup
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/osint_api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration and Constants
# ============================================================================

UPLOAD_FOLDER = Path("/tmp/osint_uploads")
CACHE_FOLDER = Path("/tmp/osint_cache")
INDEX_FOLDER = Path("/tmp/osint_index")
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp'}
SIMILARITY_THRESHOLD = 0.6  # Configurable similarity threshold
MAX_RESULTS = 100
CACHE_EXPIRY_HOURS = 24

# Ensure directories exist
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
CACHE_FOLDER.mkdir(parents=True, exist_ok=True)
INDEX_FOLDER.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Global Services Initialization
# ============================================================================

# Lazy initialization - these are created on first use
_face_engine = None
_faiss_index = None


def get_face_engine():
    """Get or initialize face recognition engine (lazy initialization)."""
    global _face_engine
    if _face_engine is None:
        try:
            logger.info("Initializing Face Engine...")
            _face_engine = FaceEngine()
            logger.info("Face Engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Face Engine: {e}")
            raise
    return _face_engine


def get_faiss_index():
    """Get or initialize FAISS index (lazy initialization)."""
    global _faiss_index
    if _faiss_index is None:
        try:
            logger.info("Initializing FAISS Index...")
            index_path = INDEX_FOLDER / "faiss_index.pkl"
            _faiss_index = FAISSIndex(
                embedding_dim=512,
                index_path=str(index_path)
            )
            logger.info(f"FAISS Index initialized successfully (size: {_faiss_index.size})")
        except Exception as e:
            logger.error(f"Failed to initialize FAISS Index: {e}")
            raise
    return _faiss_index


# ============================================================================
# Utility Functions
# ============================================================================

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_request_id() -> str:
    """Generate unique request ID."""
    return f"{uuid.uuid4().hex[:16]}_{int(datetime.utcnow().timestamp() * 1000)}"


def save_uploaded_file(file) -> Tuple[str, str]:
    """
    Save uploaded file safely.

    Args:
        file: Flask FileStorage object

    Returns:
        Tuple of (file_path, file_hash)

    Raises:
        BadRequest: If file is invalid
    """
    if not file or file.filename == '':
        raise BadRequest("No file provided")

    if not allowed_file(file.filename):
        raise BadRequest(f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    # Read file into memory
    file_content = file.read()
    file.seek(0)  # Reset for potential re-reads

    if not file_content:
        raise BadRequest("Uploaded file is empty")

    # Generate hash for deduplication
    file_hash = hashlib.md5(file_content).hexdigest()

    # Save with secure filename
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    safe_filename = f"{name}_{file_hash[:8]}{ext}"
    file_path = UPLOAD_FOLDER / safe_filename

    with open(file_path, 'wb') as f:
        f.write(file_content)

    logger.info(f"File saved: {file_path} (hash: {file_hash})")
    return str(file_path), file_hash


def cache_result(request_id: str, data: Dict[str, Any]) -> None:
    """Cache search results with expiry."""
    cache_file = CACHE_FOLDER / f"{request_id}.json"
    cache_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'data': data,
        'expires_at': (datetime.utcnow() + timedelta(hours=CACHE_EXPIRY_HOURS)).isoformat()
    }
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f)
    logger.info(f"Result cached: {request_id}")


def load_cached_result(request_id: str) -> Optional[Dict[str, Any]]:
    """Load cached result if not expired."""
    cache_file = CACHE_FOLDER / f"{request_id}.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)

        # Check expiry
        expires_at = datetime.fromisoformat(cache_data['expires_at'])
        if datetime.utcnow() > expires_at:
            cache_file.unlink()  # Delete expired cache
            logger.info(f"Cache expired: {request_id}")
            return None

        logger.info(f"Cache hit: {request_id}")
        return cache_data['data']
    except Exception as e:
        logger.error(f"Error loading cache {request_id}: {e}")
        return None


def format_search_result(match_idx: int, similarity: float, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """Format individual search result."""
    return {
        'index_id': match_idx,
        'similarity': float(similarity),
        'match_score': float(similarity * 100),  # Percentage
        'metadata': metadata or {}
    }


def require_auth(f):
    """Decorator for endpoints requiring authentication (future use)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # TODO: Implement authentication
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# API Response Helpers
# ============================================================================

def success_response(data: Any, status_code: int = 200, message: str = "Success") -> Tuple[Dict, int]:
    """Generate standardized success response."""
    return jsonify({
        'status': 'success',
        'message': message,
        'data': data,
        'timestamp': datetime.utcnow().isoformat()
    }), status_code


def error_response(message: str, status_code: int = 400, error_code: str = "ERROR", details: Optional[Dict] = None) -> Tuple[Dict, int]:
    """Generate standardized error response."""
    response = {
        'status': 'error',
        'message': message,
        'error_code': error_code,
        'timestamp': datetime.utcnow().isoformat()
    }
    if details:
        response['details'] = details
    return jsonify(response), status_code


# ============================================================================
# Health Check Endpoint
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        # Check basic components
        health_status = {
            'status': 'healthy',
            'components': {
                'api': 'ok',
                'face_engine': 'checking',
                'faiss_index': 'checking'
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Try to initialize services
        try:
            get_face_engine()
            health_status['components']['face_engine'] = 'ok'
        except Exception as e:
            health_status['components']['face_engine'] = f'error: {str(e)}'
            health_status['status'] = 'degraded'

        try:
            get_faiss_index()
            health_status['components']['faiss_index'] = 'ok'
        except Exception as e:
            health_status['components']['faiss_index'] = f'error: {str(e)}'
            health_status['status'] = 'degraded'

        status_code = 200 if health_status['status'] == 'healthy' else 503
        return jsonify(health_status), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return error_response("Health check failed", 503, "HEALTH_CHECK_ERROR")


# ============================================================================
# API Endpoints
# ============================================================================

@app.route('/api/search', methods=['POST'])
def search_faces():
    """
    Search for matching faces in the index.

    Request:
        - image: Image file (multipart/form-data)
        - threshold: Optional similarity threshold [0-1]
        - top_k: Optional number of results [1-100]
        - return_cache: Optional cache ID to return results from cache

    Response:
        {
            'request_id': str,
            'query_faces': [Face data],
            'results': [{
                'face_id': int,
                'query_face_idx': int,
                'matches': [
                    {
                        'index_id': int,
                        'similarity': float,
                        'match_score': float,
                        'metadata': {}
                    }
                ]
            }],
            'query_time_ms': float,
            'match_count': int
        }
    """
    request_id = generate_request_id()

    try:
        # Check for cached request
        if 'return_cache' in request.form:
            cached_result = load_cached_result(request.form['return_cache'])
            if cached_result:
                return success_response(cached_result, message="Result from cache")

        # Validate file upload
        if 'image' not in request.files:
            raise BadRequest("No image file provided")

        file = request.files['image']

        # Get parameters
        threshold = float(request.form.get('threshold', SIMILARITY_THRESHOLD))
        top_k = int(request.form.get('top_k', 10))

        if not 0 <= threshold <= 1:
            raise BadRequest("Threshold must be between 0 and 1")
        if not 1 <= top_k <= MAX_RESULTS:
            raise BadRequest(f"top_k must be between 1 and {MAX_RESULTS}")

        logger.info(f"[{request_id}] Search request: threshold={threshold}, top_k={top_k}")

        # Save file
        file_path, file_hash = save_uploaded_file(file)

        # Extract faces
        face_engine = get_face_engine()
        start_time = datetime.utcnow()

        faces = face_engine.extract_faces(file_path)

        if not faces:
            logger.warning(f"[{request_id}] No faces detected in image")
            result = {
                'request_id': request_id,
                'query_faces': [],
                'results': [],
                'query_time_ms': 0,
                'match_count': 0,
                'status': 'no_faces_detected'
            }
            cache_result(request_id, result)
            return success_response(result, message="No faces detected")

        logger.info(f"[{request_id}] Extracted {len(faces)} faces")

        # Search index
        faiss_index = get_faiss_index()

        if faiss_index.size == 0:
            logger.warning(f"[{request_id}] FAISS index is empty")
            result = {
                'request_id': request_id,
                'query_faces': [],
                'results': [],
                'query_time_ms': 0,
                'match_count': 0,
                'status': 'index_empty'
            }
            cache_result(request_id, result)
            return success_response(result, message="Index is empty", status_code=200)

        # Prepare results
        results = []
        total_matches = 0

        for face_idx, face in enumerate(faces):
            # Search for matches
            distances, indices = faiss_index.search(
                face.embedding.reshape(1, -1),
                k=min(top_k, faiss_index.size)
            )

            # Filter by threshold
            matches = []
            for dist, idx in zip(distances[0], indices[0]):
                similarity = 1 - dist  # Convert distance to similarity
                if similarity >= threshold:
                    matches.append(format_search_result(
                        match_idx=int(idx),
                        similarity=similarity
                    ))

            total_matches += len(matches)

            results.append({
                'face_id': face_idx,
                'query_face_idx': face_idx,
                'face_confidence': float(face.confidence),
                'matches': matches[:top_k]
            })

        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Prepare response
        result = {
            'request_id': request_id,
            'query_faces': [
                {
                    'id': idx,
                    'confidence': float(face.confidence),
                    'bounding_box': face.bounding_box.to_dict()
                }
                for idx, face in enumerate(faces)
            ],
            'results': results,
            'query_time_ms': elapsed_ms,
            'match_count': total_matches,
            'file_hash': file_hash
        }

        # Cache result
        cache_result(request_id, result)

        logger.info(f"[{request_id}] Search completed: {len(faces)} faces, {total_matches} matches ({elapsed_ms:.2f}ms)")
        return success_response(result, message="Search completed successfully")

    except BadRequest as e:
        logger.warning(f"[{request_id}] Bad request: {str(e)}")
        return error_response(str(e), 400, "INVALID_REQUEST")
    except RequestEntityTooLarge:
        logger.error(f"[{request_id}] Upload too large")
        return error_response("File too large (max 50MB)", 413, "FILE_TOO_LARGE")
    except Exception as e:
        logger.error(f"[{request_id}] Search error: {e}", exc_info=True)
        return error_response(f"Search failed: {str(e)}", 500, "SEARCH_ERROR")


@app.route('/api/batch', methods=['POST'])
def batch_search():
    """
    Batch process multiple images.

    Request:
        - images: Multiple files (multipart/form-data, field name 'images')
        - threshold: Optional similarity threshold
        - top_k: Optional number of results per image

    Response:
        {
            'batch_id': str,
            'total_images': int,
            'processed': int,
            'failed': int,
            'results': [
                {
                    'image_name': str,
                    'status': str,
                    'search_result': {...} | null,
                    'error': str | null
                }
            ],
            'batch_time_ms': float
        }
    """
    batch_id = generate_request_id()
    start_time = datetime.utcnow()

    try:
        # Get uploaded files
        files = request.files.getlist('images')

        if not files:
            raise BadRequest("No images provided")

        if len(files) > 100:
            raise BadRequest("Maximum 100 images per batch")

        # Get parameters
        threshold = float(request.form.get('threshold', SIMILARITY_THRESHOLD))
        top_k = int(request.form.get('top_k', 5))

        logger.info(f"[{batch_id}] Batch search: {len(files)} images")

        # Process each image
        results = []
        processed = 0
        failed = 0

        for file in files:
            try:
                if not file or not allowed_file(file.filename):
                    results.append({
                        'image_name': file.filename if file else 'unknown',
                        'status': 'skipped',
                        'error': 'Invalid file type'
                    })
                    failed += 1
                    continue

                # Save file
                file_path, file_hash = save_uploaded_file(file)

                # Extract faces
                face_engine = get_face_engine()
                faces = face_engine.extract_faces(file_path)

                if not faces:
                    results.append({
                        'image_name': file.filename,
                        'status': 'no_faces',
                        'search_result': None
                    })
                    failed += 1
                    continue

                # Search index
                faiss_index = get_faiss_index()

                if faiss_index.size == 0:
                    results.append({
                        'image_name': file.filename,
                        'status': 'index_empty',
                        'search_result': None
                    })
                    failed += 1
                    continue

                # Prepare search results for this image
                image_results = []
                for face_idx, face in enumerate(faces):
                    distances, indices = faiss_index.search(
                        face.embedding.reshape(1, -1),
                        k=min(top_k, faiss_index.size)
                    )

                    matches = []
                    for dist, idx in zip(distances[0], indices[0]):
                        similarity = 1 - dist
                        if similarity >= threshold:
                            matches.append(format_search_result(int(idx), similarity))

                    image_results.append({
                        'face_id': face_idx,
                        'matches': matches[:top_k]
                    })

                results.append({
                    'image_name': file.filename,
                    'status': 'success',
                    'search_result': {
                        'file_hash': file_hash,
                        'face_count': len(faces),
                        'results': image_results
                    }
                })
                processed += 1

            except Exception as e:
                logger.error(f"[{batch_id}] Error processing {file.filename}: {e}")
                results.append({
                    'image_name': file.filename,
                    'status': 'error',
                    'error': str(e)
                })
                failed += 1

        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        result = {
            'batch_id': batch_id,
            'total_images': len(files),
            'processed': processed,
            'failed': failed,
            'results': results,
            'batch_time_ms': elapsed_ms
        }

        cache_result(batch_id, result)

        logger.info(f"[{batch_id}] Batch completed: {processed} processed, {failed} failed ({elapsed_ms:.2f}ms)")
        return success_response(result, message="Batch processing completed")

    except BadRequest as e:
        logger.warning(f"[{batch_id}] Bad request: {str(e)}")
        return error_response(str(e), 400, "INVALID_REQUEST")
    except Exception as e:
        logger.error(f"[{batch_id}] Batch error: {e}", exc_info=True)
        return error_response(f"Batch processing failed: {str(e)}", 500, "BATCH_ERROR")


@app.route('/api/results/<request_id>', methods=['GET'])
def get_results(request_id: str):
    """
    Retrieve cached search results.

    Args:
        request_id: Request ID from search response

    Response: Cached search results or 404 if not found
    """
    try:
        # Validate request_id format
        if not request_id or len(request_id) < 10:
            raise BadRequest("Invalid request ID")

        cached_result = load_cached_result(request_id)

        if cached_result is None:
            logger.info(f"Results not found: {request_id}")
            return error_response("Results not found", 404, "NOT_FOUND")

        logger.info(f"Results retrieved: {request_id}")
        return success_response(cached_result, message="Results retrieved from cache")

    except BadRequest as e:
        return error_response(str(e), 400, "INVALID_REQUEST")
    except Exception as e:
        logger.error(f"Error retrieving results {request_id}: {e}")
        return error_response(f"Failed to retrieve results: {str(e)}", 500, "RETRIEVAL_ERROR")


@app.route('/api/index', methods=['POST'])
def index_faces():
    """
    Add faces to the search index.

    Request:
        - images: Image files to index (multipart/form-data, field 'images')
        - metadata: Optional JSON metadata for each image

    Response:
        {
            'batch_id': str,
            'total_images': int,
            'indexed_faces': int,
            'failed': int,
            'index_size': int,
            'results': [
                {
                    'image_name': str,
                    'face_count': int,
                    'indexed_ids': [int],
                    'error': str | null
                }
            ]
        }
    """
    batch_id = generate_request_id()

    try:
        files = request.files.getlist('images')

        if not files:
            raise BadRequest("No images provided for indexing")

        if len(files) > 100:
            raise BadRequest("Maximum 100 images per batch")

        logger.info(f"[{batch_id}] Indexing {len(files)} images")

        face_engine = get_face_engine()
        faiss_index = get_faiss_index()

        results = []
        total_indexed = 0
        failed = 0

        for file in files:
            try:
                if not file or not allowed_file(file.filename):
                    results.append({
                        'image_name': file.filename if file else 'unknown',
                        'face_count': 0,
                        'indexed_ids': [],
                        'error': 'Invalid file type'
                    })
                    failed += 1
                    continue

                # Save file
                file_path, file_hash = save_uploaded_file(file)

                # Extract faces
                faces = face_engine.extract_faces(file_path)

                if not faces:
                    results.append({
                        'image_name': file.filename,
                        'face_count': 0,
                        'indexed_ids': [],
                        'error': 'No faces detected'
                    })
                    failed += 1
                    continue

                # Add to index
                indexed_ids = []
                for face in faces:
                    idx = faiss_index.add_vector(
                        face.embedding,
                        metadata={
                            'source_file': file.filename,
                            'file_hash': file_hash,
                            'timestamp': datetime.utcnow().isoformat()
                        }
                    )
                    indexed_ids.append(idx)
                    total_indexed += 1

                results.append({
                    'image_name': file.filename,
                    'face_count': len(faces),
                    'indexed_ids': indexed_ids
                })

                logger.info(f"[{batch_id}] Indexed {len(faces)} faces from {file.filename}")

            except Exception as e:
                logger.error(f"[{batch_id}] Error indexing {file.filename}: {e}")
                results.append({
                    'image_name': file.filename,
                    'face_count': 0,
                    'indexed_ids': [],
                    'error': str(e)
                })
                failed += 1

        # Save index to disk
        try:
            faiss_index.save()
            logger.info(f"[{batch_id}] Index saved to disk")
        except Exception as e:
            logger.error(f"[{batch_id}] Error saving index: {e}")

        result = {
            'batch_id': batch_id,
            'total_images': len(files),
            'indexed_faces': total_indexed,
            'failed': failed,
            'index_size': faiss_index.size,
            'results': results
        }

        logger.info(f"[{batch_id}] Indexing completed: {total_indexed} faces added, {failed} failed")
        return success_response(result, status_code=201, message="Faces indexed successfully")

    except BadRequest as e:
        logger.warning(f"[{batch_id}] Bad request: {str(e)}")
        return error_response(str(e), 400, "INVALID_REQUEST")
    except Exception as e:
        logger.error(f"[{batch_id}] Indexing error: {e}", exc_info=True)
        return error_response(f"Indexing failed: {str(e)}", 500, "INDEXING_ERROR")


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    Get index statistics.

    Response:
        {
            'index_size': int,
            'total_faces': int,
            'embedding_dim': int,
            'cache_entries': int,
            'system_info': {
                'upload_folder_size_mb': float,
                'cache_folder_size_mb': float
            }
        }
    """
    try:
        faiss_index = get_faiss_index()

        # Count cache entries
        cache_entries = len(list(CACHE_FOLDER.glob("*.json")))

        # Calculate folder sizes
        upload_size = sum(f.stat().st_size for f in UPLOAD_FOLDER.rglob('*') if f.is_file()) / (1024 * 1024)
        cache_size = sum(f.stat().st_size for f in CACHE_FOLDER.rglob('*') if f.is_file()) / (1024 * 1024)

        stats = {
            'index_size': faiss_index.size,
            'total_faces': faiss_index.size,
            'embedding_dim': 512,
            'cache_entries': cache_entries,
            'system_info': {
                'upload_folder_mb': round(upload_size, 2),
                'cache_folder_mb': round(cache_size, 2),
                'max_upload_mb': 50
            },
            'index_info': {
                'index_path': str(INDEX_FOLDER / "faiss_index.pkl"),
                'distance_metric': 'euclidean'
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"Stats retrieved: {faiss_index.size} faces in index")
        return success_response(stats, message="Statistics retrieved")

    except Exception as e:
        logger.error(f"Error retrieving stats: {e}", exc_info=True)
        return error_response(f"Failed to retrieve statistics: {str(e)}", 500, "STATS_ERROR")


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return error_response("Endpoint not found", 404, "NOT_FOUND")


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors."""
    return error_response("Method not allowed", 405, "METHOD_NOT_ALLOWED")


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle 413 errors."""
    return error_response("File too large (max 50MB)", 413, "FILE_TOO_LARGE")


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    return error_response("Internal server error", 500, "INTERNAL_ERROR")


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("OSINT Face Search - Flask Backend API")
    logger.info("=" * 80)
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
    logger.info(f"Cache folder: {CACHE_FOLDER}")
    logger.info(f"Index folder: {INDEX_FOLDER}")
    logger.info(f"Max file size: 50MB")
    logger.info(f"Similarity threshold: {SIMILARITY_THRESHOLD}")
    logger.info("=" * 80)

    # Run in debug mode if environment variable is set
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=debug_mode,
        threaded=True,
        use_reloader=debug_mode
    )
