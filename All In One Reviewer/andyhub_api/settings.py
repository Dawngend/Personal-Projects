"""Absolute, injectable data paths for the API process."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    uploads_directory: Path
    extraction_cache_directory: Path
    course_memory_directory: Path | None = None
    max_upload_bytes: int = 20 * 1024 * 1024
    initialize_course_memory: bool = True
    start_generation_worker: bool = True
    environment: str = "development"

    @property
    def resolved_course_memory_directory(self) -> Path:
        return self.course_memory_directory or Path(__file__).resolve().parents[1] / "course_brain_db"

    @classmethod
    def defaults(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[1]
        data_root = Path(os.environ.get("ANDYHUB_DATA_ROOT", project_root))
        return cls(
            database_path=Path(
                os.environ.get("ANDYHUB_DATABASE_PATH", data_root / "Database" / "reviewer.db")
            ),
            uploads_directory=Path(
                os.environ.get("ANDYHUB_UPLOADS_DIRECTORY", data_root / "uploads")
            ),
            extraction_cache_directory=Path(
                os.environ.get(
                    "ANDYHUB_EXTRACTION_CACHE_DIR", data_root / "extraction_cache"
                )
            ),
            course_memory_directory=Path(
                os.environ.get(
                    "ANDYHUB_COURSE_MEMORY_DIRECTORY", data_root / "course_brain_db"
                )
            ),
            max_upload_bytes=int(
                os.environ.get("ANDYHUB_MAX_UPLOAD_BYTES", 20 * 1024 * 1024)
            ),
            initialize_course_memory=_environment_flag(
                "ANDYHUB_INITIALIZE_COURSE_MEMORY", True
            ),
            start_generation_worker=_environment_flag(
                "ANDYHUB_START_GENERATION_WORKER", True
            ),
            environment=os.environ.get("ANDYHUB_ENVIRONMENT", "development"),
        )


def _environment_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}
