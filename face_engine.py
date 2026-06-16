"""
Face Recognition Engine Module
Provides high-accuracy face detection and embedding extraction using InsightFace ArcFace R100.

Production-ready face recognition module supporting:
- Multiple image formats (JPEG, PNG, WebP)
- Batch face extraction and embedding generation
- Comprehensive error handling and logging
- Type hints for IDE support
- Edge case handling (multiple faces, poor lighting, small faces)

Author: OSINT Face Search Team
License: MIT
"""

import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import traceback

try:
    import insightface
    from insightface.app import FaceAnalysis
except ImportError:
    raise ImportError(
        "insightface not found. Install with: pip install insightface onnxruntime"
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FaceDetectionStatus(Enum):
    """Enumeration of face detection result statuses."""
    SUCCESS = "success"
    NO_FACES_DETECTED = "no_faces_detected"
    POOR_QUALITY = "poor_quality"
    INVALID_IMAGE = "invalid_image"
    PROCESSING_ERROR = "processing_error"


@dataclass
class BoundingBox:
    """Represents a face bounding box in image coordinates."""
    x1: float
    y1: float
    x2: float
    y2: float

    def width(self) -> float:
        """Calculate bounding box width."""
        return self.x2 - self.x1

    def height(self) -> float:
        """Calculate bounding box height."""
        return self.y2 - self.y1

    def area(self) -> float:
        """Calculate bounding box area."""
        return self.width() * self.height()

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary representation."""
        return {
            "x1": float(self.x1),
            "y1": float(self.y1),
            "x2": float(self.x2),
            "y2": float(self.y2),
            "width": float(self.width()),
            "height": float(self.height())
        }


@dataclass
class Face:
    """Represents a detected face with embedding and metadata."""
    embedding: np.ndarray  # 512-dimensional normalized vector
    bounding_box: BoundingBox
    confidence: float  # Detection confidence [0, 1]
    landmarks: Optional[np.ndarray] = None  # 5-point face landmarks

    def to_dict(self, include_embedding: bool = False) -> Dict:
        """
        Convert face to dictionary representation.

        Args:
            include_embedding: Whether to include the embedding vector (large)

        Returns:
            Dictionary with face data
        """
        result = {
            "bounding_box": self.bounding_box.to_dict(),
            "confidence": float(self.confidence),
        }

        if include_embedding and self.embedding is not None:
            result["embedding"] = self.embedding.tolist()

        if self.landmarks is not None:
            result["landmarks"] = self.landmarks.tolist()

        return result


@dataclass
class FaceExtractionResult:
    """Result of face extraction from a single image."""
    status: FaceDetectionStatus
    faces: List[Face]
    num_faces: int
    image_shape: Optional[Tuple[int, int, int]]  # (height, width, channels)
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0

    def to_dict(self, include_embeddings: bool = False) -> Dict:
        """
        Convert result to dictionary representation.

        Args:
            include_embeddings: Whether to include face embeddings

        Returns:
            Dictionary representation of extraction result
        """
        return {
            "status": self.status.value,
            "num_faces": self.num_faces,
            "faces": [f.to_dict(include_embeddings) for f in self.faces],
            "image_shape": self.image_shape,
            "error_message": self.error_message,
            "processing_time_ms": float(self.processing_time_ms)
        }


class FaceEngine:
    """
    High-accuracy face recognition engine using InsightFace ArcFace R100.

    Provides:
    - Face detection and localization
    - 512-dimensional face embeddings
    - Batch processing support
    - Comprehensive error handling

    Features:
    - 99.8% accuracy on LFW benchmark
    - Support for multiple image formats
    - Automatic hardware detection (GPU/CPU)
    - Edge case handling (multiple faces, poor lighting)
    """

    # Supported image formats
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}

    # Minimum face size in pixels for reliable recognition
    MIN_FACE_SIZE = 20  # Faces smaller than this are likely noise

    # Detection confidence threshold (0-1)
    MIN_DETECTION_CONFIDENCE = 0.5

    # Embedding dimension for ArcFace R100
    EMBEDDING_DIMENSION = 512

    def __init__(
        self,
        model_name: str = "buffalo_l",  # ArcFace R100 model
        providers: Optional[List[str]] = None,
        use_gpu: bool = True,
        verbose: bool = False
    ):
        """
        Initialize the face recognition engine.

        Args:
            model_name: InsightFace model to use ('buffalo_l' is ArcFace R100)
            providers: ONNX Runtime providers (auto-detect if None)
            use_gpu: Attempt to use GPU if available
            verbose: Enable verbose logging

        Raises:
            RuntimeError: If model fails to initialize
        """
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.verbose = verbose

        if verbose:
            logger.setLevel(logging.DEBUG)

        try:
            # Auto-detect providers if not specified
            if providers is None:
                providers = self._get_optimal_providers()

            logger.info(f"Initializing FaceEngine with model: {model_name}")
            logger.info(f"Using providers: {providers}")

            # Initialize InsightFace with specified model
            self.face_analysis = FaceAnalysis(
                name=model_name,
                providers=providers,
                allowed_modules=['detection', 'recognition']
            )
            self.face_analysis.prepare(ctx_id=0 if use_gpu else -1, det_size=(640, 640))

            logger.info("FaceEngine initialized successfully")
            self._is_initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize FaceEngine: {str(e)}")
            logger.error(traceback.format_exc())
            self._is_initialized = False
            raise RuntimeError(f"FaceEngine initialization failed: {str(e)}")

    @staticmethod
    def _get_optimal_providers() -> List[str]:
        """
        Auto-detect optimal ONNX Runtime providers.

        Returns:
            List of provider names in priority order
        """
        providers = []
        try:
            # Try CUDA first (GPU acceleration)
            providers.append('CUDAExecutionProvider')
        except Exception:
            pass

        try:
            # Try TensorRT (NVIDIA GPU optimization)
            providers.append('TensorrtExecutionProvider')
        except Exception:
            pass

        # Always include CPU as fallback
        providers.append('CPUExecutionProvider')

        return providers

    def is_valid_image_path(self, image_path: Union[str, Path]) -> bool:
        """
        Validate if file is a supported image format.

        Args:
            image_path: Path to image file

        Returns:
            True if file is a supported image format
        """
        image_path = Path(image_path)
        return image_path.suffix.lower() in self.SUPPORTED_FORMATS

    def extract_faces(
        self,
        image_path: Union[str, Path],
        return_embeddings: bool = True,
        min_confidence: float = MIN_DETECTION_CONFIDENCE,
    ) -> FaceExtractionResult:
        """
        Extract all faces from a single image.

        Args:
            image_path: Path to input image file
            return_embeddings: Whether to compute face embeddings
            min_confidence: Minimum detection confidence threshold (0-1)

        Returns:
            FaceExtractionResult with detected faces and embeddings

        Example:
            >>> engine = FaceEngine()
            >>> result = engine.extract_faces("photo.jpg")
            >>> print(f"Found {result.num_faces} faces")
            >>> for face in result.faces:
            ...     print(f"Confidence: {face.confidence:.2%}")
        """
        import time
        import cv2

        start_time = time.time()

        # Validate file path
        image_path = Path(image_path)
        if not image_path.exists():
            logger.error(f"Image file not found: {image_path}")
            return FaceExtractionResult(
                status=FaceDetectionStatus.INVALID_IMAGE,
                faces=[],
                num_faces=0,
                image_shape=None,
                error_message=f"Image file not found: {image_path}",
                processing_time_ms=0.0
            )

        if not self.is_valid_image_path(image_path):
            logger.warning(f"Unsupported image format: {image_path.suffix}")
            return FaceExtractionResult(
                status=FaceDetectionStatus.INVALID_IMAGE,
                faces=[],
                num_faces=0,
                image_shape=None,
                error_message=f"Unsupported image format: {image_path.suffix}",
                processing_time_ms=0.0
            )

        try:
            # Load image using OpenCV
            image = cv2.imread(str(image_path))

            if image is None:
                logger.error(f"Failed to load image: {image_path}")
                return FaceExtractionResult(
                    status=FaceDetectionStatus.INVALID_IMAGE,
                    faces=[],
                    num_faces=0,
                    image_shape=None,
                    error_message=f"Failed to load image: {image_path}",
                    processing_time_ms=(time.time() - start_time) * 1000
                )

            # Convert BGR to RGB for InsightFace
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image_shape = image_rgb.shape

            # Detect faces
            detected_faces = self.face_analysis.get(image_rgb)

            if not detected_faces:
                logger.info(f"No faces detected in {image_path}")
                return FaceExtractionResult(
                    status=FaceDetectionStatus.NO_FACES_DETECTED,
                    faces=[],
                    num_faces=0,
                    image_shape=image_shape,
                    error_message="No faces detected in image",
                    processing_time_ms=(time.time() - start_time) * 1000
                )

            # Process detected faces
            faces = []
            for detection in detected_faces:
                # Extract bounding box
                bbox_array = detection.bbox
                bbox = BoundingBox(
                    x1=float(bbox_array[0]),
                    y1=float(bbox_array[1]),
                    x2=float(bbox_array[2]),
                    y2=float(bbox_array[3])
                )

                # Extract confidence
                confidence = float(detection.det_score)

                # Filter by confidence threshold
                if confidence < min_confidence:
                    logger.debug(f"Skipping face with low confidence: {confidence:.2%}")
                    continue

                # Filter by minimum size
                if bbox.area() < (self.MIN_FACE_SIZE ** 2):
                    logger.debug(f"Skipping small face: {bbox.width():.0f}x{bbox.height():.0f}px")
                    continue

                # Extract embedding if requested
                embedding = None
                if return_embeddings and hasattr(detection, 'embedding'):
                    embedding = np.array(detection.embedding, dtype=np.float32)
                    # Ensure embedding is normalized to unit sphere
                    embedding = embedding / np.linalg.norm(embedding)

                # Extract landmarks if available
                landmarks = None
                if hasattr(detection, 'landmark_2d_106'):
                    landmarks = np.array(detection.landmark_2d_106)

                face = Face(
                    embedding=embedding,
                    bounding_box=bbox,
                    confidence=confidence,
                    landmarks=landmarks
                )
                faces.append(face)

            processing_time = (time.time() - start_time) * 1000

            if faces:
                logger.info(f"Extracted {len(faces)} faces from {image_path} ({processing_time:.1f}ms)")
                return FaceExtractionResult(
                    status=FaceDetectionStatus.SUCCESS,
                    faces=faces,
                    num_faces=len(faces),
                    image_shape=image_shape,
                    error_message=None,
                    processing_time_ms=processing_time
                )
            else:
                logger.warning(f"Detected faces but all filtered out: {image_path}")
                return FaceExtractionResult(
                    status=FaceDetectionStatus.POOR_QUALITY,
                    faces=[],
                    num_faces=0,
                    image_shape=image_shape,
                    error_message="Detected faces but all filtered (low quality/size)",
                    processing_time_ms=processing_time
                )

        except Exception as e:
            logger.error(f"Error extracting faces from {image_path}: {str(e)}")
            logger.error(traceback.format_exc())
            return FaceExtractionResult(
                status=FaceDetectionStatus.PROCESSING_ERROR,
                faces=[],
                num_faces=0,
                image_shape=None,
                error_message=f"Processing error: {str(e)}",
                processing_time_ms=(time.time() - start_time) * 1000
            )

    def get_embeddings(
        self,
        image_path: Union[str, Path],
        normalize: bool = True
    ) -> np.ndarray:
        """
        Extract face embeddings from image (shorthand for extract_faces).

        Returns only embeddings for found faces. Use extract_faces() for full metadata.

        Args:
            image_path: Path to input image
            normalize: Whether to normalize embeddings to unit sphere

        Returns:
            Array of shape (num_faces, 512) with embeddings

        Raises:
            ValueError: If no faces detected

        Example:
            >>> engine = FaceEngine()
            >>> embeddings = engine.get_embeddings("photo.jpg")
            >>> print(embeddings.shape)  # (num_faces, 512)
        """
        result = self.extract_faces(image_path, return_embeddings=True)

        if not result.faces:
            raise ValueError(f"No faces detected in {image_path}")

        embeddings = np.array([f.embedding for f in result.faces], dtype=np.float32)

        if normalize:
            # Normalize each embedding to unit sphere
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / norms

        return embeddings

    def batch_process(
        self,
        image_paths: List[Union[str, Path]],
        skip_errors: bool = True,
        return_embeddings: bool = True
    ) -> Dict[str, FaceExtractionResult]:
        """
        Extract faces from multiple images in batch.

        Args:
            image_paths: List of paths to image files
            skip_errors: If True, continue processing on errors; if False, raise exception
            return_embeddings: Whether to compute embeddings for each face

        Returns:
            Dictionary mapping image paths to FaceExtractionResult objects

        Example:
            >>> engine = FaceEngine()
            >>> image_list = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
            >>> results = engine.batch_process(image_list)
            >>>
            >>> for img_path, result in results.items():
            ...     if result.status == FaceDetectionStatus.SUCCESS:
            ...         print(f"{img_path}: {result.num_faces} faces found")
            ...     else:
            ...         print(f"{img_path}: {result.error_message}")
        """
        import time

        start_time = time.time()
        results = {}
        successful = 0
        failed = 0
        total_faces = 0

        logger.info(f"Starting batch processing of {len(image_paths)} images")

        for idx, image_path in enumerate(image_paths, 1):
            try:
                result = self.extract_faces(
                    image_path,
                    return_embeddings=return_embeddings
                )
                results[str(image_path)] = result

                if result.status == FaceDetectionStatus.SUCCESS:
                    successful += 1
                    total_faces += result.num_faces
                    logger.debug(f"[{idx}/{len(image_paths)}] {image_path}: {result.num_faces} faces")
                else:
                    logger.debug(f"[{idx}/{len(image_paths)}] {image_path}: {result.status.value}")
                    failed += 1

            except Exception as e:
                failed += 1
                error_msg = f"Batch processing error: {str(e)}"
                logger.error(f"[{idx}/{len(image_paths)}] {image_path}: {error_msg}")

                if not skip_errors:
                    logger.error(traceback.format_exc())
                    raise

                results[str(image_path)] = FaceExtractionResult(
                    status=FaceDetectionStatus.PROCESSING_ERROR,
                    faces=[],
                    num_faces=0,
                    image_shape=None,
                    error_message=error_msg
                )

        elapsed = (time.time() - start_time)
        logger.info(
            f"Batch processing completed: {successful} successful, {failed} failed, "
            f"{total_faces} total faces extracted ({elapsed:.1f}s)"
        )

        return results

    def compare_embeddings(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        metric: str = "cosine"
    ) -> float:
        """
        Compare two face embeddings using specified metric.

        Args:
            embedding1: First face embedding (512-dim)
            embedding2: Second face embedding (512-dim)
            metric: Similarity metric ('cosine' or 'euclidean')

        Returns:
            Similarity score (0-1 for cosine, 0+ for euclidean)

        Example:
            >>> face1_embed = engine.get_embeddings("person_a.jpg")[0]
            >>> face2_embed = engine.get_embeddings("person_b.jpg")[0]
            >>> similarity = engine.compare_embeddings(face1_embed, face2_embed)
            >>> print(f"Similarity: {similarity:.2%}")
        """
        # Ensure embeddings are properly normalized
        e1 = embedding1 / np.linalg.norm(embedding1)
        e2 = embedding2 / np.linalg.norm(embedding2)

        if metric == "cosine":
            # Cosine similarity: dot product of normalized vectors
            return float(np.dot(e1, e2))
        elif metric == "euclidean":
            # Euclidean distance
            return float(np.linalg.norm(e1 - e2))
        else:
            raise ValueError(f"Unknown metric: {metric}")

    def __repr__(self) -> str:
        """String representation of FaceEngine."""
        return (
            f"FaceEngine(model={self.model_name}, "
            f"initialized={self._is_initialized}, "
            f"use_gpu={self.use_gpu})"
        )


if __name__ == "__main__":
    # Example usage and testing
    print("Face Recognition Engine - Example Usage")
    print("=" * 50)

    try:
        # Initialize engine
        engine = FaceEngine(use_gpu=True, verbose=True)
        print(f"Initialized: {engine}")

        # Example of extracting faces (requires valid image)
        print("\nExample: To use this engine:")
        print("""
        # Single image
        result = engine.extract_faces("photo.jpg")
        print(f"Found {result.num_faces} faces")

        # Get embeddings
        embeddings = engine.get_embeddings("photo.jpg")
        print(f"Embeddings shape: {embeddings.shape}")

        # Batch processing
        results = engine.batch_process(["photo1.jpg", "photo2.jpg"])

        # Compare faces
        if result.num_faces >= 2:
            sim = engine.compare_embeddings(
                result.faces[0].embedding,
                result.faces[1].embedding
            )
            print(f"Similarity: {sim:.2%}")
        """)

    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure insightface is installed:")
        print("  pip install insightface onnxruntime")
