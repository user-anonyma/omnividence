"""Face detection, cropping, and embedding for Omnividence.

Owns the entire detect -> crop/normalize -> embed step of the pipeline using
InsightFace's ``buffalo_l`` model pack (FaceAnalysis, CPU execution provider).

Responsibilities (per the build contract):
  * ``init_model()``          — lazy-load FaceAnalysis once at startup (idempotent).
  * ``detect_largest_face()`` — detect all faces, return ONLY the largest by bbox
                                area, with a 512-d float32 L2-normalized embedding.
  * ``crop_face_jpeg()``      — crop bbox (with margin), square-pad, resize, write
                                a JPEG (used both for the provider query image and
                                the saved query-face thumbnail).
  * ``embed_face()``          — convenience: embedding of the largest face, or None.

This module makes NO identity claims and never names anyone. It only produces a
512-d face embedding used downstream for a "face similarity score" (0-100). The
embedding is taken from InsightFace's ``normed_embedding`` (already L2-normalized)
and cast to float32.

Graceful degradation: if the model has not been loaded / cannot be downloaded,
detection/embedding functions return ``None`` instead of raising, so the search
route can report the empty/failed state honestly rather than 500-ing.
"""

from __future__ import annotations

import io
import os
import threading
from typing import Optional, TypedDict, Union

import numpy as np

try:  # config provides the InsightFace model cache root + data dir
    import config  # type: ignore
    _INSIGHTFACE_ROOT = config.INSIGHTFACE_ROOT
except Exception:  # pragma: no cover - config should always import
    _INSIGHTFACE_ROOT = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "models")
    )


# ----------------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------------
class DetectedFace(TypedDict):
    bbox: list  # [x1, y1, x2, y2] ints in source-image pixel coords
    det_score: float  # detector confidence
    embedding: np.ndarray  # (512,) float32, L2-normalized (||v|| == 1)


# Accepts raw bytes, a filesystem path, or an already-decoded BGR ndarray.
ImageInput = Union[bytes, bytearray, str, os.PathLike, np.ndarray]


# ----------------------------------------------------------------------------
# Module state (the loaded model + a lock so init is thread-safe / idempotent)
# ----------------------------------------------------------------------------
_model = None  # type: ignore[var-annotated]
_model_lock = threading.Lock()
# buffalo_s (lightweight SCRFD-500M detector + MobileFace recogniser) is ~11x
# faster per image than buffalo_l on a no-AVX CPU, which is what makes embedding
# dozens of result thumbnails feasible here. Slightly less accurate than the
# heavyweight model, but plenty discriminative for similarity ranking.
_MODEL_NAME = "buffalo_s"
# 320 (not 640) detection input: result thumbnails are small and the face fills
# most of the frame, so 320 detects fine and is ~4x faster per image on CPU —
# critical when embedding dozens of thumbnails on a small box.
_DET_SIZE = (320, 320)
# SCRFD detection confidence floor. InsightFace defaults to 0.5, which can just
# miss otherwise-clear faces (e.g. some synthetic/GAN portraits score ~0.4). A
# slightly lower floor makes the demo reliably pick up a clearly-visible
# uploaded face while still rejecting non-faces.
_DET_THRESH = 0.4


def is_loaded() -> bool:
    """True once the FaceAnalysis model pack has been prepared.

    Used by /health (``model_loaded``) and as a cheap guard before inference.
    """
    return _model is not None


