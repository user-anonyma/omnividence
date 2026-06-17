"""SQLite persistence + thumbnail disk cache for Omnividence.

This module owns ALL durable I/O for the backend:

  * the SQLite database (``searches``, ``results``, ``provider_cursors``,
    ``thumb_cache``) — created idempotently on startup with WAL enabled,
  * the on-disk thumbnail cache under ``OMNI_THUMB_CACHE_DIR`` (one
    ``<sha256(image_url)>.jpg`` file per downloaded image), and
  * the per-provider pagination cursor state that powers "load more".

It is the single place the route layer goes to read/write persistent state, so
the route file itself only deals with request/response JSON. Nothing here makes
identity claims or fabricates results — failed thumbnail downloads are recorded
honestly as ``status='failed'`` and surfaced as ``thumb_path = None``.

Concurrency: every public function opens its own short-lived connection via
``_connect()`` (so it is safe to call from FastAPI's threadpool) and WAL mode
allows concurrent readers alongside a writer. The schema is created once at
startup by :func:`init_db`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from config import DB_PATH, THUMB_CACHE_DIR, THUMB_TIMEOUT_SEC

# Ranking semantics (rank + band) are owned by services/ranking.py; cache.py
# reuses them so a re-rank persisted to disk matches what the route computes.
from services.ranking import rank_and_dedup

# httpx is the project's HTTP client (see requirements.txt). It is only needed
# for the thumbnail download path, so it is imported lazily inside
# get_or_download_thumbnail() — that way the rest of cache.py (schema, CRUD,
# cursors) loads and works even before backend deps are installed / in test
# environments that never touch the network.


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _utc_now_iso() -> str:
    """Current time as an ISO-8601 UTC string (matches the schema's *_at cols)."""
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    """Open a SQLite connection with sane pragmas and ``Row`` factory.

    WAL is requested per-connection (it is a persistent database property once
    set, but re-asserting is cheap and harmless). ``check_same_thread=False``
    lets the connection be created/used inside FastAPI's worker threads.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None


def _embedding_to_blob(embedding: np.ndarray) -> bytes:
    """Serialise a 512-d float32 vector to bytes (np.tobytes => 2048 bytes)."""
    arr = np.asarray(embedding, dtype=np.float32).ravel()
    return arr.tobytes()


def _blob_to_embedding(blob: bytes) -> np.ndarray:
    """Inverse of :func:`_embedding_to_blob` -> (512,) float32 ndarray."""
    return np.frombuffer(blob, dtype=np.float32).copy()


# --------------------------------------------------------------------------- #
# Schema / init
# --------------------------------------------------------------------------- #
_SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    search_id        TEXT PRIMARY KEY,
    created_at       TEXT NOT NULL,
    query_embedding  BLOB NOT NULL,
    query_face_bbox  TEXT NOT NULL,
    query_face_det   REAL NOT NULL,
    query_thumb_path TEXT,
    providers_used   TEXT NOT NULL,
    note             TEXT,
    status           TEXT NOT NULL DEFAULT 'done',
    progress         INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id     TEXT NOT NULL REFERENCES searches(search_id),
    image_url     TEXT NOT NULL,
    thumbnail_url TEXT,
    thumb_path    TEXT,
    page_url      TEXT,
    page_title    TEXT,
    provider      TEXT NOT NULL,
    score         INTEGER,
    band          TEXT,
    rank          INTEGER,
    returned      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    UNIQUE(search_id, image_url)
);
CREATE INDEX IF NOT EXISTS idx_results_search_rank ON results(search_id, rank);
CREATE INDEX IF NOT EXISTS idx_results_search_returned ON results(search_id, returned);

CREATE TABLE IF NOT EXISTS provider_cursors (
    search_id     TEXT NOT NULL REFERENCES searches(search_id),
    provider      TEXT NOT NULL,
    next_cursor   TEXT,
    page_index    INTEGER NOT NULL DEFAULT 0,
    exhausted     INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (search_id, provider)
);

CREATE TABLE IF NOT EXISTS thumb_cache (
    image_url   TEXT PRIMARY KEY,
    thumb_path  TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def init_db() -> None:
    """Create all tables/indexes (idempotent) and enable WAL.

    Safe to call repeatedly (every statement is ``IF NOT EXISTS``). Called once
    at startup from ``main.py``. Ensures the DB's parent directory and the
    thumbnail cache directory exist first.
    """
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        # Migrations for DBs created before the streaming columns existed.
        for ddl in (
            "ALTER TABLE searches ADD COLUMN status TEXT NOT NULL DEFAULT 'done'",
            "ALTER TABLE searches ADD COLUMN progress INTEGER NOT NULL DEFAULT 100",
        ):
            try:
                conn.execute(ddl)
            except Exception:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# searches
# --------------------------------------------------------------------------- #
def create_search(
    query_embedding: np.ndarray,
    query_face_bbox: list[int],
    query_face_det: float,
    query_thumb_path: Optional[str],
    providers_used: list[str],
    note: list[str],
    status: str = "done",
    progress: int = 100,
) -> str:
    """Insert a ``searches`` row and return the new ``search_id`` (uuid4 hex).

    ``query_embedding`` is stored as 2048 raw bytes (512 float32). ``bbox``,
    ``providers_used`` and ``note`` are JSON-encoded. ``status`` is 'running'
    while a background worker is still fetching providers, else 'done'.
    """
    search_id = uuid.uuid4().hex
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO searches (
                search_id, created_at, query_embedding, query_face_bbox,
                query_face_det, query_thumb_path, providers_used, note,
                status, progress
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                search_id,
                _utc_now_iso(),
                _embedding_to_blob(query_embedding),
                json.dumps([int(v) for v in query_face_bbox]),
                float(query_face_det),
                query_thumb_path,
                json.dumps(list(providers_used)),
                json.dumps(list(note)),
                status,
                int(progress),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return search_id


def set_search_status(
    search_id: str,
    status: str,
    note: Optional[list[str]] = None,
    progress: Optional[int] = None,
) -> None:
    """Update a search's status, and optionally its notes and progress (0-100)."""
    sets = ["status = ?"]
    vals: list[Any] = [status]
    if note is not None:
        sets.append("note = ?")
        vals.append(json.dumps(list(note)))
    if progress is not None:
        sets.append("progress = ?")
        vals.append(int(progress))
    vals.append(search_id)
    conn = _connect()
    try:
        conn.execute(
            f"UPDATE searches SET {', '.join(sets)} WHERE search_id = ?", tuple(vals)
        )
        conn.commit()
    finally:
        conn.close()


def get_search(search_id: str) -> Optional[dict]:
    """Return the search row as a dict, or ``None`` if unknown.

    ``query_embedding`` is decoded back to a ``(512,)`` float32 ndarray.
    ``query_face_bbox``, ``providers_used`` and ``note`` are JSON-decoded into
    native Python lists.
    """
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM searches WHERE search_id = ?", (search_id,)
        ).fetchone()
    finally:
        conn.close()
    data = _row_to_dict(row)
    if data is None:
        return None
    data["query_embedding"] = _blob_to_embedding(data["query_embedding"])
    data["query_face_bbox"] = _json_or(data.get("query_face_bbox"), [])
    data["providers_used"] = _json_or(data.get("providers_used"), [])
    data["note"] = _json_or(data.get("note"), [])
    return data


