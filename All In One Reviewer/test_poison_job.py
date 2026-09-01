"""A job that keeps killing the worker must not block the queue forever.

claim_next_job reclaims jobs in status 'running' so that a worker restart
resumes interrupted work. Without a ceiling, a job that reliably crashes the
worker -- an OCR-heavy PDF exceeding mem_limit 480m, or a VM reboot mid-job --
is re-claimed on every restart. It is also always the OLDEST row, so it blocks
every later job while the worker restart-loops and its health endpoint keeps
answering: the queue is dead and every health check stays green.
"""

import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from andyhub_api.persistence import ApiRepository


def _payload(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        deck_name=name, subject="Subject", module_ids=["mod_1"],
        question_style="mixed", total_questions=10,
    )


class PoisonJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "reviewer.db"
        self.repo = ApiRepository(self.db)

    def _status(self, job_id: str) -> str:
        with closing(sqlite3.connect(self.db)) as connection:
            return connection.execute(
                "SELECT status FROM generation_jobs WHERE id = ?", (job_id,)
            ).fetchone()[0]

    def test_a_repeatedly_crashing_job_is_failed_and_stops_blocking_the_queue(self) -> None:
        poison = self.repo.create_job(_payload("Poison"))
        follower = self.repo.create_job(_payload("Follower"))

        # Simulate the worker dying mid-job: the row stays 'running' and is
        # reclaimed on the next start.
        for _ in range(self.repo.MAX_JOB_ATTEMPTS):
            claimed = self.repo.claim_next_job()
            self.assertEqual(claimed["id"], poison)

        # The next claim must give up on the poison job and move on.
        claimed = self.repo.claim_next_job()
        self.assertIsNotNone(claimed, "the queue must not stall on a poison job")
        self.assertEqual(
            claimed["id"], follower,
            "after the attempt ceiling the queue must progress to the next job",
        )
        self.assertEqual(self._status(poison), "failed")

    def test_the_failed_job_records_why(self) -> None:
        poison = self.repo.create_job(_payload("Poison"))
        for _ in range(self.repo.MAX_JOB_ATTEMPTS):
            self.repo.claim_next_job()
        self.repo.claim_next_job()

        with closing(sqlite3.connect(self.db)) as connection:
            error = connection.execute(
                "SELECT error FROM generation_jobs WHERE id = ?", (poison,)
            ).fetchone()[0]
        self.assertIn("claimed", error)

    def test_a_normal_job_is_unaffected(self) -> None:
        job = self.repo.create_job(_payload("Normal"))
        claimed = self.repo.claim_next_job()
        self.assertEqual(claimed["id"], job)
        self.assertEqual(claimed["attempts"], 1)

        self.repo.update_job(job, status="succeeded", stage="done")
        self.assertIsNone(self.repo.claim_next_job())

    def test_migration_adds_attempts_to_a_preexisting_database(self) -> None:
        legacy = Path(self._tmp.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as connection:
            connection.execute(
                """
                CREATE TABLE generation_jobs (
                    id TEXT PRIMARY KEY, deck_name TEXT NOT NULL, subject TEXT NOT NULL,
                    module_ids TEXT NOT NULL, question_style TEXT NOT NULL,
                    total_questions INTEGER NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0, message TEXT,
                    cards_received INTEGER NOT NULL DEFAULT 0, cards_valid INTEGER NOT NULL DEFAULT 0,
                    deck_id INTEGER, error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

        repo = ApiRepository(legacy)
        with closing(sqlite3.connect(legacy)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(generation_jobs)")}
        self.assertIn("attempts", columns)

        job = repo.create_job(_payload("After migration"))
        self.assertEqual(repo.claim_next_job()["id"], job)


if __name__ == "__main__":
    unittest.main()
