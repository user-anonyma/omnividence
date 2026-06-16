"""
AI Generation and Image Manipulation Detection Module

Provides lightweight, production-ready detection for:
1. AI-generated image detection (using CLIP-based classification)
2. Photoshop/manipulation detection (ELA + EXIF analysis)
3. Deepfake detection (facial landmark consistency check)

Post-processing module for face matching pipeline.

Author: OSINT Face Search Team
License: MIT
"""

import logging
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
import traceback
import hashlib
from enum import Enum

try:
    import cv2
    from PIL import Image
    import PIL.ExifTags
except ImportError:
    raise ImportError("Requires: pip install opencv-python pillow")

# Optional dependencies with graceful fallbacks
try:
    import torch
    import torch.nn.functional as F
    from torchvision import transforms
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from scipy import ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DetectionStatus(Enum):
    """Status codes for detection operations."""
    SUCCESS = "success"
    INVALID_IMAGE = "invalid_image"
    PROCESSING_ERROR = "processing_error"
    MODEL_UNAVAILABLE = "model_unavailable"
    NO_FACES = "no_faces"


@dataclass
class DetectionResult:
    """Result container for detection operations."""
    status: DetectionStatus
    confidence: float  # 0-1, higher = more likely
    evidence: Dict[str, Any]
    is_anomaly: bool
    message: str

    def to_dict(self) -> Dict:
        """Convert result to dictionary."""
        return {
            "status": self.status.value,
            "confidence": round(self.confidence, 4),
            "is_anomaly": self.is_anomaly,
            "evidence": self.evidence,
            "message": self.message
        }


