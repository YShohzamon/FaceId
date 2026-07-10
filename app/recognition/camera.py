"""
Camera manager — two-thread architecture for maximum FPS.

Thread 1: _capture_loop
  - Reads raw frames from the webcam at full speed.
  - Applies the cached recognition overlay (bbox + label drawn in microseconds).
  - Encodes to JPEG and stores the result.
  - Never blocked by slow AI inference — always runs at camera speed (~30 fps).

Thread 2: _recognition_loop
  - Runs face detection + ArcFace on the latest raw frame.
  - Updates the cached detection result after each inference.
  - Runs as fast as the model allows (typically 5-15 fps on CPU).
  - Completely decoupled from Thread 1.

Result: capture FPS stays near the camera's native rate even when recognition
        is slow. The bounding box just "sticks" to the last known position
        between recognition cycles — imperceptible at normal speeds.
"""

import cv2
import time
import threading
import logging
import numpy as np
from collections import deque
from dataclasses import dataclass, field

from app.recognition.drawing import draw_face_box, draw_fps

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Latest detection/recognition result — shared between threads."""
    face_detected: bool = False
    label: str = ""
    confidence: float = 0.0
    bbox: list = field(default_factory=list)
    state: str = "scanning"


class CameraManager:
    def __init__(
        self,
        camera_index: int = 0,
        target_width: int = 640,
        target_height: int = 480,
    ):
        self.camera_index = camera_index
        self.target_width = target_width
        self.target_height = target_height

        self._cap: cv2.VideoCapture | None = None
        self._capture_thread: threading.Thread | None = None
        self._recognition_thread: threading.Thread | None = None
        self._running = False

        # Shared between threads — protected by _lock
        self._frame_lock = threading.Lock()
        self._latest_frame: bytes | None = None   # encoded JPEG
        self._latest_raw: np.ndarray | None = None

        # Latest recognition result — written by recognition thread,
        # read by capture thread for overlay. Protected by _det_lock.
        self._det_lock = threading.Lock()
        self.detection_result = DetectionResult()

        # Pluggable embedder — attached by stream.py
        self.embedder = None

        # FPS measured over last 60 frames
        self._frame_times: deque = deque(maxlen=60)
        self.fps: float = 0.0

        self._consumer_count: int = 0
        self._consumer_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Open camera and start both threads. Returns True on success."""
        if self._running:
            return True

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            logger.warning("CAP_DSHOW failed, retrying with default backend...")
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.error(f"Could not open camera index {self.camera_index}")
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._cap = cap
        self._running = True

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="camera-capture",
        )
        self._recognition_thread = threading.Thread(
            target=self._recognition_loop,
            daemon=True,
            name="camera-recognition",
        )
        self._capture_thread.start()
        self._recognition_thread.start()

        logger.info("Camera started (capture + recognition threads).")
        return True

    def stop(self) -> None:
        """Stop both threads and release camera."""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        if self._recognition_thread:
            self._recognition_thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        with self._frame_lock:
            self._latest_frame = None
            self._latest_raw = None
        with self._det_lock:
            self.detection_result = DetectionResult()
        self.fps = 0.0
        logger.info("Camera stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_latest_frame(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_frame

    def get_latest_raw(self) -> np.ndarray | None:
        with self._frame_lock:
            return self._latest_raw.copy() if self._latest_raw is not None else None

    def get_detection_result(self) -> DetectionResult:
        with self._det_lock:
            r = self.detection_result
            return DetectionResult(
                face_detected=r.face_detected,
                label=r.label,
                confidence=r.confidence,
                bbox=list(r.bbox),
                state=r.state,
            )

    def add_consumer(self) -> None:
        with self._consumer_lock:
            self._consumer_count += 1

    def remove_consumer(self) -> None:
        with self._consumer_lock:
            self._consumer_count = max(0, self._consumer_count - 1)

    # ------------------------------------------------------------------
    # Thread 1: Capture loop — runs at full camera speed
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """
        Read raw frames and encode to JPEG as fast as the camera allows.
        Apply the cached recognition overlay — no AI inference here.
        """
        jpeg_params = [cv2.IMWRITE_JPEG_QUALITY, 80]

        while self._running:
            if not self._cap or not self._cap.isOpened():
                break

            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Frame read failed.")
                time.sleep(0.01)
                continue

            # Store raw frame for the recognition thread and enrollment capture
            with self._frame_lock:
                self._latest_raw = frame  # no copy — recognition thread copies

            # Draw cached recognition overlay (microseconds — no AI)
            with self._det_lock:
                r = self.detection_result

            if r.face_detected and r.bbox:
                draw_face_box(
                    frame,
                    r.bbox,
                    label=r.label,
                    confidence=r.confidence,
                    state=r.state,
                )

            draw_fps(frame, self.fps)

            # Encode to JPEG
            success, buf = cv2.imencode(".jpg", frame, jpeg_params)
            if success:
                with self._frame_lock:
                    self._latest_frame = buf.tobytes()

            # Track FPS
            now = time.monotonic()
            self._frame_times.append(now)
            if len(self._frame_times) >= 2:
                elapsed = self._frame_times[-1] - self._frame_times[0]
                if elapsed > 0:
                    self.fps = round((len(self._frame_times) - 1) / elapsed, 1)

            # Yield briefly; longer sleep when no one is watching
            with self._consumer_lock:
                consumers = self._consumer_count
            time.sleep(0.001 if consumers > 0 else 0.020)

    # ------------------------------------------------------------------
    # Thread 2: Recognition loop — runs as fast as model allows
    # ------------------------------------------------------------------

    def _recognition_loop(self) -> None:
        """
        Run face detection + ArcFace on the latest raw frame.
        This thread is completely independent of the capture thread — it may
        run at 5-15 fps on CPU, but that does NOT affect capture FPS.
        """
        from app.recognition.pipeline import process_frame

        while self._running:
            # Wait for embedder to be ready
            if not (self.embedder and self.embedder.is_ready):
                with self._det_lock:
                    self.detection_result = DetectionResult(state="scanning")
                time.sleep(0.05)
                continue

            # Grab latest raw frame
            with self._frame_lock:
                raw = self._latest_raw
                if raw is not None:
                    raw = raw.copy()

            if raw is None:
                time.sleep(0.02)
                continue

            try:
                _annotated, result = process_frame(raw, self.embedder, self.fps)

                with self._det_lock:
                    self.detection_result = DetectionResult(
                        face_detected=result["face_detected"],
                        label=result["label"],
                        confidence=result["confidence"],
                        bbox=result["bbox"],
                        state=result["state"],
                    )
            except Exception as e:
                logger.warning(f"Recognition thread error: {e}")
                time.sleep(0.05)

            # No fixed sleep — run as fast as the model allows.
            # On CPU with buffalo_l this is naturally throttled to ~5-15fps.
            # Uncomment the line below to cap recognition at N fps:
            # time.sleep(1 / 10)  # max 10 recognition fps


# Singleton
camera_manager = CameraManager()
