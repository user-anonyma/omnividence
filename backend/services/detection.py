"""
backend/services/detection.py

EXPERIMENTAL forensic heuristics — OPTIONAL, low-confidence, NOT evidence.

This module is deliberately isolated from the search path. It exposes a single
entry point, ``analyze(image_bytes) -> dict``, which the experimental
POST /api/forensics route calls. Every public function is wrapped so it can
NEVER raise: on any internal failure the result is a clean, honest
"unavailable"/"inconclusive" payload, never an exception and never a 5xx.

Honesty rules baked in here:
  * These are crude heuristics, not detectors. We label confidence "low".
  * We never claim identity, never name a person, never assert a verdict as fact.
  * Scores are bounded [0,1] proxies; labels stay conservative ("inconclusive"
    unless a heuristic is clearly tripped, and even then "possible"/"low"...).
  * If a dependency is missing or the image can't be decoded, every check is
    reported as label="unavailable" with a note explaining why.

Output contract (mirrors api/routes/forensics.py response, which passes this
through verbatim):

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

import io
from typing import Optional

# --- Soft dependencies. Anything missing => graceful "unavailable" payload. ---
try:
    import numpy as np
except Exception:  # pragma: no cover - numpy is a hard dep elsewhere, but stay safe
    np = None  # type: ignore

try:
    from PIL import Image, ImageChops, ImageFilter
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageChops = None  # type: ignore
    ImageFilter = None  # type: ignore


# Label vocabulary kept conservative and identity-free.
_LABEL_INCONCLUSIVE = "inconclusive"
_LABEL_UNAVAILABLE = "unavailable"
_LABEL_LOW = "low"
_LABEL_POSSIBLE = "possible"

_NOTE_OK = "Experimental forensic heuristics. Low confidence. Not evidence."
_NOTE_UNAVAILABLE = (
    "Experimental forensics could not run on this image "
    "(unreadable image or missing dependency). No conclusions drawn."
)


def _unavailable_payload(reason: Optional[str] = None) -> dict:
    """Every check 'unavailable'. Used when nothing could be computed."""
    note = _NOTE_UNAVAILABLE
    if reason:
        note = f"{note} ({reason})"
    return {
        "experimental": True,
        "confidence": "low",
        "checks": {
            "ai_generated": {"score": 0.0, "label": _LABEL_UNAVAILABLE},
            "manipulation_ela": {"score": 0.0, "label": _LABEL_UNAVAILABLE},
            "deepfake": {"score": 0.0, "label": _LABEL_UNAVAILABLE},
        },
        "note": note,
    }


def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _score_label(score: float) -> str:
    """Conservative label from a [0,1] heuristic score.

    We stay non-committal: most of the band is 'inconclusive'. Only a strongly
    tripped heuristic earns 'possible', and even that is hedged by the global
    'low confidence' flag. We never emit a hard 'detected'/'fake' verdict.
    """
    s = _clamp01(score)
    if s >= 0.66:
        return _LABEL_POSSIBLE
    if s >= 0.40:
        return _LABEL_LOW
    return _LABEL_INCONCLUSIVE


def _decode_image(image_bytes: bytes):
    """Decode bytes to an RGB PIL image, or None on any failure."""
    if Image is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        # Cap the working size so heuristics stay cheap and bounded.
        max_side = 1024
        w, h = img.size
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        return img
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Individual heuristics. Each returns {"score": float, "label": str} and never
# raises — callers further wrap them, but defense-in-depth keeps them safe too.
# --------------------------------------------------------------------------- #

def _ela_manipulation(img) -> dict:
    """Error Level Analysis proxy.

    Re-encode the image as JPEG at a known quality, diff against the original,
    and measure how unevenly the recompression error is distributed. Real,
    uniformly-compressed photos tend to have evenly spread ELA energy; spliced
    or locally-edited regions can show outlier patches. We turn the ratio of
    high-error pixels into a crude [0,1] score. This is a weak signal only.
    """
    if Image is None or ImageChops is None or np is None:
        return {"score": 0.0, "label": _LABEL_UNAVAILABLE}
    try:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        buf.seek(0)
        recompressed = Image.open(buf).convert("RGB")

        diff = ImageChops.difference(img, recompressed)
        arr = np.asarray(diff, dtype=np.float32)
        if arr.size == 0:
            return {"score": 0.0, "label": _LABEL_INCONCLUSIVE}

        # Per-pixel error magnitude.
        mag = arr.mean(axis=2)
        mean = float(mag.mean())
        std = float(mag.std())
        if mean <= 1e-6:
            # Effectively identical re-encode — no usable signal.
            return {"score": 0.0, "label": _LABEL_INCONCLUSIVE}

        # Fraction of pixels whose error is a strong outlier vs the local mean.
        thresh = mean + 3.0 * std
        outlier_frac = float((mag > thresh).mean())

        # Map a small outlier fraction to a modest score. Heavily damped.
        score = _clamp01(outlier_frac * 6.0)
        return {"score": round(score, 3), "label": _score_label(score)}
    except Exception:
        return {"score": 0.0, "label": _LABEL_UNAVAILABLE}


def _ai_generated(img) -> dict:
    """AI-generation proxy.

    Heuristic, NOT a classifier. Synthetic images often have unusually smooth
    high-frequency statistics and low residual noise after a light blur. We
    measure the energy of the high-frequency residual relative to overall
    contrast; very low residual energy is a faint hint of synthesis or heavy
    smoothing. This is unreliable and intentionally damped.
    """
    if Image is None or ImageFilter is None or np is None:
        return {"score": 0.0, "label": _LABEL_UNAVAILABLE}
    try:
        gray = np.asarray(img.convert("L"), dtype=np.float32)
        if gray.size == 0:
            return {"score": 0.0, "label": _LABEL_INCONCLUSIVE}

        blurred = np.asarray(
            img.convert("L").filter(ImageFilter.GaussianBlur(radius=1.2)),
            dtype=np.float32,
        )
        residual = gray - blurred
        residual_energy = float(np.abs(residual).mean())
        contrast = float(gray.std()) + 1e-6

        # Normalized high-frequency residual. Lower => smoother => faint AI hint.
        ratio = residual_energy / contrast
        # Invert and scale: little residual relative to contrast nudges the score up.
        score = _clamp01(0.5 - ratio) * 1.2
        score = _clamp01(score)
        return {"score": round(score, 3), "label": _score_label(score)}
    except Exception:
        return {"score": 0.0, "label": _LABEL_UNAVAILABLE}


def _deepfake(img) -> dict:
    """Deepfake proxy.

    There is no reliable lightweight deepfake test, and we do not pretend to
    have one. We compute a very weak blockiness/seam statistic (variance of
    8x8 block-edge gradients) that can loosely correlate with face-swap
    compositing artifacts, then damp it hard. Almost always 'inconclusive'.
    """
    if np is None:
        return {"score": 0.0, "label": _LABEL_UNAVAILABLE}
    try:
        gray = np.asarray(img.convert("L"), dtype=np.float32)
        h, w = gray.shape[:2]
        if h < 16 or w < 16:
            return {"score": 0.0, "label": _LABEL_INCONCLUSIVE}

        # Gradient magnitude along block boundaries vs interior.
        gx = np.abs(np.diff(gray, axis=1))
        gy = np.abs(np.diff(gray, axis=0))

        # Edges that fall on an 8px grid (JPEG block seams / composite seams).
        col_edges = gx[:, 7::8].mean() if gx.shape[1] > 8 else gx.mean()
        row_edges = gy[7::8, :].mean() if gy.shape[0] > 8 else gy.mean()
        block_energy = float((col_edges + row_edges) / 2.0)

        overall = float((gx.mean() + gy.mean()) / 2.0) + 1e-6
        ratio = block_energy / overall  # ~1.0 normal; >1 means seam-heavy.

        score = _clamp01((ratio - 1.0) * 0.8)  # heavily damped
        return {"score": round(score, 3), "label": _score_label(score)}
    except Exception:
        return {"score": 0.0, "label": _LABEL_UNAVAILABLE}


# --------------------------------------------------------------------------- #
# Public entry point.
# --------------------------------------------------------------------------- #

def analyze(image_bytes: bytes) -> dict:
    """Run the experimental forensic heuristics on raw image bytes.

    Returns the forensics payload dict (see module docstring). NEVER raises:
    any failure to decode or compute yields an honest "unavailable" payload.
    The caller (POST /api/forensics) passes this through as 200, even on
    internal failure — there is no error path that reaches the client as 5xx.
    """
    try:
        if not image_bytes:
            return _unavailable_payload("empty upload")

        img = _decode_image(image_bytes)
        if img is None:
            return _unavailable_payload("could not decode image")

        checks = {
            "ai_generated": _ai_generated(img),
            "manipulation_ela": _ela_manipulation(img),
            "deepfake": _deepfake(img),
        }

        # If every check came back unavailable, surface that honestly.
        if all(c.get("label") == _LABEL_UNAVAILABLE for c in checks.values()):
            return _unavailable_payload("heuristics unavailable")

        return {
            "experimental": True,
            "confidence": "low",
            "checks": checks,
            "note": _NOTE_OK,
        }
    except Exception:
        # Last-resort catch-all: still a clean 200-shaped payload.
        return _unavailable_payload("unexpected internal error")
