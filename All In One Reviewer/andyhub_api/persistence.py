"""SQLite persistence for API-only modules, jobs, and resumable quiz sessions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from repositories import open_connection


@dataclass(frozen=True)
class StoredModule:
    id: str
    filename: str
    stored_filename: str
    media_type: str
    size_bytes: int
    content_hash: str
    extraction_status: str


class ApiRepository:
    """Keeps Phase 2 tables beside the unchanged legacy deck/card schema."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    def _connection(self):
        return open_connection(self.database_path)

    def ping(self) -> bool:
        try:
            with self._connection() as connection:
                return connection.execute("SELECT 1").fetchone() == (1,)
        except sqlite3.Error:
            return False

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS modules (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, stored_filename TEXT NOT NULL,
                    media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, content_hash TEXT NOT NULL UNIQUE,
                    extraction_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id TEXT PRIMARY KEY, deck_name TEXT NOT NULL, subject TEXT NOT NULL, module_ids TEXT NOT NULL,
                    question_style TEXT NOT NULL, total_questions INTEGER NOT NULL, status TEXT NOT NULL,
                    stage TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, message TEXT,
                    cards_received INTEGER NOT NULL DEFAULT 0, cards_valid INTEGER NOT NULL DEFAULT 0,
                    deck_id INTEGER, error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS quiz_sessions (
                    id TEXT PRIMARY KEY, deck_id INTEGER NOT NULL, mode TEXT NOT NULL, card_order TEXT NOT NULL,
                    current_index INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    session_id TEXT NOT NULL, card_id INTEGER NOT NULL, status TEXT NOT NULL,
                    wrong_count INTEGER NOT NULL DEFAULT 0, revealed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (session_id, card_id)
                );
                """
            )
            # Additive migration: CREATE TABLE IF NOT EXISTS never alters an
            # existing table, so a database created before the poison-job
            # ceiling has no attempts column and every claim would raise.
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(generation_jobs)")
            }
            if "attempts" not in columns:
                connection.execute(
                    "ALTER TABLE generation_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
                )

    def list_modules(self) -> list[StoredModule]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, filename, stored_filename, media_type, size_bytes, content_hash, extraction_status "
                "FROM modules ORDER BY created_at DESC"
            ).fetchall()
        return [StoredModule(*row) for row in rows]

    def get_module(self, module_id: str) -> StoredModule | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, filename, stored_filename, media_type, size_bytes, content_hash, extraction_status "
                "FROM modules WHERE id = ?", (module_id,)
            ).fetchone()
        return StoredModule(*row) if row else None

    def get_module_by_hash(self, content_hash: str) -> StoredModule | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, filename, stored_filename, media_type, size_bytes, content_hash, extraction_status "
                "FROM modules WHERE content_hash = ?", (content_hash,)
            ).fetchone()
        return StoredModule(*row) if row else None

    def create_module(self, filename: str, stored_filename: str, media_type: str, size_bytes: int, content_hash: str) -> StoredModule:
        module = StoredModule(f"mod_{uuid4().hex}", filename, stored_filename, media_type, size_bytes, content_hash, "pending")
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO modules (id, filename, stored_filename, media_type, size_bytes, content_hash, extraction_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (module.id, module.filename, module.stored_filename, module.media_type, module.size_bytes, module.content_hash, module.extraction_status),
            )
        return module

    def create_job(self, payload: Any) -> str:
        job_id = f"gen_{uuid4().hex}"
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO generation_jobs (id, deck_name, subject, module_ids, question_style, total_questions, status, stage) VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued')",
                (job_id, payload.deck_name, payload.subject, json.dumps(payload.module_ids), payload.question_style, payload.total_questions),
            )
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    #: How many times one job may be claimed before it is treated as poison.
    #: Reclaiming 'running' jobs is what makes a worker restart resume work, but
    #: without a ceiling a job that reliably kills the worker (an OCR-heavy PDF
    #: exceeding mem_limit 480m, say) is re-claimed forever. It is also always
    #: the OLDEST row, so it blocks every later job while the worker restarts in
    #: a loop and its health endpoint keeps answering: the queue is dead and
    #: every check stays green.
    MAX_JOB_ATTEMPTS = 3

    def claim_next_job(self) -> dict[str, Any] | None:
        """Atomically claim work; running jobs are reclaimed after a process restart."""
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            # Serialize the claim: two workers must not take the same row.
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            while True:
                row = connection.execute(
                    "SELECT id, attempts FROM generation_jobs"
                    " WHERE status IN ('queued', 'running') ORDER BY created_at LIMIT 1"
                ).fetchone()
                if not row:
                    return None

                if row["attempts"] >= self.MAX_JOB_ATTEMPTS:
                    connection.execute(
                        "UPDATE generation_jobs SET status = 'failed', stage = 'failed',"
                        " message = ?, error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (
                            "Generation failed repeatedly and was stopped",
                            f"Job was claimed {row['attempts']} times without completing. "
                            "It is treated as poison so the queue can continue.",
                            row["id"],
                        ),
                    )
                    continue

                connection.execute(
                    "UPDATE generation_jobs SET status = 'running', stage = 'extracting',"
                    " message = 'Preparing uploaded modules', attempts = attempts + 1,"
                    " updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (row["id"],),
                )
                claimed = connection.execute(
                    "SELECT * FROM generation_jobs WHERE id = ?", (row["id"],)
                ).fetchone()
                return dict(claimed)

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = "CURRENT_TIMESTAMP"
        assignments = ", ".join(f"{key} = {value}" if key == "updated_at" else f"{key} = ?" for key, value in fields.items())
        values = [value for key, value in fields.items() if key != "updated_at"] + [job_id]
        with self._connection() as connection:
            connection.execute(f"UPDATE generation_jobs SET {assignments} WHERE id = ?", values)

    def create_session(self, deck_id: int, mode: str, card_ids: list[int]) -> str:
        session_id = f"quiz_{uuid4().hex}"
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO quiz_sessions (id, deck_id, mode, card_order) VALUES (?, ?, ?, ?)",
                (session_id, deck_id, mode, json.dumps(card_ids)),
            )
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def advance(self, session_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            session = connection.execute("SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                return None
            order = json.loads(session["card_order"])
            next_index = min(session["current_index"] + 1, len(order))
            connection.execute(
                "UPDATE quiz_sessions SET current_index = ?, completed = ? WHERE id = ?",
                (next_index, int(next_index >= len(order)), session_id),
            )
            updated = connection.execute("SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(updated)

    def record_attempt(self, session_id: str, card_id: int, correct: bool, *, revealed: bool = False) -> bool:
        """Record one cumulative miss per card/session and return whether it was newly recorded.

        A resolved attempt (answered correctly or revealed) is frozen: a later submission for the
        same card cannot downgrade its status, inflate wrong_count, or bump cards.times_missed.
        Without this a double-click or retry race un-resolves a solved card, which then blocks
        advance with card_not_resolved and permanently skews the cross-session times_missed count.
        """
        with self._connection() as connection:
            # Take the write lock BEFORE the read. submit_answer is a sync
            # endpoint, so FastAPI runs it in the threadpool and two in-flight
            # requests execute in parallel. On a deferred connection the SELECT
            # holds no lock, so a double-submit had both callers see no row,
            # both INSERT, and one raise IntegrityError on the composite
            # primary key as an uncaught 500 -- or, on the update path, both
            # compute first_miss and double-count cards.times_missed, which is
            # cross-session and permanent. busy_timeout=5000 makes the loser
            # wait rather than fail.
            if not connection.in_transaction:
                connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, wrong_count, revealed FROM quiz_attempts WHERE session_id = ? AND card_id = ?",
                (session_id, card_id),
            ).fetchone()
            if row is not None and (row[0] == "correct" or row[2]):
                return False
            first_miss = not correct and (row is None or row[1] == 0)
            if row is None:
                connection.execute(
                    "INSERT INTO quiz_attempts (session_id, card_id, status, wrong_count, revealed) VALUES (?, ?, ?, ?, ?)",
                    (session_id, card_id, "correct" if correct else "wrong", int(not correct), int(revealed)),
                )
            else:
                connection.execute(
                    "UPDATE quiz_attempts SET status = ?, wrong_count = wrong_count + ?, revealed = MAX(revealed, ?) WHERE session_id = ? AND card_id = ?",
                    ("correct" if correct else "wrong", int(not correct), int(revealed), session_id, card_id),
                )
            if first_miss:
                connection.execute("UPDATE cards SET times_missed = times_missed + 1 WHERE id = ?", (card_id,))
        return first_miss

    def attempt_for_current_card(self, session_id: str, card_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM quiz_attempts WHERE session_id = ? AND card_id = ?", (session_id, card_id)
            ).fetchone()
        return dict(row) if row else None

    def summary(self, session_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            session = connection.execute("SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)).fetchone()
            attempts = connection.execute("SELECT * FROM quiz_attempts WHERE session_id = ?", (session_id,)).fetchall()
        return {"session": dict(session), "attempts": [dict(row) for row in attempts]}