def _json_or(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #
# Columns the caller may supply on a result row (besides search_id/created_at).
_RESULT_FIELDS = (
    "image_url",
    "thumbnail_url",
    "thumb_path",
    "page_url",
    "page_title",
    "provider",
    "score",
    "band",
    "rank",
    "returned",
)


def store_results(search_id: str, rows: list[dict]) -> int:
    """Upsert ranked result rows; return the count of NEWLY inserted rows.

    Uses ``INSERT OR IGNORE`` against ``UNIQUE(search_id, image_url)`` so a
    re-seen image is not duplicated across pages. ``score`` may be ``None``
    (no face detected in the thumbnail) and is stored as SQL NULL. ``band`` is
    persisted as the band *key* string (e.g. ``"strong"`` / ``"no_face"``).
    Missing optional fields default to ``None`` (or 0 for ``returned``).
    """
    if not rows:
        return 0
    now = _utc_now_iso()
    inserted = 0
    conn = _connect()
    try:
        for row in rows:
            image_url = row.get("image_url")
            provider = row.get("provider")
            if not image_url or not provider:
                # image_url + provider are NOT NULL in the schema; skip silently
                # rather than raising into the request path.
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO results (
                    search_id, image_url, thumbnail_url, thumb_path, page_url,
                    page_title, provider, score, band, rank, returned, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    search_id,
                    image_url,
                    row.get("thumbnail_url"),
                    row.get("thumb_path"),
                    row.get("page_url"),
                    row.get("page_title"),
                    provider,
                    _opt_int(row.get("score")),
                    row.get("band"),
                    _opt_int(row.get("rank")),
                    int(row.get("returned", 0) or 0),
                    now,
                ),
            )
            inserted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()
    finally:
        conn.close()
    return inserted


