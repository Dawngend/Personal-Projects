"""The legacy database facade must agree with the API on which file to open.

Found by the first real Phase 5 staging run: the worker container crashed with
PermissionError creating a relative 'Database' directory inside the image. The
permission error was only the visible symptom. The real defect is that
generator.py imports database.py, which hardcoded a path relative to the
current directory, so a deployed worker would have written generated decks to a
private file while the API served a different one.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent


def load_database_module(name: str):
    """Load database.py fresh so module-level path resolution re-runs."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "database.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


class DatabasePathResolutionTests(unittest.TestCase):
    def test_explicit_database_path_wins(self):
        with patch.dict(
            "os.environ",
            {"ANDYHUB_DATABASE_PATH": "/data/Database/reviewer.db"},
            clear=False,
        ):
            module = load_database_module("_db_explicit")
        self.assertEqual(module.DB_PATH, "/data/Database/reviewer.db")

    def test_data_root_is_honored_when_no_explicit_path(self):
        environment = {"ANDYHUB_DATA_ROOT": str(Path("/data"))}
        with patch.dict("os.environ", environment, clear=False):
            with patch.dict("os.environ", {"ANDYHUB_DATABASE_PATH": ""}):
                module = load_database_module("_db_data_root")
        self.assertEqual(
            Path(module.DB_PATH), Path("/data") / "Database" / "reviewer.db"
        )

    def test_streamlit_relative_default_is_unchanged(self):
        # No container variables set: the historical behavior must survive.
        with patch.dict(
            "os.environ",
            {"ANDYHUB_DATABASE_PATH": "", "ANDYHUB_DATA_ROOT": ""},
            clear=False,
        ):
            module = load_database_module("_db_default")
        self.assertEqual(Path(module.DB_PATH), Path("Database") / "reviewer.db")

    def test_blank_values_are_treated_as_unset(self):
        with patch.dict(
            "os.environ",
            {"ANDYHUB_DATABASE_PATH": "   ", "ANDYHUB_DATA_ROOT": "  "},
            clear=False,
        ):
            module = load_database_module("_db_blank")
        self.assertEqual(Path(module.DB_PATH), Path("Database") / "reviewer.db")

    def test_facade_and_api_settings_agree_under_container_environment(self):
        """The whole point: one configured path, one database file."""
        from andyhub_api.settings import Settings

        container = {
            "ANDYHUB_DATA_ROOT": "/data",
            "ANDYHUB_DATABASE_PATH": "/data/Database/reviewer.db",
        }
        with patch.dict("os.environ", container, clear=False):
            module = load_database_module("_db_agreement")
            settings = Settings.defaults()
        self.assertEqual(Path(module.DB_PATH), settings.database_path)


if __name__ == "__main__":
    unittest.main()
