"""
FAISS exact-cosine vector index + SQLite metadata for Omnividence.

Design (v1, local-only):
- faiss.IndexFlatIP(512): exact brute-force inner-product search. No training,
  no IVF/PQ/HNSW. Because every vector is L2-normalized before add and before
  query, inner product == cosine similarity in [-1, 1]. Scores are returned
  DIRECTLY (no "1 - dist" / "1/(1+dist)" conversions anywhere).
- SQLite (data/metadata.db) is the single source of truth mapping each FAISS
  position (faiss_id, 0-based == index.ntotal at insert time) to its metadata.
- Fixed on-disk paths under <repo>/data/ so the index + DB survive restarts and
  are stable regardless of the current working directory.

IndexFlatIP is exact and fine up to ~1M vectors on CPU. Upgrading to IVF+PQ for
larger corpora is out of scope for v1.

No Docker. No GPU assumptions.
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover
    raise ImportError(
        "faiss not found. Install the CPU build with: pip install faiss-cpu"
    )

logger = logging.getLogger(__name__)

# Fixed, CWD-independent data directory: <repo>/data
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_INDEX_PATH = DATA_DIR / "faiss.index"
DEFAULT_DB_PATH = DATA_DIR / "metadata.db"


class FAISSIndex:
    """
    Exact cosine similarity face index backed by faiss.IndexFlatIP + SQLite.

    Public interface (the build contract):
        __init__(embedding_dim=512, index_path=<repo>/data/faiss.index, db_path=None)
        .size -> int                     (property; == index.ntotal)
        .add_vector(embedding, metadata=None) -> int      (returns faiss_id)
        .search(query_vectors, k=10) -> (scores[N,k], indices[N,k])
        .get_metadata(faiss_id) -> dict | None
        .get_sources() -> List[dict]     ([{value,label,count}])
        .get_stats() -> dict
        .save() -> bool
        .load() -> bool
    """

    def __init__(
        self,
        embedding_dim: int = 512,
        index_path: str = str(DEFAULT_INDEX_PATH),
        db_path: Optional[str] = None,
    ):
        self.embedding_dim = int(embedding_dim)
        self.index_path = Path(index_path)
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH

        # Ensure parent dirs exist (paths may have been overridden).
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._index: Optional["faiss.Index"] = None

        self._init_db()
        self.load()

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS faces (
                    faiss_id       INTEGER PRIMARY KEY,
                    label          TEXT,
                    image_path     TEXT NOT NULL,
                    source_url     TEXT,
                    source         TEXT DEFAULT 'local',
                    source_type    TEXT DEFAULT 'public_databases',
                    bbox_x1        REAL,
                    bbox_y1        REAL,
                    bbox_x2        REAL,
                    bbox_y2        REAL,
                    det_score      REAL,
                    metadata_json  TEXT,
                    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_faces_label  ON faces(label);
                CREATE INDEX IF NOT EXISTS idx_faces_source ON faces(source);

                CREATE TABLE IF NOT EXISTS index_meta (
                    key        TEXT PRIMARY KEY,
                    value      TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def _faces_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0])

    # ------------------------------------------------------------------ #
    # Index lifecycle
    # ------------------------------------------------------------------ #
    @property
    def size(self) -> int:
        with self._lock:
            return 0 if self._index is None else int(self._index.ntotal)

    def load(self) -> bool:
        """Rehydrate the index from disk (or create a fresh empty one)."""
        with self._lock:
            try:
                if self.index_path.exists():
                    self._index = faiss.read_index(str(self.index_path))
                    if self._index.d != self.embedding_dim:
                        logger.warning(
                            "Index dimension mismatch: file d=%d, expected %d. "
                            "Recreating empty index.",
                            self._index.d,
                            self.embedding_dim,
                        )
                        self._index = faiss.IndexFlatIP(self.embedding_dim)
                else:
                    self._index = faiss.IndexFlatIP(self.embedding_dim)

                # Reconcile FAISS vector count against the SQLite metadata count.
                db_count = self._faces_count()
                if self._index.ntotal != db_count:
                    logger.warning(
                        "DESYNC: FAISS ntotal=%d but faces table has %d rows. "
                        "Metadata may not map cleanly to vectors; serving anyway.",
                        self._index.ntotal,
                        db_count,
                    )
                logger.info(
                    "FAISSIndex loaded: %d vectors (dim=%d) from %s",
                    self._index.ntotal,
                    self.embedding_dim,
                    self.index_path,
                )
                return True
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to load index, starting fresh: %s", exc)
                self._index = faiss.IndexFlatIP(self.embedding_dim)
                return False

    def save(self) -> bool:
        """Persist the FAISS index (binary) and update index_meta."""
        with self._lock:
            if self._index is None:
                return False
            try:
                faiss.write_index(self._index, str(self.index_path))
                self._upsert_meta(
                    {
                        "embedding_dim": str(self.embedding_dim),
                        "index_type": "IndexFlatIP",
                        "metric": "inner_product_cosine",
                        "vector_count": str(self._index.ntotal),
                    }
                )
                logger.info(
                    "FAISSIndex saved: %d vectors -> %s",
                    self._index.ntotal,
                    self.index_path,
                )
                return True
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to save index: %s", exc)
                return False

    def _upsert_meta(self, kv: Dict[str, str]) -> None:
        with self._connect() as conn:
            for key, value in kv.items():
                conn.execute(
                    """
                    INSERT INTO index_meta (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, value),
                )
            conn.commit()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _normalize(self, vectors: np.ndarray) -> np.ndarray:
        """Coerce to float32 (N, dim) and L2-normalize each row (guard norm==0)."""
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[1] != self.embedding_dim:
            raise ValueError(
                f"Expected embeddings of dim {self.embedding_dim}, got {arr.shape[1]}"
            )
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    # ------------------------------------------------------------------ #
    # Add
    # ------------------------------------------------------------------ #
    def add_vector(self, embedding: np.ndarray, metadata: Optional[dict] = None) -> int:
        """
        Add one 512-d embedding + its metadata. Returns the assigned faiss_id.

        faiss_id is set explicitly to index.ntotal BEFORE the add so the SQLite
        row position always equals the FAISS vector position. The caller is
        responsible for calling save() once after a batch (for performance).
        """
        metadata = metadata or {}
        vec = self._normalize(embedding)  # (1, dim)
        if vec.shape[0] != 1:
            raise ValueError("add_vector expects a single embedding, not a batch")

        with self._lock:
            new_id = int(self._index.ntotal)
            self._index.add(vec.reshape(1, self.embedding_dim))

            bbox = metadata.get("bbox")
            if bbox is not None and len(bbox) == 4:
                bx1, by1, bx2, by2 = (float(b) for b in bbox)
            else:
                bx1 = by1 = bx2 = by2 = None

            # Anything not mapped to a dedicated column goes into metadata_json.
            reserved = {
                "label",
                "image_path",
                "source_url",
                "source",
                "source_type",
                "bbox",
                "det_score",
            }
            extras = {k: v for k, v in metadata.items() if k not in reserved}
            metadata_json = json.dumps(extras) if extras else None

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO faces (
                        faiss_id, label, image_path, source_url, source,
                        source_type, bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                        det_score, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id,
                        metadata.get("label"),
                        metadata.get("image_path", ""),
                        metadata.get("source_url"),
                        metadata.get("source", "local"),
                        metadata.get("source_type", "public_databases"),
                        bx1,
                        by1,
                        bx2,
                        by2,
                        (float(metadata["det_score"]) if metadata.get("det_score") is not None else None),
                        metadata_json,
                    ),
                )
                conn.commit()

            return new_id

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def search(
        self, query_vectors: np.ndarray, k: int = 10
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Exact cosine search. Returns (scores[N,k], indices[N,k]).

        scores are cosine similarity in [-1, 1] DIRECTLY from IndexFlatIP inner
        product (no conversion). indices are faiss_id values; -1 marks an empty
        slot when k > size.
        """
        q = self._normalize(query_vectors)  # (N, dim)
        n = q.shape[0]

        with self._lock:
            size = int(self._index.ntotal)
            if size == 0:
                return (
                    np.empty((n, 0), dtype=np.float32),
                    np.full((n, 0), -1, dtype=np.int64),
                )
            k = max(1, min(int(k), size))
            scores, indices = self._index.search(q, k)
            return scores, indices

    # ------------------------------------------------------------------ #
    # Metadata accessors
    # ------------------------------------------------------------------ #
    def get_metadata(self, faiss_id: int) -> Optional[dict]:
        """Return the flat metadata dict for a faiss_id, or None if missing."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM faces WHERE faiss_id = ?", (int(faiss_id),)
            ).fetchone()
        if row is None:
            return None

        bbox = None
        if row["bbox_x1"] is not None:
            bbox = (
                row["bbox_x1"],
                row["bbox_y1"],
                row["bbox_x2"],
                row["bbox_y2"],
            )

        extras = {}
        if row["metadata_json"]:
            try:
                extras = json.loads(row["metadata_json"])
            except (ValueError, TypeError):
                extras = {}

        return {
            "faiss_id": int(row["faiss_id"]),
            "label": row["label"],
            "image_path": row["image_path"],
            "source_url": row["source_url"],
            "source": row["source"],
            "source_type": row["source_type"],
            "bbox": bbox,
            "det_score": row["det_score"],
            "metadata": extras,
        }

    def get_sources(self) -> List[dict]:
        """
        Distinct source/source_type buckets for the /api/sources endpoint.
        Returns [{value, label, count}] sorted by count desc.
        """
        out: List[dict] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source, source_type, COUNT(*) AS cnt
                FROM faces
                GROUP BY source, source_type
                ORDER BY cnt DESC
                """
            ).fetchall()
        for row in rows:
            source = row["source"] or "local"
            source_type = row["source_type"] or "public_databases"
            out.append(
                {
                    "value": source,
                    "label": f"{source} ({source_type})",
                    "count": int(row["cnt"]),
                }
            )
        return out

    def get_stats(self) -> dict:
        """Index statistics for /api/stats."""
        with self._connect() as conn:
            total_faces = int(conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0])
            distinct_labels = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT label) FROM faces WHERE label IS NOT NULL"
                ).fetchone()[0]
            )
        return {
            "index_size": self.size,
            "total_faces": total_faces,
            "embedding_dim": self.embedding_dim,
            "index_type": "IndexFlatIP",
            "metric": "cosine",
            "distinct_labels": distinct_labels,
        }


__all__ = ["FAISSIndex", "DATA_DIR"]
