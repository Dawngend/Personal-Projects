"""record_attempt must survive a double-submit.

submit_answer is a sync endpoint, so FastAPI runs it in the anyio threadpool
and two in-flight requests execute in parallel. record_attempt read the
existing attempt on a deferred connection, which holds no write lock, then
wrote. Two callers could therefore both observe "no attempt yet" and:

  * both INSERT, so one raises IntegrityError on PRIMARY KEY (session_id,
    card_id) and returns an uncaught 500, or
  * both count a first miss, double-incrementing cards.times_missed, which is
    cross-session and never corrected.
"""

import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from andyhub_api.persistence import ApiRepository


class RecordAttemptConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "reviewer.db"
        self.repo = ApiRepository(str(self.db))

        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute(
                "INSERT INTO decks (name, modules_included, subject) VALUES (?, ?, ?)",
                ("Deck", "module.pdf", "Subject"),
            )
            connection.execute(
                "INSERT INTO cards (deck_id, type, question, correct_answer, times_missed)"
                " VALUES (1, 'multiple_choice', 'q', 'a', 0)"
            )
            connection.commit()
        self.card_id = 1

    def _times_missed(self) -> int:
        with closing(sqlite3.connect(self.db)) as connection:
            return connection.execute(
                "SELECT times_missed FROM cards WHERE id = ?", (self.card_id,)
            ).fetchone()[0]

    def test_parallel_first_wrong_answers_do_not_raise_or_double_count(self) -> None:
        session = "session-double-submit"

        def submit():
            return self.repo.record_attempt(session, self.card_id, correct=False, revealed=False)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = [f.result() for f in [pool.submit(submit) for _ in range(8)]]

        self.assertEqual(
            self._times_missed(), 1,
            "a card missed once must be counted once no matter how many parallel submits arrive",
        )
        self.assertEqual(
            sum(1 for r in results if r), 1,
            "exactly one caller may report the first miss",
        )

    def test_parallel_submits_leave_exactly_one_attempt_row(self) -> None:
        session = "session-one-row"

        with ThreadPoolExecutor(max_workers=6) as pool:
            for future in [
                pool.submit(
                    self.repo.record_attempt, session, self.card_id,
                    correct=False, revealed=False,
                )
                for _ in range(6)
            ]:
                future.result()

        with closing(sqlite3.connect(self.db)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE session_id = ?", (session,)
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_resolved_attempt_still_cannot_be_downgraded(self) -> None:
        session = "session-frozen"
        self.repo.record_attempt(session, self.card_id, correct=True, revealed=False)
        before = self._times_missed()

        self.assertFalse(
            self.repo.record_attempt(session, self.card_id, correct=False, revealed=False)
        )
        self.assertEqual(self._times_missed(), before)


if __name__ == "__main__":
    unittest.main()
