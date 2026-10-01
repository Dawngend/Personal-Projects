"""Lifecycle, validation, and CRUD coverage for generated study notes."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from andyhub_api.main import create_app
from andyhub_api.services import validate_generated_note
from andyhub_api.settings import Settings
from generator import GenerationDependencies
from repositories import DeckRepository


VALID_SECTION = {
    "heading": "Vector spaces",
    "summary": "A vector space is closed under addition and scalar multiplication.",
    "key_terms": [{"term": "basis", "definition": "A linearly independent spanning set."}],
    "properties": [{"name": "closure", "statement": "Adding two vectors stays in the space."}],
    "worked_examples": [
        {
            "problem": "Test whether R2 is closed under addition.",
            "steps": ["Choose two vectors.", "Add their components."],
            "answer": "The sum remains in R2.",
        }
    ],
    "common_mistakes": ["Checking one example instead of the general case."],
    "source_refs": ["Linear Algebra.pdf"],
}

NOTE_PAYLOAD = {
    "sections": [VALID_SECTION, {"heading": "Malformed section"}],
    "formula_sheet": [
        {"name": "Linear combination", "expression": "a_1v_1 + ... + a_nv_n", "when_to_use": "To express span."}
    ],
    "self_check": [{"question": "What defines a basis?", "answer": "Independence and span."}],
}


class GeneratedNotesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            database_path=root / "reviewer.db",
            uploads_directory=root / "uploads",
            extraction_cache_directory=root / "cache",
            initialize_course_memory=False,
            start_generation_worker=False,
        )

        def dependencies() -> GenerationDependencies:
            return GenerationDependencies(
                extract_file=lambda _: "vector space module content " * 20,
                create_client=lambda: object(),
                get_context=lambda *_: "",
                query_cards=lambda *_: [],
                add_memory=lambda *_: None,
                persist_deck=lambda name, modules, subject, cards: DeckRepository(
                    self.settings.database_path
                ).create_with_cards(name, modules, subject, cards).id,
                sleep=lambda _: None,
                query_notes=lambda *_: NOTE_PAYLOAD,
            )

        self.app = create_app(self.settings, dependencies_factory=dependencies)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def _upload(self) -> dict:
        response = self.client.post(
            "/api/v1/modules",
            files=[("files", ("Linear Algebra.pdf", b"module source", "application/pdf"))],
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["items"][0]

    def test_note_job_moves_from_queued_to_complete(self) -> None:
        module = self._upload()
        queued = self.client.post(
            "/api/v1/note-jobs",
            json={
                "title": "Linear Algebra Notes",
                "subject": "Math",
                "moduleIds": [module["id"]],
                "depth": "standard",
            },
        )
        self.assertEqual(queued.status_code, 202, queued.text)
        self.assertEqual(queued.json()["status"], "queued")

        self.assertTrue(self.app.state.note_service.run_pending_once())
        complete = self.client.get(f"/api/v1/note-jobs/{queued.json()['id']}")
        self.assertEqual(complete.status_code, 200, complete.text)
        self.assertEqual(complete.json()["status"], "complete")
        self.assertEqual(complete.json()["sectionsReceived"], 2)
        self.assertEqual(complete.json()["sectionsValid"], 1)
        self.assertIsInstance(complete.json()["noteId"], int)
        self.assertEqual(self.client.get("/api/v1/decks").json(), [])

        events = self.client.get(f"/api/v1/note-jobs/{queued.json()['id']}/events")
        self.assertEqual(events.status_code, 200)
        self.assertIn("event: progress", events.text)
        self.assertIn('"status":"complete"', events.text)

    def test_malformed_sections_are_rejected_individually(self) -> None:
        content, received, valid = validate_generated_note([NOTE_PAYLOAD])
        self.assertEqual(received, 2)
        self.assertEqual(valid, 1)
        self.assertEqual([section.heading for section in content.sections], ["Vector spaces"])
        with self.assertRaises(ValueError):
            validate_generated_note([{"sections": [VALID_SECTION]}])

    def test_notes_crud_routes_return_structured_content_and_delete(self) -> None:
        module = self._upload()
        queued = self.client.post(
            "/api/v1/note-jobs",
            json={
                "title": "Printable Algebra",
                "subject": "Math",
                "moduleIds": [module["id"]],
                "depth": "deep",
            },
        ).json()
        self.app.state.note_service.run_pending_once()
        note_id = self.client.get(f"/api/v1/note-jobs/{queued['id']}").json()["noteId"]

        listed = self.client.get("/api/v1/notes")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()[0]["title"], "Printable Algebra")
        self.assertNotIn("content", listed.json()[0])

        detail = self.client.get(f"/api/v1/notes/{note_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["moduleIds"], [module["id"]])
        self.assertEqual(detail.json()["content"]["sections"][0]["heading"], "Vector spaces")
        self.assertEqual(len(detail.json()["content"]["formulaSheet"]), 1)
        with closing(sqlite3.connect(self.settings.database_path)) as connection:
            stored = json.loads(
                connection.execute("SELECT content FROM notes WHERE id = ?", (note_id,)).fetchone()[0]
            )
        self.assertIsInstance(stored, dict)
        self.assertIn("formula_sheet", stored)
        self.assertNotIsInstance(stored, str)

        deleted = self.client.delete(f"/api/v1/notes/{note_id}")
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(self.client.get(f"/api/v1/notes/{note_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/notes").json(), [])


class ReviewerStyleNotesTests(unittest.TestCase):
    """Memory aids, comparison tables, and the cram sheet added for reviewer-style notes."""

    SECTION = {
        **VALID_SECTION,
        "memory_aids": [
            {"label": "DSDM phases", "text": "Pam Finds Big Fat Dogs In Parks."},
            {"label": "", "text": "an empty label is invalid"},
        ],
        "comparisons": [
            {"title": "401 vs 403", "columns": ["Code", "Meaning"], "rows": [["401", "Who are you"], ["403", "No"]]},
            {"title": "ragged", "columns": ["A", "B"], "rows": [["only one cell"]]},
            {"title": "one column", "columns": ["A"], "rows": [["x"]]},
        ],
    }

    def test_bad_memory_aids_and_comparisons_never_cost_the_section(self) -> None:
        payload = {
            "sections": [self.SECTION],
            "formula_sheet": [],
            "self_check": [],
            "cram_sheet": [{"topic": "SDLC", "remember": "Six phases"}, {"topic": "", "remember": "bad"}],
        }
        content, received, valid = validate_generated_note([payload])
        self.assertEqual((received, valid), (1, 1))
        section = content.sections[0]
        self.assertEqual([m.label for m in section.memory_aids], ["DSDM phases"])
        self.assertEqual([c.title for c in section.comparisons], ["401 vs 403"])
        self.assertEqual([c.topic for c in content.cram_sheet], ["SDLC"])

    def test_notes_without_the_new_fields_still_validate(self) -> None:
        content, _, valid = validate_generated_note(
            [{"sections": [VALID_SECTION], "formula_sheet": [], "self_check": []}]
        )
        self.assertEqual(valid, 1)
        self.assertEqual(content.sections[0].memory_aids, [])
        self.assertEqual(content.cram_sheet, [])
        stored_shape = content.model_dump(mode="json")
        self.assertIn("cram_sheet", stored_shape)

    def test_old_stored_note_json_loads_with_defaults(self) -> None:
        from andyhub_api.schemas import NoteContent

        legacy = {
            "sections": [VALID_SECTION],
            "formula_sheet": [],
            "self_check": [],
        }
        loaded = NoteContent.model_validate(legacy)
        self.assertEqual(loaded.sections[0].comparisons, [])

    def test_prompt_asks_for_reviewer_style_output(self) -> None:
        from generator import get_andy_note_prompt

        prompt = get_andy_note_prompt("standard", ["a.pdf"])
        for needle in ("memory_aids", "comparisons", "cram_sheet", "plain language"):
            self.assertIn(needle, prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