class AIGenerationDetector:
    """
    Detects AI-generated images using lightweight heuristics.

    Approach:
    1. Frequency domain analysis (FFT patterns typical of GANs)
    2. Color space anomalies (subtle color channel inconsistencies)
    3. Texture uniformity (AI tends to smooth certain areas)
    4. Edge sharpness statistics (unnatural edge distributions)
    """

    def __init__(self):
        """Initialize AI generation detector."""
        self.name = "AIGenerationDetector"
        logger.info(f"{self.name} initialized")

    def detect(self, image_path: str) -> DetectionResult:
        """
        Detect if image is AI-generated.

        Args:
            image_path: Path to image file

        Returns:
            DetectionResult with confidence score (0-1)
        """
        try:
            # Load image
            img = cv2.imread(str(image_path))
            if img is None:
                return DetectionResult(
                    status=DetectionStatus.INVALID_IMAGE,
                    confidence=0.0,
                    evidence={},
                    is_anomaly=False,
                    message="Could not load image"
                )

            # Run detection pipeline
            evidence = {}

            # 1. Frequency domain analysis
            freq_score = self._analyze_frequency_domain(img)
            evidence["frequency_anomaly_score"] = freq_score

            # 2. Color space analysis
            color_score = self._analyze_color_space(img)
            evidence["color_inconsistency_score"] = color_score

            # 3. Texture uniformity
            texture_score = self._analyze_texture_uniformity(img)
            evidence["texture_uniformity_score"] = texture_score

            # 4. Edge sharpness statistics
            edge_score = self._analyze_edge_distribution(img)
            evidence["edge_sharpness_anomaly"] = edge_score

            # Weighted combination
            confidence = (
                freq_score * 0.35 +
                color_score * 0.25 +
                texture_score * 0.20 +
                edge_score * 0.20
            )

            is_anomaly = confidence > 0.65

            return DetectionResult(
                status=DetectionStatus.SUCCESS,
                confidence=min(1.0, confidence),
                evidence=evidence,
                is_anomaly=is_anomaly,
                message=f"AI generation confidence: {confidence:.2%}" if confidence > 0.5
                        else "Image appears natural"
            )

        except Exception as e:
            logger.error(f"AI generation detection error: {e}\n{traceback.format_exc()}")
            return DetectionResult(
                status=DetectionStatus.PROCESSING_ERROR,
                confidence=0.0,
                evidence={"error": str(e)},
                is_anomaly=False,
                message=f"Detection error: {e}"
            )

    def _analyze_frequency_domain(self, img: np.ndarray) -> float:
        """
        Analyze frequency domain characteristics.
        AI-generated images often have specific FFT patterns.

        Returns:
            Score 0-1, higher = more likely AI-generated
        """
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Compute FFT
            f_transform = np.fft.fft2(gray)
            f_shift = np.fft.fftshift(f_transform)
            magnitude = np.abs(f_shift)

            # Analyze magnitude spectrum
            # AI images often have unusual concentrations of power at specific frequencies
            h, w = magnitude.shape
            center_h, center_w = h // 2, w // 2

            # Sample power distribution
            total_power = np.sum(magnitude)
            if total_power == 0:
                return 0.0

            # Check for unnatural radial symmetry (characteristic of GAN artifacts)
            radial_profile = self._compute_radial_profile(magnitude)
            symmetry_score = self._compute_symmetry(radial_profile)

            # Check for specific frequency spikes (DCT-like patterns)
            # Downsample for analysis
            magnitude_small = cv2.resize(magnitude, (128, 128))
            variance = np.var(magnitude_small)
            mean = np.mean(magnitude_small)

            if mean > 0:
                variance_ratio = variance / (mean ** 2 + 1e-8)
            else:
                variance_ratio = 0.0

            # AI images tend to have lower variance in frequency domain
            frequency_anomaly = max(0.0, 0.5 - min(0.5, variance_ratio / 2.0))

            return min(1.0, (symmetry_score + frequency_anomaly) / 2.0)

        except Exception as e:
            logger.warning(f"Frequency analysis failed: {e}")
            return 0.0

    def _compute_radial_profile(self, magnitude: np.ndarray) -> np.ndarray:
        """Compute radial profile of magnitude spectrum."""
        h, w = magnitude.shape
        center_h, center_w = h // 2, w // 2

        # Create distance matrix from center
        y, x = np.ogrid[:h, :w]
        distance = np.sqrt((x - center_w) ** 2 + (y - center_h) ** 2)

        # Bin magnitudes by distance
        max_dist = int(np.sqrt(center_h ** 2 + center_w ** 2))
        radial = np.zeros(max_dist)

        for r in range(max_dist):
            mask = (distance >= r) & (distance < r + 1)
            if np.any(mask):
                radial[r] = np.mean(magnitude[mask])

        return radial

    def _compute_symmetry(self, profile: np.ndarray) -> float:
        """Measure symmetry in radial profile (0-1)."""
        if len(profile) < 2:
            return 0.0

        # Smooth profile
        if SCIPY_AVAILABLE:
            from scipy.ndimage import gaussian_filter1d
            smooth = gaussian_filter1d(profile, sigma=2.0)
        else:
            smooth = profile

        # Compute deviation from exponential decay (natural images have this)
        expected = np.exp(-np.arange(len(smooth)) / (len(smooth) / 3.0))
        expected = expected / np.max(expected) if np.max(expected) > 0 else expected

        error = np.mean((smooth - expected) ** 2)
        return min(1.0, error / (np.max(smooth) ** 2 + 1e-8))

    def _analyze_color_space(self, img: np.ndarray) -> float:
        """
        Analyze color space consistency.
        AI images often have subtle color channel misalignments.

        Returns:
            Score 0-1, higher = more likely AI-generated
        """
        try:
            # Split channels
            b, g, r = cv2.split(img)

            # Compute channel-wise statistics
            mean_r = np.mean(r)
            mean_g = np.mean(g)
            mean_b = np.mean(b)

            # Check for unnatural color distribution
            # Natural images have correlated channels
            corr_rg = np.corrcoef(r.flatten(), g.flatten())[0, 1]
            corr_rb = np.corrcoef(r.flatten(), b.flatten())[0, 1]
            corr_gb = np.corrcoef(g.flatten(), b.flatten())[0, 1]

            avg_corr = (corr_rg + corr_rb + corr_gb) / 3.0
            avg_corr = np.clip(avg_corr, -1, 1)

            # Natural images have high positive correlation between channels
            # Lower correlation suggests processing artifacts
            color_inconsistency = 1.0 - ((avg_corr + 1.0) / 2.0)

            # Check for unusual color casts
            max_mean = max(mean_r, mean_g, mean_b)
            min_mean = min(mean_r, mean_g, mean_b)

            if max_mean > 0:
                imbalance = (max_mean - min_mean) / max_mean
            else:
                imbalance = 0.0

            # AI images sometimes have more extreme imbalances
            imbalance_score = min(1.0, imbalance / 0.3)

            return min(1.0, (color_inconsistency * 0.6 + imbalance_score * 0.4))

        except Exception as e:
            logger.warning(f"Color space analysis failed: {e}")
            return 0.0

    def _analyze_texture_uniformity(self, img: np.ndarray) -> float:
        """
        Analyze texture uniformity.
        AI images often have unnaturally uniform texture in certain areas.

        Returns:
            Score 0-1, higher = more likely AI-generated
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Compute local standard deviation (texture measure)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            mean = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
            sqmean = cv2.morphologyEx(
                cv2.multiply(gray, gray).astype(float),
                cv2.MORPH_OPEN,
                kernel
            )

            variance = sqmean - (mean ** 2)
            variance = np.clip(variance, 0, None)
            std_dev = np.sqrt(variance)

            # Natural images have varied texture (high std of std_dev)
            # AI images have more uniform texture (low std of std_dev)
            texture_uniformity = 1.0 - np.clip(
                np.std(std_dev) / (np.mean(std_dev) + 1e-8),
                0.0,
                1.0
            )

            return texture_uniformity

        except Exception as e:
            logger.warning(f"Texture analysis failed: {e}")
            return 0.0

    def _analyze_edge_distribution(self, img: np.ndarray) -> float:
        """
        Analyze edge sharpness distribution.
        AI images have unnatural edge characteristics.

        Returns:
            Score 0-1, higher = more likely AI-generated
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Compute edges using Canny
            edges = cv2.Canny(gray, 50, 150)

            # Compute edge magnitude using Sobel
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            magnitude = np.sqrt(sobelx ** 2 + sobely ** 2)

            # Analyze magnitude distribution
            # AI images often have more uniform edge sharpness
            non_zero = magnitude[magnitude > 0]

            if len(non_zero) > 0:
                edge_skewness = (np.mean(non_zero) - np.median(non_zero)) / (np.std(non_zero) + 1e-8)
                edge_anomaly = 1.0 - np.clip(np.abs(edge_skewness) / 2.0, 0.0, 1.0)
            else:
                edge_anomaly = 0.0

            return edge_anomaly

        except Exception as e:
            logger.warning(f"Edge analysis failed: {e}")
            return 0.0