def _opt_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_results(
    search_id: str,
    only_unreturned: bool = False,
    limit: Optional[int] = None,
) -> list[dict]:
    """Fetch result rows for a search ordered by ``rank`` asc.

    ``only_unreturned`` restricts to ``returned = 0`` (the buffered rows not yet
    sent to the client). ``limit`` caps the number of rows. Rows with a NULL
    rank sort last. Each row is returned as a plain dict mirroring the schema.
    """
    sql = "SELECT * FROM results WHERE search_id = ?"
    params: list[Any] = [search_id]
    if only_unreturned:
        sql += " AND returned = 0"
    # NULL ranks sort last; then rank asc; id asc as a final stable tiebreak.
    sql += " ORDER BY (rank IS NULL) ASC, rank ASC, id ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    conn = _connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def mark_returned(search_id: str, ids: list[int]) -> None:
    """Set ``returned = 1`` for the given result row ids within a search."""
    if not ids:
        return
    int_ids = [int(i) for i in ids]
    placeholders = ",".join("?" for _ in int_ids)
    conn = _connect()
    try:
        conn.execute(
            f"UPDATE results SET returned = 1 "
            f"WHERE search_id = ? AND id IN ({placeholders})",
            [search_id, *int_ids],
        )
        conn.commit()
    finally:
        conn.close()


def rerank_search(search_id: str) -> None:
    """Recompute global rank + band over ALL of a search's results and persist.

    Applies ``rank_and_dedup`` semantics (services/ranking.py) to the stored
    scores so the on-disk ``rank``/``band`` reflect the full result set after a
    new "load more" batch lands. Dedup is already enforced by the UNIQUE
    constraint, so every stored row is re-ranked (none are dropped); ordering
    matches the route's in-memory ranking exactly.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, image_url, provider, score FROM results WHERE search_id = ?",
            (search_id,),
        ).fetchall()
        bare = [
            {
                "id": r["id"],
                "image_url": r["image_url"],
                "provider": r["provider"],
                "score": r["score"],
            }
            for r in rows
        ]
        ranked = rank_and_dedup(bare)
        for row in ranked:
            conn.execute(
                "UPDATE results SET rank = ?, band = ? WHERE id = ?",
                (row["rank"], row["band"], row["id"]),
            )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# provider cursors
# --------------------------------------------------------------------------- #
def get_cursors(search_id: str) -> dict[str, dict]:
    """Return ``{provider: {next_cursor, page_index, exhausted}}`` for a search.

    ``exhausted`` is a bool. ``next_cursor`` is the opaque JSON-string token (or
    ``None``). An empty dict means no provider has been queried yet for this
    search.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT provider, next_cursor, page_index, exhausted "
            "FROM provider_cursors WHERE search_id = ?",
            (search_id,),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, dict] = {}
    for r in rows:
        out[r["provider"]] = {
            "next_cursor": r["next_cursor"],
            "page_index": r["page_index"],
            "exhausted": bool(r["exhausted"]),
        }
    return out


