from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_version_file_matches_unreleased_changelog_version(self):
        version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        match = re.search(r"^Version: `([^`]+)`", changelog, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(version, match.group(1))

    def test_readme_describes_all_eight_weapon_families(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Eight versioned weapon/animation families", readme)
        self.assertNotIn("Seven versioned weapon/animation families", readme)


if __name__ == "__main__":
    unittest.main()
