"""Phase 0 characterization tests for the pre-FastAPI AndyHub Python engine.

These tests deliberately describe behavior and storage shapes before backend
decoupling. They use temporary storage and fake integration boundaries: no
Groq request, OCR, production SQLite write, or Chroma write is performed.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parent


def load_module(module_name: str, filename: str):
    """Load a source file under an isolated module name."""
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def load_generator_with_fakes():
    """Load generator.py without importing network/OCR integration modules."""
    fake_rag = types.ModuleType("rag_engine")
    fake_rag.add_to_memory = lambda *args, **kwargs: None
    fake_rag.get_historical_context = lambda *args, **kwargs: ""
    fake_extractor = types.ModuleType("extractor")
    fake_extractor.process_module_file_v2 = lambda path: ""
    fake_database = types.ModuleType("database")
    fake_database.create_deck_with_cards = lambda *args, **kwargs: 1
    fake_database.create_deck = lambda *args, **kwargs: 1
    fake_database.add_card = lambda *args, **kwargs: None
    with patch.dict(sys.modules, {
        "rag_engine": fake_rag,
        "extractor": fake_extractor,
        "database": fake_database,
    }):
        return load_module("_phase0_generator", "generator.py")


def load_database_with_isolated_file(module_name: str):
    """Load database.py without its import-time init touching reviewer.db."""
    with patch("sqlite3.connect"):
        database = load_module(module_name, "database.py")
    for stale_path in (REPO_ROOT / "Database").glob(".phase0-contract-*.db"):
        stale_path.unlink(missing_ok=True)
    temporary_path = REPO_ROOT / "Database" / f".phase0-contract-{uuid4().hex}.db"
    database.DB_PATH = str(temporary_path)
    database.init_db()
    return database, temporary_path


def load_rag_engine_with_fake_chroma():
    """Load rag_engine.py against a recording Chroma-compatible boundary."""
    class FakeCollection:
        def __init__(self):
            self.upserts: list[dict] = []
            self.queries: list[dict] = []
            self.query_result = {"documents": [[]], "metadatas": [[{}]]}
            self.query_error: Exception | None = None

        def upsert(self, **kwargs):
            self.upserts.append(kwargs)

        def query(self, **kwargs):
            self.queries.append(kwargs)
            if self.query_error:
                raise self.query_error
            return self.query_result

    class FakeClient:
        def __init__(self):
            self.path: str | None = None
            self.collection = FakeCollection()

        def get_or_create_collection(self, **kwargs):
            self.collection_args = kwargs
            return self.collection

    fake_client = FakeClient()
    chromadb = types.ModuleType("chromadb")
    chromadb.PersistentClient = lambda path: setattr(fake_client, "path", path) or fake_client
    embedding_functions = types.ModuleType("embedding_functions")
    embedding_functions.DefaultEmbeddingFunction = lambda: "phase0-default-embedding"
    chromadb_utils = types.ModuleType("chromadb.utils")
    chromadb_utils.embedding_functions = embedding_functions
    with patch.dict(sys.modules, {
        "chromadb": chromadb,
        "chromadb.utils": chromadb_utils,
        "chromadb.utils.embedding_functions": embedding_functions,
    }):
        module = load_module("_phase0_rag_engine", "rag_engine.py")
        module.initialize_course_memory(
            chroma_client=fake_client,
            embedding_function="phase0-default-embedding",
        )
    return module, fake_client


class GeneratorContractTests(unittest.TestCase):
    def setUp(self):
        self.generator = load_generator_with_fakes()

    def test_question_style_contracts_include_all_three_persisted_card_types(self):
        self.assertEqual(self.generator.QUESTION_STYLES, {
            "multiple_choice": "Multiple Choice",
            "enumeration": "Enumeration",
            "problem": "Problem-Solving",
            "mixed": "Mixed",
        })
        self.assertIn('"type": "multiple_choice"', self.generator.get_andy_prompt(3, "multiple_choice"))
        self.assertIn('"type": "enumeration"', self.generator.get_andy_prompt(3, "enumeration"))
        self.assertIn('"type": "problem"', self.generator.get_andy_prompt(3, "problem"))
        self.assertIn("at least one multiple_choice", self.generator.get_andy_prompt(3, "mixed"))
        with self.assertRaisesRegex(ValueError, "Unsupported question style"):
            self.generator.get_andy_prompt(3, "essay")

    def test_card_validation_and_storage_shapes_are_the_current_contract(self):
        multiple_choice = {
            "type": "multiple_choice",
            "question": "Which operation is associative?",
            "options": ["Addition", "Transpose", "Inverse", "Rank"],
            "correct_answer": "Addition",
        }
        enumeration = {
            "type": "enumeration",
            "question": "Name the two matrix operations.",
            "correct_answer": ["matrix addition", "matrix multiplication"],
        }
        problem = {
            "type": "problem",
            "question": "Find det([[3, 0], [0, 8]]).",
            "correct_answer": "24",
            "solution_steps": ["Multiply diagonal entries.", "3 × 8 = 24."],
        }
        for index, card in enumerate((multiple_choice, enumeration, problem), start=1):
            self.assertTrue(self.generator._validate_card(card, index))
        self.assertEqual(self.generator._card_storage_values(multiple_choice), (
            "Addition", ["Addition", "Transpose", "Inverse", "Rank"],
        ))
        self.assertEqual(self.generator._card_storage_values(enumeration), (
            '["matrix addition", "matrix multiplication"]',
            ["matrix addition", "matrix multiplication"],
        ))
        self.assertEqual(self.generator._card_storage_values(problem), (
            "24", {"final_answer": "24", "solution_steps": ["Multiply diagonal entries.", "3 × 8 = 24."]},
        ))

    def test_invalid_new_card_variants_are_rejected(self):
        self.assertFalse(self.generator._validate_card({
            "type": "enumeration", "question": "Name one", "correct_answer": ["only one"]
        }, 1))
        self.assertFalse(self.generator._validate_card({
            "type": "problem", "question": "Compute", "correct_answer": "24", "solution_steps": []
        }, 2))
        self.assertFalse(self.generator._validate_card({
            "type": "multiple_choice", "question": "Pick one", "options": ["A", "B", "C"], "correct_answer": "A"
        }, 3))

    def test_custom_generation_preserves_all_three_storage_variants(self):
        generator = self.generator
        raw_cards = [
            {"type": "multiple_choice", "question": "MCQ?", "options": ["A", "B", "C", "D"], "correct_answer": "A"},
            {"type": "enumeration", "question": "Enumerate?", "correct_answer": ["first", "second"]},
            {"type": "problem", "question": "Solve?", "correct_answer": "24", "solution_steps": ["Step one", "Step two"]},
        ]
        saved_cards: list[object] = []
        memories: list[tuple] = []
        generator.process_module_file_v2 = lambda path: "x" * 80
        generator._get_client = lambda: object()
        generator.get_historical_context = lambda chunk, subject: "\ncontext"
        generator._query_groq = lambda client, chunk, system_prompt: raw_cards
        generator.add_to_memory = lambda *args: memories.append(args)
        generator.create_deck_with_cards = lambda name, modules, subject, cards: saved_cards.extend(cards) or 73
        deck_id = generator.generate_custom_deck(
            selected_files=["module.pdf"], deck_name="Contract Deck", subject="Linear Algebra",
            total_questions=3, question_style="mixed",
        )
        self.assertEqual(deck_id, 73)
        self.assertEqual(memories[0][0:2], ("Contract Deck", "Linear Algebra"))
        self.assertEqual([card.card_type for card in saved_cards], ["multiple_choice", "enumeration", "problem"])
        self.assertEqual(saved_cards[0].correct_answer, "A")
        self.assertEqual(saved_cards[0].options, ["A", "B", "C", "D"])
        self.assertEqual(saved_cards[1].correct_answer, '["first", "second"]')
        self.assertEqual(saved_cards[1].options, ["first", "second"])
        self.assertEqual(saved_cards[2].correct_answer, "24")
        self.assertEqual(saved_cards[2].options, {
            "final_answer": "24", "solution_steps": ["Step one", "Step two"],
        })

    def test_text_helpers_preserve_paragraph_boundaries_and_json_payloads(self):
        self.assertEqual(self.generator._chunk_text("alpha\n\nbeta\n\ngamma", max_chars=11), ["alpha\n\nbeta", "gamma"])
        self.assertEqual(self.generator._strip_json_fences("```json\n{\"questions\": []}\n```"), '{"questions": []}')


class DatabaseContractTests(unittest.TestCase):
    def test_sqlite_schema_and_tuple_rows_are_preserved(self):
        database, temporary_path = load_database_with_isolated_file("_phase0_database")
        try:
            deck_id = database.create_deck("Midterm", "m1.pdf, m2.pptx", "Linear Algebra")
            database.add_card(deck_id, "multiple_choice", "MCQ?", "A", ["A", "B", "C", "D"])
            database.add_card(deck_id, "enumeration", "List?", '["one", "two"]', ["one", "two"])
            database.add_card("1", "problem", "Solve?", "24", {
                "final_answer": "24", "solution_steps": ["Compute."],
            })
            self.assertEqual(database.get_decks(), [(1, "Midterm", "m1.pdf, m2.pptx", "Linear Algebra")])
            self.assertEqual(database.get_cards_for_deck(deck_id), [
                (1, 1, "multiple_choice", "MCQ?", "A", '["A", "B", "C", "D"]', 0),
                (2, 1, "enumeration", "List?", '["one", "two"]', '["one", "two"]', 0),
                (3, 1, "problem", "Solve?", "24", '{"final_answer": "24", "solution_steps": ["Compute."]}', 0),
            ])
            database.update_card_miss_count(2, increment=2)
            self.assertEqual(database.get_cards_for_deck(deck_id)[1][-1], 2)
            import sqlite3
            connection = sqlite3.connect(database.DB_PATH)
            try:
                columns = [row[1] for row in connection.execute("PRAGMA table_info(cards)")]
            finally:
                connection.close()
            self.assertEqual(columns, [
                "id", "deck_id", "type", "question", "correct_answer", "options", "times_missed",
            ])
        finally:
            temporary_path.unlink(missing_ok=True)

    def test_falsey_options_are_stored_as_null(self):
        database, temporary_path = load_database_with_isolated_file("_phase0_database_falsey")
        try:
            deck_id = database.create_deck("Deck", "module.pdf", "CS")
            database.add_card(deck_id, "legacy", "Question", "Answer", [])
            self.assertIsNone(database.get_cards_for_deck(deck_id)[0][5])
        finally:
            temporary_path.unlink(missing_ok=True)


class RagEngineContractTests(unittest.TestCase):
    def test_memory_upsert_normalizes_subject_and_uses_stable_ids(self):
        rag, fake_client = load_rag_engine_with_fake_chroma()
        rag.add_to_memory("Module One", " Linear Algebra ", ["first", "second"])
        self.assertEqual(fake_client.collection_args["name"], "feu_modules")
        self.assertEqual(fake_client.collection.upserts, [{
            "documents": ["first", "second"],
            "metadatas": [
                {"source": "Module One", "subject": "linear algebra"},
                {"source": "Module One", "subject": "linear algebra"},
            ],
            "ids": ["Module One_chunk_0", "Module One_chunk_1"],
        }])

    def test_context_query_is_subject_scoped_and_formats_source_excerpts(self):
        rag, fake_client = load_rag_engine_with_fake_chroma()
        fake_client.collection.query_result = {
            "documents": [["A" * 600, "short document"]],
            "metadatas": [[{"source": "Module A"}, {"source": "Module B"}]],
        }
        context = rag.get_historical_context("current chunk", " Data Science ", n_results=3)
        self.assertEqual(fake_client.collection.queries, [{
            "query_texts": ["current chunk"], "n_results": 3, "where": {"subject": "data science"},
        }])
        self.assertTrue(context.startswith("\n\n--- PAST RELEVANT KNOWLEDGE (From Vector DB) ---\n"))
        self.assertIn("[Module A]: " + "A" * 500 + "...", context)
        self.assertIn("[Module B]: short document...", context)

    def test_empty_or_failed_vector_queries_return_empty_context(self):
        rag, fake_client = load_rag_engine_with_fake_chroma()
        self.assertEqual(rag.get_historical_context("current", "CS"), "")
        fake_client.collection.query_error = RuntimeError("offline")
        self.assertEqual(rag.get_historical_context("current", "CS"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
