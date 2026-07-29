from __future__ import annotations

import tempfile
import unittest
import subprocess
from pathlib import Path

from tools.scan_secrets import find_index_secrets, find_secrets, line_contains_secret


class SecretScannerTests(unittest.TestCase):
    def test_detects_quoted_unquoted_and_hyphenated_credentials(self):
        token = "sk-" + "a" * 24
        password_value = "CorrectHorse" + "BatteryStaple"
        client_value = "abcdefghijkl" + "mnopqrst"
        api_key = "OPENAI_API_" + "KEY"
        password = "pass" + "word"
        client_secret = "client_" + "secret"
        self.assertTrue(line_contains_secret(f"{api_key}={token}"))
        self.assertTrue(line_contains_secret(f"{password}: {password_value}"))
        self.assertTrue(line_contains_secret(f"{client_secret}='{client_value}'"))
        key = "DATABASE_" + "PASSWORD"
        quoted_value = "Abc#Very Long, " + "Secret; Password123"
        self.assertTrue(line_contains_secret(f'{key}="{quoted_value}"'))

    def test_detects_prefixed_environment_credential_names(self):
        value = "a" * 24
        database_password = "DATABASE_" + "PASSWORD"
        stripe_api_key = "STRIPE_API_" + "KEY"
        github_token = "GITHUB_" + "TOKEN"
        self.assertTrue(line_contains_secret(f"{database_password}={value}"))
        self.assertTrue(line_contains_secret(f"{stripe_api_key}={value}"))
        self.assertTrue(line_contains_secret(f"{github_token}={value}"))
        configured_value = "configuredStrong" + "Secret123"
        self.assertTrue(line_contains_secret(f"{database_password}={configured_value}"))

    def test_allows_environment_references_and_documented_placeholders(self):
        api_key = "api_" + "key"
        password = "pass" + "word"
        openai_api_key = "OPENAI_API_" + "KEY"
        self.assertFalse(line_contains_secret(f"{openai_api_key}=${{{openai_api_key}}}"))
        self.assertFalse(line_contains_secret(f"{api_key}=YOUR_API_KEY_HERE"))
        self.assertFalse(line_contains_secret(f"{password}: EXAMPLE_PASSWORD"))
        self.assertFalse(line_contains_secret(f"{password}=config.password"))

    def test_rejects_hard_coded_environment_fallbacks(self):
        key = "DATABASE_" + "PASSWORD"
        fallback = "CorrectHorse" + "BatteryStaple"
        self.assertTrue(line_contains_secret(f"{key}=${{{key}:-{fallback}}}"))
        self.assertTrue(
            line_contains_secret(f'{key} = os.getenv("{key}", "{fallback}")')
        )
        self.assertFalse(line_contains_secret(f'{key} = os.getenv("{key}")'))
        self.assertTrue(line_contains_secret(f'{key}="{fallback.upper()}123"'))
        self.assertTrue(
            line_contains_secret(f'{key}={{"primary":"{fallback}"}}')
        )
        self.assertTrue(line_contains_secret(f'{key}=["{fallback}"]'))
        escaped = "Abc\\\"" + fallback
        self.assertTrue(line_contains_secret(f'{key}="{escaped}"'))
        self.assertTrue(
            line_contains_secret(f'$password = $condition ? "{fallback}" : $env:{key}')
        )

    def test_selected_package_files_can_be_scanned_before_archiving(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clean = root / "clean.txt"
            unsafe = root / "unsafe.txt"
            clean.write_text("api_key=YOUR_API_KEY_HERE\n", encoding="utf-8")
            unsafe.write_text("password=" + "s" * 20 + "\n", encoding="utf-8")
            findings = find_secrets([clean, unsafe], root=root)
        self.assertEqual(["unsafe.txt:1"], findings)

    def test_index_scan_catches_a_staged_secret_hidden_by_worktree_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            credential = root / "settings.env"
            key = "DATABASE_" + "PASSWORD"
            credential.write_text(f"{key}={'x' * 24}\n", encoding="utf-8")
            subprocess.run(["git", "add", "settings.env"], cwd=root, check=True)
            credential.write_text(f"{key}=YOUR_PASSWORD_HERE\n", encoding="utf-8")
            findings = find_index_secrets(root)
        self.assertEqual(["settings.env:1"], findings)


if __name__ == "__main__":
    unittest.main()
