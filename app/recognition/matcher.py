"""
Face matcher — compares a query embedding against the in-memory store.

Algorithm:
  - All stored embeddings are L2-normalized (done at load time).
  - Query embedding is L2-normalized here.
  - Similarity = dot product (equivalent to cosine similarity for unit vectors).
  - Best match is the stored embedding with the highest dot product.
  - If best score >= threshold → recognized; else → Stranger.

This is extremely fast: a matrix multiply of shape (1, 512) @ (512, N)
runs in microseconds on CPU even for hundreds of students.
"""

import numpy as np
import logging

from app.core.config import settings
from app.services.embedding_service import get_embedding_store, store_is_empty

logger = logging.getLogger(__name__)


class MatchResult:
    __slots__ = ("matched", "student_id", "student_name", "confidence")

    def __init__(
        self,
        matched: bool,
        student_id: int | None,
        student_name: str,
        confidence: float,
    ):
        self.matched = matched
        self.student_id = student_id
        self.student_name = student_name
        self.confidence = confidence

    @property
    def state(self) -> str:
        if self.matched:
            return "known"
        return "unknown"

    def __repr__(self) -> str:
        return (
            f"<MatchResult matched={self.matched} "
            f"name={self.student_name!r} conf={self.confidence:.3f}>"
        )


def match_embedding(query: np.ndarray) -> MatchResult:
    """
    Compare query embedding against the in-memory store.

    Args:
        query: 512-dim float32 embedding (raw, not normalized).

    Returns:
        MatchResult with .matched, .student_id, .student_name, .confidence
    """
    if store_is_empty():
        return MatchResult(
            matched=False,
            student_id=None,
            student_name="Stranger",
            confidence=0.0,
        )

    matrix, ids, names = get_embedding_store()

    # L2-normalize query
    norm = np.linalg.norm(query)
    if norm == 0:
        return MatchResult(False, None, "Stranger", 0.0)
    query_normed = query / norm

    # Cosine similarities: shape (N,)
    similarities = matrix @ query_normed  # matrix is already normalized

    best_idx = int(np.argmax(similarities))
    best_score = float(similarities[best_idx])
    threshold = settings.recognition_threshold

    if best_score >= threshold:
        return MatchResult(
            matched=True,
            student_id=ids[best_idx],
            student_name=names[best_idx],
            confidence=best_score,
        )

    return MatchResult(
        matched=False,
        student_id=None,
        student_name="Stranger",
        confidence=best_score,
    )
