from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main


class AppSettingsTests(unittest.TestCase):
    def test_user_settings_overlay_tracked_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tracked = root / "tracked.json"
            user = root / "user" / "settings.json"
            tracked.write_text(
                json.dumps({"render_resolution": 512, "llm_provider": "none"}),
                encoding="utf-8",
            )
            user.parent.mkdir()
            user.write_text(json.dumps({"llm_provider": "ollama"}), encoding="utf-8")
            with (
                patch.object(main, "DEFAULT_SETTINGS_FILE", tracked),
                patch.object(main, "SETTINGS", user),
            ):
                settings = main.load_settings()
        self.assertEqual(512, settings["render_resolution"])
        self.assertEqual("ollama", settings["llm_provider"])
        self.assertIn("ollama_base_url", settings)

    def test_invalid_user_settings_fall_back_without_losing_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tracked = root / "tracked.json"
            user = root / "settings.json"
            tracked.write_text(json.dumps({"cache_enabled": False}), encoding="utf-8")
            user.write_text("[]", encoding="utf-8")
            with (
                patch.object(main, "DEFAULT_SETTINGS_FILE", tracked),
                patch.object(main, "SETTINGS", user),
            ):
                settings = main.load_settings()
        self.assertFalse(settings["cache_enabled"])
        self.assertEqual("none", settings["llm_provider"])

    def test_save_settings_creates_an_atomic_personal_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "nested" / "settings.json"
            with patch.object(main, "SETTINGS", target):
                main.save_settings({"cache_enabled": True})
            self.assertEqual({"cache_enabled": True}, json.loads(target.read_text(encoding="utf-8")))
            self.assertEqual([], list(target.parent.glob("*.tmp")))

    def test_malformed_runtime_types_are_normalized_for_worker_selection(self):
        settings = main.normalize_settings(
            {
                "performance_metrics": "not-a-list",
                "available_memory_gb": float("inf"),
                "cache_enabled": "yes",
                "render_resolution": True,
                "llm_provider": ["ollama"],
            }
        )
        self.assertEqual([], settings["performance_metrics"])
        self.assertIsNone(settings["available_memory_gb"])
        self.assertIs(settings["cache_enabled"], True)
        self.assertEqual(768, settings["render_resolution"])
        self.assertEqual("none", settings["llm_provider"])


if __name__ == "__main__":
    unittest.main()
