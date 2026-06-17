#!/usr/bin/env python3
"""
Omnividence bulk indexer + self-test (DoD harness).

Walk an LFW-layout dataset directory (person_name/img.jpg), detect + embed every
face with the FaceEngine, and write each 512-d L2-normalized embedding into the
FAISS IndexFlatIP plus its metadata row in SQLite. After building, run a
self-test: re-embed a random indexed image, search the index, and assert the top
match maps back to that same image/identity with cosine similarity ~1.0.

This is the definition-of-done smoke test. After running it:
  - /api/stats reports a non-zero vector count, and
  - uploading one of the indexed images to /api/search returns that person as
    the top match.

Embedding contract (shared with face_engine / faiss_index / app):
  512-d, float32, L2-normalized, cosine similarity via inner product.

Local-only. No network. No GPU assumption (CPU by default). No Docker.

Usage:
    python build_index.py --dataset /path/to/lfw [--limit N] [--reset]
                          [--source dataset:lfw] [--source-type public_databases]
    python build_index.py --dataset /path/to/lfw --self-test-only
"""

import argparse
import logging
import os
import random
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from face_engine import FaceEngine, FaceDetectionStatus
from faiss_index import FAISSIndex, DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("build_index")

# Image extensions we will attempt to index (must match FaceEngine support).
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Self-test threshold: an image queried against its own indexed copy should come
# back near 1.0. Allow a small slack for float / save+load round-tripping.
SELF_TEST_SIM_THRESHOLD = 0.9

# Persist to disk every N images so a long build doesn't hold everything in RAM
# only, and a crash mid-build keeps prior progress.
SAVE_EVERY = 500


# --------------------------------------------------------------------------- #
# Dataset walking
# --------------------------------------------------------------------------- #
def _iter_dataset_images(dataset_dir: Path):
    """
    Yield (label, image_path) pairs from an LFW-style dataset.

    Tolerant of two layouts:
      1. Nested:  dataset/Person_Name/img_0001.jpg  -> label = "Person_Name"
      2. Flat:    dataset/img_0001.jpg              -> label = "img_0001"

    Yields sorted, deterministic order so --limit is reproducible.
    """
    dataset_dir = Path(dataset_dir)

    subdirs = sorted(p for p in dataset_dir.iterdir() if p.is_dir())
    if subdirs:
        # Nested (canonical LFW) layout.
        for person_dir in subdirs:
            label = person_dir.name
            for img_path in sorted(person_dir.iterdir()):
                if img_path.is_file() and img_path.suffix.lower() in IMAGE_EXTS:
                    yield label, img_path
    else:
        # Flat directory of images; label from filename stem.
        for img_path in sorted(dataset_dir.iterdir()):
            if img_path.is_file() and img_path.suffix.lower() in IMAGE_EXTS:
                yield img_path.stem, img_path


