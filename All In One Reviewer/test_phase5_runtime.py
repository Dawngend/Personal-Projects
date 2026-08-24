from __future__ import annotations

from pathlib import Path
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from andyhub_api.main import create_app
from andyhub_api.settings import Settings
from repositories import open_connection


def test_deployment_settings_resolve_all_state_under_configured_data_root() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        with patch.dict(
            "os.environ",
            {
                "ANDYHUB_DATA_ROOT": temporary_directory,
                "ANDYHUB_START_GENERATION_WORKER": "false",
                "ANDYHUB_ENVIRONMENT": "staging",
            },
            clear=False,
        ):
            settings = Settings.defaults()

    root = Path(temporary_directory)
    assert settings.database_path == root / "Database" / "reviewer.db"
    assert settings.uploads_directory == root / "uploads"
    assert settings.extraction_cache_directory == root / "extraction_cache"
    assert settings.resolved_course_memory_directory == root / "course_brain_db"
    assert not settings.start_generation_worker
    assert settings.environment == "staging"


def test_sqlite_connections_enable_wal_busy_timeout_and_foreign_keys() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "reviewer.db"
        with open_connection(database_path) as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert journal_mode == "wal"
    assert busy_timeout == 5000
    assert foreign_keys == 1


def test_api_health_reports_dependencies_worker_mode_and_request_id() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        settings = Settings(
            database_path=root / "Database" / "reviewer.db",
            uploads_directory=root / "uploads",
            extraction_cache_directory=root / "extraction_cache",
            course_memory_directory=root / "course_brain_db",
            initialize_course_memory=False,
            start_generation_worker=False,
            environment="staging",
        )
        with patch.dict("os.environ", {"GROQ_API_KEY": "smoke-only"}, clear=False):
            with TestClient(create_app(settings)) as client:
                response = client.get("/api/v1/health", headers={"x-request-id": "test-request"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request"
    assert response.json() == {
        "status": "ok",
        "service": "api",
        "database": "ok",
        "course_memory": "ok",
        "generator": "configured",
        "worker_mode": "external",
    }
