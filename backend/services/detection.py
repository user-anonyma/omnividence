"""
backend/services/detection.py

Forensic image checks — OPTIONAL, off the search path, never raises.

Exposes ``analyze(image_bytes) -> dict`` for the experimental POST /api/forensics
route. Three checks:

  * ``ai_generated``     — real classifier (Swin-Base ONNX, int8). Flags
                            diffusion / GAN / Midjourney / SDXL imagery.
  * ``deepfake``         — real classifier (ViT-base ONNX, int8), gated behind a
                            face crop (reuses the InsightFace detector). Flags
                            face-swap / face-manipulation.
  * ``manipulation_ela`` — pure-CPU algorithmic ensemble (ELA + local noise
                            inconsistency + JPEG-ghost). Soft tamper suspicion.

Hardware reality: the host is a no-AVX 2-core Celeron. Both ONNX models are the
pre-quantized int8 variants (≈90 MB each) which onnxruntime runs on SSE kernels
in a few seconds. Sessions are lazy singletons (downloaded + loaded on first
use, then cached). If a model can't be fetched or loaded, that check degrades to
a heuristic estimate or "unavailable" — it never crashes the route.

Output contract (passed through verbatim by api/routes/forensics.py):

    {
      "experimental": true,
      "confidence": "low",
      "checks": {
        "ai_generated":     {"score": <0..1>, "label": <str>, "level": <str>},
        "manipulation_ela": {"score": <0..1>, "label": <str>, "level": <str>},
        "deepfake":         {"score": <0..1>, "label": <str>, "level": <str>}
      },
      "note": <str>
    }

``level`` ∈ {"clean", "suspicious", "uncertain", "unavailable"} drives the UI
colour; ``label`` is the human phrase; ``score`` is the model probability of the
"bad" outcome (AI-generated / deepfake / manipulated).
"""

from __future__ import annotations

import io
import os
import threading
import urllib.request
from typing import Optional

# --- Soft dependencies. Anything missing => graceful degrade, never a crash. ---
try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    from PIL import Image, ImageChops, ImageFilter
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageChops = None  # type: ignore
    ImageFilter = None  # type: ignore

try:
    import cv2  # only used by the manipulation ensemble
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover
    ort = None  # type: ignore

try:
    import config  # type: ignore
    _MODELS_DIR = os.path.join(config.INSIGHTFACE_ROOT, "forensics")
except Exception:  # pragma: no cover
    _MODELS_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "models", "forensics")
    )


# --------------------------------------------------------------------------- #
# Model registry — pre-quantized int8 ONNX, verified to run on the no-AVX CPU.
# --------------------------------------------------------------------------- #
_AI_GEN = {
    "name": "smogy_ai_detector_int8.onnx",
    "url": "https://huggingface.co/onnx-community/SMOGY-Ai-images-detector-ONNX/resolve/main/onnx/model_quantized.onnx",
    "min_bytes": 50 * 1024 * 1024,  # ~93 MB; reject a truncated/HTML download
}
_DEEPFAKE = {
    "name": "deepfake_v2_vit_int8.onnx",
    "url": "https://huggingface.co/onnx-community/Deep-Fake-Detector-v2-Model-ONNX/resolve/main/onnx/model_quantized.onnx",
    "min_bytes": 50 * 1024 * 1024,  # ~87 MB
}

# Preprocessing constants.
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)
_HALF = (0.5, 0.5, 0.5)

# Pillow resample enum moved under Image.Resampling; keep a version-proof handle.
_BICUBIC = getattr(getattr(Image, "Resampling", None), "BICUBIC", None) or (
    getattr(Image, "BICUBIC", 3) if Image is not None else 3
)

_NOTE_OK = "Experimental forensic checks. Treat as a hint, not proof."
_NOTE_UNAVAILABLE = (
    "Experimental forensics could not run on this image "
    "(unreadable image or missing dependency). No conclusions drawn."
)

# Lazy ONNX session cache + load lock (sessions are not cheap to build).
_sessions: dict = {}
_session_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Small helpers.
# --------------------------------------------------------------------------- #
def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def _softmax(logits) -> "np.ndarray":
    a = np.asarray(logits, dtype=np.float64)
    e = np.exp(a - a.max())
    return e / (e.sum() + 1e-12)


