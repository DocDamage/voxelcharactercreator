from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.catalog import catalog_games, filter_character_catalog, load_character_catalog


ROOT = Path(__file__).resolve().parents[1]


class CharacterCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = load_character_catalog(ROOT, validate=True)

    def test_catalog_loads_the_complete_valid_character_library(self):
        self.assertEqual(140, len(self.records))
        self.assertTrue(all(record.valid for record in self.records))
        self.assertIn("FF7", catalog_games(self.records))

    def test_filter_matches_metadata_terms_and_game(self):
        cloud = filter_character_catalog(self.records, "cloud hero", "FF7")
        self.assertEqual(["ff7_cloud"], [record.job_id for record in cloud])
        self.assertEqual([], filter_character_catalog(self.records, "cloud", "FF8"))

    def test_fast_catalog_inherits_role_metadata_without_resolving_jobs(self):
        fast_records = load_character_catalog(ROOT)
        cast_record = next(record for record in fast_records if record.job_id == "cast_001")
        self.assertNotEqual("unknown", cast_record.role)

    def test_invalid_json_remains_visible_and_searchable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "characters" / "broken" / "bad_job.json"
            path.parent.mkdir(parents=True)
            path.write_text("{not json", encoding="utf-8")
            records = load_character_catalog(root)
        self.assertEqual(1, len(records))
        self.assertFalse(records[0].valid)
        self.assertEqual("INVALID  \u2022  bad_job", records[0].label)
        self.assertEqual(records, filter_character_catalog(records, "bad_job"))


if __name__ == "__main__":
    unittest.main()
