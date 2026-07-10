"""
Application configuration.
All settings are loaded from environment variables (via .env file).
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # --- Application ---
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    debug: bool = Field(default=True, alias="DEBUG")
    secret_key: str = Field(default="change-this-secret", alias="SECRET_KEY")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/face_attendance",
        alias="DATABASE_URL"
    )

    # --- Face Recognition ---
    recognition_threshold: float = Field(default=0.45, alias="RECOGNITION_THRESHOLD")
    use_gpu: bool = Field(default=False, alias="USE_GPU")
    gpu_id: int = Field(default=0, alias="GPU_ID")

    # --- Attendance ---
    attendance_cooldown_seconds: int = Field(default=30, alias="ATTENDANCE_COOLDOWN_SECONDS")

    # --- File Paths ---
    face_images_dir: str = Field(default="face_data/images", alias="FACE_IMAGES_DIR")
    embeddings_dir: str = Field(default="face_data/embeddings", alias="EMBEDDINGS_DIR")

    # --- Logging ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="logs/app.log", alias="LOG_FILE")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
    }

    def get_ctx_id(self) -> int:
        """Return ONNX Runtime context ID: gpu_id when USE_GPU=True, else -1 (CPU)."""
        if self.use_gpu:
            return self.gpu_id
        return -1

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        dirs = [
            Path(self.face_images_dir),
            Path(self.embeddings_dir),
            Path(self.log_file).parent,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
