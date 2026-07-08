"""
Face capture helper for enrollment.

Workflow:
  1. Camera is already running (CameraManager).
  2. Caller asks for a frame snapshot at the current moment.
  3. We check that exactly one face is present and it is large enough.
  4. We save the raw image and return the path.

The 5 angle sequence is managed by the API layer / frontend.
Each angle is captured on-demand when the user is ready.

Angles (in order):
  0 - Front
  1 - Left
  2 - Right
  3 - Up (slightly)
  4 - Down (slightly)

Face validation supports two detector types:
  - FaceDetector (SCRFD standalone)
  - FaceEmbedder (buffalo_l) via embed_frame()  ← preferred when already loaded
"""

import cv2
import uuid
import logging
from pathlib import Path

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

ANGLE_LABELS = ["front", "left", "right", "up", "down"]
ANGLE_INSTRUCTIONS = [
    "Look straight at the camera",
    "Turn your head slightly to the LEFT",
    "Turn your head slightly to the RIGHT",
    "Tilt your head slightly UP",
    "Tilt your head slightly DOWN",
]

# Minimum face bounding-box area as fraction of frame area
MIN_FACE_AREA_RATIO = 0.04


class CaptureError(Exception):
    """Raised when a capture attempt fails validation."""
    pass


def _detect_faces_generic(frame: np.ndarray, detector) -> list:
    """
    Detect faces using either a FaceDetector or FaceEmbedder.
    Returns a list of face objects (each has a .bbox attribute).
    Returns empty list on failure.
    """
    if hasattr(detector, "embed_frame"):
        # FaceEmbedder path: uses buffalo_l's detection result
        try:
            _emb, face = detector.embed_frame(frame)
            if face is None:
                return []
            return [face]
        except Exception as e:
            logger.warning(f"embedder detect error: {e}")
            return []
    elif hasattr(detector, "detect"):
        # FaceDetector path: standalone SCRFD
        try:
            return detector.detect(frame) or []
        except Exception as e:
            logger.warning(f"detector detect error: {e}")
            return []
    return []


def _validate_single_face(frame: np.ndarray, detector) -> object:
    """Return the largest detected face or raise CaptureError."""
    faces = _detect_faces_generic(frame, detector)
    if not faces:
        raise CaptureError("No face detected in the image.")
    if len(faces) > 1:
        raise CaptureError("Multiple faces detected. Only one person should be in the image.")

    face = faces[0]
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    face_area = (x2 - x1) * (y2 - y1)
    frame_area = frame.shape[0] * frame.shape[1]

    if face_area / frame_area < MIN_FACE_AREA_RATIO:
        raise CaptureError("Face is too small in the image. Use a closer photo.")

    return face


def _save_angle_frame(
    student_folder: Path,
    angle_index: int,
    frame: np.ndarray,
    face,
) -> dict:
    """Save a validated frame for the given angle and return capture metadata."""
    angle_label = ANGLE_LABELS[angle_index]
    filename = f"{angle_label}_{uuid.uuid4().hex[:8]}.jpg"
    image_path = student_folder / filename
    student_folder.mkdir(parents=True, exist_ok=True)

    success = cv2.imwrite(str(image_path), frame)
    if not success:
        raise CaptureError("Failed to save image. Check disk permissions.")

    logger.info(f"Saved angle '{angle_label}' -> {image_path}")

    det_score = float(getattr(face, "det_score", 1.0))
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    return {
        "image_path": str(image_path),
        "angle_label": angle_label,
        "bbox": [x1, y1, x2, y2],
        "score": det_score,
    }


def capture_angle(
    student_folder: Path,
    angle_index: int,
    detector,
    camera_manager,
) -> dict:
    """
    Capture one face image for the given angle index.

    Args:
        student_folder: Directory to save images in.
        angle_index:    0..4 corresponding to ANGLE_LABELS.
        detector:       FaceDetector OR FaceEmbedder instance (must be ready).
        camera_manager: CameraManager instance (must be running).

    Returns:
        {
            "image_path": str,
            "angle_label": str,
            "bbox": [x1, y1, x2, y2],
            "score": float,
        }

    Raises:
        CaptureError with a user-friendly message.
    """
    if not camera_manager.is_running:
        raise CaptureError("Camera is not running. Start the camera first.")

    if not detector.is_ready:
        raise CaptureError("Face detector is not loaded.")

    frame = camera_manager.get_latest_raw()
    if frame is None:
        raise CaptureError("Could not read a frame from the camera.")

    face = _validate_single_face(frame, detector)
    return _save_angle_frame(student_folder, angle_index, frame, face)


def upload_angle_from_file(
    student_folder: Path,
    angle_index: int,
    detector,
    file_bytes: bytes,
) -> dict:
    """
    Save one face image for the given angle from an uploaded file.

    Raises:
        CaptureError with a user-friendly message.
    """
    if not detector.is_ready:
        raise CaptureError("Face detector is not loaded.")

    if not file_bytes:
        raise CaptureError("Uploaded file is empty.")

    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise CaptureError("Could not read the image file. Use JPG, PNG, or WEBP.")

    face = _validate_single_face(frame, detector)
    return _save_angle_frame(student_folder, angle_index, frame, face)


def make_student_folder(student_name: str, student_id: int) -> Path:
    """Create a unique folder for a student's face images."""
    safe_name = "".join(c if c.isalnum() else "_" for c in student_name)
    folder = Path(settings.face_images_dir) / f"{student_id}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
