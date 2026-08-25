from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

import pytest

from deploy.staging.copy_state import copy_state


PROJECT_ROOT = Path(__file__).resolve().parent


def test_staging_state_copy_is_complete_verified_and_recoverable() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        source = root / "production"
        destination = root / "staging" / "data"
        (source / "Database").mkdir(parents=True)
        with closing(sqlite3.connect(source / "Database" / "reviewer.db")) as connection:
            connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
            connection.execute("INSERT INTO marker VALUES ('first')")
            connection.commit()
        for name in ("uploads", "extraction_cache", "course_brain_db"):
            (source / name).mkdir()
            (source / name / f"{name}.txt").write_text(name, encoding="utf-8")

        result = copy_state(source, destination)
        manifest = json.loads((destination / "STATE_MANIFEST.json").read_text(encoding="utf-8"))
        with closing(sqlite3.connect(destination / "Database" / "reviewer.db")) as connection:
            copied_value = connection.execute("SELECT value FROM marker").fetchone()[0]

        assert copied_value == "first"
        assert result["file_count"] == 4
        assert set(manifest["files"]) == {
            "Database/reviewer.db",
            "uploads/uploads.txt",
            "extraction_cache/extraction_cache.txt",
            "course_brain_db/course_brain_db.txt",
        }
        with pytest.raises(FileExistsError):
            copy_state(source, destination)

        replacement = copy_state(source, destination, replace=True)
        assert replacement["previous"] is not None
        assert Path(str(replacement["previous"])).is_dir()


def test_compose_proxy_and_tunnel_are_staging_only() -> None:
    compose = (PROJECT_ROOT / "compose.staging.yaml").read_text(encoding="utf-8")
    proxy = (PROJECT_ROOT / "deploy/staging/nginx.conf").read_text(encoding="utf-8")
    tunnel = (
        PROJECT_ROOT / "deploy/staging/cloudflared/config.yml.example"
    ).read_text(encoding="utf-8")

    for service in ("api:", "worker:", "web:", "proxy:", "tunnel:", "smoke:"):
        assert service in compose
    assert '"127.0.0.1:${STAGING_PORT:-8081}:8080"' in compose
    assert "location ^~ /api/v1/" in proxy
    assert "location /" in proxy
    assert "hostname: staging.andyhub.org" in tunnel
    assert "hostname: andyhub.org" not in tunnel
