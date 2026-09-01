"""Modules must be read by their stored content-hash name, never by display name.

Uploads are written to disk as `{sha256}{ext}` but the database also keeps the
user's original filename. The generation path passed the DISPLAY name to
prepare_custom_deck, which joins it onto uploads_directory. Two consequences:

  * normally the file is not found and the whole job fails, and
  * uploads/ is the same directory the legacy Streamlit app filled with files
    named after their originals, so a stale legacy file with a colliding name
    is extracted instead and the deck is silently built from the WRONG
    document.

The decoy test below fails against the old code.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from generator import prepare_custom_deck

LONG_ENOUGH = "x" * 400


class ModuleLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.uploads = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _extractor(self):
        def extract(path: str) -> str:
            name = Path(path).name
            target = self.uploads / name
            if not target.exists():
                return f"Error: {name} not found"
            return target.read_text(encoding="utf-8")
        return extract

    def test_reads_the_stored_hash_name_not_the_decoy_at_the_display_name(self) -> None:
        stored = "a1b2c3d4e5f6.pdf"
        display = "Linear Algebra Week 3.pdf"
        (self.uploads / stored).write_text("REAL MODULE CONTENT " + LONG_ENOUGH, encoding="utf-8")
        # A stale legacy upload sitting at the display name, as the Streamlit
        # app would have left it in this very directory.
        (self.uploads / display).write_text("STALE LEGACY CONTENT " + LONG_ENOUGH, encoding="utf-8")

        preparation = prepare_custom_deck(
            [stored],
            display_names=[display],
            extract_file=self._extractor(),
            uploads_directory=str(self.uploads),
            report=lambda _: None,
        )

        self.assertIsNotNone(preparation)
        self.assertIn("REAL MODULE CONTENT", preparation.combined_text)
        self.assertNotIn(
            "STALE LEGACY CONTENT", preparation.combined_text,
            "the deck was built from a stale legacy file that merely shared the display name",
        )

    def test_provenance_keeps_the_human_readable_name(self) -> None:
        stored = "deadbeef0123.pdf"
        display = "Chapter 1 Notes.pdf"
        (self.uploads / stored).write_text("CONTENT " + LONG_ENOUGH, encoding="utf-8")

        preparation = prepare_custom_deck(
            [stored],
            display_names=[display],
            extract_file=self._extractor(),
            uploads_directory=str(self.uploads),
            report=lambda _: None,
        )

        self.assertIsNotNone(preparation)
        self.assertEqual(preparation.selected_files, (display,))
        self.assertIn(display, preparation.combined_text)
        self.assertNotIn(stored, preparation.combined_text)

    def test_display_names_defaults_to_selected_files_for_the_cli_path(self) -> None:
        name = "notes.pdf"
        (self.uploads / name).write_text("CONTENT " + LONG_ENOUGH, encoding="utf-8")

        preparation = prepare_custom_deck(
            [name],
            extract_file=self._extractor(),
            uploads_directory=str(self.uploads),
            report=lambda _: None,
        )

        self.assertIsNotNone(preparation)
        self.assertEqual(preparation.selected_files, (name,))

    def test_mismatched_display_names_is_a_hard_error(self) -> None:
        with self.assertRaises(ValueError):
            prepare_custom_deck(
                ["a.pdf", "b.pdf"],
                display_names=["only-one.pdf"],
                extract_file=self._extractor(),
                uploads_directory=str(self.uploads),
                report=lambda _: None,
            )


class ServiceUsesStoredFilenameTests(unittest.TestCase):
    """The API generation path must pass stored_filename, not filename."""

    def test_generation_path_selects_stored_filename(self) -> None:
        source = Path("andyhub_api/services.py").read_text(encoding="utf-8")
        marker = "prepare_custom_deck("
        start = source.index(marker)
        call = source[start : source.index(")", source.index("report=", start))]

        self.assertIn("module.stored_filename for module in resolved", call)
        self.assertIn("display_names=", call)
        # The lookup list is the first positional argument, so stored_filename
        # must appear before display_names= in the call. If they are swapped,
        # the deck is read by display name again.
        self.assertLess(
            call.index("stored_filename"), call.index("display_names="),
            "stored_filename must be the positional lookup list, not the display_names value",
        )


if __name__ == "__main__":
    unittest.main()