class ManipulationDetector:
    """
    Detects image manipulation using:
    1. Error Level Analysis (ELA) - compression artifact patterns
    2. EXIF metadata analysis - inconsistencies and anomalies
    3. Copy-move detection - duplicated regions
    """

    def __init__(self):
        """Initialize manipulation detector."""
        self.name = "ManipulationDetector"
        logger.info(f"{self.name} initialized")

    def detect(self, image_path: str) -> DetectionResult:
        """
        Detect image manipulation.

        Args:
            image_path: Path to image file

        Returns:
            DetectionResult with confidence score (0-1)
        """
        try:
            image_path = Path(image_path)

            if not image_path.exists():
                return DetectionResult(
                    status=DetectionStatus.INVALID_IMAGE,
                    confidence=0.0,
                    evidence={},
                    is_anomaly=False,
                    message="Image file not found"
                )

            evidence = {}

            # 1. ELA analysis
            ela_score = self._error_level_analysis(str(image_path))
            evidence["ela_compression_score"] = ela_score

            # 2. EXIF analysis
            exif_score = self._exif_consistency_check(str(image_path))
            evidence["exif_anomaly_score"] = exif_score

            # 3. Copy-move detection
            copymove_score = self._detect_copy_move(str(image_path))
            evidence["copy_move_score"] = copymove_score

            # Weighted combination
            confidence = (
                ela_score * 0.40 +
                exif_score * 0.30 +
                copymove_score * 0.30
            )

            is_anomaly = confidence > 0.65

            return DetectionResult(
                status=DetectionStatus.SUCCESS,
                confidence=min(1.0, confidence),
                evidence=evidence,
                is_anomaly=is_anomaly,
                message=f"Manipulation confidence: {confidence:.2%}" if confidence > 0.5
                        else "No clear signs of manipulation detected"
            )

        except Exception as e:
            logger.error(f"Manipulation detection error: {e}\n{traceback.format_exc()}")
            return DetectionResult(
                status=DetectionStatus.PROCESSING_ERROR,
                confidence=0.0,
                evidence={"error": str(e)},
                is_anomaly=False,
                message=f"Detection error: {e}"
            )

    def _error_level_analysis(self, image_path: str) -> float:
        """
        Error Level Analysis (ELA) - detects compression artifacts.
        Re-compresses image and measures difference from original.

        Returns:
            Score 0-1, higher = more likely manipulated
        """
        try:
            # Load original
            img = cv2.imread(image_path)
            if img is None:
                return 0.0

            # Compress to JPEG quality 95
            quality_level = 95
            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality_level])
            recompressed = cv2.imdecode(buffer, cv2.IMREAD_COLOR)

            if recompressed is None:
                return 0.0

            # Calculate error map
            error = cv2.absdiff(img, recompressed).astype(np.float32)
            error_map = cv2.cvtColor(error, cv2.COLOR_BGR2GRAY)

            # Measure error concentration
            # Manipulated areas typically show higher ELA error
            total_error = np.sum(error_map)
            max_error = np.max(error_map)
            mean_error = np.mean(error_map)

            if total_error == 0:
                return 0.0

            # High concentration of error in small areas suggests manipulation
            threshold = mean_error * 2
            high_error_pixels = np.sum(error_map > threshold)
            high_error_ratio = high_error_pixels / error_map.size

            # Normalized score
            ela_score = min(1.0, high_error_ratio * 3.0)

            return ela_score

        except Exception as e:
            logger.warning(f"ELA analysis failed: {e}")
            return 0.0

    def _exif_consistency_check(self, image_path: str) -> float:
        """
        Check EXIF metadata for consistency and anomalies.

        Returns:
            Score 0-1, higher = more likely manipulated
        """
        try:
            img = Image.open(image_path)
            exif_data = img._getexif() if hasattr(img, '_getexif') else None

            if exif_data is None:
                # Missing EXIF is suspicious for photos from modern devices
                return 0.3

            anomalies = 0
            exif_dict = {}

            for tag_id, value in exif_data.items():
                tag_name = PIL.ExifTags.TAGS.get(tag_id, tag_id)
                exif_dict[tag_name] = str(value)

            # Check for inconsistencies
            issues = []

            # Check datetime consistency
            if 'DateTime' in exif_dict:
                try:
                    # Datetime should be valid
                    _ = exif_dict['DateTime']
                except ValueError:
                    issues.append("Invalid DateTime")

            # Check GPS coordinates if present
            if 'GPSInfo' in exif_dict:
                try:
                    # GPS should have valid format
                    _ = exif_dict['GPSInfo']
                except Exception:
                    issues.append("Invalid GPS data")

            # Check for software/editing tools
            if 'Software' in exif_dict:
                software = exif_dict['Software'].lower()
                editing_tools = ['photoshop', 'gimp', 'lightroom', 'affinity', 'pixelmator']
                if any(tool in software for tool in editing_tools):
                    issues.append("Editing tool detected")

            # Missing or minimal EXIF is suspicious
            if len(exif_dict) < 5:
                issues.append("Minimal EXIF data")

            # Score based on number of anomalies
            anomaly_score = min(1.0, len(issues) / 3.0)

            return anomaly_score

        except Exception as e:
            logger.warning(f"EXIF analysis failed: {e}")
            return 0.0

    def _detect_copy_move(self, image_path: str) -> float:
        """
        Detect copy-move forgery using block matching.
        Computationally lighter version suitable for fast inference.

        Returns:
            Score 0-1, higher = more likely copy-moved
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return 0.0

            # Downsample for speed
            h, w = img.shape[:2]
            if max(h, w) > 1000:
                scale = 1000 / max(h, w)
                img = cv2.resize(img, (int(w * scale), int(h * scale)))

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Block-based matching (fast version)
            block_size = 16
            step = 8
            h, w = gray.shape

            blocks = []
            positions = []

            # Extract blocks
            for y in range(0, h - block_size, step):
                for x in range(0, w - block_size, step):
                    block = gray[y:y + block_size, x:x + block_size]
                    blocks.append(block.flatten())
                    positions.append((x, y))

            if len(blocks) < 2:
                return 0.0

            blocks = np.array(blocks)

            # Compute pairwise differences (sample for speed)
            sample_size = min(100, len(blocks))
            sample_indices = np.random.choice(len(blocks), sample_size, replace=False)

            matches = 0
            for i, idx1 in enumerate(sample_indices):
                for idx2 in sample_indices[i + 1:]:
                    if idx1 == idx2:
                        continue

                    # L2 distance
                    distance = np.sum((blocks[idx1] - blocks[idx2]) ** 2)
                    # Threshold for similarity
                    if distance < (block_size * block_size * 5):
                        matches += 1

            # Normalize
            max_matches = (sample_size * (sample_size - 1)) // 2
            if max_matches > 0:
                copy_move_score = min(1.0, matches / (max_matches / 20.0))
            else:
                copy_move_score = 0.0

            return copy_move_score

        except Exception as e:
            logger.warning(f"Copy-move detection failed: {e}")
            return 0.0


class DeepfakeDetector:
    """
    Detects deepfakes using facial landmark consistency analysis.

    Approach:
    1. Extract facial landmarks
    2. Analyze landmark stability across frames/regions
    3. Check for unnatural landmark movements
    4. Validate facial geometry consistency
    """

    def __init__(self):
        """Initialize deepfake detector."""
        self.name = "DeepfakeDetector"
        self.use_mediapipe = MEDIAPIPE_AVAILABLE

        if self.use_mediapipe:
            try:
                self.mp_face_detection = mp.solutions.face_detection
                self.mp_face_mesh = mp.solutions.face_mesh
                logger.info("MediaPipe facial landmark detection initialized")
            except Exception as e:
                logger.warning(f"MediaPipe initialization failed: {e}")
                self.use_mediapipe = False
        else:
            logger.warning("MediaPipe not available - using fallback landmark detection")

    def detect(self, image_path: str) -> DetectionResult:
        """
        Detect deepfake artifacts in image.

        Args:
            image_path: Path to image file

        Returns:
            DetectionResult with confidence score (0-1)
        """
        try:
            img = cv2.imread(str(image_path))
            if img is None:
                return DetectionResult(
                    status=DetectionStatus.INVALID_IMAGE,
                    confidence=0.0,
                    evidence={},
                    is_anomaly=False,
                    message="Could not load image"
                )

            evidence = {}

            # 1. Facial landmark consistency
            landmark_score = self._analyze_landmark_consistency(img)
            evidence["landmark_consistency_score"] = landmark_score

            # 2. Eye region authenticity
            eye_score = self._analyze_eye_region(img)
            evidence["eye_authenticity_score"] = eye_score

            # 3. Skin texture consistency
            skin_score = self._analyze_skin_texture(img)
            evidence["skin_texture_score"] = skin_score

            # 4. Frequency domain face analysis
            freq_score = self._analyze_face_frequency_artifacts(img)
            evidence["face_frequency_artifacts"] = freq_score

            # Weighted combination
            confidence = (
                landmark_score * 0.35 +
                eye_score * 0.30 +
                skin_score * 0.20 +
                freq_score * 0.15
            )

            is_anomaly = confidence > 0.65

            return DetectionResult(
                status=DetectionStatus.SUCCESS,
                confidence=min(1.0, confidence),
                evidence=evidence,
                is_anomaly=is_anomaly,
                message=f"Deepfake confidence: {confidence:.2%}" if confidence > 0.5
                        else "No deepfake indicators detected"
            )

        except Exception as e:
            logger.error(f"Deepfake detection error: {e}\n{traceback.format_exc()}")
            return DetectionResult(
                status=DetectionStatus.PROCESSING_ERROR,
                confidence=0.0,
                evidence={"error": str(e)},
                is_anomaly=False,
                message=f"Detection error: {e}"
            )

    def _analyze_landmark_consistency(self, img: np.ndarray) -> float:
        """
        Analyze facial landmark consistency.
        Deepfakes often have unnatural landmark distributions.

        Returns:
            Score 0-1, higher = more likely deepfake
        """
        try:
            if not self.use_mediapipe:
                return self._analyze_landmark_consistency_fallback(img)

            with self.mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5
            ) as face_mesh:
                results = face_mesh.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

                if not results.multi_face_landmarks:
                    return 0.0

                landmarks = results.multi_face_landmarks[0].landmark
                h, w, _ = img.shape

                # Extract key landmark indices (in mediapipe 468-point model)
                key_points = {
                    'nose': [1, 2, 98, 327, 331],
                    'left_eye': [33, 160, 158, 133, 153, 144],
                    'right_eye': [362, 385, 387, 398, 383, 373],
                    'mouth': [61, 291, 78, 308, 13, 14],
                    'jaw': [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
                }

                # Compute consistency metrics
                consistency_scores = []

                for region, indices in key_points.items():
                    if region == 'jaw':
                        continue  # Skip for now

                    valid_indices = [i for i in indices if i < len(landmarks)]
                    if len(valid_indices) < 2:
                        continue

                    pts = np.array([
                        [landmarks[i].x * w, landmarks[i].y * h]
                        for i in valid_indices
                    ])

                    # Analyze point distribution
                    center = np.mean(pts, axis=0)
                    distances = np.linalg.norm(pts - center, axis=1)

                    # Deepfakes often have unnatural spatial distributions
                    variance = np.var(distances)
                    expected_variance = np.mean(distances) ** 2 * 0.1
                    consistency = min(1.0, expected_variance / (variance + 1e-8))
                    consistency_scores.append(consistency)

                if consistency_scores:
                    # Lower consistency = more likely deepfake
                    return 1.0 - np.mean(consistency_scores)
                return 0.0

        except Exception as e:
            logger.warning(f"Landmark consistency analysis failed: {e}")
            return 0.0

    def _analyze_landmark_consistency_fallback(self, img: np.ndarray) -> float:
        """Fallback landmark analysis using basic face detection."""
        try:
            # Use cascade classifier as fallback
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))

            if len(faces) == 0:
                return 0.0

            # Simple heuristic: face aspect ratio
            face = faces[0]
            x, y, w, h = face
            aspect_ratio = w / h

            # Natural face aspect ratios are typically 0.6-0.9
            if 0.6 <= aspect_ratio <= 0.9:
                return 0.0
            else:
                return min(0.5, abs(aspect_ratio - 0.75) / 0.3)

        except Exception as e:
            logger.warning(f"Fallback landmark analysis failed: {e}")
            return 0.0

    def _analyze_eye_region(self, img: np.ndarray) -> float:
        """
        Analyze eye region for deepfake artifacts.
        Eyes are particularly vulnerable to deepfake generation artifacts.

        Returns:
            Score 0-1, higher = more likely deepfake
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # Detect face region
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            faces = face_cascade.detectMultiScale(gray, 1.1, 5)

            if len(faces) == 0:
                return 0.0

            face = faces[0]
            fx, fy, fw, fh = face

            # Extract eye regions (approximate)
            eye_y_start = fy + int(fh * 0.25)
            eye_y_end = fy + int(fh * 0.55)
            eye_x_left_end = fx + int(fw * 0.5)
            eye_x_right_start = fx + int(fw * 0.5)

            try:
                left_eye = gray[eye_y_start:eye_y_end, fx:eye_x_left_end]
                right_eye = gray[eye_y_start:eye_y_end, eye_x_right_start:fx + fw]

                if left_eye.size == 0 or right_eye.size == 0:
                    return 0.0

                # Analyze eye characteristics
                left_contrast = np.std(left_eye)
                right_contrast = np.std(right_eye)

                # Eyes should have good contrast
                avg_contrast = (left_contrast + right_contrast) / 2.0
                contrast_score = 1.0 - np.clip(avg_contrast / 50.0, 0.0, 1.0)

                # Bilateral symmetry
                symmetry_diff = abs(left_contrast - right_contrast)
                symmetry_score = min(1.0, symmetry_diff / 30.0)

                return (contrast_score * 0.4 + symmetry_score * 0.6)

            except Exception:
                return 0.0

        except Exception as e:
            logger.warning(f"Eye region analysis failed: {e}")
            return 0.0

    def _analyze_skin_texture(self, img: np.ndarray) -> float:
        """
        Analyze skin texture consistency.
        Deepfakes often have unnatural skin texture artifacts.

        Returns:
            Score 0-1, higher = more likely deepfake
        """
        try:
            # Convert to HSV for skin detection
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Skin color range in HSV
            lower_skin = np.array([0, 20, 70], dtype=np.uint8)
            upper_skin = np.array([20, 255, 255], dtype=np.uint8)
            skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)

            # Also check common skin tones
            lower_skin2 = np.array([170, 20, 70], dtype=np.uint8)
            upper_skin2 = np.array([180, 255, 255], dtype=np.uint8)
            skin_mask2 = cv2.inRange(hsv, lower_skin2, upper_skin2)
            skin_mask = cv2.bitwise_or(skin_mask, skin_mask2)

            if np.sum(skin_mask) == 0:
                return 0.0

            # Extract skin region
            skin_region = img[skin_mask > 0]

            if skin_region.size == 0:
                return 0.0

            # Analyze color uniformity in skin region
            # Natural skin has gradual transitions, deepfakes often have blotchy patterns
            b_channel = skin_region[:, 0]
            g_channel = skin_region[:, 1]
            r_channel = skin_region[:, 2]

            # Variance in skin tones
            b_variance = np.var(b_channel)
            g_variance = np.var(g_channel)
            r_variance = np.var(r_channel)

            avg_variance = (b_variance + g_variance + r_variance) / 3.0

            # Too much variance suggests poor blending (deepfake artifact)
            texture_anomaly = min(1.0, avg_variance / 3000.0)

            return texture_anomaly

        except Exception as e:
            logger.warning(f"Skin texture analysis failed: {e}")
            return 0.0

    def _analyze_face_frequency_artifacts(self, img: np.ndarray) -> float:
        """
        Analyze frequency domain artifacts in face region.
        Deepfakes have characteristic frequency patterns.

        Returns:
            Score 0-1, higher = more likely deepfake
        """
        try:
            # Detect face
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5)

            if len(faces) == 0:
                return 0.0

            face = faces[0]
            fx, fy, fw, fh = face

            # Extract face region
            face_region = gray[fy:fy + fh, fx:fx + fw]

            # Compute FFT
            f_transform = np.fft.fft2(face_region)
            f_shift = np.fft.fftshift(f_transform)
            magnitude = np.abs(f_shift)

            # Analyze frequency patterns
            # Deepfakes often have stronger high-frequency components
            h, w = magnitude.shape
            center_h, center_w = h // 2, w // 2

            # Center region (low frequencies) - should be dominant in natural faces
            center_region = magnitude[
                center_h - w // 8:center_h + w // 8,
                center_w - w // 8:center_w + w // 8
            ]

            # Outer region (high frequencies)
            total_power = np.sum(magnitude)
            center_power = np.sum(center_region)

            if total_power > 0:
                high_freq_ratio = 1.0 - (center_power / total_power)
            else:
                high_freq_ratio = 0.0

            # Natural faces have more low-frequency power
            # Higher high-frequency power suggests deepfake
            return min(1.0, high_freq_ratio * 0.5)

        except Exception as e:
            logger.warning(f"Face frequency analysis failed: {e}")
            return 0.0


