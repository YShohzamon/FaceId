"""
FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import setup_logging
from app.database.connection import create_tables, close_db, AsyncSessionLocal
from app.api.routes import pages, students, attendance, stream, enrollment
from app.recognition.camera import camera_manager
from app.services.embedding_service import load_all_embeddings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup and shutdown tasks."""
    setup_logging()
    settings.ensure_directories()
    logger = logging.getLogger(__name__)
    logger.info("Starting FaceID Attendance System...")
    logger.info(f"Debug={settings.debug} | GPU={'enabled' if settings.use_gpu else 'disabled (CPU)'}")

    await create_tables()

    # Load existing embeddings into memory so recognition is ready immediately
    async with AsyncSessionLocal() as db:
        count = await load_all_embeddings(db)
        logger.info(f"Loaded {count} face embeddings into memory.")

    yield

    # Stop camera if it was left running
    if camera_manager.is_running:
        camera_manager.stop()
    await close_db()
    logger.info("Application shut down.")


app = FastAPI(
    title="FaceID Attendance System",
    description="Real-time face recognition attendance system",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(pages.router)
app.include_router(students.router)
app.include_router(attendance.router)
app.include_router(stream.router)
app.include_router(enrollment.router)