# --------------------------------------------------------------------------- #
# Reset
# --------------------------------------------------------------------------- #
def reset_index(index_path: Path, db_path: Path) -> None:
    """Delete the on-disk FAISS index and SQLite DB for a clean rebuild."""
    for p in (index_path, db_path):
        try:
            if p.exists():
                p.unlink()
                logger.info("Removed %s", p)
        except OSError as exc:
            logger.warning("Could not remove %s: %s", p, exc)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_index(
    dataset_dir,
    engine: FaceEngine,
    index: FAISSIndex,
    limit: Optional[int] = None,
    source: str = "dataset:lfw",
    source_type: str = "public_databases",
) -> Dict:
    """
    Walk the dataset, embed every detected face, and add it to the index.

    Args:
        dataset_dir: LFW-layout directory (person_name/img.jpg) or flat dir.
        engine: an initialized FaceEngine (CPU).
        index: an initialized FAISSIndex (embedding_dim=512).
        limit: max number of IMAGES to process (None = all).
        source: display bucket stored on every face (frontend result.source).
        source_type: a SOURCE_TYPES value stored on every face.

    Returns:
        dict of build statistics.
    """
    dataset_dir = Path(dataset_dir).resolve()
    if not dataset_dir.is_dir():
        raise NotADirectoryError(f"Dataset directory not found: {dataset_dir}")

    images_seen = 0
    images_with_faces = 0
    images_no_face = 0
    images_failed = 0
    faces_indexed = 0
    labels_seen = set()

    start = time.time()
    since_save = 0

    for label, img_path in _iter_dataset_images(dataset_dir):
        if limit is not None and images_seen >= limit:
            break
        images_seen += 1

        try:
            result = engine.extract_faces(str(img_path))
        except Exception as exc:  # defensive: never let one bad image kill the build
            images_failed += 1
            logger.warning("Failed to process %s: %s", img_path, exc)
            continue

        if result.status != FaceDetectionStatus.SUCCESS or not result.faces:
            images_no_face += 1
            logger.debug(
                "No usable face in %s (%s)", img_path.name, result.status.value
            )
            continue

        images_with_faces += 1
        labels_seen.add(label)

        for face in result.faces:
            bb = face.bounding_box
            metadata = {
                "label": label,
                "image_path": str(img_path.resolve()),
                "source": source,
                "source_type": source_type,
                "det_score": float(face.confidence),
                "bbox": (bb.x1, bb.y1, bb.x2, bb.y2),
            }
            index.add_vector(face.embedding, metadata=metadata)
            faces_indexed += 1
            since_save += 1

        if since_save >= SAVE_EVERY:
            index.save()
            since_save = 0
            logger.info(
                "Progress: %d images, %d faces indexed (size=%d)",
                images_seen,
                faces_indexed,
                index.size,
            )

    # Final flush to disk.
    index.save()

    elapsed = time.time() - start
    stats = {
        "dataset_dir": str(dataset_dir),
        "images_seen": images_seen,
        "images_with_faces": images_with_faces,
        "images_no_face": images_no_face,
        "images_failed": images_failed,
        "faces_indexed": faces_indexed,
        "distinct_labels": len(labels_seen),
        "index_size": index.size,
        "elapsed_sec": round(elapsed, 2),
    }
    return stats


