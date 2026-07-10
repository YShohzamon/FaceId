"""
Face detector using InsightFace SCRFD model.

SCRFD (Sample and Computation Redistribution Face Detector) is fast,
accurate, and works well at 2-3 meter distances.

InsightFace downloads the model automatically on first use (~30 MB).
The model is cached in ~/.insightface/models/

Detection result:
    FaceDetection(bbox, kps, score)
    - bbox: [x1, y1, x2, y2]  (pixel coords)
    - kps:  5 keypoints [[x,y], ...] for alignment
    - score: confidence (0.0 - 1.0)
"""

import logging
import numpy as np
import cv2

logger = logging.getLogger(__name__)


class FaceDetector:
    def __init__(self, det_size: tuple[int, int] = (640, 640), ctx_id: int = -1):
        """
        Args:
            det_size: SCRFD input resolution. (640,640) is the best balance of
                      speed vs accuracy. Lower = faster, Higher = better for small faces.
            ctx_id:   -1 = CPU, 0 = first GPU
        """
        self.det_size = det_size
        self.ctx_id = ctx_id
        self._app = None
        self._ready = False

    def load(self) -> bool:
        """Load the InsightFace app with SCRFD detector. Returns True on success."""
        try:
            import insightface
            from insightface.app import FaceAnalysis

            logger.info("Loading InsightFace model (may download on first run)...")

            # Lightweight SCRFD-only fallback when FaceEmbedder (buffalo_l) is not loaded.
            self._app = FaceAnalysis(
                name="buffalo_sc",
                allowed_modules=["detection"],
                providers=self._get_providers(),
            )
            self._app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
            self._ready = True
            logger.info(f"FaceDetector ready | ctx_id={self.ctx_id} | det_size={self.det_size}")
            return True

        except Exception as e:
            logger.error(f"Failed to load FaceDetector: {e}")
            return False

    def detect(self, frame: np.ndarray) -> list:
        """
        Run face detection on a BGR frame.

        Returns a list of detected faces (InsightFace Face objects).
        Each face has:  .bbox, .kps, .det_score
        Returns empty list if not ready or no face found.
        """
        if not self._ready or self._app is None:
            return []

        try:
            faces = self._app.get(frame)
            # Keep only the highest-confidence face (single-person system)
            if faces:
                faces = sorted(faces, key=lambda f: f.det_score, reverse=True)
                return faces[:1]
            return []

        except Exception as e:
            logger.warning(f"Detection error: {e}")
            return []

    def align_face(self, frame: np.ndarray, face) -> np.ndarray | None:
        """
        Crop and align face to 112x112 using 5 landmark points.
        Returns aligned BGR image or None on failure.
        """
        if face.kps is None:
            return None
        try:
            from insightface.utils import face_align
            aligned = face_align.norm_crop(frame, landmark=face.kps)
            return aligned
        except Exception as e:
            logger.warning(f"Face alignment error: {e}")
            return None

    @property
    def is_ready(self) -> bool:
        return self._ready

    def _get_providers(self) -> list[str]:
        """Return ONNX Runtime execution providers in priority order."""
        if self.ctx_id >= 0:
            try:
                import onnxruntime as ort
                available = ort.get_available_providers()
                if "CUDAExecutionProvider" in available:
                    logger.info("GPU (CUDA) provider selected.")
                    return ["CUDAExecutionProvider", "CPUExecutionProvider"]
            except Exception:
                pass
        logger.info("CPU provider selected.")
        return ["CPUExecutionProvider"]


# Singleton — defaults to CPU (ctx_id=-1). Pass settings.get_ctx_id() to honor USE_GPU.
face_detector = FaceDetector()
