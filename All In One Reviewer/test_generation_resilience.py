"""A chunk that fails to parse must not abort the whole generation.

Found on the first successful containerised generation: three cards had already
come back when a later chunk failed to parse. The JSON error handler then tried
to write groq_raw_error.txt into the working directory, which is /app and not
writable by the container user. The handler meant to recover from the error
raised PermissionError instead, and the entire job failed with zero valid cards
despite work having succeeded.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import generator


def _response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class UnparseableChunkTests(unittest.TestCase):
    def test_valid_response_returns_its_questions(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response(
            json.dumps({"questions": [{"type": "problem", "question": "Q"}]})
        )
        result = generator._query_groq(client, "module text")
        self.assertEqual(len(result), 1)

    def test_unparseable_chunk_returns_empty_rather_than_raising(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response("not json at all")
        self.assertEqual(generator._query_groq(client, "module text"), [])

    def test_an_unwritable_debug_path_cannot_fail_the_chunk(self):
        """The exact production failure: the debug write raises PermissionError."""
        client = MagicMock()
        client.chat.completions.create.return_value = _response("not json at all")

        with patch.object(
            Path, "write_text", side_effect=PermissionError(13, "Permission denied")
        ):
            result = generator._query_groq(client, "module text")

        self.assertEqual(
            result, [], "a failed debug write must degrade to an empty chunk"
        )

    def test_an_unwritable_debug_directory_cannot_fail_the_chunk(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response("not json at all")

        with patch.object(
            Path, "mkdir", side_effect=PermissionError(13, "Permission denied")
        ):
            result = generator._query_groq(client, "module text")

        self.assertEqual(result, [])

    def test_debug_output_goes_to_a_writable_directory(self, ):
        client = MagicMock()
        client.chat.completions.create.return_value = _response("not json at all")

        written = {}

        def capture(self, data, encoding=None):  # noqa: ANN001
            written["path"] = self
            written["data"] = data

        with patch.object(Path, "write_text", capture):
            generator._query_groq(client, "module text")

        self.assertIn("path", written, "the raw response should still be saved")
        self.assertNotEqual(
            Path(written["path"]).parent,
            Path("."),
            "it must not be written to the working directory",
        )

    def test_a_transport_error_still_returns_empty(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("connection reset")
        self.assertEqual(generator._query_groq(client, "module text"), [])


if __name__ == "__main__":
    unittest.main()