def _decode_image(image_bytes: bytes, max_side: int = 1024):
    """Decode bytes to a bounded-size RGB PIL image, or None on failure."""
    if Image is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_side:
            s = max_side / float(max(w, h))
            img = img.resize((max(1, int(w * s)), max(1, int(h * s))))
        return img
    except Exception:
        return None


def _square_pad(img):
    """Letterbox to a centred square so the 224x224 resize keeps face geometry
    (squashing a portrait crop distorts the face and skews the classifier)."""
    w, h = img.size
    if w == h:
        return img
    s = max(w, h)
    bg = Image.new("RGB", (s, s), (0, 0, 0))
    bg.paste(img, ((s - w) // 2, (s - h) // 2))
    return bg


def _preprocess(img, mean, std, square=False):
    """RGB PIL -> NCHW float32 batch normalised with mean/std, 224x224."""
    if square:
        img = _square_pad(img)
    r = img.convert("RGB").resize((224, 224), _BICUBIC)
    arr = np.asarray(r, dtype=np.float32) / 255.0
    arr = (arr - np.asarray(mean, np.float32)) / np.asarray(std, np.float32)
    return np.ascontiguousarray(arr.transpose(2, 0, 1)[None], dtype=np.float32)


def _download(url: str, dest: str, min_bytes: int) -> bool:
    """Fetch a model to ``dest`` atomically. Returns True on a valid file."""
    try:
        if os.path.exists(dest) and os.path.getsize(dest) >= min_bytes:
            return True
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        req = urllib.request.Request(url, headers={"User-Agent": "omnividence/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if os.path.getsize(tmp) < min_bytes:
            os.remove(tmp)
            return False
        os.replace(tmp, dest)
        return True
    except Exception:
        try:
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
        except Exception:
            pass
        return False


def _get_session(spec: dict):
    """Lazy-load (download + build) an ONNX session. None if unavailable."""
    if ort is None or np is None:
        return None
    key = spec["name"]
    sess = _sessions.get(key)
    if sess is not None:
        return sess
    with _session_lock:
        sess = _sessions.get(key)
        if sess is not None:
            return sess
        dest = os.path.join(_MODELS_DIR, spec["name"])
        if not _download(spec["url"], dest, spec["min_bytes"]):
            return None
        try:
            so = ort.SessionOptions()
            so.intra_op_num_threads = 2
            so.inter_op_num_threads = 1
            so.log_severity_level = 3
            sess = ort.InferenceSession(
                dest, sess_options=so, providers=["CPUExecutionProvider"]
            )
            _sessions[key] = sess
            return sess
        except Exception:
            return None


def _run_classifier(spec: dict, x) -> Optional["np.ndarray"]:
    """Run a 2-class image classifier, return softmax probabilities or None."""
    sess = _get_session(spec)
    if sess is None:
        return None
    try:
        name = sess.get_inputs()[0].name
        logits = sess.run(None, {name: x})[0][0]
        return _softmax(logits)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Check 1 — AI-generated (real classifier, FFT heuristic fallback).
# --------------------------------------------------------------------------- #
def _ai_generated(img, image_bytes: bytes) -> dict:
    if np is None or Image is None:
        return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}
    try:
        # Score the whole frame. (A tight face crop was tried and rejected: this
        # Swin misfires on letterboxed face crops, reading real faces as ~0.99.
        # The full frame is cleanly calibrated: real ~0.00, AI 0.74-1.0.)
        x = _preprocess(img, _IMAGENET_MEAN, _IMAGENET_STD)
        p = _run_classifier(_AI_GEN, x)
        if p is not None and p.shape[-1] >= 2:
            # SMOGY id2label: {0: "artificial", 1: "human"} -> P(AI) = p[0].
            score = _clamp01(float(p[0]))
            # Real photos sit ~0.00, so a 0.50 bar adds recall on borderline AI
            # with almost no false-positive risk.
            if score >= 0.50:
                return {"score": round(score, 3), "label": "Likely AI-generated", "level": "suspicious"}
            if score < 0.30:
                return {"score": round(score, 3), "label": "Likely a real photo", "level": "clean"}
            return {"score": round(score, 3), "label": "Possibly AI-generated", "level": "uncertain"}
    except Exception:
        pass
    # Degraded fallback: weak FFT-smoothness heuristic, never claims certainty.
    return _ai_generated_heuristic(img)


def _ai_generated_heuristic(img) -> dict:
    if Image is None or ImageFilter is None or np is None:
        return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}
    try:
        gray = np.asarray(img.convert("L"), dtype=np.float32)
        if gray.size == 0:
            return {"score": 0.0, "label": "Uncertain", "level": "uncertain"}
        blurred = np.asarray(
            img.convert("L").filter(ImageFilter.GaussianBlur(radius=1.2)),
            dtype=np.float32,
        )
        ratio = float(np.abs(gray - blurred).mean()) / (float(gray.std()) + 1e-6)
        score = _clamp01((0.5 - ratio) * 1.2)
        return {"score": round(score, 3), "label": "Estimate (detector offline)", "level": "uncertain"}
    except Exception:
        return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}


# --------------------------------------------------------------------------- #
# Check 2 — Manipulation / tampering (pure-CPU ensemble).
# --------------------------------------------------------------------------- #
def _ela_signal(img) -> Optional[float]:
    if Image is None or ImageChops is None or np is None:
        return None
    try:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        buf.seek(0)
        diff = ImageChops.difference(img, Image.open(buf).convert("RGB"))
        mag = np.asarray(diff, dtype=np.float32).mean(axis=2)
        mean = float(mag.mean())
        if mean <= 1e-6:
            return 0.0
        outlier = float((mag > (mean + 3.0 * float(mag.std()))).mean())
        return _clamp01(outlier * 6.0)
    except Exception:
        return None


def _noise_signal(img) -> Optional[float]:
    """Local noise-floor inconsistency: spliced regions carry a different
    residual noise variance than the host image."""
    if np is None:
        return None
    try:
        gray = np.asarray(img.convert("L"), dtype=np.float32)
        if cv2 is not None:
            med = cv2.medianBlur(gray.astype(np.uint8), 3).astype(np.float32)
        else:
            # Cheap 3x3 median-ish surrogate via box blur if OpenCV is absent.
            med = np.asarray(
                img.convert("L").filter(ImageFilter.MedianFilter(size=3)),
                dtype=np.float32,
            )
        resid = gray - med
        th = 32
        H, W = resid.shape
        if H < th * 2 or W < th * 2:
            return 0.0
        stds = [
            resid[y : y + th, x : x + th].std()
            for y in range(0, H - th + 1, th)
            for x in range(0, W - th + 1, th)
        ]
        stds = np.asarray(stds, dtype=np.float32)
        if stds.size < 4:
            return 0.0
        rel = float(stds.std()) / (float(stds.mean()) + 1e-6)
        # Normal photos sit ~0.4-0.7; splices push the relative spread up.
        return _clamp01((rel - 0.7) / 1.3)
    except Exception:
        return None


def _ghost_signal(img) -> Optional[float]:
    """JPEG-ghost: a pasted region originally saved at a different quality
    minimises its recompression error at a different quality than the host."""
    if Image is None or np is None:
        return None
    try:
        base = np.asarray(img.convert("RGB"), dtype=np.float32)
        H, W = base.shape[:2]
        th = 16
        ny, nx = H // th, W // th
        if ny < 3 or nx < 3:
            return 0.0
        base_u8 = base.astype(np.uint8)
        maps = []
        for q in range(60, 96, 5):
            buf = io.BytesIO()
            Image.fromarray(base_u8).save(buf, "JPEG", quality=q)
            buf.seek(0)
            rec = np.asarray(Image.open(buf).convert("RGB"), dtype=np.float32)
            diff = ((base - rec) ** 2).mean(axis=2)
            tile = diff[: ny * th, : nx * th].reshape(ny, th, nx, th).mean(axis=(1, 3))
            maps.append(tile)
        errs = np.stack(maps)  # (Q, ny, nx)
        best_q = errs.argmin(axis=0)
        mode = np.bincount(best_q.ravel()).argmax()
        dev = float((np.abs(best_q - mode) >= 2).mean())
        return _clamp01(dev * 2.0)
    except Exception:
        return None


def _manipulation(img) -> dict:
    if np is None or Image is None:
        return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}
    try:
        # Bound the working size so the ensemble stays sub-second.
        work = img
        if max(img.size) > 768:
            s = 768 / float(max(img.size))
            work = img.resize((max(1, int(img.size[0] * s)), max(1, int(img.size[1] * s))))
        parts, weights = [], []
        for sig, w in ((_ela_signal(work), 0.45), (_noise_signal(work), 0.35), (_ghost_signal(work), 0.20)):
            if sig is not None:
                parts.append(sig * w)
                weights.append(w)
        if not weights:
            return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}
        score = _clamp01(sum(parts) / sum(weights))
        if score >= 0.60:
            return {"score": round(score, 3), "label": "Possible tampering", "level": "suspicious"}
        if score <= 0.35:
            return {"score": round(score, 3), "label": "No tampering signs", "level": "clean"}
        return {"score": round(score, 3), "label": "Uncertain", "level": "uncertain"}
    except Exception:
        return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}