def upsert_cursor(
    search_id: str,
    provider: str,
    next_cursor: Optional[str],
    page_index: int,
    exhausted: bool,
) -> None:
    """Insert or update a provider's pagination cursor for a search."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO provider_cursors (
                search_id, provider, next_cursor, page_index, exhausted, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(search_id, provider) DO UPDATE SET
                next_cursor = excluded.next_cursor,
                page_index  = excluded.page_index,
                exhausted   = excluded.exhausted,
                updated_at  = excluded.updated_at
            """,
            (
                search_id,
                provider,
                next_cursor,
                int(page_index),
                1 if exhausted else 0,
                _utc_now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def any_more_available(search_id: str) -> bool:
    """True if more results can still be surfaced for this search.

    That is the case if ANY provider cursor is not exhausted, OR any result row
    is still buffered (``returned = 0``). Drives the ``has_more`` flag returned
    by the route.
    """
    conn = _connect()
    try:
        not_exhausted = conn.execute(
            "SELECT 1 FROM provider_cursors "
            "WHERE search_id = ? AND exhausted = 0 LIMIT 1",
            (search_id,),
        ).fetchone()
        if not_exhausted is not None:
            return True
        buffered = conn.execute(
            "SELECT 1 FROM results "
            "WHERE search_id = ? AND returned = 0 LIMIT 1",
            (search_id,),
        ).fetchone()
        return buffered is not None
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# thumbnail cache
# --------------------------------------------------------------------------- #
def thumb_disk_path(image_url: str) -> str:
    """Deterministic ``<THUMB_CACHE_DIR>/<sha256(image_url)>.jpg`` path.

    The key is always the *image_url* (not the source/thumbnail url), so the
    same image maps to one stable file regardless of which URL was downloaded.
    """
    digest = hashlib.sha256((image_url or "").encode("utf-8")).hexdigest()
    return os.path.join(THUMB_CACHE_DIR, f"{digest}.jpg")


# A small, honest user-agent. Some hosts reject the default httpx UA.
_THUMB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; OmnividenceBot/1.0; "
        "face-similarity-search-demo)"
    )
}


def get_or_download_thumbnail(
    image_url: str, source_url: Optional[str]
) -> Optional[str]:
    """Return a local thumbnail path for ``image_url``, downloading if needed.

    Lookup/cache semantics:
      * If ``thumb_cache`` already has ``status='ok'`` for ``image_url`` AND the
        file still exists on disk, return its path immediately.
      * Otherwise download from ``source_url`` if given else ``image_url`` (the
        provider thumbnail is preferred since it is smaller), with timeout
        ``OMNI_THUMB_TIMEOUT_SEC``, save to the deterministic disk path, record
        ``status='ok'``, and return the path.
      * On ANY failure (network, timeout, empty body, non-image) record
        ``status='failed'`` and return ``None``.

    Never raises — failures are recorded honestly and surfaced as a missing
    thumbnail (``thumb_path = None``) rather than crashing the search pipeline.
    """
    if not image_url:
        return None

    # 1) Fast path: a prior successful download whose file is still present.
    cached = _get_thumb_cache(image_url)
    if cached is not None and cached.get("status") == "ok":
        path = cached.get("thumb_path")
        if path and os.path.isfile(path):
            return path
        # Recorded ok but file vanished -> fall through and re-download.

    out_path = thumb_disk_path(image_url)
    download_url = source_url or image_url

    try:
        import httpx  # lazy: only needed when actually downloading

        os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
        with httpx.Client(
            timeout=THUMB_TIMEOUT_SEC,
            follow_redirects=True,
            headers=_THUMB_HEADERS,
        ) as client:
            resp = client.get(download_url)
            resp.raise_for_status()
            content = resp.content
        if not content:
            raise ValueError("empty response body")
        # Persist exactly what was downloaded (already a JPEG/PNG/etc. from the
        # provider); face.py re-decodes it, so we don't re-encode here.
        with open(out_path, "wb") as fh:
            fh.write(content)
    except Exception:
        # Any error -> honest "failed" record, no thumbnail surfaced.
        _record_thumb_cache(image_url, out_path, "failed")
        return None

    _record_thumb_cache(image_url, out_path, "ok")
    return out_path


def _get_thumb_cache(image_url: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT image_url, thumb_path, status, created_at "
            "FROM thumb_cache WHERE image_url = ?",
            (image_url,),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row)


def _record_thumb_cache(image_url: str, thumb_path: str, status: str) -> None:
    """Upsert a thumb_cache row (keyed by image_url)."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO thumb_cache (image_url, thumb_path, status, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(image_url) DO UPDATE SET
                thumb_path = excluded.thumb_path,
                status     = excluded.status,
                created_at = excluded.created_at
            """,
            (image_url, thumb_path, status, _utc_now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
