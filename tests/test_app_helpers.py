from __future__ import annotations

import tempfile
import unittest
import subprocess
import threading
import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.main import App, newest_existing, normalize_build_report


class AppHelperTests(unittest.TestCase):
    def test_non_object_and_malformed_report_sections_are_safe(self):
        non_object = normalize_build_report([])
        self.assertEqual("INVALID_REPORT", non_object["diagnostics"][0]["code"])

        malformed = normalize_build_report({"diagnostics": "bad", "stages": {}})
        self.assertEqual([], malformed["stages"])
        self.assertEqual("INVALID_REPORT_SECTIONS", malformed["diagnostics"][0]["code"])

    def test_artifact_sort_ignores_missing_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            older = root / "older.png"
            newer = root / "newer.png"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")
            older.touch()
            newer.touch()
            missing = root / "missing.png"
            results = newest_existing((missing, newer, older))
        self.assertEqual({newer, older}, set(results))

    def test_process_shutdown_escalates_from_terminate_to_kill(self):
        class StubbornProcess:
            def __init__(self) -> None:
                self.terminated = False
                self.killed = False

            def poll(self):
                return 0 if self.killed else None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                if not self.killed:
                    raise subprocess.TimeoutExpired("blender", timeout)
                return 0

            def kill(self):
                self.killed = True

        process = StubbornProcess()
        App._terminate_processes([("item", process)], wait=True)
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)

    def test_persistence_failure_does_not_skip_active_process_termination(self):
        class ActiveProcess:
            def poll(self):
                return None

        class FailingQueue:
            def cancel_pending(self, _reason):
                raise OSError("queue is read-only")

            def update(self, _item_id, **_values):
                raise OSError("queue is read-only")

        app = object.__new__(App)
        process = ActiveProcess()
        app.cancel_requested = threading.Event()
        app.worker_lock = threading.RLock()
        app.procs = {"active": process}
        app.cancelled_item_ids = set()
        app.build_queue = FailingQueue()

        with patch.object(App, "_terminate_processes") as terminate:
            active, pending, errors = App._request_build_cancellation(
                app,
                pending_reason="cancel test",
                wait=True,
            )

        self.assertTrue(app.cancel_requested.is_set())
        self.assertEqual({"active"}, app.cancelled_item_ids)
        self.assertEqual((1, 0), (active, pending))
        self.assertEqual(2, len(errors))
        terminate.assert_called_once_with([("active", process)], wait=True)

    def test_start_does_not_duplicate_an_existing_pending_job(self):
        job = Path(__file__).resolve()

        class PendingQueue:
            def snapshot(self):
                return (SimpleNamespace(job_path=str(job), status="pending"),)

            def add_many(self, _jobs):
                raise AssertionError("existing pending job must not be enqueued twice")

        app = object.__new__(App)
        app.building = False
        app.llm_busy = False
        app.build_queue = PendingQueue()
        app._preflight_jobs = Mock(return_value=True)
        app._archive_preview = Mock()
        app._start_workers = Mock()
        app.bar = {}

        App.start(app, [job])

        app._preflight_jobs.assert_called_once_with([job])
        app._archive_preview.assert_not_called()
        app._start_workers.assert_called_once_with()

    def test_live_process_prevents_explicit_snapshot_discard(self):
        class ActiveProcess:
            def poll(self):
                return None

        app = object.__new__(App)
        snapshot = SimpleNamespace(root=Path("snapshot"))
        app.build_input_snapshot = snapshot
        app.worker_lock = threading.RLock()
        app.procs = {"active": ActiveProcess()}
        app._append_log = Mock()

        with patch("app.main.remove_build_input_snapshot") as remove:
            removed = App._discard_build_input_snapshot(app)

        self.assertFalse(removed)
        self.assertIs(snapshot, app.build_input_snapshot)
        remove.assert_not_called()

    def test_dead_worker_queue_state_is_recovered_as_interrupted(self):
        item = SimpleNamespace(
            id="orphan", job_path="character.json", status="running"
        )

        class RecoverableQueue:
            def snapshot(self):
                return (item,)

            def update(self, item_id, **values):
                self.updated = (item_id, values)

        app = object.__new__(App)
        app.worker_lock = threading.RLock()
        app.procs = {}
        app.build_queue = RecoverableQueue()

        messages = App._recover_inactive_queue_items(app)

        self.assertEqual("orphan", app.build_queue.updated[0])
        self.assertEqual("interrupted", app.build_queue.updated[1]["status"])
        self.assertEqual(1, len(messages))

    def test_finished_process_sweep_includes_previously_retained_workers(self):
        class FinishedProcess:
            pid = 12345

            def poll(self):
                return 0

        app = object.__new__(App)
        process = FinishedProcess()
        app.worker_lock = threading.RLock()
        app.procs = {"retained": process}
        app.build_input_snapshot = None

        released = App._release_finished_processes(app, [])

        self.assertEqual(1, released)
        self.assertEqual({}, app.procs)

    @patch("app.main.messagebox.showinfo")
    def test_idle_pending_queue_can_be_cancelled(self, showinfo):
        class PendingQueue:
            def status_counts(self):
                return {"pending": 2}

        app = object.__new__(App)
        app.building = False
        app.build_queue = PendingQueue()
        app.cancel_requested = threading.Event()
        app.events = queue.Queue()
        app._request_build_cancellation = Mock(return_value=(0, 2, []))
        app._discard_build_input_snapshot = Mock()
        app._update_queue_status = Mock()

        App.cancel_build(app)

        app._request_build_cancellation.assert_called_once()
        app._discard_build_input_snapshot.assert_called_once_with()
        app._update_queue_status.assert_called_once_with()
        showinfo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