# --------------------------------------------------------------------------- #
# Self-test (definition of done)
# --------------------------------------------------------------------------- #
def self_test(engine: FaceEngine, index: FAISSIndex, samples: int = 3) -> bool:
    """
    Re-query a few indexed images against the index and assert each comes back as
    its own top match with similarity > SELF_TEST_SIM_THRESHOLD.

    A match is accepted if the returned top-1 faiss_id maps to the SAME image
    path that produced the query (ideal), OR at minimum the same label, AND the
    cosine similarity exceeds the threshold.

    Returns True only if every sampled image self-matches.
    """
    if index.size == 0:
        logger.error("SELF-TEST FAIL: index is empty, nothing to query.")
        return False

    # Pull a random set of indexed rows directly from SQLite.
    conn = sqlite3.connect(str(index.db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT faiss_id, label, image_path FROM faces "
            "WHERE image_path IS NOT NULL AND image_path != ''"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        logger.error("SELF-TEST FAIL: no indexed faces with image paths.")
        return False

    sample_rows = random.sample(rows, min(samples, len(rows)))

    all_ok = True
    print("\n--- SELF-TEST ---")
    for row in sample_rows:
        faiss_id = int(row["faiss_id"])
        label = row["label"]
        image_path = row["image_path"]

        if not Path(image_path).exists():
            logger.warning("Skipping self-test for missing file: %s", image_path)
            continue

        result = engine.extract_faces(image_path)
        if result.status != FaceDetectionStatus.SUCCESS or not result.faces:
            logger.error(
                "SELF-TEST FAIL: could not re-embed %s (%s)",
                image_path,
                result.status.value,
            )
            all_ok = False
            continue

        emb = result.faces[0].embedding.reshape(1, -1)
        scores, indices = index.search(emb, k=1)

        if indices.shape[1] == 0 or int(indices[0][0]) == -1:
            logger.error("SELF-TEST FAIL: empty search result for %s", image_path)
            all_ok = False
            continue

        top_id = int(indices[0][0])
        top_sim = float(scores[0][0])
        top_meta = index.get_metadata(top_id) or {}
        top_label = top_meta.get("label")
        top_path = top_meta.get("image_path")

        same_image = (top_id == faiss_id) or (top_path == image_path)
        same_label = (top_label is not None and top_label == label)
        sim_ok = top_sim > SELF_TEST_SIM_THRESHOLD
        ok = sim_ok and (same_image or same_label)

        status = "PASS" if ok else "FAIL"
        print(
            f"[{status}] query faiss_id={faiss_id} label={label!r}\n"
            f"        -> top_id={top_id} label={top_label!r} sim={top_sim:.4f}"
            f" (same_image={same_image}, same_label={same_label})"
        )
        if not ok:
            all_ok = False

    print(f"SELF-TEST {'PASS' if all_ok else 'FAIL'}")
    return all_ok


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_summary(stats: Dict) -> None:
    print("\n--- BUILD SUMMARY ---")
    print(f"Dataset:            {stats['dataset_dir']}")
    print(f"Images seen:        {stats['images_seen']}")
    print(f"Images with faces:  {stats['images_with_faces']}")
    print(f"Images no face:     {stats['images_no_face']}")
    print(f"Images failed:      {stats['images_failed']}")
    print(f"Faces indexed:      {stats['faces_indexed']}")
    print(f"Distinct labels:    {stats['distinct_labels']}")
    print(f"Index size:         {stats['index_size']}")
    print(f"Elapsed:            {stats['elapsed_sec']}s")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Omnividence bulk face indexer + self-test (LFW layout)."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Dataset directory (LFW layout: person_name/img.jpg, or flat dir).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of images to process (default: all).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete data/faiss.index + data/metadata.db before building.",
    )
    parser.add_argument(
        "--source",
        default="dataset:lfw",
        help="Source bucket stored on every face (default: dataset:lfw).",
    )
    parser.add_argument(
        "--source-type",
        default="public_databases",
        help="Source type stored on every face (default: public_databases).",
    )
    parser.add_argument(
        "--self-test-only",
        action="store_true",
        help="Skip building; only run the self-test against the existing index.",
    )
    parser.add_argument(
        "--no-self-test",
        action="store_true",
        help="Build the index but skip the self-test.",
    )
    parser.add_argument(
        "--self-test-samples",
        type=int,
        default=3,
        help="Number of indexed images to re-query in the self-test (default: 3).",
    )
    args = parser.parse_args(argv)

    index_path = DATA_DIR / "faiss.index"
    db_path = DATA_DIR / "metadata.db"

    if args.reset and not args.self_test_only:
        reset_index(index_path, db_path)

    # Make the self-test deterministic-ish run to run (still random sample, but
    # seeded so failures are reproducible).
    random.seed(int(os.getenv("OMNIVIDENCE_SEED", "1337")))

    logger.info("Initializing FaceEngine (CPU)...")
    engine = FaceEngine(use_gpu=False)

    logger.info("Opening FAISS index at %s", index_path)
    index = FAISSIndex(embedding_dim=512, index_path=str(index_path))

    if not args.self_test_only:
        stats = build_index(
            dataset_dir=args.dataset,
            engine=engine,
            index=index,
            limit=args.limit,
            source=args.source,
            source_type=args.source_type,
        )
        _print_summary(stats)

        if stats["faces_indexed"] == 0:
            logger.error(
                "No faces were indexed. Check that --dataset points at an "
                "LFW-layout directory of readable images with detectable faces."
            )
            return 2

    if args.no_self_test:
        return 0

    passed = self_test(engine, index, samples=args.self_test_samples)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