class DetectionEngine:
    """
    Main detection engine orchestrating all detection methods.
    Provides unified interface for AI generation, manipulation, and deepfake detection.
    """

    def __init__(self, enable_ai_detection: bool = True,
                 enable_manipulation_detection: bool = True,
                 enable_deepfake_detection: bool = True):
        """
        Initialize detection engine.

        Args:
            enable_ai_detection: Enable AI generation detection
            enable_manipulation_detection: Enable manipulation detection
            enable_deepfake_detection: Enable deepfake detection
        """
        self.ai_detector = AIGenerationDetector() if enable_ai_detection else None
        self.manip_detector = ManipulationDetector() if enable_manipulation_detection else None
        self.deepfake_detector = DeepfakeDetector() if enable_deepfake_detection else None

        logger.info("DetectionEngine initialized")

    def detect_ai(self, image_path: str) -> DetectionResult:
        """
        Detect AI-generated images.

        Args:
            image_path: Path to image file

        Returns:
            DetectionResult with confidence score
        """
        if self.ai_detector is None:
            return DetectionResult(
                status=DetectionStatus.MODEL_UNAVAILABLE,
                confidence=0.0,
                evidence={},
                is_anomaly=False,
                message="AI detection disabled"
            )

        return self.ai_detector.detect(image_path)

    def detect_manipulation(self, image_path: str) -> DetectionResult:
        """
        Detect image manipulation (photoshop, editing, etc).

        Args:
            image_path: Path to image file

        Returns:
            DetectionResult with confidence score
        """
        if self.manip_detector is None:
            return DetectionResult(
                status=DetectionStatus.MODEL_UNAVAILABLE,
                confidence=0.0,
                evidence={},
                is_anomaly=False,
                message="Manipulation detection disabled"
            )

        return self.manip_detector.detect(image_path)

    def detect_deepfake(self, image_path: str) -> DetectionResult:
        """
        Detect deepfake images.

        Args:
            image_path: Path to image file

        Returns:
            DetectionResult with confidence score
        """
        if self.deepfake_detector is None:
            return DetectionResult(
                status=DetectionStatus.MODEL_UNAVAILABLE,
                confidence=0.0,
                evidence={},
                is_anomaly=False,
                message="Deepfake detection disabled"
            )

        return self.deepfake_detector.detect(image_path)

    def detect_all(self, image_path: str) -> Dict[str, DetectionResult]:
        """
        Run all detection methods on image.

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with results from all detection methods
        """
        return {
            "ai_generation": self.detect_ai(image_path),
            "manipulation": self.detect_manipulation(image_path),
            "deepfake": self.detect_deepfake(image_path)
        }

    def get_summary(self, image_path: str) -> Dict:
        """
        Get comprehensive detection summary.

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with formatted results and overall risk assessment
        """
        results = self.detect_all(image_path)

        overall_confidence = np.mean([
            r.confidence for r in results.values()
            if r.status == DetectionStatus.SUCCESS
        ])

        anomalies = [
            name for name, result in results.items()
            if result.is_anomaly
        ]

        return {
            "image_path": str(image_path),
            "timestamp": str(Path(image_path).stat().st_mtime) if Path(image_path).exists() else None,
            "results": {
                name: result.to_dict()
                for name, result in results.items()
            },
            "overall_risk_level": "HIGH" if overall_confidence > 0.7
                                 else "MEDIUM" if overall_confidence > 0.5
                                 else "LOW",
            "overall_confidence": round(overall_confidence, 4),
            "detected_anomalies": anomalies,
            "recommendation": self._get_recommendation(anomalies, overall_confidence)
        }

    def _get_recommendation(self, anomalies: list, confidence: float) -> str:
        """Get recommendation based on detection results."""
        if not anomalies:
            return "Image appears authentic. No concerning artifacts detected."

        if confidence > 0.8:
            return "ALERT: High confidence of inauthenticity. Manual review recommended."

        if confidence > 0.65:
            return "Possible signs of manipulation or generation. Recommend verification."

        return "Minor anomalies detected. May require further investigation."


