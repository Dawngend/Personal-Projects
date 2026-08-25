"""Create a verified, recoverable staging copy of AndyHub's local state."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4


STATE_DIRECTORIES = ("uploads", "extraction_cache", "course_brain_db")


def copy_state(source: Path, destination: Path, *, replace: bool = False) -> dict[str, object]:
    source = source.resolve()
    destination = destination.resolve()
    database = source / "Database" / "reviewer.db"
    if not database.is_file():
        raise FileNotFoundError(f"production SQLite file not found: {database}")
    if source == destination:
        raise ValueError("source and staging destination must be different")
    if destination.exists() and any(destination.iterdir()) and not replace:
        raise FileExistsError(
            f"staging destination is not empty: {destination}; rerun with --replace"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    incoming = destination.parent / f".{destination.name}.incoming-{uuid4().hex}"
    previous: Path | None = None
    try:
        (incoming / "Database").mkdir(parents=True)
        _backup_sqlite(database, incoming / "Database" / "reviewer.db")
        for directory_name in STATE_DIRECTORIES:
            source_directory = source / directory_name
            target_directory = incoming / directory_name
            if source_directory.is_dir():
                shutil.copytree(source_directory, target_directory)
            else:
                target_directory.mkdir()

        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "files": _file_manifest(incoming),
        }
        (incoming / "STATE_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        if destination.exists():
            previous = destination.parent / (
                f"{destination.name}.previous-"
                + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            )
            destination.replace(previous)
        incoming.replace(destination)
        return {
            "destination": str(destination),
            "previous": str(previous) if previous else None,
            "file_count": len(manifest["files"]),
        }
    except Exception:
        shutil.rmtree(incoming, ignore_errors=True)
        raise


def _backup_sqlite(source: Path, destination: Path) -> None:
    source_uri = source.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
        with closing(sqlite3.connect(destination)) as destination_connection:
            source_connection.backup(destination_connection)


def _file_manifest(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
        files[path.relative_to(root).as_posix()] = digest.hexdigest()
    return files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy production-shaped AndyHub state into the isolated staging data root."
    )
    parser.add_argument("--source", required=True, type=Path, help="current production app root")
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path(".staging/data"),
        help="isolated staging data root (default: .staging/data)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="archive the current staging copy before installing the new snapshot",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = copy_state(args.source, args.destination, replace=args.replace)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
