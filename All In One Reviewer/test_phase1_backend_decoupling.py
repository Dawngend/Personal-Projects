"""Offline Phase 1 tests for backend boundaries retained by the Streamlit app."""

from __future__ import annotations

import importlib
import ast
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import extractor
import generator
from generator import GenerationDependencies, orchestrate_custom_deck
from grading import (
    decode_card_options,
    grade_enumeration,
    grade_problem_answer,
    problem_payload,
)
from rag_engine import initialize_course_memory
from repositories import CardRepository, DeckRepository, NewCard


class ExtractionCacheTests(unittest.TestCase):
    def test_same_content_under_two_names_uses_one_content_hash_cache_entry(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first.pdf"
            second = root / "renamed.pdf"
            first.write_bytes(b"same course module")
            second.write_bytes(b"same course module")
            cache_directory = root / "cache"
            calls: list[str] = []

            def fake_extract(file_path: str, cache_file: str) -> str:
                calls.append(file_path)
                Path(cache_file).write_text("extracted content", encoding="utf-8")
                return "extracted content"

            with (
                patch.object(extractor, "EXTRACTION_CACHE_DIR", cache_directory),
                patch.object(extractor, "extract_text_from_pdf", fake_extract),
            ):
                self.assertEqual(extractor.process_module_file_v2(str(first)), "extracted content")
                self.assertEqual(extractor.process_module_file_v2(str(second)), "extracted content")

            self.assertEqual(calls, [str(first)])
            self.assertEqual(len(list(cache_directory.glob("*.txt"))), 1)


class RepositoryTests(unittest.TestCase):
    def test_typed_repositories_preserve_schema_and_atomic_deck_creation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "reviewer.db"
            decks = DeckRepository(database_path)
            cards = CardRepository(database_path)
            with self.assertRaisesRegex(ValueError, "without valid cards"):
                decks.create_with_cards("Empty", "m.pdf", "Math", [])
            self.assertEqual(decks.list(), [])

            deck = decks.create_with_cards(
                "Linear Algebra",
                "module.pdf",
                "Linear Algebra",
                [NewCard("multiple_choice", "Question?", "A", ["A", "B", "C", "D"])],
            )
            stored_cards = cards.list_for_deck(deck.id)
            self.assertEqual((deck.name, deck.subject), ("Linear Algebra", "Linear Algebra"))
            self.assertEqual(stored_cards[0].options, '["A", "B", "C", "D"]')
            cards.increment_miss_count(stored_cards[0].id, 2)
            self.assertEqual(cards.list_for_deck(deck.id)[0].times_missed, 2)


class CourseMemoryTests(unittest.TestCase):
    def test_memory_initializes_once_from_an_injected_chroma_boundary(self):
        class FakeCollection:
            def __init__(self):
                self.queries: list[dict] = []

            def query(self, **kwargs):
                self.queries.append(kwargs)
                return {"documents": [[]], "metadatas": [[{}]]}

        class FakeClient:
            def __init__(self):
                self.collection = FakeCollection()
                self.calls = 0

            def get_or_create_collection(self, **kwargs):
                self.calls += 1
                return self.collection

        rag = importlib.import_module("rag_engine")
        rag._course_memory = None
        client = FakeClient()
        first = initialize_course_memory(chroma_client=client, embedding_function="default")
        second = initialize_course_memory(chroma_client=FakeClient(), embedding_function="other")

        self.assertIs(first, second)
        self.assertEqual(client.calls, 1)
        first.get_historical_context("chunk", " Linear Algebra ")
        self.assertEqual(client.collection.queries[0]["where"], {"subject": "linear algebra"})
        rag._course_memory = None


class GenerationOrchestrationTests(unittest.TestCase):
    def test_orchestrator_validates_before_the_transactional_persistence_step(self):
        persisted: list[tuple] = []
        raw_cards = [{
            "type": "multiple_choice",
            "question": "Which value is a determinant?",
            "options": ["24", "transpose", "vector", "rank"],
            "correct_answer": "24",
        }]
        dependencies = GenerationDependencies(
            extract_file=lambda _: "x" * 80,
            create_client=lambda: object(),
            get_context=lambda chunk, subject: "",
            query_cards=lambda client, chunk, prompt: raw_cards,
            add_memory=lambda name, subject, chunks: None,
            persist_deck=lambda name, modules, subject, cards: persisted.append((name, modules, subject, cards)) or 42,
            sleep=lambda _: None,
        )

        deck_id = orchestrate_custom_deck(
            ["module.pdf"], "Deck", "Linear Algebra", 1,
            dependencies=dependencies, report=lambda _: None,
        )

        self.assertEqual(deck_id, 42)
        self.assertEqual(persisted[0][0:3], ("Deck", "module.pdf", "Linear Algebra"))
        self.assertEqual(persisted[0][3][0].correct_answer, "24")

        no_valid_cards = GenerationDependencies(
            **{**dependencies.__dict__, "query_cards": lambda client, chunk, prompt: [{"type": "bad"}]}
        )
        self.assertIsNone(orchestrate_custom_deck(
            ["module.pdf"], "No Deck", "Linear Algebra", 1,
            dependencies=no_valid_cards, report=lambda _: None,
        ))
        self.assertEqual(len(persisted), 1)

    def test_legacy_single_file_generation_keeps_its_existing_database_facade(self):
        saved_cards: list[dict] = []
        raw_cards = [{
            "type": "multiple_choice",
            "question": "Which value is a determinant?",
            "options": ["24", "transpose", "vector", "rank"],
            "correct_answer": "24",
        }]
        with (
            patch.object(generator, "process_module_file_v2", return_value="x" * 80),
            patch.object(generator, "_get_client", return_value=object()),
            patch.object(generator, "get_historical_context", return_value=""),
            patch.object(generator, "_query_groq", return_value=raw_cards),
            patch.object(generator, "add_to_memory"),
            patch.object(generator, "create_deck", return_value=17),
            patch.object(generator, "add_card", side_effect=lambda **kwargs: saved_cards.append(kwargs)),
        ):
            deck_id = generator.generate_deck_from_file(
                "module.pdf", "Legacy Deck", "Linear Algebra", "multiple_choice"
            )

        self.assertEqual(deck_id, 17)
        self.assertEqual(saved_cards[0]["deck_id"], 17)


class GradingTests(unittest.TestCase):
    def test_grading_and_legacy_payloads_are_pure_python(self):
        self.assertEqual(decode_card_options('["A", "B"]'), ["A", "B"])
        self.assertEqual(decode_card_options("not json"), [])
        self.assertEqual(grade_enumeration("Closure, identity", ["closure", "identity", "inverse"]), (
            ["closure", "identity"], ["inverse"],
        ))
        self.assertTrue(grade_problem_answer("1,024", "1024"))
        self.assertEqual(problem_payload({"final_answer": "24", "solution_steps": ["Multiply."]}, "fallback"), (
            "24", ["Multiply."],
        ))


class ImportBoundaryTests(unittest.TestCase):
    def test_refactored_modules_have_no_streamlit_import(self):
        for module_name in ("extractor", "repositories", "rag_engine", "grading", "generator"):
            module = importlib.import_module(module_name)
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            imported_modules = {
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            }
            self.assertNotIn("streamlit", imported_modules, module_name)
        self.assertNotIn("streamlit", sys.modules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
