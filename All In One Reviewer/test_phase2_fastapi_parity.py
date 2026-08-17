"""Offline OpenAPI and end-to-end contract tests for the Phase 2 parity API."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from andyhub_api.main import create_app
from andyhub_api.settings import Settings
from generator import GenerationDependencies
from repositories import DeckRepository


RAW_CARDS = [
    {"type": "multiple_choice", "question": "MCQ", "options": ["A", "B", "C", "D"], "correct_answer": "B"},
    {"type": "enumeration", "question": "Enum", "correct_answer": ["closure", "identity"]},
    {"type": "problem", "question": "Problem", "correct_answer": "24", "solution_steps": ["Multiply the factors."]},
]


class Phase2ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            database_path=root / "reviewer.db",
            uploads_directory=root / "uploads",
            extraction_cache_directory=root / "cache",
            initialize_course_memory=False,
        )

        def dependencies() -> GenerationDependencies:
            return GenerationDependencies(
                extract_file=lambda _: "module text " * 20,
                create_client=lambda: object(),
                get_context=lambda *_: "",
                query_cards=lambda *_: RAW_CARDS,
                add_memory=lambda *_: None,
                persist_deck=lambda name, modules, subject, cards: DeckRepository(self.settings.database_path).create_with_cards(name, modules, subject, cards).id,
                sleep=lambda _: None,
            )

        self.app = create_app(self.settings, dependencies_factory=dependencies)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def test_upload_generation_and_quiz_complete_without_exposing_answer_keys(self):
        upload = self.client.post(
            "/api/v1/modules",
            files=[("files", ("Linear Algebra.pdf", b"module source", "application/pdf"))],
        )
        self.assertEqual(upload.status_code, 201, upload.text)
        module = upload.json()["items"][0]
        self.assertTrue(module["id"].startswith("mod_"))
        self.assertEqual(module["contentHash"], "sha256:" + __import__("hashlib").sha256(b"module source").hexdigest())
        duplicate = self.client.post("/api/v1/modules", files=[("files", ("copy.pdf", b"module source", "application/pdf"))])
        self.assertTrue(duplicate.json()["items"][0]["duplicate"])

        queued = self.client.post("/api/v1/generation-jobs", json={
            "deckName": "Algebra", "subject": "Math", "moduleIds": [module["id"]], "questionStyle": "mixed", "totalQuestions": 3,
        })
        self.assertEqual(queued.status_code, 202, queued.text)
        job_id = queued.json()["id"]
        for _ in range(50):
            job = self.client.get(f"/api/v1/generation-jobs/{job_id}").json()
            if job["status"] in {"complete", "failed"}:
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(job["stage"], "complete")
        self.assertEqual(job["cardsValid"], 3)
        events = self.client.get(f"/api/v1/generation-jobs/{job_id}/events")
        self.assertEqual(events.status_code, 200)
        self.assertIn("event: progress", events.text)

        detail = self.client.get(f"/api/v1/decks/{job['deckId']}?include=cards")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("correct_answer", detail.text)
        self.assertNotIn("solution_steps", detail.text)
        self.assertEqual({card["type"] for card in detail.json()["cards"]}, {"multiple_choice", "enumeration", "problem"})

        created = self.client.post("/api/v1/quiz-sessions", json={"deckId": job["deckId"], "mode": "all"})
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["id"]
        answers = {"MCQ": ("multiple_choice", "B"), "Enum": ("enumeration", "closure, identity"), "Problem": ("problem", "24.0")}
        for _ in range(3):
            session = self.client.get(f"/api/v1/quiz-sessions/{session_id}").json()
            card = session["card"]
            answer_type, value = answers[card["question"]]
            grade = self.client.post(f"/api/v1/quiz-sessions/{session_id}/answers", json={"cardId": card["id"], "answer": {"type": answer_type, "value": value}})
            self.assertEqual(grade.status_code, 200, grade.text)
            self.assertTrue(grade.json()["correct"])
            advanced = self.client.post(f"/api/v1/quiz-sessions/{session_id}/advance")
            self.assertEqual(advanced.status_code, 200, advanced.text)
        summary = self.client.get(f"/api/v1/quiz-sessions/{session_id}/summary").json()
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["correct"], 3)

    def test_openapi_has_discriminated_card_contract_and_validation_errors_are_stable(self):
        document = self.client.get("/openapi.json").json()
        serialized = __import__("json").dumps(document)
        self.assertIn('"discriminator"', serialized)
        self.assertIn('"multiple_choice"', serialized)
        self.assertNotIn("correct_answer", serialized)
        invalid = self.client.post("/api/v1/generation-jobs", json={})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["error"]["code"], "validation_error")

    def test_problem_reveal_records_a_single_miss_per_session(self):
        deck = DeckRepository(self.settings.database_path).create_with_cards(
            "Problems", "m.pdf", "Math",
            [__import__("repositories").NewCard("problem", "Solve", "24", {"final_answer": "24", "solution_steps": ["Multiply."]})],
        )
        session = self.client.post("/api/v1/quiz-sessions", json={"deckId": deck.id, "mode": "all"}).json()
        card_id = session["card"]["id"]
        first = self.client.post(f"/api/v1/quiz-sessions/{session['id']}/cards/{card_id}/reveal-solution")
        second = self.client.post(f"/api/v1/quiz-sessions/{session['id']}/cards/{card_id}/reveal-solution")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(DeckRepository(self.settings.database_path).get(deck.id).name, "Problems")
        from repositories import CardRepository
        self.assertEqual(CardRepository(self.settings.database_path).get(card_id).times_missed, 1)

    def test_resubmitting_a_solved_card_cannot_un_resolve_it(self):
        deck = DeckRepository(self.settings.database_path).create_with_cards(
            "Doubles", "d.pdf", "Math",
            [__import__("repositories").NewCard("multiple_choice", "2+2?", "4", ["3", "4"])],
        )
        session = self.client.post("/api/v1/quiz-sessions", json={"deckId": deck.id, "mode": "all"}).json()
        session_id, card_id = session["id"], session["card"]["id"]
        answer_url = f"/api/v1/quiz-sessions/{session_id}/answers"
        first = self.client.post(answer_url, json={"cardId": card_id, "answer": {"type": "multiple_choice", "value": "4"}})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["correct"])
        self.assertTrue(first.json()["complete"])
        # A stray double-click / retry race lands a wrong answer on an already-solved card.
        second = self.client.post(answer_url, json={"cardId": card_id, "answer": {"type": "multiple_choice", "value": "3"}})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertFalse(second.json()["correct"])
        self.assertTrue(second.json()["complete"], "a solved card must stay resolved")
        # advance must not be blocked by card_not_resolved, and the miss must not be counted.
        advanced = self.client.post(f"/api/v1/quiz-sessions/{session_id}/advance")
        self.assertEqual(advanced.status_code, 200, advanced.text)
        from repositories import CardRepository
        self.assertEqual(CardRepository(self.settings.database_path).get(card_id).times_missed, 0)
        summary = self.client.get(f"/api/v1/quiz-sessions/{session_id}/summary").json()
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["missedCardIds"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