# --------------------------------------------------------------------------- #
# Check 3 — Deepfake (real classifier, face-gated).
# --------------------------------------------------------------------------- #
def _face_crop(image_bytes: bytes):
    """Detect the largest face in the ORIGINAL bytes and return a padded crop
    (PIL RGB), or None if no face / detector unavailable."""
    if Image is None:
        return None
    try:
        from services import face as face_svc
    except Exception:
        return None
    try:
        det = face_svc.detect_largest_face(image_bytes)
        if not det:
            return None
        x1, y1, x2, y2 = (int(v) for v in det["bbox"][:4])
        full = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        W, H = full.size
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0 or bh <= 0:
            return None
        mx, my = int(bw * 0.3), int(bh * 0.3)
        cx1, cy1 = max(0, x1 - mx), max(0, y1 - my)
        cx2, cy2 = min(W, x2 + mx), min(H, y2 + my)
        if cx2 <= cx1 or cy2 <= cy1:
            return None
        return full.crop((cx1, cy1, cx2, cy2))
    except Exception:
        return None


def _deepfake(image_bytes: bytes) -> dict:
    if np is None or Image is None:
        return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}
    try:
        crop = _face_crop(image_bytes)
        if crop is None:
            return {"score": 0.0, "label": "No face to analyze", "level": "unavailable"}
        x = _preprocess(crop, _HALF, _HALF, square=True)
        p = _run_classifier(_DEEPFAKE, x)
        if p is None or p.shape[-1] < 2:
            return {"score": 0.0, "label": "Detector unavailable", "level": "unavailable"}
        # id2label: {0: "Realism", 1: "Deepfake"} -> P(fake) = p[1].
        # This ViT is FP-skewed (it reads some real faces ~0.7), so the bar for
        # "suspicious" is deliberately high to avoid false alarms on real photos.
        score = _clamp01(float(p[1]))
        if score >= 0.82:
            return {"score": round(score, 3), "label": "Possible deepfake", "level": "suspicious"}
        if score < 0.50:
            return {"score": round(score, 3), "label": "No deepfake signs", "level": "clean"}
        return {"score": round(score, 3), "label": "Inconclusive", "level": "uncertain"}
    except Exception:
        return {"score": 0.0, "label": "Unavailable", "level": "unavailable"}


