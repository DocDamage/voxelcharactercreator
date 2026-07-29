from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vcf_core.editing import JobEditor, duplicate_variant
from vcf_core.jobs import load_job
from vcf_core.operator import BuildCache, BuildQueue, PreflightReport, STAGES, SingleInstanceLock, atomic_write_json, run_preflight


ROOT = Path(__file__).resolve().parents[1]


class QueueTests(unittest.TestCase):
    def test_single_instance_lock_excludes_a_second_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "app.lock"
            first = SingleInstanceLock(path)
            second = SingleInstanceLock(path)
            first.acquire()
            try:
                with self.assertRaisesRegex(RuntimeError, "already using"):
                    second.acquire()
            finally:
                first.release()
            second.acquire()
            second.release()

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

    def test_add_many_persists_once_and_add_remains_compatible(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            queue = BuildQueue(path)
            with patch.object(queue, "_save", wraps=queue._save) as save:
                added = queue.add_many(Path(f"job-{index}.json") for index in range(3))
                self.assertEqual(1, save.call_count)
            self.assertEqual(3, len(added))
            self.assertEqual(added, queue.items)
            self.assertEqual([item.job_path for item in added], ["job-0.json", "job-1.json", "job-2.json"])
            self.assertEqual(3, len(json.loads(path.read_text(encoding="utf-8"))["items"]))
            with patch.object(queue, "_save", wraps=queue._save) as save:
                single = queue.add(Path("single.json"))
                self.assertEqual(1, save.call_count)
            self.assertEqual("single.json", single.job_path)
            with patch.object(queue, "_save", wraps=queue._save) as save:
                self.assertEqual([], queue.add_many([]))
                save.assert_not_called()

    def test_add_many_rolls_back_memory_when_persistence_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            queue = BuildQueue(path)
            existing = queue.add(Path("existing.json"))
            persisted_before = path.read_bytes()
            with patch.object(queue, "_save", side_effect=OSError("disk unavailable")):
                with self.assertRaisesRegex(OSError, "disk unavailable"):
                    queue.add_many([Path("new-a.json"), Path("new-b.json")])
            self.assertEqual([existing.id], [item.id for item in queue.snapshot()])
            self.assertEqual(persisted_before, path.read_bytes())

    def test_corrupt_queue_is_quarantined_without_losing_original_bytes(self):
        malformed_payloads = {
            "invalid_json": b'{"items": [',
            "wrong_root": json.dumps([{"id": "a", "job_path": "a.json"}]).encode(),
            "future_schema": json.dumps({"schema_version": 2, "items": []}).encode(),
            "bad_status": json.dumps({"schema_version": 1, "items": [{"id": "a", "job_path": "a.json", "status": "unknown"}]}).encode(),
            "bad_stage": json.dumps({"schema_version": 1, "items": [{"id": "a", "job_path": "a.json", "stage": "unknown"}]}).encode(),
            "duplicate_ids": json.dumps({"schema_version": 1, "items": [{"id": "a", "job_path": "a.json"}, {"id": "a", "job_path": "b.json"}]}).encode(),
        }
        for name, original in malformed_payloads.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "queue.json"
                path.write_bytes(original)
                queue = BuildQueue(path)
                self.assertEqual([], queue.items)
                self.assertIsNotNone(queue.quarantined_path)
                self.assertEqual(original, queue.quarantined_path.read_bytes())
                self.assertEqual([], json.loads(path.read_text(encoding="utf-8"))["items"])
                self.assertEqual([queue.quarantined_path], list(path.parent.glob("queue.json.corrupt-*")))

    def test_all_queue_transitions_roll_back_when_persistence_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            queue = BuildQueue(Path(folder) / "queue.json")
            first, second = queue.add_many([Path("first.json"), Path("second.json")])

            with patch.object(queue, "_save", side_effect=OSError("read-only")):
                with self.assertRaises(OSError):
                    queue.update(first.id, status="failed", error="boom")
            self.assertEqual("pending", queue.snapshot()[0].status)

            with patch.object(queue, "_save", side_effect=OSError("read-only")):
                with self.assertRaises(OSError):
                    queue.claim_pending(1)
            self.assertEqual(["pending", "pending"], [item.status for item in queue.snapshot()])

            queue.update(first.id, status="failed", error="boom")
            with patch.object(queue, "_save", side_effect=OSError("read-only")):
                with self.assertRaises(OSError):
                    queue.resume()
            self.assertEqual("failed", queue.snapshot()[0].status)

            queue.update(second.id, status="running")
            self.assertEqual(2, queue.resume(include_inactive_workers=True))
            self.assertEqual(["pending", "pending"], [item.status for item in queue.snapshot()])

            with patch.object(queue, "_save", side_effect=OSError("read-only")):
                with self.assertRaises(OSError):
                    queue.cancel_pending("cancelled")
            self.assertEqual("pending", queue.snapshot()[1].status)

    def test_legacy_queue_without_schema_is_normalized(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            path.write_text(json.dumps({"items": [{"id": "legacy", "job_path": "job.json"}]}), encoding="utf-8")
            queue = BuildQueue(path)
            self.assertEqual("pending", queue.items[0].status)
            self.assertEqual(1, json.loads(path.read_text(encoding="utf-8"))["schema_version"])
            self.assertIsNone(queue.quarantined_path)

    def test_cancel_pending_and_snapshot_leave_running_work_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            queue = BuildQueue(path)
            for name in ("one", "two", "three"):
                queue.add(Path(f"{name}.json"))
            claimed = queue.claim_pending(1)
            self.assertEqual(2, queue.cancel_pending("Operator stopped queued work"))
            self.assertEqual(0, queue.cancel_pending("Nothing else remains"))
            counts = queue.status_counts()
            self.assertEqual(1, counts["running"])
            self.assertEqual(2, counts["cancelled"])
            self.assertEqual(0, counts["pending"])
            self.assertEqual("running", claimed[0].status)
            cancelled = [item for item in queue.snapshot() if item.status == "cancelled"]
            self.assertTrue(all(item.error == "Operator stopped queued work" for item in cancelled))
            detached = queue.snapshot()
            detached[0].status = "failed"
            self.assertEqual("running", queue.snapshot()[0].status)
            with self.assertRaises(ValueError):
                queue.cancel_pending("  ")
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(2, sum(item["status"] == "cancelled" for item in persisted["items"]))


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
            key = "a" * 64
            cache.put(key, {"promoted_output": "exports/missing"})
            self.assertIsNone(cache.get(key))

    def test_cache_verifies_gate_output_containment_and_artifact_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "exports" / "original" / "hero"
            output.mkdir(parents=True)
            artifact = output / "hero.glb"
            artifact.write_bytes(b"valid artifact")
            report = {
                "job": "original_hero",
                "status": "complete",
                "promoted_output": "exports/original/hero",
                "blocking_checks": {
                    "passed": True,
                    "required": ["artifact_completeness"],
                    "missing": [],
                    "failed": [],
                },
                "artifacts": [
                    {
                        "name": artifact.name,
                        "size_bytes": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
            cache = BuildCache(root)
            key = "b" * 64
            cache.put(key, report)
            (output / "original_hero_report.json").write_text("{}\n", encoding="utf-8")
            self.assertIsNotNone(cache.get(key))
            artifact.write_bytes(b"replaced by another build")
            self.assertIsNone(cache.get(key))

            artifact.write_bytes(b"valid artifact")
            (output / "stale.fbx").write_bytes(b"stale output from another build")
            self.assertIsNone(cache.get(key))

            traversal_key = "c" * 64
            report["promoted_output"] = "../outside"
            cache.put(traversal_key, report)
            self.assertIsNone(cache.get(traversal_key))


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

    def test_compact_variant_can_override_source_using_inherited_body_template(self):
        path = ROOT / "characters" / "ff7" / "cloud.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        resolved_source = load_job(path, ROOT)["source"]
        updated = JobEditor(raw, ROOT).apply({"source": resolved_source})
        self.assertEqual(resolved_source, updated["source"])
        self.assertEqual("original_heavy_sword_hero", updated["variant_of"])
        self.assertNotIn("body_template", updated)
        self.assertNotIn("rig_template", updated)


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