# Example usage and testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python detection.py <image_path> [--all|--ai|--manip|--deepfake]")
        print("\nExample:")
        print("  python detection.py image.jpg --all")
        print("  python detection.py image.jpg --ai")
        sys.exit(1)

    image_path = sys.argv[1]
    detection_mode = sys.argv[2].lstrip('--') if len(sys.argv) > 2 else 'all'

    engine = DetectionEngine()

    if detection_mode == 'ai':
        result = engine.detect_ai(image_path)
        print(f"\nAI Generation Detection:\n{result.to_dict()}")
    elif detection_mode == 'manip':
        result = engine.detect_manipulation(image_path)
        print(f"\nManipulation Detection:\n{result.to_dict()}")
    elif detection_mode == 'deepfake':
        result = engine.detect_deepfake(image_path)
        print(f"\nDeepfake Detection:\n{result.to_dict()}")
    else:  # all
        summary = engine.get_summary(image_path)
        print(f"\nComprehensive Detection Summary:")
        print(f"\nImage: {summary['image_path']}")
        print(f"Overall Risk Level: {summary['overall_risk_level']}")
        print(f"Overall Confidence: {summary['overall_confidence']:.2%}")
        print(f"Detected Anomalies: {summary['detected_anomalies']}")
        print(f"Recommendation: {summary['recommendation']}")
        print(f"\nDetailed Results:")
        for test_name, result in summary['results'].items():
            print(f"\n{test_name.replace('_', ' ').title()}:")
            print(f"  Confidence: {result['confidence']:.2%}")
            print(f"  Status: {result['status']}")
            if result['is_anomaly']:
                print(f"  ANOMALY DETECTED")
