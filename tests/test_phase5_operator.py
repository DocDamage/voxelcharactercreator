from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vcf_core.editing import JobEditor, duplicate_variant
from vcf_core.operator import BuildCache, BuildQueue, PreflightReport, STAGES, atomic_write_json, run_preflight


ROOT = Path(__file__).resolve().parents[1]


class QueueTests(unittest.TestCase):
    def test_queue_persists_stage_retry_and_resumes_interrupted_items(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            queue = BuildQueue(path)
            item = queue.add(ROOT / "characters/original/heavy_sword_hero.json")
            queue.update(item.id, status="running", stage="rig")
            recovered = BuildQueue(path)
            self.assertEqual("interrupted", recovered.items[0].status)
            recovered.retry(item.id, "rig")
            self.assertEqual("rig", recovered.next_pending().retry_from_stage)

    def test_unknown_retry_stage_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            queue = BuildQueue(Path(folder) / "queue.json")
            item = queue.add(Path("job.json"))
            with self.assertRaises(ValueError): queue.retry(item.id, "made_up")


class CacheTests(unittest.TestCase):
    def test_cache_key_changes_with_tool_or_config_hash(self):
        cache = BuildCache(ROOT)
        job = ROOT / "characters/original/heavy_sword_hero.json"
        first = cache.key(job, {"blender": "4.5.5"})
        second = cache.key(job, {"blender": "4.6.0"})
        self.assertNotEqual(first, second)
        self.assertEqual(first, cache.key(job, {"blender": "4.5.5"}))

    def test_cache_requires_promoted_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); cache = BuildCache(root)
            cache.put("abc", {"promoted_output": "exports/missing"})
            self.assertIsNone(cache.get("abc"))


class EditingTests(unittest.TestCase):
    def test_job_edits_are_valid_undoable_and_atomic(self):
        source = ROOT / "characters/original/heavy_sword_hero.json"
        job = json.loads(source.read_text(encoding="utf-8"))
        editor = JobEditor(job, ROOT)
        editor.apply({"accent_colors": ["#112233"]})
        self.assertEqual(["#112233"], editor.value["accent_colors"])
        self.assertNotEqual(["#112233"], editor.undo()["accent_colors"])
        self.assertEqual(["#112233"], editor.redo()["accent_colors"])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "job.json"; editor.save(target)
            self.assertEqual(["#112233"], json.loads(target.read_text())["accent_colors"])

    def test_duplicate_records_variant_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "variant.json"
            value = duplicate_variant(ROOT / "characters/original/heavy_sword_hero.json", target,
                                      "original_heavy_sword_hero_blue", "Blue Hero", ROOT)
            self.assertEqual("original_heavy_sword_hero", value["variant_of"])


class PreflightTests(unittest.TestCase):
    @patch("vcf_core.operator._command_version", return_value=(True, "Blender 4.5.5"))
    def test_preflight_reports_optional_tools_and_validates_job(self, _version):
        settings = {"blender_path": __file__, "llm_provider": "none"}
        report = run_preflight(ROOT, settings, [ROOT / "characters/original/heavy_sword_hero.json"])
        self.assertIsInstance(report, PreflightReport)
        self.assertTrue(report.capabilities["blender"])
        self.assertTrue(any(issue.code == "PREFLIGHT_GODOT" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
