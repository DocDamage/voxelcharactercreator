from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.package_windows import build_parser, package_files
from vcf_core.production import package_source_distribution


ROOT = Path(__file__).resolve().parents[1]


class PackageFileSelectionTests(unittest.TestCase):
    def test_untracked_files_require_explicit_development_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            (root / ".gitignore").write_text(
                (ROOT / ".gitignore").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            tracked = root / "tracked.txt"
            tracked.write_text("tracked\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", ".gitignore", "tracked.txt"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            sentinel = root / "untracked-sentinel.txt"
            sentinel.write_text("development only\n", encoding="utf-8")
            credential_key = "SEC" + "RET"
            (root / ".env").write_text(f"{credential_key}=do-not-package\n", encoding="utf-8")
            (root / ".env.local").write_text(f"{credential_key}=also-do-not-package\n", encoding="utf-8")
            example = root / ".env.example"
            example.write_text(f"{credential_key}=example-only\n", encoding="utf-8")

            default_files = set(package_files(root))
            development_files = set(
                package_files(root, include_untracked_development_files=True)
            )
            default_manifest = package_source_distribution(
                root, root / "default.zip", default_files
            )
            development_manifest = package_source_distribution(
                root, root / "development.zip", development_files
            )
            default_paths = {item["path"] for item in default_manifest["files"]}
            development_paths = {
                item["path"] for item in development_manifest["files"]
            }

            self.assertIn(tracked, default_files)
            self.assertNotIn(sentinel, default_files)
            self.assertNotIn(example, default_files)
            self.assertIn(sentinel, development_files)
            self.assertIn(example, development_files)
            self.assertNotIn(root / ".env", development_files)
            self.assertNotIn(root / ".env.local", development_files)
            self.assertNotIn("untracked-sentinel.txt", default_paths)
            self.assertIn("untracked-sentinel.txt", development_paths)

    def test_development_opt_in_flag_is_explicit(self) -> None:
        args = build_parser().parse_args(["--include-untracked-development-files"])
        self.assertTrue(args.include_untracked_development_files)


if __name__ == "__main__":
    unittest.main()