# --------------------------------------------------------------------------- #
# Public entry point.
# --------------------------------------------------------------------------- #
def _unavailable_payload(reason: Optional[str] = None) -> dict:
    note = _NOTE_UNAVAILABLE if not reason else f"{_NOTE_UNAVAILABLE} ({reason})"
    cell = {"score": 0.0, "label": "Unavailable", "level": "unavailable"}
    return {
        "experimental": True,
        "confidence": "low",
        "checks": {
            "ai_generated": dict(cell),
            "manipulation_ela": dict(cell),
            "deepfake": dict(cell),
        },
        "note": note,
    }


def analyze(image_bytes: bytes) -> dict:
    """Run the forensic checks on raw image bytes. NEVER raises."""
    try:
        if not image_bytes:
            return _unavailable_payload("empty upload")
        img = _decode_image(image_bytes)
        if img is None:
            return _unavailable_payload("could not decode image")

        checks = {
            "ai_generated": _ai_generated(img, image_bytes),
            "manipulation_ela": _manipulation(img),
            "deepfake": _deepfake(image_bytes),
        }
        if all(c.get("level") == "unavailable" for c in checks.values()):
            return _unavailable_payload("checks unavailable")
        return {
            "experimental": True,
            "confidence": "low",
            "checks": checks,
            "note": _NOTE_OK,
        }
    except Exception:
        return _unavailable_payload("unexpected internal error")
