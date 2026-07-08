"""
Recognition pipeline — called from the dedicated recognition thread.

Each frame goes through:
  Embedder (detection + ArcFace) → Matcher → return result dict

The frame-skip mechanism has been removed. Since the recognition thread
runs independently from the capture thread, there is no need to skip
frames to keep capture FPS high — the two threads operate concurrently.

The capture thread applies the cached result overlay at full camera speed.
"""

import logging
import numpy as np

from app.recognition.matcher import match_embedding, MatchResult
from app.services.embedding_service import store_is_empty

logger = logging.getLogger(__name__)


def process_frame(
    frame: np.ndarray,
    embedder,
    fps: float,
) -> tuple[np.ndarray, dict]:
    """
    Run the full recognition pipeline on one BGR frame.

    Note: The returned annotated_frame is NOT used by the capture thread —
    the capture thread draws the overlay itself from the result dict.
    The annotated_frame is returned only for API compatibility.

    Returns:
        (frame, result_dict)

        result_dict keys:
            face_detected: bool
            label:         str
            confidence:    float
            state:         "known" | "unknown" | "scanning"
            bbox:          list[int] or []
    """
    result = {
        "face_detected": False,
        "label": "",
        "confidence": 0.0,
        "state": "scanning",
        "bbox": [],
    }

    if not embedder.is_ready:
        return frame, result

    try:
        embedding, face = embedder.embed_frame(frame)

        if face is None or embedding is None:
            return frame, result

        bbox = face.bbox
        result["face_detected"] = True
        result["bbox"] = [int(v) for v in bbox]

        if store_is_empty():
            result["state"] = "scanning"
            result["label"] = "No students enrolled"
            return frame, result

        match: MatchResult = match_embedding(embedding)

        if match.matched:
            result["label"] = match.student_name
            result["confidence"] = match.confidence
            result["state"] = "known"
        else:
            result["label"] = "Stranger"
            result["confidence"] = match.confidence
            result["state"] = "unknown"

    except Exception as e:
        logger.warning(f"Pipeline error: {e}")

    return frame, result
