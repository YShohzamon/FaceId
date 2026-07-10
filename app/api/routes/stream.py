"""
Camera stream routes.

/api/stream/start  — start camera + load embedder (det + ArcFace)
/api/stream/stop   — stop camera
/api/stream/feed   — MJPEG video stream (annotated frames)
/api/stream/status — JSON: camera state, FPS, recognition result + attendance logging
"""

import asyncio
import logging
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.recognition.camera import camera_manager
from app.recognition.embedder import face_embedder
from app.database.connection import get_db
from app.services.attendance_service import log_attendance, is_on_cooldown
from app.core.config import settings

router = APIRouter(prefix="/api/stream", tags=["stream"])
logger = logging.getLogger(__name__)

_BOUNDARY = b"frame"
_CONTENT_TYPE = f"multipart/x-mixed-replace; boundary={_BOUNDARY.decode()}"


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
                # Private import: compute remaining cooldown without a DB query.
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
    Polled every 500 ms by the frontend. Cooldown is enforced in memory
    before writing to the database.
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

    Poll interval ~20 ms (~50 fps cap for the MJPEG consumer loop).
    The capture thread runs at native camera speed; this loop serves
    the latest annotated frame to the browser.
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
            await asyncio.sleep(0.020)
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
