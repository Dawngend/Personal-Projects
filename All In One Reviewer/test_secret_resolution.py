"""GROQ_API_KEY_FILE must be authoritative in a deployed container.

_get_client swallowed OSError when the mounted secret could not be read and
then fell through to .streamlit/secrets.toml. In a container built from a
developer working directory that file can exist, so an unreadable mounted
secret -- the root-owned-secret failure fixed in a95473d -- would silently be
papered over by a key baked into the image, defeating the permission check the
cutover performs. The fallback is now developer-only.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import generator


class SecretResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._cwd = os.getcwd()
        self.addCleanup(os.chdir, self._cwd)

    def _clear(self) -> dict:
        return {"GROQ_API_KEY": "", "GROQ_API_KEY_FILE": ""}

    def test_readable_secret_file_is_used(self) -> None:
        secret = self.tmp / "groq_api_key"
        secret.write_text("gsk_from_the_mounted_secret\n", encoding="utf-8")

        env = self._clear() | {"GROQ_API_KEY_FILE": str(secret)}
        with patch.dict("os.environ", env, clear=False):
            with patch.object(generator, "Groq") as groq:
                generator._get_client()

        self.assertEqual(groq.call_args.kwargs["api_key"], "gsk_from_the_mounted_secret")

    def test_unreadable_secret_file_does_not_fall_back_to_streamlit(self) -> None:
        # A developer-style secrets.toml sitting in the working directory, the
        # shape that a working-directory image build would bake in.
        os.chdir(self.tmp)
        (self.tmp / ".streamlit").mkdir()
        (self.tmp / ".streamlit" / "secrets.toml").write_text(
            'GROQ_API_KEY = "gsk_baked_into_the_image"\n', encoding="utf-8"
        )

        env = self._clear() | {"GROQ_API_KEY_FILE": str(self.tmp / "does-not-exist")}
        with patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeError):
                generator._get_client()

    def test_configured_secret_file_disables_the_streamlit_fallback_entirely(self) -> None:
        os.chdir(self.tmp)
        (self.tmp / ".streamlit").mkdir()
        (self.tmp / ".streamlit" / "secrets.toml").write_text(
            'GROQ_API_KEY = "gsk_baked_into_the_image"\n', encoding="utf-8"
        )
        empty_secret = self.tmp / "empty_secret"
        empty_secret.write_text("   \n", encoding="utf-8")

        env = self._clear() | {"GROQ_API_KEY_FILE": str(empty_secret)}
        with patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeError):
                generator._get_client()

    def test_developer_machine_still_falls_back_when_no_secret_file_configured(self) -> None:
        os.chdir(self.tmp)
        (self.tmp / ".streamlit").mkdir()
        (self.tmp / ".streamlit" / "secrets.toml").write_text(
            'GROQ_API_KEY = "gsk_developer_local"\n', encoding="utf-8"
        )

        with patch.dict("os.environ", self._clear(), clear=False):
            with patch.object(generator, "Groq") as groq:
                generator._get_client()

        self.assertEqual(groq.call_args.kwargs["api_key"], "gsk_developer_local")

    def test_environment_variable_still_wins(self) -> None:
        env = self._clear() | {"GROQ_API_KEY": "gsk_from_env"}
        with patch.dict("os.environ", env, clear=False):
            with patch.object(generator, "Groq") as groq:
                generator._get_client()

        self.assertEqual(groq.call_args.kwargs["api_key"], "gsk_from_env")


if __name__ == "__main__":
    unittest.main()
