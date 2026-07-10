"""
ArcFace face embedder.

Generates a 512-dimensional embedding vector from an aligned face image.
Uses InsightFace's buffalo_l model which includes both:
  - SCRFD (detection)
  - ArcFace (recognition)

Design:
  - FaceEmbedder loads the full buffalo_l model (detection + recognition).
  - embed_image_file() reads a saved image and extracts one embedding.
  - embed_frame() runs detection + embedding on a live BGR frame.

Embedding storage:
  - Each embedding is saved as a .npy file (512 float32 values, ~2 KB).
  - The file path is stored in the DB (FaceEmbedding.embedding_path).
  - At recognition time all embeddings are loaded into memory as a matrix.
"""

import cv2
import logging
import numpy as np
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class FaceEmbedder:
    def __init__(self, ctx_id: int = -1):
        self.ctx_id = ctx_id
        self._app = None
        self._ready = False

    def load(self) -> bool:
        """Load InsightFace buffalo_l model (detection + ArcFace recognition)."""
        try:
            from insightface.app import FaceAnalysis

            logger.info("Loading InsightFace buffalo_l (det + rec)...")
            self._app = FaceAnalysis(
                name="buffalo_l",
                providers=self._get_providers(),
            )
            self._app.prepare(ctx_id=self.ctx_id, det_size=(640, 640))
            self._ready = True
            logger.info(f"FaceEmbedder ready | ctx_id={self.ctx_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load FaceEmbedder: {e}")
            return False

    # ------------------------------------------------------------------
    # Embedding from a saved image file
    # ------------------------------------------------------------------

    def embed_image_file(self, image_path: str) -> np.ndarray | None:
        """
        Load an image from disk, detect the face, and return its embedding.
        Returns None if no face is found or loading fails.
        """
        if not self._ready:
            logger.error("FaceEmbedder not loaded.")
            return None

        frame = cv2.imread(image_path)
        if frame is None:
            logger.warning(f"Could not read image: {image_path}")
            return None

        return self._extract_embedding(frame)

    # ------------------------------------------------------------------
    # Embedding from a live BGR frame (used in recognition pipeline)
    # ------------------------------------------------------------------

    def embed_frame(self, frame: np.ndarray):
        """
        Run full detection + embedding on a raw BGR frame.
        Returns (embedding, face) or (None, None).
        Used by the recognition pipeline (process_frame / camera thread).
        """
        if not self._ready or self._app is None:
            return None, None
        try:
            faces = self._app.get(frame)
            if not faces:
                return None, None
            face = sorted(faces, key=lambda f: f.det_score, reverse=True)[0]
            if face.embedding is None:
                return None, None
            return face.embedding, face
        except Exception as e:
            logger.warning(f"embed_frame error: {e}")
            return None, None

    # ------------------------------------------------------------------
    # Batch generate embeddings for all images of a student
    # ------------------------------------------------------------------

    def generate_for_student(
        self,
        image_paths: list[str],
        student_id: int,
    ) -> list[dict]:
        """
        Generate and save embeddings for a list of image paths.

        Returns a list of dicts:
            [{"image_path": ..., "embedding_path": ..., "success": bool}, ...]
        """
        results = []
        emb_dir = Path(settings.embeddings_dir) / str(student_id)
        emb_dir.mkdir(parents=True, exist_ok=True)

        for image_path in image_paths:
            emb = self.embed_image_file(image_path)
            if emb is None:
                logger.warning(f"No embedding for {image_path}")
                results.append({
                    "image_path": image_path,
                    "embedding_path": "",
                    "success": False,
                })
                continue

            # Build .npy filename from image filename
            stem = Path(image_path).stem
            emb_path = emb_dir / f"{stem}.npy"
            np.save(str(emb_path), emb)

            results.append({
                "image_path": image_path,
                "embedding_path": str(emb_path),
                "success": True,
            })
            logger.info(f"Embedding saved: {emb_path}")

        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_embedding(self, frame: np.ndarray) -> np.ndarray | None:
        """Run detection + recognition on frame, return embedding or None."""
        try:
            faces = self._app.get(frame)
            if not faces:
                return None
            face = sorted(faces, key=lambda f: f.det_score, reverse=True)[0]
            return face.embedding  # 512-dim float32 ndarray
        except Exception as e:
            logger.warning(f"Embedding extraction error: {e}")
            return None

    def _get_providers(self) -> list[str]:
        if self.ctx_id >= 0:
            try:
                import onnxruntime as ort
                if "CUDAExecutionProvider" in ort.get_available_providers():
                    return ["CUDAExecutionProvider", "CPUExecutionProvider"]
            except Exception:
                pass
        return ["CPUExecutionProvider"]

    @property
    def is_ready(self) -> bool:
        return self._ready


# Singleton — defaults to CPU (ctx_id=-1). Pass settings.get_ctx_id() to honor USE_GPU.
face_embedder = FaceEmbedder()