def init_model() -> None:
    """Lazy-load ``FaceAnalysis('buffalo_l', root=OMNI_INSIGHTFACE_ROOT)`` and
    ``prepare(ctx_id=-1)`` (CPU). Called once at startup; idempotent and
    thread-safe. Downloads the model pack on first run (persisted under the
    InsightFace root).

    Raises on genuine load failure so startup can surface the real error; the
    inference helpers below, by contrast, degrade gracefully to ``None``.
    """
    global _model
    if _model is not None:
        return
    with _model_lock:
        if _model is not None:  # re-check inside the lock
            return
        # Imported lazily so merely importing this module (e.g. for tests that
        # only touch the pure helpers) does not require onnxruntime/insightface.
        from insightface.app import FaceAnalysis

        os.makedirs(_INSIGHTFACE_ROOT, exist_ok=True)
        app = FaceAnalysis(
            name=_MODEL_NAME,
            root=_INSIGHTFACE_ROOT,
            providers=["CPUExecutionProvider"],
            # Only the detector + ArcFace recogniser are needed for similarity.
            # Skipping the landmark + genderage models cuts ~60% of per-image CPU,
            # which matters a lot when embedding dozens of result thumbnails on a
            # small box.
            allowed_modules=["detection", "recognition"],
        )
        # ctx_id=-1 -> CPU. det_size keeps detection deterministic across inputs;
        # det_thresh lowered slightly so clearly-visible faces aren't missed.
        app.prepare(ctx_id=-1, det_size=_DET_SIZE, det_thresh=_DET_THRESH)
        _model = app


def _ensure_model():
    """Return the loaded model, loading it on demand. Returns ``None`` if the
    model cannot be loaded (so callers degrade gracefully rather than raising)."""
    if _model is not None:
        return _model
    try:
        init_model()
    except Exception:
        return None
    return _model


# ----------------------------------------------------------------------------
# Image decoding helpers
# ----------------------------------------------------------------------------
def _to_bgr(image: ImageInput) -> Optional[np.ndarray]:
    """Decode any supported input into an OpenCV-style BGR uint8 ndarray.

    Accepts raw bytes, a filesystem path, or an existing ndarray (assumed BGR if
    3-channel). Returns ``None`` if the image cannot be decoded.
    """
    import cv2

    # Already an ndarray: normalize channel layout to 3-channel BGR uint8.
    if isinstance(image, np.ndarray):
        arr = image
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        if arr.ndim == 2:  # grayscale -> BGR
            return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        if arr.ndim == 3 and arr.shape[2] == 4:  # BGRA -> BGR
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        if arr.ndim == 3 and arr.shape[2] == 3:
            return arr
        return None

    # Read bytes from a path if needed.
    raw: Optional[bytes] = None
    if isinstance(image, (bytes, bytearray)):
        raw = bytes(image)
    elif isinstance(image, (str, os.PathLike)):
        try:
            with open(os.fspath(image), "rb") as fh:
                raw = fh.read()
        except Exception:
            return None
    else:
        return None

    if not raw:
        return None

    # Prefer Pillow for robust decoding (handles EXIF orientation, webp, CMYK),
    # then hand a contiguous BGR array to OpenCV/InsightFace.
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(raw)) as im:
            im = ImageOps.exif_transpose(im)  # respect camera orientation
            im = im.convert("RGB")
            rgb = np.asarray(im)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return np.ascontiguousarray(bgr)
    except Exception:
        pass

    # Fallback: let OpenCV decode the buffer directly.
    try:
        buf = np.frombuffer(raw, dtype=np.uint8)
        bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        return bgr
    except Exception:
        return None


def _largest_face(faces) -> Optional[object]:
    """Return the InsightFace ``Face`` with the largest bbox area, or ``None``."""
    best = None
    best_area = -1.0
    for f in faces:
        try:
            x1, y1, x2, y2 = (float(v) for v in f.bbox[:4])
        except Exception:
            continue
        area = max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))
        if area > best_area:
            best_area = area
            best = f
    return best


