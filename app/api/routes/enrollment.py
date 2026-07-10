"""
Enrollment API routes.

Flow:
  POST /api/enroll/student                      — create student record
  POST /api/enroll/capture/{id}/{angle_index}   — capture one face angle
  POST /api/enroll/upload/{id}/{angle_index}    — upload one face angle from file
  POST /api/enroll/generate/{id}                — generate ArcFace embeddings
  GET  /api/enroll/angles                       — angle list + instructions
  GET  /api/enroll/status/{id}                  — angles captured so far
"""

import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.database.connection import get_db
from app.models.face_embedding import FaceEmbedding
from app.services.student_service import create_student, get_student_by_id
from app.services.student_service import save_face_image_record
from app.services.embedding_service import (
    generate_embeddings_for_student,
    load_all_embeddings,
)
from app.recognition.embedder import face_embedder
from app.recognition.camera import camera_manager
from app.recognition.detector import face_detector
from app.enrollment.capture import (
    capture_angle,
    upload_angle_from_file,
    make_student_folder,
    ANGLE_LABELS,
    ANGLE_INSTRUCTIONS,
    CaptureError,
)

router = APIRouter(prefix="/api/enroll", tags=["enrollment"])
logger = logging.getLogger(__name__)

TOTAL_ANGLES = len(ANGLE_LABELS)  # 5
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
}


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class StudentCreateRequest(BaseModel):
    name: str
    student_code: str | None = None


class StudentCreateResponse(BaseModel):
    student_id: int
    name: str
    message: str


class CaptureResponse(BaseModel):
    success: bool
    angle_label: str
    angle_index: int
    angles_done: int
    total_angles: int
    enrollment_complete: bool
    message: str


async def _get_active_detector():
    """Return the best available face detector (buffalo_l preferred)."""
    if face_embedder.is_ready:
        return face_embedder

    if not face_detector.is_ready:
        loaded = await asyncio.to_thread(face_detector.load)
        if not loaded:
            raise HTTPException(status_code=503, detail="Face detector failed to load.")
    return face_detector


