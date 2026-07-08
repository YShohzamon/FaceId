"""
Embedding service — generate and store ArcFace embeddings for a student.

Also provides the in-memory embedding store used by the recognition engine.
All student embeddings are loaded into a NumPy matrix at startup / after enrollment.
"""

import logging
import numpy as np
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.face_embedding import FaceEmbedding
from app.models.student import Student

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# In-memory embedding store
# ------------------------------------------------------------------
# Structure:
#   _embeddings_matrix : (N, 512) float32   — stacked embeddings
#   _student_ids       : list[int]           — matching student IDs
#   _student_names     : list[str]           — matching student names
#
# These are rebuilt after enrollment or on startup.

_embeddings_matrix: np.ndarray | None = None
_student_ids: list[int] = []
_student_names: list[str] = []


async def generate_embeddings_for_student(
    db: AsyncSession,
    student_id: int,
    embedder,
) -> dict:
    """
    Generate ArcFace embeddings for all captured images of a student
    that don't yet have an embedding.

    Updates FaceEmbedding.embedding_path in the DB.

    Returns:
        {"generated": int, "failed": int, "total": int}
    """
    # Fetch all image records without an embedding
    result = await db.execute(
        select(FaceEmbedding)
        .where(FaceEmbedding.student_id == student_id)
        .where(FaceEmbedding.embedding_path == "")
    )
    records: list[FaceEmbedding] = result.scalars().all()

    if not records:
        logger.info(f"No pending embeddings for student {student_id}.")
        return {"generated": 0, "failed": 0, "total": 0}

    image_paths = [r.image_path for r in records]

    # Run embedding generation (CPU-bound, called from async context via to_thread)
    results = embedder.generate_for_student(image_paths, student_id)

    generated = 0
    failed = 0

    for record, res in zip(records, results):
        if res["success"] and res["embedding_path"]:
            record.embedding_path = res["embedding_path"]
            generated += 1
        else:
            failed += 1

    await db.commit()
    logger.info(
        f"Student {student_id}: {generated} embeddings generated, {failed} failed."
    )
    return {"generated": generated, "failed": failed, "total": len(records)}


async def load_all_embeddings(db: AsyncSession) -> int:
    """
    Load all embeddings from disk into the in-memory store.
    Called at startup and after each enrollment.

    Returns the total number of embeddings loaded.
    """
    global _embeddings_matrix, _student_ids, _student_names

    result = await db.execute(
        select(FaceEmbedding, Student.name)
        .join(Student, FaceEmbedding.student_id == Student.id)
        .where(FaceEmbedding.embedding_path != "")
        .where(Student.is_active == True)
    )
    rows = result.all()

    vectors = []
    ids = []
    names = []

    for emb_record, student_name in rows:
        path = Path(emb_record.embedding_path)
        if not path.exists():
            logger.warning(f"Embedding file missing: {path}")
            continue
        try:
            vec = np.load(str(path)).astype(np.float32)
            vectors.append(vec)
            ids.append(emb_record.student_id)
            names.append(student_name)
        except Exception as e:
            logger.warning(f"Failed to load embedding {path}: {e}")

    if vectors:
        _embeddings_matrix = np.stack(vectors, axis=0)  # (N, 512)
        # L2-normalize all rows so cosine similarity = dot product
        norms = np.linalg.norm(_embeddings_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        _embeddings_matrix = _embeddings_matrix / norms
    else:
        _embeddings_matrix = None

    _student_ids = ids
    _student_names = names

    logger.info(f"Embedding store: {len(vectors)} vectors loaded.")
    return len(vectors)


def get_embedding_store() -> tuple:
    """Return (matrix, ids, names) — used by the recognition matcher."""
    return _embeddings_matrix, _student_ids, _student_names


def store_is_empty() -> bool:
    return _embeddings_matrix is None or len(_student_ids) == 0
