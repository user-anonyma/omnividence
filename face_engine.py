"""
Face Recognition Engine Module
==============================

Local-only face detection + 512-dimensional ArcFace embeddings via InsightFace
(buffalo_l: SCRFD detection + ArcFace R100 recognition).

This module is the SOLE producer of embeddings for Omnividence. Every embedding
it emits is:
  - dimension 512
  - dtype float32
  - L2 unit-normalized (so inner product == cosine similarity in [-1, 1])

CPU-only by default (use_gpu=False). No Docker, no GPU assumption. The CUDA
execution provider is only used when onnxruntime actually exposes it.

extract_faces() ALWAYS returns a FaceExtractionResult object (with .status and
.faces), never a bare list.

Author: Omnividence
License: MIT
"""

import logging
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple, Union

import numpy as np

try:
    from insightface.app import FaceAnalysis
except ImportError:  # pragma: no cover - import guard
    raise ImportError(
        "insightface not found. Install with: pip install insightface onnxruntime opencv-python"
    )

# Configure module logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Embedding contract constants (shared across engine, index, app, build_index)
EMBEDDING_DIM = 512


class FaceDetectionStatus(Enum):
    """Status of a face extraction attempt on a single image."""

    SUCCESS = "success"
    NO_FACES_DETECTED = "no_faces_detected"
    POOR_QUALITY = "poor_quality"
    INVALID_IMAGE = "invalid_image"
    PROCESSING_ERROR = "processing_error"


