"""Deck summaries preserve legacy counts without per-deck card queries."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from andyhub_api.main import create_app
from andyhub_api.settings import Settings
from repositories import CardRepository, DeckRepository, NewCard, open_connection


class DeckSummaryQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            database_path=root / "reviewer.db",
            uploads_directory=root / "uploads",
            extraction_cache_directory=root / "cache",
            initialize_course_memory=False,
            start_generation_worker=False,
        )
        self.client = self.enterContext(TestClient(create_app(self.settings)))
        self.decks = DeckRepository(self.settings.database_path)
        self.cards = CardRepository(self.settings.database_path)
        self.mixed = self.decks.create_with_cards(
            "Mixed deck", " First.pdf, , Second.pdf ", "Math",
            [
                NewCard("multiple_choice", "MCQ one", "B", ["A", "B", "C", "D"]),
                NewCard("multiple_choice", "MCQ two", "A", ["A", "B"]),
                NewCard("enumeration", "Enum", '["closure", "identity"]', ["closure", "identity"]),
                NewCard("problem", "Problem one", "24"),
                NewCard("problem", "Problem two", "12"),
            ],
        )
        for card, misses in zip(self.cards.list_for_deck(self.mixed.id), (2, 0, 3, 1, 4)):
            self.cards.increment_miss_count(card.id, misses)
        self.empty = self.decks.create("Empty deck", "", "History")
        self.unknown_type = self.decks.create_with_cards(
            "Legacy deck", "Legacy.pdf", "Math",
            [NewCard("legacy_type", "Legacy question", "answer")],
        )
        unknown_card = self.cards.list_for_deck(self.unknown_type.id)[0]
        self.cards.increment_miss_count(unknown_card.id, 7)

    def old_summary(self, deck) -> dict:
        cards = self.cards.list_for_deck(deck.id)
        return {
            "id": deck.id,
            "name": deck.name,
            "subject": deck.subject,
            "modules": [item.strip() for item in deck.modules_included.split(",") if item.strip()],
            "moduleRefs": None,
            "cardCount": len(cards),
            "questionTypes": {
                kind: sum(card.card_type == kind for card in cards)
                for kind in ("multiple_choice", "enumeration", "problem")
            },
            "totalMisses": sum(card.times_missed for card in cards),
        }

    def test_list_and_detail_match_old_summaries(self) -> None:
        expected = [self.old_summary(deck) for deck in self.decks.list()]
        response = self.client.get("/api/v1/decks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        for summary in expected:
            with self.subTest(deck_id=summary["id"]):
                response = self.client.get(f"/api/v1/decks/{summary['id']}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {**summary, "cards": None})

    def test_filters_and_limit_preserve_deck_order(self) -> None:
        response = self.client.get(
            "/api/v1/decks", params={"subject": "mAtH", "search": "DECK", "limit": 1},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [self.old_summary(self.mixed)])
        response = self.client.get("/api/v1/decks", params={"search": "history"})
        self.assertEqual(response.json(), [self.old_summary(self.empty)])

    def test_detail_includes_cards_with_one_card_load(self) -> None:
        cards = self.cards.list_for_deck(self.mixed.id)
        expected_cards = [
            {"id": cards[0].id, "type": "multiple_choice", "question": "MCQ one", "options": ["A", "B", "C", "D"]},
            {"id": cards[1].id, "type": "multiple_choice", "question": "MCQ two", "options": ["A", "B"]},
            {"id": cards[2].id, "type": "enumeration", "question": "Enum", "expectedCount": 2},
            {"id": cards[3].id, "type": "problem", "question": "Problem one", "answerFormatHint": "Final answer (scalar/text auto-grading)"},
            {"id": cards[4].id, "type": "problem", "question": "Problem two", "answerFormatHint": "Final answer (scalar/text auto-grading)"},
        ]
        with patch("repositories.open_connection", wraps=open_connection) as connections:
            response = self.client.get(f"/api/v1/decks/{self.mixed.id}", params={"include": "cards"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {**self.old_summary(self.mixed), "cards": expected_cards})
        self.assertLessEqual(connections.call_count, 3)

    def test_unknown_deck_returns_404(self) -> None:
        response = self.client.get("/api/v1/decks/999999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_list_connection_count_does_not_grow_with_decks(self) -> None:
        with patch("repositories.open_connection", wraps=open_connection) as connections:
            response = self.client.get("/api/v1/decks")
        self.assertEqual(response.status_code, 200)
        initial_count = connections.call_count

        for index in range(20):
            self.decks.create_with_cards(
                f"Extra deck {index}", "Extra.pdf", "Math",
                [NewCard("problem", "Extra problem", "42")],
            )
        expected = [self.old_summary(deck) for deck in self.decks.list()]
        with patch("repositories.open_connection", wraps=open_connection) as connections:
            response = self.client.get("/api/v1/decks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        self.assertEqual(connections.call_count, initial_count)
        self.assertLessEqual(connections.call_count, 2)


if __name__ == "__main__":
    unittest.main()
