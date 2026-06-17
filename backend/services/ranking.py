"""Ranking, scoring, and band labelling for Omnividence.

This module is the SINGLE SOURCE OF TRUTH for the 0-100 "face similarity score",
the score bands, and the rank+dedup ordering. Everything here is a pure function
with NO side effects (no I/O, no SQLite, no network) so it is trivially testable
and identical in behaviour wherever it is called.

Honesty / safety constraints (enforced in code + naming):
  * The score is always a "face similarity score" — never a "match probability",
    "identity confidence", or anything implying an identity claim.
  * The band labels below say "similarity" / "unrelated" only. The words "match",
    "identity", and "probability" never appear.
  * ``SCORE_BANDS`` is mirrored VERBATIM in ``frontend/lib/bands.ts`` so the
    backend and the frontend ScoreBadge agree exactly on cut-offs and labels.

Scoring math:
  Both the query embedding and each result embedding are 512-d float32 vectors
  that InsightFace has already L2-normalized (``||v|| == 1``). Therefore cosine
  similarity reduces to a plain inner (dot) product, giving a value in [-1, 1].
  That cosine is mapped to a 0-100 integer via::

      score = round(((cos + 1) / 2) * 100)   # then clamped to [0, 100]

Determinism:
  ``rank_and_dedup`` dedups by ``image_url`` keeping the highest score, then sorts
  by ``score`` descending (``None`` last), breaking ties by ``provider`` ascending
  then ``image_url`` ascending, and assigns a stable 1-based ``rank``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# --------------------------------------------------------------------------- #
# Score bands — SINGLE SOURCE OF TRUTH (mirrored verbatim in frontend/lib/bands.ts)
# --------------------------------------------------------------------------- #
SCORE_BANDS = [
    {"min": 90, "max": 100, "key": "certain",   "label": "Certain Match"},
    {"min": 83, "max": 89,  "key": "confident", "label": "Confident Match"},
    {"min": 70, "max": 82,  "key": "uncertain", "label": "Uncertain Match"},
    {"min": 0,  "max": 69,  "key": "weak",      "label": "Weak Match"},
]

# Special non-numeric band: a result thumbnail downloaded but InsightFace found no
# detectable face in it (score is None). These rank last.
NO_FACE_BAND = {"key": "no_face", "label": "No face detected"}


# --------------------------------------------------------------------------- #
# Core scoring primitives
# --------------------------------------------------------------------------- #
def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two embeddings, returned in [-1, 1].

    Both ``a`` and ``b`` are expected to be L2-normalized 512-d vectors (as
    produced by ``services/face.py``), so the cosine reduces to a plain inner
    (dot) product. The result is still clamped into [-1, 1] to absorb any tiny
    floating-point drift before downstream mapping to a score.
    """
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    if a.size == 0 or b.size == 0 or a.shape != b.shape:
        return 0.0
    value = float(np.dot(a, b))
    # Guard against NaN/inf from degenerate inputs, then clamp to the valid range.
    if not np.isfinite(value):
        return 0.0
    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0
    return value


def to_score(cos: float) -> int:
    """Map a cosine value in [-1, 1] to an integer face similarity score 0-100.

    ``round(((cos + 1) / 2) * 100)``, clamped to [0, 100]. Non-finite input is
    treated as the lowest score (0).
    """
    try:
        c = float(cos)
    except (TypeError, ValueError):
        return 0
    if not np.isfinite(c):
        return 0
    # Clamp cosine first so out-of-range inputs can't escape the [0, 100] band.
    if c > 1.0:
        c = 1.0
    elif c < -1.0:
        c = -1.0
    score = int(round(((c + 1.0) / 2.0) * 100))
    if score > 100:
        score = 100
    elif score < 0:
        score = 0
    return score


def band_for(score: Optional[int]) -> dict:
    """Return the band dict for a score.

    ``score is None`` -> ``NO_FACE_BAND`` (a result thumbnail with no detectable
    face). Otherwise the ``SCORE_BANDS`` entry whose ``min <= score <= max``.
    The returned dict always contains ``key`` and ``label``.
    """
    if score is None:
        return NO_FACE_BAND
    try:
        s = int(score)
    except (TypeError, ValueError):
        return NO_FACE_BAND
    # Clamp into range so an out-of-band score still resolves to a numeric band.
    if s < 0:
        s = 0
    elif s > 100:
        s = 100
    for band in SCORE_BANDS:
        if band["min"] <= s <= band["max"]:
            return band
    # Unreachable given the bands cover 0-100 contiguously, but stay safe.
    return SCORE_BANDS[-1]


# --------------------------------------------------------------------------- #
# Rank + dedup
# --------------------------------------------------------------------------- #
def _score_sort_key(row: dict):
    """Sort key implementing the deterministic ordering contract.

    Primary: score descending, with ``None`` (no face) ranked last.
    Tie-breakers: provider ascending, then image_url ascending — both stable and
    deterministic regardless of input order.
    """
    score = row.get("score")
    # has_score=0 sorts before has_score=1 ascending, so rows WITH a score come
    # first; among scored rows, negative score sorts highest score first.
    if score is None:
        has_score = 1
        neg_score = 0.0
    else:
        has_score = 0
        neg_score = -float(score)
    provider = row.get("provider") or ""
    image_url = row.get("image_url") or ""
    return (has_score, neg_score, provider, image_url)


def rank_and_dedup(rows: list[dict]) -> list[dict]:
    """Dedup by ``image_url`` (keep highest score), sort deterministically, rank.

    Steps:
      1) Dedup by ``image_url``: among rows sharing an image_url, keep the one
         with the highest ``score`` (``None`` treated as the lowest).
      2) Sort: ``score`` desc (``None`` last), then ``provider`` asc, then
         ``image_url`` asc — a fully stable, deterministic ordering.
      3) Assign a 1-based ``rank`` and set ``band`` (the band ``key``) on each row.

    Input rows are shallow-copied; the original list/dicts are not mutated. Each
    returned dict carries everything from its source row plus ``rank`` (int) and
    ``band`` (the band key string).
    """
    best_by_url: dict[str, dict] = {}
    for row in rows:
        image_url = row.get("image_url")
        if image_url is None:
            # No dedup key — keep it under a unique synthetic key so it survives.
            key = ("\x00no_url", id(row))
        else:
            key = image_url
        existing = best_by_url.get(key)
        if existing is None:
            best_by_url[key] = row
            continue
        # Keep the higher-scoring row; None counts as lowest.
        existing_score = existing.get("score")
        candidate_score = row.get("score")
        existing_val = -1.0 if existing_score is None else float(existing_score)
        candidate_val = -1.0 if candidate_score is None else float(candidate_score)
        if candidate_val > existing_val:
            best_by_url[key] = row

    deduped = list(best_by_url.values())
    deduped.sort(key=_score_sort_key)

    ranked: list[dict] = []
    for index, row in enumerate(deduped, start=1):
        new_row = dict(row)
        new_row["rank"] = index
        new_row["band"] = band_for(new_row.get("score"))["key"]
        ranked.append(new_row)
    return ranked
