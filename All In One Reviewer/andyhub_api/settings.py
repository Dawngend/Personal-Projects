"""Absolute, injectable data paths for the API process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    uploads_directory: Path
    extraction_cache_directory: Path
    max_upload_bytes: int = 20 * 1024 * 1024
    initialize_course_memory: bool = True

    @classmethod
    def defaults(cls) -> "Settings":
        root = Path(__file__).resolve().parents[1]
        return cls(
            database_path=root / "Database" / "reviewer.db",
            uploads_directory=root / "uploads",
            extraction_cache_directory=root / "extraction_cache",
        )
