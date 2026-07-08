"""
Camera stream routes.

/api/stream/start  — start camera + load embedder (det + ArcFace)
/api/stream/stop   — stop camera
/api/stream/feed   — MJPEG video stream (annotated frames)
/api/stream/status — JSON: camera state, FPS, recognition result + attendance logging
"""

import asyncio
import logging
import numpy as np
import cv2
from fastapi import APIRouter, Depends, Response, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.recognition.camera import camera_manager
from app.recognition.embedder import face_embedder
from app.recognition.pipeline import process_frame
from app.database.connection import get_db
from app.services.attendance_service import log_attendance, is_on_cooldown
from app.core.config import settings

router = APIRouter(prefix="/api/stream", tags=["stream"])
logger = logging.getLogger(__name__)

_BOUNDARY = b"frame"
_CONTENT_TYPE = f"multipart/x-mixed-replace; boundary={_BOUNDARY.decode()}"
MAX_FRAME_BYTES = 10 * 1024 * 1024
ALLOWED_FRAME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
}


async def _ensure_embedder_loaded() -> bool:
    """Load FaceEmbedder if not ready. Returns True when ready."""
    if face_embedder.is_ready:
        camera_manager.embedder = face_embedder
        return True

    logger.info("Loading FaceEmbedder (buffalo_l)...")
    loaded = await asyncio.to_thread(face_embedder.load)
    if loaded:
        camera_manager.embedder = face_embedder
        logger.info("FaceEmbedder ready.")
    else:
        logger.warning("FaceEmbedder failed to load.")
    return loaded


async def _apply_attendance(
    db: AsyncSession,
    result: dict,
) -> tuple[bool, int]:
    """Log attendance for a known face and return (logged, cooldown_remaining)."""
    attendance_logged = False
    cooldown_remaining = 0

    if result.get("face_detected") and result.get("state") == "known" and result.get("label"):
        student_id = _get_student_id_from_label(result["label"])
        if student_id is not None:
            attendance_logged = await log_attendance(
                db,
                student_id=student_id,
                student_name=result["label"],
                confidence=result.get("confidence", 0.0),
            )
            if not attendance_logged and is_on_cooldown(student_id):
                from app.services.attendance_service import _cooldown
                from datetime import datetime, timezone

                last = _cooldown.get(student_id)
                if last:
                    elapsed = (datetime.now(tz=timezone.utc) - last).total_seconds()
                    cooldown_remaining = max(
                        0, int(settings.attendance_cooldown_seconds - elapsed)
                    )

    return attendance_logged, cooldown_remaining


@router.post("/start")
async def start_camera():
    """Start webcam + load FaceEmbedder (buffalo_l: detection + ArcFace)."""
    embedder_ready = await _ensure_embedder_loaded()
    if not embedder_ready:
        logger.warning("FaceEmbedder failed — stream will run without recognition.")

    if camera_manager.is_running:
        return {"status": "already_running", "embedder_ready": face_embedder.is_ready}

    try:
        success = await asyncio.to_thread(camera_manager.start)
    except Exception as e:
        logger.error(f"Camera start exception: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": f"Camera error: {str(e)}"},
        )

    if not success:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Could not open camera."},
        )

    return {"status": "started", "embedder_ready": face_embedder.is_ready}


@router.post("/prepare")
async def prepare_recognition():
    """
    Load the AI model without starting the server webcam.
    Used when the browser captures frames from the phone camera.
    """
    embedder_ready = await _ensure_embedder_loaded()
    if not embedder_ready:
        raise HTTPException(
            status_code=503,
            detail="ArcFace model failed to load. Check server logs.",
        )

    return {
        "status": "ready",
        "embedder_ready": True,
        "mode": "client",
    }


@router.post("/recognize-frame")
async def recognize_frame(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Run recognition on a single frame uploaded from a client device camera.
    Used by mobile browsers that send phone camera frames to the server.
    """
    if file.content_type not in ALLOWED_FRAME_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Unsupported image type. Use JPG, PNG, WEBP, or BMP.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Empty image.")
    if len(file_bytes) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=422, detail="Image too large (max 10 MB).")

    embedder_ready = await _ensure_embedder_loaded()
    if not embedder_ready:
        raise HTTPException(status_code=503, detail="AI model is not ready.")

    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=422, detail="Could not decode image.")

    _, result = await asyncio.to_thread(process_frame, frame, face_embedder, 0.0)
    attendance_logged, cooldown_remaining = await _apply_attendance(db, result)

    return {
        "running": True,
        "mode": "client",
        "fps": 0,
        "embedder_ready": True,
        "face_detected": result["face_detected"],
        "label": result["label"],
        "confidence": round(result["confidence"], 3),
        "state": result["state"],
        "bbox": result.get("bbox", []),
        "attendance_logged": attendance_logged,
        "cooldown_remaining": cooldown_remaining,
    }


@router.post("/stop")
async def stop_camera():
    """Stop the webcam capture thread."""
    await asyncio.to_thread(camera_manager.stop)
    return {"status": "stopped"}


@router.get("/status")
async def camera_status(db: AsyncSession = Depends(get_db)):
    """
    Return camera state, FPS, and latest recognition result.
    Also triggers attendance logging when a known student is detected.
    Called every 500 ms by the frontend — this is the attendance write point.
    """
    det = camera_manager.get_detection_result()

    result = {
        "face_detected": det.face_detected,
        "label": det.label,
        "confidence": det.confidence,
        "state": det.state,
    }
    attendance_logged, cooldown_remaining = await _apply_attendance(db, result)

    return {
        "running": camera_manager.is_running,
        "mode": "server",
        "fps": camera_manager.fps,
        "embedder_ready": face_embedder.is_ready,
        "face_detected": det.face_detected,
        "label": det.label,
        "confidence": round(det.confidence, 3),
        "state": det.state,
        "attendance_logged": attendance_logged,
        "cooldown_remaining": cooldown_remaining,
    }


@router.get("/feed")
async def video_feed():
    """MJPEG stream — annotated frames."""
    if not camera_manager.is_running:
        return Response(content=b"", media_type="image/jpeg")

    return StreamingResponse(_mjpeg_generator(), media_type=_CONTENT_TYPE)


async def _mjpeg_generator():
    """
    Async generator yielding annotated MJPEG frames.

    Targets ~30 fps by sleeping 20ms between frames.
    The capture thread runs at native camera speed; we just serve
    whatever the latest frame is as fast as the browser can receive it.
    """
    camera_manager.add_consumer()
    last_frame: bytes | None = None
    try:
        while camera_manager.is_running:
            frame = camera_manager.get_latest_frame()
            # Only send when there's a new frame (avoid duplicate frames)
            if frame and frame is not last_frame:
                last_frame = frame
                yield (
                    b"--" + _BOUNDARY + b"\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame + b"\r\n"
                )
            await asyncio.sleep(0.020)   # 50 fps ceiling — browser limits anyway
    except asyncio.CancelledError:
        pass
    finally:
        camera_manager.remove_consumer()


# ------------------------------------------------------------------
# Helper: resolve student name → student_id from the embedding store
# ------------------------------------------------------------------
def _get_student_id_from_label(label: str) -> int | None:
    """
    Look up student_id by name from the in-memory embedding store.
    Uses the same store that the matcher uses — no DB hit needed.
    """
    from app.services.embedding_service import get_embedding_store
    _, ids, names = get_embedding_store()
    for sid, sname in zip(ids, names):
        if sname == label:
            return sid
    return None