async def _save_angle_and_respond(
    student_id: int,
    angle_index: int,
    result: dict,
    db: AsyncSession,
) -> CaptureResponse:
    await save_face_image_record(
        db,
        student_id=student_id,
        image_path=result["image_path"],
        angle_label=result["angle_label"],
    )

    # Counts face_embeddings rows (image captured); .npy files come from /generate.
    angles_done = await db.scalar(
        select(func.count(FaceEmbedding.id))
        .where(FaceEmbedding.student_id == student_id)
    )
    enrollment_complete = angles_done >= TOTAL_ANGLES

    return CaptureResponse(
        success=True,
        angle_label=result["angle_label"],
        angle_index=angle_index,
        angles_done=angles_done,
        total_angles=TOTAL_ANGLES,
        enrollment_complete=enrollment_complete,
        message=(
            "Enrollment complete! Embeddings will be generated."
            if enrollment_complete
            else f"Captured {angles_done}/{TOTAL_ANGLES} angles."
        ),
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/angles")
async def get_angles():
    """Return the ordered list of angles and their instructions."""
    return {
        "angles": [
            {"index": i, "label": ANGLE_LABELS[i], "instruction": ANGLE_INSTRUCTIONS[i]}
            for i in range(TOTAL_ANGLES)
        ]
    }


@router.post("/student", response_model=StudentCreateResponse)
async def create_student_record(
    payload: StudentCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Step 1: Create the student DB record before capturing images."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Student name cannot be empty.")

    student = await create_student(db, name=name, student_code=payload.student_code)
    return StudentCreateResponse(
        student_id=student.id,
        name=student.name,
        message="Student created. Proceed to face capture.",
    )


@router.post("/capture/{student_id}/{angle_index}", response_model=CaptureResponse)
async def capture_face_angle(
    student_id: int,
    angle_index: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2 (×5): Capture one face image for the given angle.
    The frontend calls this endpoint for each of the 5 angles in sequence.
    """
    if angle_index < 0 or angle_index >= TOTAL_ANGLES:
        raise HTTPException(
            status_code=422,
            detail=f"angle_index must be 0–{TOTAL_ANGLES - 1}."
        )

    student = await get_student_by_id(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Ensure camera is running
    if not camera_manager.is_running:
        raise HTTPException(status_code=503, detail="Camera is not running. Open camera first.")

    # Prefer buffalo_l (already loaded for stream) over standalone SCRFD
    active_detector = await _get_active_detector()

    # Build the student's image folder
    student_folder = make_student_folder(student.name, student.id)

    try:
        result = await asyncio.to_thread(
            capture_angle,
            student_folder,
            angle_index,
            active_detector,
            camera_manager,
        )
    except CaptureError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await _save_angle_and_respond(student_id, angle_index, result, db)


@router.post("/upload/{student_id}/{angle_index}", response_model=CaptureResponse)
async def upload_face_angle(
    student_id: int,
    angle_index: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload one face image for the given angle from a file (no camera required).
    """
    if angle_index < 0 or angle_index >= TOTAL_ANGLES:
        raise HTTPException(
            status_code=422,
            detail=f"angle_index must be 0–{TOTAL_ANGLES - 1}."
        )

    student = await get_student_by_id(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Unsupported file type. Use JPG, PNG, WEBP, or BMP.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=422, detail="File is too large. Maximum size is 10 MB.")

    active_detector = await _get_active_detector()
    student_folder = make_student_folder(student.name, student.id)

    try:
        result = await asyncio.to_thread(
            upload_angle_from_file,
            student_folder,
            angle_index,
            active_detector,
            file_bytes,
        )
    except CaptureError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await _save_angle_and_respond(student_id, angle_index, result, db)


@router.get("/status/{student_id}")
async def enrollment_status(student_id: int, db: AsyncSession = Depends(get_db)):
    """Return how many angles have been captured for a student."""
    student = await get_student_by_id(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    angles_done = await db.scalar(
        select(func.count(FaceEmbedding.id))
        .where(FaceEmbedding.student_id == student_id)
    )

    return {
        "student_id": student_id,
        "student_name": student.name,
        "angles_done": angles_done,
        "total_angles": TOTAL_ANGLES,
        "complete": angles_done >= TOTAL_ANGLES,
    }


@router.post("/generate/{student_id}")
async def generate_embeddings(
    student_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate ArcFace embeddings for all captured images of a student.
    Reloads the in-memory embedding store so recognition works immediately.
    """
    student = await get_student_by_id(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Load embedder if not already loaded (buffalo_l ~300 MB, downloads once)
    if not face_embedder.is_ready:
        logger.info("Loading ArcFace model (buffalo_l)...")
        loaded = await asyncio.to_thread(face_embedder.load)
        if not loaded:
            raise HTTPException(
                status_code=503,
                detail="ArcFace model failed to load. Check logs.",
            )

    # Fetch all image records that don't have an embedding yet
    result = await db.execute(
        select(FaceEmbedding)
        .where(FaceEmbedding.student_id == student_id)
        .where(FaceEmbedding.embedding_path == "")
    )
    pending_records: list[FaceEmbedding] = result.scalars().all()

    if not pending_records:
        return {
            "student_id": student_id,
            "generated": 0,
            "failed": 0,
            "total": 0,
            "message": "All images already have embeddings.",
        }

    image_paths = [r.image_path for r in pending_records]

    # CPU-heavy: run in thread pool so the event loop stays unblocked
    emb_results = await asyncio.to_thread(
        face_embedder.generate_for_student, image_paths, student_id
    )

    # Update DB records with the generated embedding paths
    generated = 0
    failed = 0
    for record, res in zip(pending_records, emb_results):
        if res["success"] and res["embedding_path"]:
            record.embedding_path = res["embedding_path"]
            generated += 1
        else:
            failed += 1

    await db.commit()
    logger.info(f"Student {student_id}: {generated} embeddings saved, {failed} failed.")

    # Reload in-memory store so recognition picks up the new student immediately
    total_loaded = await load_all_embeddings(db)
    logger.info(f"Embedding store reloaded: {total_loaded} vectors.")

    return {
        "student_id": student_id,
        "student_name": student.name,
        "generated": generated,
        "failed": failed,
        "total": len(pending_records),
        "store_size": total_loaded,
        "message": f"Generated {generated}/{len(pending_records)} embeddings successfully.",
    }