@dataclass
class BoundingBox:
    """Axis-aligned face bounding box in image pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    def width(self) -> float:
        return self.x2 - self.x1

    def height(self) -> float:
        return self.y2 - self.y1

    def area(self) -> float:
        return self.width() * self.height()

    def to_dict(self) -> Dict[str, float]:
        return {
            "x1": float(self.x1),
            "y1": float(self.y1),
            "x2": float(self.x2),
            "y2": float(self.y2),
            "width": float(self.width()),
            "height": float(self.height()),
        }


@dataclass
class Face:
    """A detected face: 512-d L2-normalized embedding plus metadata."""

    embedding: np.ndarray  # shape (512,), float32, L2-normalized
    bounding_box: BoundingBox
    confidence: float  # detection confidence in [0, 1]
    landmarks: Optional[np.ndarray] = None  # 5-point keypoints from detection.kps

    def to_dict(self, include_embedding: bool = False) -> Dict:
        result: Dict = {
            "bounding_box": self.bounding_box.to_dict(),
            "confidence": float(self.confidence),
        }
        if include_embedding and self.embedding is not None:
            result["embedding"] = np.asarray(self.embedding, dtype=np.float32).tolist()
        if self.landmarks is not None:
            result["landmarks"] = np.asarray(self.landmarks).tolist()
        return result


@dataclass
class FaceExtractionResult:
    """Result of extracting faces from a single image."""

    status: FaceDetectionStatus
    faces: List[Face]
    num_faces: int
    image_shape: Optional[Tuple[int, int, int]]  # (height, width, channels)
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0

    def to_dict(self, include_embeddings: bool = False) -> Dict:
        return {
            "status": self.status.value,
            "num_faces": self.num_faces,
            "faces": [f.to_dict(include_embeddings) for f in self.faces],
            "image_shape": list(self.image_shape) if self.image_shape else None,
            "error_message": self.error_message,
            "processing_time_ms": float(self.processing_time_ms),
        }


class FaceEngine:
    """
    Local face recognition engine using InsightFace buffalo_l.

    - SCRFD detector + ArcFace R100 recognizer (512-d embeddings)
    - CPU-only by default; GPU provider used only if actually present
    - Produces L2-normalized float32 embeddings (cosine == inner product)
    """

    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    # Minimum face side (px); faces smaller than this are likely noise/artifacts.
    MIN_FACE_SIZE = 20

    # Default detection confidence threshold.
    MIN_DETECTION_CONFIDENCE = 0.5

    EMBEDDING_DIMENSION = EMBEDDING_DIM

    def __init__(
        self,
        model_name: str = "buffalo_l",
        use_gpu: bool = False,
        det_size: Tuple[int, int] = (640, 640),
        verbose: bool = False,
    ):
        """
        Initialize the engine. Downloads buffalo_l on first use (handled by
        InsightFace into ~/.insightface/models).

        Args:
            model_name: InsightFace model pack ('buffalo_l' = SCRFD + ArcFace R100)
            use_gpu: Use CUDA if onnxruntime exposes it. Default False (local CPU).
            det_size: Detector input size.
            verbose: Enable debug logging.

        Raises:
            RuntimeError: if model initialization fails.
        """
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.det_size = det_size
        self.verbose = verbose
        self._is_initialized = False

        if verbose:
            logger.setLevel(logging.DEBUG)

        try:
            providers = self._get_optimal_providers(use_gpu)
            logger.info("Initializing FaceEngine with model '%s'", model_name)
            logger.info("ONNX Runtime providers: %s", providers)

            self.face_analysis = FaceAnalysis(
                name=model_name,
                providers=providers,
                allowed_modules=["detection", "recognition"],
            )
            ctx_id = 0 if use_gpu else -1
            self.face_analysis.prepare(ctx_id=ctx_id, det_size=det_size)

            self._is_initialized = True
            logger.info("FaceEngine initialized successfully (ctx_id=%d)", ctx_id)

        except Exception as e:
            logger.error("Failed to initialize FaceEngine: %s", e)
            logger.error(traceback.format_exc())
            self._is_initialized = False
            raise RuntimeError(f"FaceEngine initialization failed: {e}")

    @staticmethod
    def _get_optimal_providers(use_gpu: bool) -> List[str]:
        """
        Build the ONNX Runtime provider list.

        Only includes CUDAExecutionProvider when use_gpu is requested AND
        onnxruntime actually reports it as available. CPUExecutionProvider is
        always included as the fallback. This avoids "provider not found" noise
        on CPU-only installs.
        """
        providers: List[str] = []
        if use_gpu:
            try:
                import onnxruntime as ort

                available = set(ort.get_available_providers())
                for p in ("CUDAExecutionProvider", "TensorrtExecutionProvider"):
                    if p in available:
                        providers.append(p)
            except Exception:
                # onnxruntime unavailable or query failed -> CPU only
                pass
        providers.append("CPUExecutionProvider")
        return providers

    def is_valid_image_path(self, image_path: Union[str, Path]) -> bool:
        """True if the file extension is a supported image format."""
        return Path(image_path).suffix.lower() in self.SUPPORTED_FORMATS

    def extract_faces(
        self,
        image_path: Union[str, Path],
        min_confidence: float = MIN_DETECTION_CONFIDENCE,
    ) -> FaceExtractionResult:
        """
        Detect faces and compute 512-d L2-normalized embeddings for one image.

        ALWAYS returns a FaceExtractionResult (never a list). Inspect .status and
        iterate .faces.

        Args:
            image_path: path to the image file.
            min_confidence: minimum detection confidence to keep a face.

        Returns:
            FaceExtractionResult
        """
        import time

        cv2 = self._cv2()
        start = time.time()
        image_path = Path(image_path)

        if not image_path.exists():
            logger.error("Image file not found: %s", image_path)
            return FaceExtractionResult(
                status=FaceDetectionStatus.INVALID_IMAGE,
                faces=[],
                num_faces=0,
                image_shape=None,
                error_message=f"Image file not found: {image_path}",
                processing_time_ms=0.0,
            )

        if not self.is_valid_image_path(image_path):
            logger.warning("Unsupported image format: %s", image_path.suffix)
            return FaceExtractionResult(
                status=FaceDetectionStatus.INVALID_IMAGE,
                faces=[],
                num_faces=0,
                image_shape=None,
                error_message=f"Unsupported image format: {image_path.suffix}",
                processing_time_ms=0.0,
            )

        try:
            # Load as BGR (OpenCV default). InsightFace expects BGR ndarray, so
            # do NOT convert to RGB here.
            image = cv2.imread(str(image_path))
            if image is None:
                logger.error("Failed to decode image: %s", image_path)
                return FaceExtractionResult(
                    status=FaceDetectionStatus.INVALID_IMAGE,
                    faces=[],
                    num_faces=0,
                    image_shape=None,
                    error_message=f"Failed to decode image: {image_path}",
                    processing_time_ms=(time.time() - start) * 1000,
                )

            image_shape = tuple(image.shape)  # (h, w, c)

            detections = self.face_analysis.get(image)  # raw BGR

            if not detections:
                return FaceExtractionResult(
                    status=FaceDetectionStatus.NO_FACES_DETECTED,
                    faces=[],
                    num_faces=0,
                    image_shape=image_shape,
                    error_message="No faces detected in image",
                    processing_time_ms=(time.time() - start) * 1000,
                )

            faces: List[Face] = []
            for det in detections:
                bbox_arr = det.bbox
                bbox = BoundingBox(
                    x1=float(bbox_arr[0]),
                    y1=float(bbox_arr[1]),
                    x2=float(bbox_arr[2]),
                    y2=float(bbox_arr[3]),
                )

                confidence = float(getattr(det, "det_score", 0.0))
                if confidence < min_confidence:
                    logger.debug("Drop face: low confidence %.3f", confidence)
                    continue
                if bbox.area() < (self.MIN_FACE_SIZE ** 2):
                    logger.debug(
                        "Drop face: too small %.0fx%.0f", bbox.width(), bbox.height()
                    )
                    continue

                # Embedding: 512-d, float32, L2-normalized (guard norm==0 -> NaN).
                raw = getattr(det, "embedding", None)
                if raw is None:
                    logger.debug("Drop face: no embedding from recognizer")
                    continue
                embedding = np.asarray(raw, dtype=np.float32).reshape(-1)
                norm = float(np.linalg.norm(embedding))
                embedding = embedding / (norm if norm > 0 else 1.0)

                # 5-point keypoints from detection.kps (buffalo_l reliably has these).
                kps = getattr(det, "kps", None)
                landmarks = np.asarray(kps, dtype=np.float32) if kps is not None else None

                faces.append(
                    Face(
                        embedding=embedding,
                        bounding_box=bbox,
                        confidence=confidence,
                        landmarks=landmarks,
                    )
                )

            elapsed = (time.time() - start) * 1000

            if faces:
                logger.info(
                    "Extracted %d face(s) from %s (%.1fms)",
                    len(faces),
                    image_path.name,
                    elapsed,
                )
                return FaceExtractionResult(
                    status=FaceDetectionStatus.SUCCESS,
                    faces=faces,
                    num_faces=len(faces),
                    image_shape=image_shape,
                    error_message=None,
                    processing_time_ms=elapsed,
                )

            # Detections existed but all were filtered (low conf / small).
            return FaceExtractionResult(
                status=FaceDetectionStatus.POOR_QUALITY,
                faces=[],
                num_faces=0,
                image_shape=image_shape,
                error_message="Detected faces but all filtered (low quality/size)",
                processing_time_ms=elapsed,
            )

        except Exception as e:
            logger.error("Error extracting faces from %s: %s", image_path, e)
            logger.error(traceback.format_exc())
            return FaceExtractionResult(
                status=FaceDetectionStatus.PROCESSING_ERROR,
                faces=[],
                num_faces=0,
                image_shape=None,
                error_message=f"Processing error: {e}",
                processing_time_ms=(time.time() - start) * 1000,
            )

    def get_embeddings(self, image_path: Union[str, Path]) -> np.ndarray:
        """
        Return embeddings for every detected face in the image.

        Args:
            image_path: path to the image.

        Returns:
            np.ndarray of shape (num_faces, 512), float32, L2-normalized.
            Empty array of shape (0, 512) if no faces were detected.
        """
        result = self.extract_faces(image_path)
        if not result.faces:
            return np.empty((0, self.EMBEDDING_DIMENSION), dtype=np.float32)
        return np.stack(
            [np.asarray(f.embedding, dtype=np.float32) for f in result.faces]
        )

    def compare_embeddings(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        metric: str = "cosine",
    ) -> float:
        """
        Compare two embeddings.

        Args:
            embedding1, embedding2: 512-d vectors.
            metric: 'cosine' (inner product of normalized vecs, [-1,1]) or
                    'euclidean' (L2 distance of normalized vecs).

        Returns:
            float similarity/distance.
        """
        e1 = np.asarray(embedding1, dtype=np.float32).reshape(-1)
        e2 = np.asarray(embedding2, dtype=np.float32).reshape(-1)
        n1 = float(np.linalg.norm(e1))
        n2 = float(np.linalg.norm(e2))
        e1 = e1 / (n1 if n1 > 0 else 1.0)
        e2 = e2 / (n2 if n2 > 0 else 1.0)

        if metric == "cosine":
            return float(np.dot(e1, e2))
        if metric == "euclidean":
            return float(np.linalg.norm(e1 - e2))
        raise ValueError(f"Unknown metric: {metric}")

    @staticmethod
    def _cv2():
        """Lazy import of OpenCV so importing this module is cheap and tolerant."""
        import cv2  # noqa: WPS433

        return cv2

    def __repr__(self) -> str:
        return (
            f"FaceEngine(model={self.model_name!r}, "
            f"initialized={self._is_initialized}, use_gpu={self.use_gpu})"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="FaceEngine smoke test: verify a single image yields a "
        "512-d L2-normalized embedding."
    )
    parser.add_argument("image", nargs="?", help="Path to a test image with a face")
    parser.add_argument("--gpu", action="store_true", help="Attempt GPU (default CPU)")
    args = parser.parse_args()

    print("Omnividence FaceEngine")
    print("=" * 50)
    engine = FaceEngine(use_gpu=args.gpu, verbose=True)
    print(f"Initialized: {engine}")

    if not args.image:
        print("\nNo image provided. Pass an image path to run the embedding check:")
        print("  python face_engine.py /path/to/face.jpg")
        raise SystemExit(0)

    result = engine.extract_faces(args.image)
    print(f"\nStatus: {result.status.value}")
    print(f"Faces found: {result.num_faces}")
    if result.faces:
        emb = result.faces[0].embedding
        norm = float(np.linalg.norm(emb))
        print(f"Embedding shape: {emb.shape}  dtype: {emb.dtype}")
        print(f"Embedding L2 norm: {norm:.6f}  (expected ~1.0)")
        ok = emb.shape == (512,) and emb.dtype == np.float32 and abs(norm - 1.0) < 1e-3
        print("CHECK:", "PASS" if ok else "FAIL")
    else:
        print(f"No usable face: {result.error_message}")
