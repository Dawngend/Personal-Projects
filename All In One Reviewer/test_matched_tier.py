"""Tests that the matched comparison tier reaches the API surface.

grade_problem_answer already reports which tier proved equivalence. Until now
every caller collapsed that into a bare boolean, so the UI could not tell a
verbatim match from an accepted equivalent form ("3/4" for "0.75"). These tests
pin the tier all the way out to the JSON contract.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from andyhub_api.main import create_app
from andyhub_api.settings import Settings
from generator import GenerationDependencies
from grading import equivalent_form_note, grade_problem_answer
from repositories import DeckRepository, NewCard


class TestTierIsReportedByTheGradingLayer(unittest.TestCase):
    """The pure layer: no I/O, just the ladder's own verdict."""

    def test_verbatim_match_reports_exact(self):
        self.assertEqual(grade_problem_answer("0.75", "0.75").tier, "exact")

    def test_fraction_against_decimal_reports_numeric(self):
        self.assertEqual(grade_problem_answer("3/4", "0.75").tier, "numeric")

    def test_matrix_spacing_difference_reports_structured(self):
        result = grade_problem_answer("[[1, 2], [3, 4]]", "[[1,2],[3,4]]")
        self.assertEqual(result.tier, "structured")

    def test_wrong_answer_reports_fail(self):
        self.assertEqual(grade_problem_answer("5", "0.75").tier, "fail")

    def test_result_stays_truthy_compatible(self):
        # Existing callers treat the result as a plain bool; that must not break.
        self.assertTrue(grade_problem_answer("3/4", "0.75"))
        self.assertFalse(grade_problem_answer("5", "0.75"))


class TestEquivalentFormNote(unittest.TestCase):
    """The shared explanation both surfaces render, so they cannot drift."""

    def test_exact_match_stays_silent(self):
        self.assertIsNone(equivalent_form_note("exact"))

    def test_absent_tier_stays_silent(self):
        self.assertIsNone(equivalent_form_note(None))

    def test_failed_match_stays_silent(self):
        self.assertIsNone(equivalent_form_note("fail"))

    def test_each_equivalent_tier_is_explained(self):
        for tier in ("numeric", "structured", "symbolic"):
            with self.subTest(tier=tier):
                note = equivalent_form_note(tier)
                self.assertIsNotNone(note)
                self.assertNotIn("—", note, "no em dashes in user-facing copy")

    def test_the_note_stays_free_of_jargon(self):
        # The student reads this, so tier names must not leak into the copy.
        for tier in ("numeric", "structured", "symbolic"):
            with self.subTest(tier=tier):
                self.assertNotIn(tier, equivalent_form_note(tier).lower())


class TestTierReachesTheApi(unittest.TestCase):
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
                query_cards=lambda *_: [],
                add_memory=lambda *_: None,
                persist_deck=lambda *_: 0,
                sleep=lambda _: None,
            )

        self.app = create_app(self.settings, dependencies_factory=dependencies)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def _grade(self, card: NewCard, answer_type: str, value: str) -> dict:
        deck = DeckRepository(self.settings.database_path).create_with_cards(
            "Deck", "m.pdf", "Math", [card]
        )
        session = self.client.post(
            "/api/v1/quiz-sessions", json={"deckId": deck.id, "mode": "all"}
        ).json()
        response = self.client.post(
            f"/api/v1/quiz-sessions/{session['id']}/answers",
            json={
                "cardId": session["card"]["id"],
                "answer": {"type": answer_type, "value": value},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _problem(self, expected: str) -> NewCard:
        return NewCard(
            "problem",
            "Solve",
            expected,
            {"final_answer": expected, "solution_steps": ["Work it through."]},
        )

    def test_verbatim_problem_answer_reports_exact(self):
        body = self._grade(self._problem("0.75"), "problem", "0.75")
        self.assertTrue(body["correct"])
        self.assertEqual(body["matchedTier"], "exact")

    def test_equivalent_fraction_reports_numeric(self):
        body = self._grade(self._problem("0.75"), "problem", "3/4")
        self.assertTrue(body["correct"])
        self.assertEqual(body["matchedTier"], "numeric")

    def test_equivalent_matrix_reports_structured(self):
        body = self._grade(self._problem("[[1,2],[3,4]]"), "problem", "[[1, 2], [3, 4]]")
        self.assertTrue(body["correct"])
        self.assertEqual(body["matchedTier"], "structured")

    def test_wrong_problem_answer_reports_no_tier(self):
        body = self._grade(self._problem("0.75"), "problem", "5")
        self.assertFalse(body["correct"])
        self.assertIsNone(body["matchedTier"])

    def test_multiple_choice_reports_no_tier(self):
        card = NewCard("multiple_choice", "2+2?", "4", ["3", "4"])
        body = self._grade(card, "multiple_choice", "4")
        self.assertTrue(body["correct"])
        self.assertIsNone(
            body["matchedTier"], "the ladder does not run for multiple choice"
        )

    def test_enumeration_reports_no_tier(self):
        # Enumeration stores the expected items as JSON in correct_answer and as
        # the authoritative list in options, matching _card_storage_values.
        items = ["closure", "identity"]
        card = NewCard("enumeration", "Name two", json.dumps(items), items)
        body = self._grade(card, "enumeration", "closure and identity")
        self.assertTrue(body["correct"])
        self.assertIsNone(body["matchedTier"], "the ladder does not run for enumeration")

    def test_matched_tier_is_published_in_the_openapi_contract(self):
        document = self.client.get("/openapi.json").json()
        grade_result = document["components"]["schemas"]["GradeResult"]
        self.assertIn("matchedTier", grade_result["properties"])
        # The answer key itself must still never leak into the contract.
        self.assertNotIn("correct_answer", __import__("json").dumps(document))


if __name__ == "__main__":
    unittest.main()