def _normalize_vec(vec: np.ndarray) -> np.ndarray:
    """Cast to float32 and L2-normalize (unit norm). Zero vectors are returned
    as-is (cast) to avoid division by zero."""
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(v))
    if norm > 0.0:
        v = v / norm
    return v.astype(np.float32)


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
def detect_largest_face(image_bytes_or_path: ImageInput) -> Optional[DetectedFace]:
    """Detect all faces and return ONLY the one with the largest bbox area
    ``((x2-x1)*(y2-y1))``.

    Returns ``None`` if the model is unavailable, the image can't be decoded, or
    no face is found. The embedding is taken from InsightFace's
    ``normed_embedding`` (already L2-normalized) and cast to float32; it is
    re-normalized defensively to guarantee unit norm for the cosine step.
    """
    model = _ensure_model()
    if model is None:
        return None

    bgr = _to_bgr(image_bytes_or_path)
    if bgr is None:
        return None

    try:
        faces = model.get(bgr)
    except Exception:
        return None
    if not faces:
        return None

    face = _largest_face(faces)
    if face is None:
        return None

    # bbox -> ints in source pixel coords, clamped to the image bounds.
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in face.bbox[:4])
    bbox = [
        int(max(0, min(round(x1), w))),
        int(max(0, min(round(y1), h))),
        int(max(0, min(round(x2), w))),
        int(max(0, min(round(y2), h))),
    ]

    # Prefer the pre-normalized embedding; fall back to the raw one if absent.
    emb = getattr(face, "normed_embedding", None)
    if emb is None:
        emb = getattr(face, "embedding", None)
    if emb is None:
        return None
    embedding = _normalize_vec(emb)
    if embedding.shape[0] != 512:
        # buffalo_l produces 512-d; guard against an unexpected model swap.
        return None

    det = getattr(face, "det_score", None)
    det_score = float(det) if det is not None else 0.0

    return DetectedFace(bbox=bbox, det_score=det_score, embedding=embedding)


def crop_face_jpeg(
    image_bytes_or_path: ImageInput,
    bbox: list,
    out_path: str,
    margin: float = 0.25,
    size: int = 512,
) -> str:
    """Crop ``bbox`` (with ``margin`` padding), square-pad, resize to ``size`` x
    ``size``, and write a JPEG to ``out_path``. Returns ``out_path``.

    Used to build the cropped-face image sent to the reverse-image-search
    providers AND the saved ``query_thumb_path``. The crop is square-padded
    (letterboxed on black) so faces are never stretched.

    Raises ``ValueError`` if the image cannot be decoded — the caller already
    has a valid ``bbox`` from ``detect_largest_face`` at this point, so a decode
    failure here is a genuine error worth surfacing.
    """
    import cv2

    bgr = _to_bgr(image_bytes_or_path)
    if bgr is None:
        raise ValueError("crop_face_jpeg: could not decode source image")

    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in bbox[:4])

    # Expand the box by `margin` of its size on each side.
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    mx = bw * margin
    my = bh * margin
    cx1 = int(max(0, round(x1 - mx)))
    cy1 = int(max(0, round(y1 - my)))
    cx2 = int(min(w, round(x2 + mx)))
    cy2 = int(min(h, round(y2 + my)))

    # Degenerate box (e.g. bbox fully outside the image): fall back to full image.
    if cx2 <= cx1 or cy2 <= cy1:
        crop = bgr
    else:
        crop = bgr[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        crop = bgr

    # Square-pad on black so the face keeps its aspect ratio, then resize.
    ch, cw = crop.shape[:2]
    side = max(ch, cw)
    square = np.zeros((side, side, 3), dtype=np.uint8)
    off_y = (side - ch) // 2
    off_x = (side - cw) // 2
    square[off_y:off_y + ch, off_x:off_x + cw] = crop

    out = cv2.resize(square, (size, size), interpolation=cv2.INTER_AREA)

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    ok = cv2.imwrite(out_path, out, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        # Fallback to Pillow if the OpenCV writer (codec/path) failed.
        from PIL import Image

        rgb = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
        Image.fromarray(rgb).save(out_path, format="JPEG", quality=92)
    return out_path


def embed_face(image_bytes_or_path: ImageInput) -> Optional[np.ndarray]:
    """Convenience wrapper: the largest face's embedding, or ``None``.

    Returns a ``(512,)`` float32 L2-normalized vector, or ``None`` if no face is
    detected / the model is unavailable. Used to embed each downloaded result
    thumbnail before scoring.
    """
    face = detect_largest_face(image_bytes_or_path)
    if face is None:
        return None
    return face["embedding"]
