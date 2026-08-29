"""The extraction cache must never serve an empty result as if it were real.

Found during the Phase 5 staging rehearsal: a module reported 0 extracted
characters while logging "Found saved extraction! Skipping Tesseract". The
cache held a 0-byte entry. Because extraction appends page by page, a failed
or interrupted run leaves an empty or partial file, and the existence-only
check then treats it as complete. The module can never recover: OCR is skipped
forever and generation silently produces nothing from it.

Clearing the entry and re-extracting produced 17,510 characters, confirming the
document was fine and the cache was the problem.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import extractor


class ExtractionCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.module = self.root / "module.pdf"
        self.module.write_bytes(b"%PDF-1.4 fake")
        self.cache_dir = self.root / "cache"
        self.cache_dir.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _cache_path(self) -> Path:
        return Path(extractor.get_cache_filename(str(self.module)))

    def _run(self):
        with patch.dict(
            "os.environ",
            {"ANDYHUB_EXTRACTION_CACHE_DIR": str(self.cache_dir)},
            clear=False,
        ):
            return extractor.process_module_file_v2(str(self.module))

    def test_populated_cache_is_reused_without_re_extracting(self):
        with patch.dict(
            "os.environ",
            {"ANDYHUB_EXTRACTION_CACHE_DIR": str(self.cache_dir)},
            clear=False,
        ):
            cache_file = Path(extractor.get_cache_filename(str(self.module)))
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text("real extracted text", encoding="utf-8")

            with patch.object(extractor, "extract_text_from_pdf") as extract:
                result = extractor.process_module_file_v2(str(self.module))

        self.assertEqual(result, "real extracted text")
        extract.assert_not_called()

    def test_empty_cache_entry_triggers_re_extraction(self):
        with patch.dict(
            "os.environ",
            {"ANDYHUB_EXTRACTION_CACHE_DIR": str(self.cache_dir)},
            clear=False,
        ):
            cache_file = Path(extractor.get_cache_filename(str(self.module)))
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text("", encoding="utf-8")

            with patch.object(
                extractor, "extract_text_from_pdf", return_value="recovered text"
            ) as extract:
                result = extractor.process_module_file_v2(str(self.module))

        self.assertEqual(result, "recovered text")
        extract.assert_called_once()

    def test_whitespace_only_cache_entry_triggers_re_extraction(self):
        with patch.dict(
            "os.environ",
            {"ANDYHUB_EXTRACTION_CACHE_DIR": str(self.cache_dir)},
            clear=False,
        ):
            cache_file = Path(extractor.get_cache_filename(str(self.module)))
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text("   \n\t \n", encoding="utf-8")

            with patch.object(
                extractor, "extract_text_from_pdf", return_value="recovered text"
            ) as extract:
                result = extractor.process_module_file_v2(str(self.module))

        self.assertEqual(result, "recovered text")
        extract.assert_called_once()

    def test_empty_cache_entry_is_removed_so_it_cannot_be_reused(self):
        with patch.dict(
            "os.environ",
            {"ANDYHUB_EXTRACTION_CACHE_DIR": str(self.cache_dir)},
            clear=False,
        ):
            cache_file = Path(extractor.get_cache_filename(str(self.module)))
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text("", encoding="utf-8")

            with patch.object(
                extractor, "extract_text_from_pdf", return_value="recovered text"
            ):
                extractor.process_module_file_v2(str(self.module))

            self.assertFalse(
                cache_file.exists(),
                "the stale empty entry must be cleared, not left to be re-read",
            )


class GroqModelConfigurationTests(unittest.TestCase):
    """A retired model must be fixable by configuration, not a code edit."""

    @staticmethod
    def _load_generator_model(environment):
        import importlib.util
        import sys

        root = Path(__file__).resolve().parent
        with patch.dict("os.environ", environment, clear=False):
            spec = importlib.util.spec_from_file_location(
                "_generator_model_probe", root / "generator.py"
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules["_generator_model_probe"] = module
            try:
                spec.loader.exec_module(module)
                return module.MODEL_NAME
            finally:
                sys.modules.pop("_generator_model_probe", None)

    def test_environment_variable_overrides_the_default(self):
        model = self._load_generator_model({"ANDYHUB_GROQ_MODEL": "some/other-model"})
        self.assertEqual(model, "some/other-model")

    def test_default_is_a_model_verified_against_the_real_prompt(self):
        model = self._load_generator_model({"ANDYHUB_GROQ_MODEL": ""})
        self.assertEqual(model, "openai/gpt-oss-120b")

    def test_the_retired_model_is_not_the_default(self):
        model = self._load_generator_model({"ANDYHUB_GROQ_MODEL": ""})
        self.assertNotEqual(
            model,
            "llama-3.3-70b-versatile",
            "Groq removed this model; it returns 404 model_not_found",
        )

    def test_blank_environment_value_falls_back_to_the_default(self):
        model = self._load_generator_model({"ANDYHUB_GROQ_MODEL": "   "})
        self.assertEqual(model, "openai/gpt-oss-120b")


if __name__ == "__main__":
    unittest.main()
