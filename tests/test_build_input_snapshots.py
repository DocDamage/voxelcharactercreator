from __future__ import annotations

import tempfile
import unittest
import os
import json
import subprocess
import sys
from pathlib import Path

from vcf_core.operator import BuildCache
from vcf_core.snapshots import (
    create_build_input_snapshot,
    lease_build_input_snapshot,
    live_build_input_snapshot_pids,
    prune_stale_build_input_snapshots,
    release_build_input_snapshot_lease,
    remove_build_input_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


class BuildInputSnapshotTests(unittest.TestCase):
    def test_snapshot_preserves_the_complete_build_fingerprint(self) -> None:
        job = ROOT / "characters" / "original" / "heavy_sword_hero.json"
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "snapshots"
            snapshot = create_build_input_snapshot(ROOT, [job], parent)
            snapshot_job = snapshot.job_path(job)
            self.assertTrue(snapshot_job.is_file())
            self.assertTrue((snapshot.root / "blender_worker" / "process_character.py").is_file())
            self.assertEqual(
                BuildCache(ROOT).key(job, {}),
                BuildCache(snapshot.root).key(snapshot_job, {}),
            )
            remove_build_input_snapshot(snapshot.root, parent)
            self.assertFalse(snapshot.root.exists())

    def test_cleanup_rejects_paths_outside_the_snapshot_parent(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                remove_build_input_snapshot(root, root / "snapshots")

    def test_snapshot_rejects_jobs_outside_characters_before_publishing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "snapshots"
            with self.assertRaises(ValueError):
                create_build_input_snapshot(ROOT, [ROOT / "README.md"], parent)
            self.assertFalse(parent.exists())

    def test_cleanup_requires_an_owned_uuid_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "snapshots"
            unowned = parent / ("a" * 32)
            unowned.mkdir(parents=True)
            with self.assertRaises(ValueError):
                remove_build_input_snapshot(unowned, parent)
            self.assertTrue(unowned.is_dir())

    def test_prune_removes_only_stale_owned_snapshots(self) -> None:
        job = ROOT / "characters" / "original" / "heavy_sword_hero.json"
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "snapshots"
            snapshot = create_build_input_snapshot(ROOT, [job], parent)
            unowned = parent / ("f" * 32)
            unowned.mkdir()
            os.utime(snapshot.root, (0, 0))
            os.utime(unowned, (0, 0))
            # The creator lease prevents a second app instance from pruning a
            # snapshot whose batch is still active, regardless of directory age.
            self.assertEqual([], prune_stale_build_input_snapshots(parent, max_age_seconds=1))
            release_build_input_snapshot_lease(snapshot.root)
            os.utime(snapshot.root, (0, 0))
            removed = prune_stale_build_input_snapshots(parent, max_age_seconds=1)
            self.assertEqual([snapshot.root], removed)
            self.assertTrue(unowned.is_dir())

    def test_independent_worker_lease_protects_snapshot_after_owner_release(self) -> None:
        job = ROOT / "characters" / "original" / "heavy_sword_hero.json"
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "snapshots"
            snapshot = create_build_input_snapshot(ROOT, [job], parent)
            release_build_input_snapshot_lease(snapshot.root)
            lease_build_input_snapshot(snapshot.root, os.getpid())
            os.utime(snapshot.root, (0, 0))
            self.assertEqual([], prune_stale_build_input_snapshots(parent, max_age_seconds=1))
            release_build_input_snapshot_lease(snapshot.root, os.getpid())
            os.utime(snapshot.root, (0, 0))
            self.assertEqual(
                [snapshot.root],
                prune_stale_build_input_snapshots(parent, max_age_seconds=1),
            )

    def test_explicit_cleanup_refuses_a_live_worker_lease(self) -> None:
        job = ROOT / "characters" / "original" / "heavy_sword_hero.json"
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "snapshots"
            snapshot = create_build_input_snapshot(ROOT, [job], parent)
            process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                lease_build_input_snapshot(snapshot.root, process.pid)
                with self.assertRaisesRegex(RuntimeError, "active worker"):
                    remove_build_input_snapshot(snapshot.root, parent)
            finally:
                process.terminate()
                process.wait(timeout=5)
                release_build_input_snapshot_lease(snapshot.root, process.pid)
            remove_build_input_snapshot(snapshot.root, parent)

    def test_reused_pid_does_not_keep_a_snapshot_alive(self) -> None:
        job = ROOT / "characters" / "original" / "heavy_sword_hero.json"
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "snapshots"
            snapshot = create_build_input_snapshot(ROOT, [job], parent)
            lease = next(snapshot.root.glob(".vcf-build-input-lease-*"))
            identity = json.loads(lease.read_text(encoding="utf-8"))
            identity["creation_token"] = "definitely-not-this-process"
            lease.write_text(json.dumps(identity), encoding="utf-8")
            self.assertEqual(set(), live_build_input_snapshot_pids(parent))
            os.utime(snapshot.root, (0, 0))
            self.assertEqual(
                [snapshot.root],
                prune_stale_build_input_snapshots(parent, max_age_seconds=1),
            )


if __name__ == "__main__":
    unittest.main()
