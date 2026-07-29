from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from app.services.job_validator import validate_job
    from app.services.llm_client import apply_patch, proposal_diff, run_ollama, run_openai
except ModuleNotFoundError:  # Support launching with ``python app/main.py``.
    from services.job_validator import validate_job
    from services.llm_client import apply_patch, proposal_diff, run_ollama, run_openai
from vcf_core.assets import load_registry
from vcf_core.editing import JobEditor, duplicate_variant
from vcf_core.operator import BuildQueue, STAGES, SingleInstanceLock, atomic_write_json, run_preflight
from vcf_core.factory import measured_parallelism
from vcf_core.jobs import load_job, resolve_job
from vcf_core.viewer import AnimationPlayerError, launch_player
from vcf_core.snapshots import (
    BuildInputSnapshot,
    create_build_input_snapshot,
    lease_build_input_snapshot,
    live_build_input_snapshot_pids,
    prune_stale_build_input_snapshots,
    release_build_input_snapshot_lease,
    remove_build_input_snapshot,
)
from app.advanced_editor import AdvancedCharacterEditor
from app.catalog import (
    CharacterRecord,
    catalog_games,
    filter_character_catalog,
    load_character_catalog,
    load_character_record,
)
from vcf_core.editor3d import run_editor


DEFAULT_SETTINGS_FILE = ROOT / "config" / "settings.json"
BUILD_SNAPSHOT_PARENT = ROOT / "exports" / ".queue" / "snapshots"


def _user_settings_path() -> Path:
    override = os.environ.get("VCF_SETTINGS_PATH")
    if override:
        return Path(override)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "VoxelCharacterFactory" / "settings.json"


SETTINGS = _user_settings_path()
DEFAULT_SETTINGS: dict[str, Any] = {
    "blender_path": "",
    "godot_path": "",
    "render_resolution": 768,
    "llm_provider": "none",
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen2.5-coder:7b",
    "openai_base_url": "https://api.openai.com/v1",
    "openai_model": "gpt-5-mini",
    "cache_enabled": True,
    "performance_metrics": [],
    "available_memory_gb": None,
}


def normalize_settings(value: object) -> dict[str, Any]:
    """Return type-safe settings while preserving forward-compatible keys."""

    incoming = value if isinstance(value, dict) else {}
    result = {**DEFAULT_SETTINGS, **incoming}
    for key in (
        "blender_path",
        "godot_path",
        "ollama_base_url",
        "ollama_model",
        "openai_base_url",
        "openai_model",
    ):
        if not isinstance(result.get(key), str):
            result[key] = DEFAULT_SETTINGS[key]
    provider = result.get("llm_provider")
    if not isinstance(provider, str) or provider not in {"none", "ollama", "openai"}:
        result["llm_provider"] = "none"
    if not isinstance(result.get("cache_enabled"), bool):
        result["cache_enabled"] = True
    resolution = result.get("render_resolution")
    if isinstance(resolution, bool) or not isinstance(resolution, int) or not 64 <= resolution <= 4096:
        result["render_resolution"] = DEFAULT_SETTINGS["render_resolution"]
    metrics = result.get("performance_metrics")
    result["performance_metrics"] = (
        [item for item in metrics if isinstance(item, dict)]
        if isinstance(metrics, list)
        else []
    )
    memory = result.get("available_memory_gb")
    if (
        isinstance(memory, bool)
        or not isinstance(memory, (int, float))
        or not math.isfinite(float(memory))
        or memory <= 0
    ):
        result["available_memory_gb"] = None
    return result


def load_settings() -> dict:
    defaults = dict(DEFAULT_SETTINGS)
    try:
        tracked = json.loads(DEFAULT_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        tracked = {}
    if isinstance(tracked, dict):
        defaults.update(tracked)
    try:
        loaded = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return normalize_settings(defaults)
    if not isinstance(loaded, dict):
        return normalize_settings(defaults)
    return normalize_settings({**defaults, **loaded})


def save_settings(data: dict) -> None:
    atomic_write_json(SETTINGS, data)


def normalize_build_report(value: object) -> dict[str, Any]:
    """Normalize untrusted report JSON for safe dashboard rendering."""

    if not isinstance(value, dict):
        return {
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "INVALID_REPORT",
                    "message": "The build report root must be a JSON object.",
                    "corrective_action": "Rebuild the character to regenerate the report.",
                }
            ],
            "stages": [],
        }
    report = dict(value)
    diagnostics = report.get("diagnostics", [])
    stages = report.get("stages", [])
    report["diagnostics"] = (
        [item for item in diagnostics if isinstance(item, dict)]
        if isinstance(diagnostics, list)
        else []
    )
    report["stages"] = (
        [item for item in stages if isinstance(item, dict)]
        if isinstance(stages, list)
        else []
    )
    if not isinstance(diagnostics, list) or not isinstance(stages, list):
        report["diagnostics"].append(
            {
                "severity": "error",
                "code": "INVALID_REPORT_SECTIONS",
                "message": "The report diagnostics or stages section is malformed.",
                "corrective_action": "Rebuild the character to regenerate the report.",
            }
        )
    return report


def newest_existing(paths) -> list[Path]:
    """Sort existing artifacts newest-first while tolerating filesystem races."""

    records: list[tuple[float, Path]] = []
    for path in paths:
        try:
            records.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return [path for _mtime, path in sorted(records, key=lambda item: item[0], reverse=True)]


def detect_blender() -> str:
    base = Path(r"C:\Program Files\Blender Foundation")
    candidates: list[str | None] = []
    if base.exists():
        def version(path: Path) -> tuple[int, ...]:
            numbers = re.findall(r"\d+", path.parent.name)
            return tuple(map(int, numbers))

        candidates.extend(str(path) for path in sorted(base.glob("Blender */blender.exe"), key=version, reverse=True))
    candidates.append(shutil.which("blender"))
    return next((str(Path(path)) for path in candidates if path and Path(path).is_file()), "")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Voxel Character Factory")
        self.geometry("1280x820")
        self.minsize(1000, 650)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.instance_lock = SingleInstanceLock(
            ROOT / "exports" / ".queue" / "app.lock"
        )
        try:
            self.instance_lock.acquire()
        except RuntimeError as exc:
            self.withdraw()
            messagebox.showerror("Project already open", str(exc), parent=self)
            self.destroy()
            raise SystemExit(2) from exc
        orphaned_workers = live_build_input_snapshot_pids(BUILD_SNAPSHOT_PARENT) - {
            os.getpid()
        }
        if orphaned_workers:
            self.instance_lock.release()
            rendered = ", ".join(str(pid) for pid in sorted(orphaned_workers))
            self.withdraw()
            messagebox.showerror(
                "Previous build still running",
                "Blender worker process(es) from a previous app session still own "
                f"immutable build inputs: {rendered}. Stop them before reopening the project.",
                parent=self,
            )
            self.destroy()
            raise SystemExit(2)

        self.settings = load_settings()
        self.settings["blender_path"] = self.settings.get("blender_path") or detect_blender()
        self.catalog = load_character_catalog(ROOT)
        self.visible_records: list[CharacterRecord] = list(self.catalog)
        self.jobs = [record.path for record in self.catalog]
        self.current_job_path: Path | None = None
        self.current_file_snapshot: bytes | None = None
        self._selection_guard = False
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.build_queue = BuildQueue(ROOT / "exports" / ".queue" / "queue.json")
        self.procs: dict[str, subprocess.Popen[str]] = {}
        self.worker_lock = threading.RLock()
        self.cancel_requested = threading.Event()
        self.cancelled_item_ids: set[str] = set()
        self.workers_remaining = 0
        self.worker_errors: list[str] = []
        self.building = False
        self.llm_busy = False
        self.build_input_snapshot: BuildInputSnapshot | None = None
        self.build_settings: dict[str, Any] = deepcopy(self.settings)
        self.worker_threads: list[threading.Thread] = []
        self.active_editor_paths: set[Path] = set()

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        left = ttk.Frame(self, padding=12)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        ttk.Label(left, text="Character Library", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        search_row = ttk.Frame(left)
        search_row.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        search_row.columnconfigure(0, weight=1)
        self.search_value = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_value)
        self.search_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(search_row, text="Clear", command=lambda: self.search_value.set("")).grid(
            row=0, column=1, padx=(6, 0)
        )

        filter_row = ttk.Frame(left)
        filter_row.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        filter_row.columnconfigure(0, weight=1)
        self.game_filter = tk.StringVar(value="All")
        self.game_combo = ttk.Combobox(
            filter_row,
            textvariable=self.game_filter,
            values=catalog_games(self.catalog),
            state="readonly",
            width=12,
        )
        self.game_combo.grid(row=0, column=0, sticky="w")
        self.catalog_count = ttk.Label(filter_row)
        self.catalog_count.grid(row=0, column=1, sticky="e")

        list_frame = ttk.Frame(left)
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.list = tk.Listbox(list_frame, width=34, height=16, exportselection=False)
        self.list.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.list.configure(yscrollcommand=list_scroll.set)
        self.list.bind("<<ListboxSelect>>", self._on_job_selected)

        def add_actions(row: int, title: str, actions: list[tuple[str, Any]]) -> None:
            group = ttk.LabelFrame(left, text=title, padding=6)
            group.grid(row=row, column=0, sticky="ew", pady=(8, 0))
            group.columnconfigure((0, 1), weight=1)
            for index, (label, command) in enumerate(actions):
                ttk.Button(group, text=label, command=command).grid(
                    row=index // 2,
                    column=index % 2,
                    sticky="ew",
                    padx=(0 if index % 2 == 0 else 3, 3 if index % 2 == 0 else 0),
                    pady=2,
                )

        add_actions(4, "Production", [
            ("Build Selected", self.build_one),
            ("Build All\u2026", self.build_all),
            ("Cancel", self.cancel_build),
            ("Preflight", self.show_preflight),
            ("Retry Failed", self.retry_failed),
            ("Resume Queue", self.resume_batch),
        ])
        add_actions(5, "Editing", [
            ("Assets", self.edit_assets),
            ("Overrides", self.edit_overrides),
            ("3D Editor", self.open_3d_editor),
            ("Duplicate", self.duplicate_selected),
        ])
        add_actions(6, "Review & Tools", [
            ("Results", self.browse_results),
            ("Describe", self.describe_changes),
            ("Open Exports", self.open_exports),
            ("Settings", self.open_settings),
        ])

        main = ttk.Frame(self, padding=12)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.job_title = ttk.Label(header, text="Character Job", font=("Segoe UI", 16, "bold"))
        self.job_title.grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Validate", command=self.validate_editor).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(header, text="Save", command=self.save_job).grid(row=0, column=2, padx=(8, 0))
        self.job_path_label = ttk.Label(header, text="No character selected")
        self.job_path_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        editor_frame = ttk.Frame(main)
        editor_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)
        self.editor = tk.Text(editor_frame, wrap="none", font=("Consolas", 10), undo=True)
        self.editor.grid(row=0, column=0, sticky="nsew")
        editor_y = ttk.Scrollbar(editor_frame, orient="vertical", command=self.editor.yview)
        editor_y.grid(row=0, column=1, sticky="ns")
        editor_x = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.editor.xview)
        editor_x.grid(row=1, column=0, sticky="ew")
        self.editor.configure(yscrollcommand=editor_y.set, xscrollcommand=editor_x.set)
        self.editor.bind("<<Modified>>", self._editor_modified)

        box = ttk.LabelFrame(main, text="Build Log", padding=8)
        box.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.log = tk.Text(box, height=11, bg="#111", fg="#eee", insertbackground="white", font=("Consolas", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(box, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set, state="disabled")
        self.stage_label = ttk.Label(box, text="Ready")
        self.stage_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(box, text="Clear Log", command=self.clear_log).grid(row=1, column=1, sticky="e", pady=(8, 0))
        self.bar = ttk.Progressbar(box, mode="determinate", maximum=len(STAGES))
        self.bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        self.search_value.trace_add("write", lambda *_args: self._refresh_catalog())
        self.game_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_catalog())
        self.bind("<Control-s>", self._shortcut_save)
        self.bind("<Control-f>", self._shortcut_find)
        self.bind("<F5>", self._shortcut_validate)
        self._refresh_catalog()
        if self.visible_records:
            self._select_catalog_path(self.visible_records[0].path)
            self._load_job(self.visible_records[0].path)
        self._update_queue_status()
        if self.build_queue.quarantined_path is not None:
            self._append_log(
                "Recovered from an invalid build queue. The original was preserved at "
                f"{self.build_queue.quarantined_path}.\n"
            )
        try:
            removed_snapshots = prune_stale_build_input_snapshots(BUILD_SNAPSHOT_PARENT)
            if removed_snapshots:
                self._append_log(
                    f"Removed {len(removed_snapshots)} stale build-input snapshot(s).\n"
                )
        except (OSError, ValueError) as exc:
            self._append_log(f"Could not prune stale build-input snapshots: {exc}\n")
        self.after(100, self.drain_events)

    def _listed_record(self) -> CharacterRecord | None:
        selection = self.list.curselection()
        if not selection or selection[0] >= len(self.visible_records):
            return None
        return self.visible_records[selection[0]]

    def selected(self) -> Path | None:
        """Return the document currently open in the editor."""

        return self.current_job_path

    def _select_catalog_path(self, path: Path | None) -> None:
        self._selection_guard = True
        try:
            self.list.selection_clear(0, tk.END)
            if path is None:
                return
            for index, record in enumerate(self.visible_records):
                if record.path == path:
                    self.list.selection_set(index)
                    self.list.activate(index)
                    self.list.see(index)
                    break
        finally:
            self._selection_guard = False

    def _refresh_catalog(self) -> None:
        self.visible_records = filter_character_catalog(
            self.catalog, self.search_value.get(), self.game_filter.get()
        )
        self.list.delete(0, tk.END)
        for record in self.visible_records:
            self.list.insert(tk.END, record.label)
        self.catalog_count.configure(text=f"{len(self.visible_records)} of {len(self.catalog)}")
        self.game_combo.configure(values=catalog_games(self.catalog))
        self._select_catalog_path(self.current_job_path)

    def _update_catalog_record(self, path: Path) -> None:
        record = load_character_record(path, ROOT)
        self.catalog = [item for item in self.catalog if item.path != path]
        self.catalog.append(record)
        self.catalog.sort(key=lambda item: item.path)
        self.jobs = [item.path for item in self.catalog]
        self._refresh_catalog()

    def _on_job_selected(self, _event=None) -> None:
        if self._selection_guard:
            return
        record = self._listed_record()
        if record is None or record.path == self.current_job_path:
            return
        previous = self.current_job_path
        if not self._confirm_editor_transition():
            self._select_catalog_path(previous)
            return
        self._load_job(record.path)

    def _confirm_editor_transition(self) -> bool:
        if self.current_job_path is None or not self.editor.edit_modified():
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved job changes",
            f"Save changes to {self.current_job_path.name} before continuing?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return self.save_job(notify=False)
        return True

    def _load_job(self, path: Path) -> None:
        try:
            snapshot = path.read_bytes()
            content = snapshot.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            messagebox.showerror("Could not open job", str(exc), parent=self)
            self._select_catalog_path(self.current_job_path)
            return
        self.current_job_path = path
        self.current_file_snapshot = snapshot
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", content)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self._select_catalog_path(path)
        self._update_document_status()

    def show_job(self, path: Path | None = None) -> None:
        """Refresh an externally edited job without replacing another document."""

        path = path or self.current_job_path
        if path is None:
            return
        self._update_catalog_record(path)
        if path != self.current_job_path:
            return
        if self.editor.edit_modified():
            messagebox.showwarning(
                "Job updated externally",
                "The 3D editor saved this job, but the main editor also has unsaved changes. "
                "Its buffer was kept; reload and merge the on-disk changes before saving.",
                parent=self,
            )
            self._update_document_status()
            return
        self._load_job(path)

    def _editor_modified(self, _event=None) -> None:
        self._update_document_status()

    def _update_document_status(self) -> None:
        record = next(
            (item for item in self.catalog if item.path == self.current_job_path), None
        )
        if record is None:
            self.job_title.configure(text="Character Job")
            self.job_path_label.configure(text="No character selected")
            return
        suffix = " *" if self.editor.edit_modified() else ""
        self.job_title.configure(text=f"{record.name}{suffix}")
        details = str(record.path.relative_to(ROOT))
        if record.variant_of:
            details += f"  \u2022  inherits {record.variant_of}"
        if not record.valid:
            details += f"  \u2022  INVALID: {record.error.splitlines()[0]}"
        self.job_path_label.configure(text=details)

    def _shortcut_save(self, _event=None) -> str:
        self.save_job()
        return "break"

    def _shortcut_find(self, _event=None) -> str:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def _shortcut_validate(self, _event=None) -> str:
        self.validate_editor()
        return "break"

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", tk.END)
        self.log.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def _update_queue_status(self, activity: str | None = None) -> None:
        counts = self.build_queue.status_counts()
        active = sum(counts[state] for state in ("pending", "running", "cancelling"))
        recoverable = sum(counts[state] for state in ("failed", "cancelled", "interrupted"))
        prefix = activity or ("Building" if self.building else "Ready")
        details = []
        if active:
            details.append(f"{active} active")
        if recoverable:
            details.append(f"{recoverable} recoverable")
        self.stage_label.configure(text=" \u2022 ".join((prefix, *details)))

    def validate_editor(self) -> bool:
        if self.current_job_path is None:
            return False
        try:
            raw = self.editor_job()
            resolved = resolve_job(raw, ROOT)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Validation failed", str(exc), parent=self)
            return False
        inherited = f"\nInherited from: {raw['variant_of']}" if raw.get("variant_of") else ""
        messagebox.showinfo(
            "Job is valid",
            f"{resolved.get('name', self.current_job_path.stem)}\n"
            f"ID: {resolved.get('id', '?')}\nSchema: Job v{resolved.get('schema_version', '?')}"
            f"{inherited}",
            parent=self,
        )
        return True

    def _save_current_document(
        self, path: Path, job: dict[str, Any], *, parent: tk.Misc
    ) -> bool:
        if path != self.current_job_path or self.current_file_snapshot is None:
            messagebox.showerror(
                "Save refused",
                "The open-document state no longer matches this job. Reload it before saving.",
                parent=parent,
            )
            return False
        try:
            current = path.read_bytes()
        except OSError as exc:
            messagebox.showerror("Save refused", f"Could not re-read the job:\n{exc}", parent=parent)
            return False
        if current != self.current_file_snapshot:
            messagebox.showerror(
                "Job changed on disk",
                "This job was modified outside the main editor after it was opened. "
                "Your changes were not saved. Reload the job and merge the newer changes first.",
                parent=parent,
            )
            return False
        try:
            atomic_write_json(path, job)
            self.current_file_snapshot = path.read_bytes()
        except OSError as exc:
            messagebox.showerror("Could not save job", str(exc), parent=parent)
            return False
        return True

    def editor_job(self) -> dict:
        job = json.loads(self.editor.get("1.0", tk.END))
        try:
            errors = validate_job(job, project_root=ROOT)
        except Exception as exc:
            raise ValueError(f"The job validator could not process this document: {exc}") from exc
        if errors:
            raise ValueError("\n".join(f"• {error}" for error in errors))
        return job

    def save_job(self, *, notify: bool = True) -> bool:
        path = self.current_job_path
        if not path:
            return False
        try:
            job = self.editor_job()
            if not self._save_current_document(path, job, parent=self):
                return False
            self.editor.edit_modified(False)
            self._update_catalog_record(path)
            self._update_document_status()
            if notify:
                messagebox.showinfo("Saved", job.get("name", path.stem))
            return True
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Invalid job", str(exc))
            return False

    def build_one(self) -> None:
        path = self.selected()
        if path and self.save_job(notify=False):
            self.start([path])

    def build_all(self) -> None:
        if self.current_job_path and not self.save_job(notify=False):
            return
        count = len(self.jobs)
        workers = measured_parallelism(
            self.settings.get("performance_metrics", []),
            memory_gb=self.settings.get("available_memory_gb"),
        )
        if not messagebox.askyesno(
            "Build the full catalog?",
            f"Queue all {count} character jobs using up to {workers} workers?\n\n"
            "This can take a long time. You can cancel safely and resume the queue later.",
            parent=self,
        ):
            return
        self.start(self.jobs)

    def _preflight_jobs(self, jobs: list[Path]) -> bool:
        jobs = list(dict.fromkeys(path.resolve() for path in jobs))
        self.settings["blender_path"] = self.settings.get("blender_path") or detect_blender()
        snapshot: BuildInputSnapshot | None = None
        try:
            snapshot = create_build_input_snapshot(ROOT, jobs, BUILD_SNAPSHOT_PARENT)
            snapshot_jobs = [snapshot.job_path(path) for path in jobs]
            preflight = run_preflight(
                snapshot.root,
                self.settings,
                snapshot_jobs,
                output_root=ROOT,
            )
        except Exception as exc:
            if snapshot is not None:
                try:
                    remove_build_input_snapshot(snapshot.root, BUILD_SNAPSHOT_PARENT)
                except (OSError, ValueError):
                    pass
            messagebox.showerror("Could not snapshot build inputs", str(exc), parent=self)
            return False
        if not preflight.ok:
            try:
                remove_build_input_snapshot(snapshot.root, BUILD_SNAPSHOT_PARENT)
            except (OSError, ValueError):
                pass
            messagebox.showerror(
                "Preflight blocked the build",
                "\n\n".join(
                    f"{issue.message}\nAction: {issue.corrective_action}"
                    for issue in preflight.issues
                    if issue.severity == "error"
                ),
                parent=self,
            )
            return False
        warnings = [issue for issue in preflight.issues if issue.severity == "warning"]
        if warnings:
            self._append_log(
                "\nPreflight warnings:\n"
                + "\n".join(
                    f"- {issue.component}: {issue.message} Action: {issue.corrective_action}"
                    for issue in warnings
                )
                + "\n"
            )
        try:
            save_settings(self.settings)
        except OSError as exc:
            try:
                remove_build_input_snapshot(snapshot.root, BUILD_SNAPSHOT_PARENT)
            except (OSError, ValueError):
                pass
            messagebox.showerror("Could not save settings", str(exc), parent=self)
            return False
        if not self._discard_build_input_snapshot():
            try:
                remove_build_input_snapshot(snapshot.root, BUILD_SNAPSHOT_PARENT)
            except (OSError, RuntimeError, ValueError):
                pass
            messagebox.showerror(
                "Previous build still owns its inputs",
                "A prior Blender process is still using its immutable input snapshot. "
                "Stop that worker before starting another batch.",
                parent=self,
            )
            return False
        self.build_input_snapshot = snapshot
        return True

    def _discard_build_input_snapshot(self) -> bool:
        snapshot = self.build_input_snapshot
        if snapshot is None:
            return True
        with self.worker_lock:
            live = [process for process in self.procs.values() if process.poll() is None]
        if live:
            self._append_log(
                "\nPreserved build-input snapshot because a Blender worker is still active.\n"
            )
            return False
        try:
            remove_build_input_snapshot(snapshot.root, BUILD_SNAPSHOT_PARENT)
        except (OSError, RuntimeError, ValueError) as exc:
            self._append_log(f"\nCould not remove build-input snapshot: {exc}\n")
            return False
        self.build_input_snapshot = None
        return True

    def start(self, jobs: list[Path]) -> None:
        if self.building:
            messagebox.showwarning("Busy", "A build is already running.")
            return
        if self.llm_busy:
            messagebox.showwarning(
                "Busy", "Wait for the active LLM proposal to finish before building.", parent=self
            )
            return
        jobs = list(dict.fromkeys(path.resolve() for path in jobs))
        existing_pending = {
            Path(item.job_path).resolve()
            for item in self.build_queue.snapshot()
            if item.status == "pending"
        }
        new_jobs = [path for path in jobs if path not in existing_pending]
        prepared_jobs = sorted(existing_pending | set(new_jobs))
        if not prepared_jobs or not self._preflight_jobs(prepared_jobs):
            return
        for path in new_jobs:
            self._archive_preview(path)
        try:
            if new_jobs:
                self.build_queue.add_many(new_jobs)
        except Exception as exc:
            self._discard_build_input_snapshot()
            messagebox.showerror("Could not enqueue builds", str(exc), parent=self)
            return
        self.building = True
        self.bar["value"] = 0
        self._start_workers()

    def _start_workers(self) -> None:
        pending = self.build_queue.status_counts().get("pending", 0)
        if not pending:
            self.building = False
            self._discard_build_input_snapshot()
            self._update_queue_status()
            return
        pending_paths = {
            Path(item.job_path).resolve()
            for item in self.build_queue.snapshot()
            if item.status == "pending"
        }
        snapshot = self.build_input_snapshot
        missing_snapshots = sorted(
            path
            for path in pending_paths
            if snapshot is None
            or path.resolve() not in snapshot.jobs
        )
        if missing_snapshots:
            self.building = False
            self._discard_build_input_snapshot()
            messagebox.showerror(
                "Queue inputs were not verified",
                "These queued jobs must pass preflight again before launch:\n"
                + "\n".join(str(path) for path in missing_snapshots),
                parent=self,
            )
            self._update_queue_status()
            return
        self.build_settings = deepcopy(self.settings)
        worker_count = min(pending, measured_parallelism(
            self.build_settings.get("performance_metrics", []),
            memory_gb=self.build_settings.get("available_memory_gb"),
        ))
        with self.worker_lock:
            self.cancel_requested.clear()
            self.cancelled_item_ids.clear()
        self.workers_remaining = worker_count
        self.worker_errors = []
        self.worker_threads = []
        self.events.put(("log", f"\nStarting {worker_count} measured queue worker(s).\n"))
        for _index in range(worker_count):
            thread = threading.Thread(target=self.worker, daemon=True)
            self.worker_threads.append(thread)
            thread.start()

    def worker(self) -> None:
        try:
            while not self.cancel_requested.is_set():
                claimed = self.build_queue.claim_pending(1)
                if not claimed:
                    break
                item = claimed[0]
                path = Path(item.job_path).resolve()
                if self.cancel_requested.is_set():
                    with self.worker_lock:
                        self.cancelled_item_ids.add(item.id)
                    self.build_queue.update(
                        item.id,
                        status="cancelled",
                        error="Cancelled by operator before launch.",
                    )
                    break
                self.events.put(("log", f"\n=== {path.stem} ===\n"))
                process: subprocess.Popen[str] | None = None
                process_snapshot_root: Path | None = None
                try:
                    snapshot = self.build_input_snapshot
                    if snapshot is None:
                        raise RuntimeError("The immutable build-input snapshot is unavailable.")
                    snapshot_path = snapshot.job_path(path)
                    command = [
                        self.build_settings["blender_path"],
                        "--background",
                        "--python",
                        str(snapshot.root / "blender_worker" / "process_character.py"),
                        "--",
                        "--job",
                        str(snapshot_path),
                        "--project-root",
                        str(ROOT),
                        "--input-root",
                        str(snapshot.root),
                    ]
                    if item.retry_from_stage:
                        command.extend(["--retry-stage", item.retry_from_stage])
                    if not self.build_settings.get("cache_enabled", True):
                        command.append("--no-cache")
                    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    child_environment = os.environ.copy()
                    if self.build_settings.get("godot_path"):
                        child_environment["VCF_GODOT"] = self.build_settings["godot_path"]
                    launch_cancelled = False
                    with self.worker_lock:
                        if self.cancel_requested.is_set():
                            self.cancelled_item_ids.add(item.id)
                            launch_cancelled = True
                        else:
                            process = subprocess.Popen(
                                command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                cwd=ROOT,
                                creationflags=flags,
                                env=child_environment,
                            )
                            self.procs[item.id] = process
                            process_snapshot_root = snapshot.root
                            lease_build_input_snapshot(snapshot.root, process.pid)
                    if launch_cancelled:
                        self.build_queue.update(
                            item.id,
                            status="cancelled",
                            error="Cancelled by operator before launch.",
                        )
                        break
                    assert process is not None
                    if process.stdout:
                        for line in process.stdout:
                            if line.startswith("VCF_EVENT "):
                                try:
                                    event = json.loads(line[len("VCF_EVENT "):])
                                    if event.get("type") == "stage":
                                        stage = str(event.get("name"))
                                        self.build_queue.update(item.id, stage=stage)
                                        self.events.put(("stage", {"job": path.stem, "stage": stage}))
                                except (ValueError, KeyError, TypeError):
                                    pass
                            self.events.put(("log", f"[{path.stem}] {line}"))
                    code = process.wait()
                    current = next(
                        entry for entry in self.build_queue.snapshot() if entry.id == item.id
                    )
                    with self.worker_lock:
                        item_cancelled = item.id in self.cancelled_item_ids
                    if current.status in {"cancelling", "cancelled"} or item_cancelled:
                        self.build_queue.update(
                            item.id,
                            status="cancelled",
                            error="Cancelled by operator; no output was promoted.",
                        )
                    elif code:
                        error = f"Blender exited with code {code}"
                        self.build_queue.update(item.id, status="failed", error=error)
                        with self.worker_lock:
                            self.worker_errors.append(f"{path.name}: {error}")
                    else:
                        self.build_queue.update(item.id, status="complete", error=None)
                except Exception as exc:
                    with self.worker_lock:
                        item_cancelled = item.id in self.cancelled_item_ids
                    status = "cancelled" if item_cancelled else "failed"
                    error = (
                        "Cancelled by operator; no output was promoted."
                        if status == "cancelled"
                        else f"Worker failed: {exc}"
                    )
                    try:
                        self.build_queue.update(item.id, status=status, error=error)
                    except (OSError, ValueError, StopIteration):
                        pass
                    if status == "failed":
                        with self.worker_lock:
                            self.worker_errors.append(f"{path.name}: {error}")
                finally:
                    if process is not None and process.poll() is None:
                        self._terminate_processes([(item.id, process)], wait=True)
                    if (
                        process is not None
                        and process_snapshot_root is not None
                        and process.poll() is not None
                    ):
                        with self.worker_lock:
                            if self.procs.get(item.id) is process:
                                self.procs.pop(item.id, None)
                        try:
                            release_build_input_snapshot_lease(
                                process_snapshot_root, process.pid
                            )
                        except (OSError, ValueError):
                            pass
        except Exception as exc:
            with self.worker_lock:
                self.worker_errors.append(f"Queue worker failed: {exc}")
        finally:
            with self.worker_lock:
                self.workers_remaining -= 1
                last_worker = self.workers_remaining == 0
            if last_worker:
                recovery_messages = self._recover_inactive_queue_items()
                with self.worker_lock:
                    self.worker_errors.extend(recovery_messages)
                    errors = list(self.worker_errors)
                if self.cancel_requested.is_set():
                    self.events.put(("cancelled", "Build queue cancelled. Unfinished output was not promoted."))
                elif errors:
                    self.events.put(("failed", "\n".join(errors)))
                else:
                    self.events.put(("done", "Builds completed."))

    def _recover_inactive_queue_items(self) -> list[str]:
        """Make dead workers resumable after a terminal queue write failure."""

        with self.worker_lock:
            active_ids = {
                item_id
                for item_id, process in self.procs.items()
                if process.poll() is None
            }
        messages: list[str] = []
        for item in self.build_queue.snapshot():
            if item.status not in {"running", "cancelling"} or item.id in active_ids:
                continue
            message = (
                "The worker exited before its terminal queue state could be persisted. "
                "The item was recovered as interrupted and can be resumed."
            )
            try:
                self.build_queue.update(
                    item.id, status="interrupted", error=message
                )
            except Exception as exc:
                messages.append(
                    f"{Path(item.job_path).name}: queue recovery could not be saved ({exc}). "
                    "Restore write access to exports/.queue, then use Resume Batch or restart the app."
                )
            else:
                messages.append(f"{Path(item.job_path).name}: {message}")
        return messages

    @staticmethod
    def _terminate_processes(
        active: list[tuple[str, subprocess.Popen[str]]], *, wait: bool
    ) -> None:
        for _item_id, process in active:
            if process.poll() is None:
                try:
                    process.terminate()
                except (OSError, ProcessLookupError):
                    pass
        if not wait:
            return
        deadline = time.monotonic() + 3.0
        for _item_id, process in active:
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=max(0.05, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=1.0)
                except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
                    pass

    def _release_finished_processes(
        self, attempted: list[tuple[str, subprocess.Popen[str]]]
    ) -> int:
        snapshot = self.__dict__.get("build_input_snapshot")
        with self.worker_lock:
            candidates = dict(self.procs)
        candidates.update(dict(attempted))
        released = 0
        for item_id, process in candidates.items():
            if process.poll() is None:
                continue
            with self.worker_lock:
                if self.procs.get(item_id) is process:
                    self.procs.pop(item_id, None)
                    released += 1
            if snapshot is not None:
                try:
                    release_build_input_snapshot_lease(snapshot.root, process.pid)
                except (AttributeError, OSError, ValueError):
                    pass
        return released

    def _finish_process_termination(
        self, active: list[tuple[str, subprocess.Popen[str]]]
    ) -> None:
        self._terminate_processes(active, wait=True)
        self._release_finished_processes(active)
        with self.worker_lock:
            no_workers = self.workers_remaining == 0
            no_processes = not any(process.poll() is None for process in self.procs.values())
        if no_workers and no_processes:
            messages = self._recover_inactive_queue_items()
            if messages:
                self.events.put(("log", "\n" + "\n".join(messages) + "\n"))
            self.events.put(("shutdown_complete", "All Blender workers have stopped."))

    def _request_build_cancellation(
        self, *, pending_reason: str, wait: bool
    ) -> tuple[int, int, list[str]]:
        """Cancel queued/running work, always terminating children if persistence fails."""

        self.cancel_requested.set()
        errors: list[str] = []
        try:
            pending = self.build_queue.cancel_pending(pending_reason)
        except Exception as exc:
            pending = 0
            errors.append(f"Could not persist queued cancellation: {exc}")

        with self.worker_lock:
            active = [
                (item_id, process)
                for item_id, process in self.procs.items()
                if process.poll() is None
            ]
            self.cancelled_item_ids.update(item_id for item_id, _process in active)

        for item_id, _process in active:
            try:
                self.build_queue.update(item_id, status="cancelling")
            except Exception as exc:
                errors.append(f"Could not persist cancellation for {item_id}: {exc}")

        if wait:
            self._terminate_processes(active, wait=True)
            self._release_finished_processes(active)
        else:
            self._terminate_processes(active, wait=False)
            threading.Thread(
                target=self._finish_process_termination,
                args=(active,),
                daemon=True,
            ).start()
        return len(active), pending, errors

    def cancel_build(self) -> None:
        pending_count = self.build_queue.status_counts().get("pending", 0)
        if not self.building and not pending_count:
            messagebox.showinfo("Build queue", "No build is currently running.", parent=self)
            return
        was_building = self.building
        active, pending, errors = self._request_build_cancellation(
            pending_reason="Cancelled by operator before launch; no output was promoted.",
            wait=False,
        )
        self.events.put(
            ("log", f"\nCancellation requested for {active} active and {pending} queued build(s).\n")
        )
        if errors:
            self.events.put(("log", "\n" + "\n".join(errors) + "\n"))
            messagebox.showwarning(
                "Cancellation state not saved",
                "Build processes were stopped, but some queue status changes could not be saved:\n\n"
                + "\n".join(errors),
                parent=self,
            )
        if was_building:
            self._update_queue_status("Cancelling")
        else:
            self.cancel_requested.clear()
            self._discard_build_input_snapshot()
            self._update_queue_status()
            messagebox.showinfo(
                "Build queue", f"Cancelled {pending} queued build(s).", parent=self
            )

    def drain_events(self) -> None:
        released_processes = self._release_finished_processes([])
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "llm_error":
                    self._llm_failed(payload)
                    continue
                if kind == "llm_result":
                    self._review_llm_proposal(
                        payload["path"], payload["original"], payload["patch"]
                    )
                    continue
                if kind == "editor_done":
                    self._editor_finished(payload["path"], payload["result"])
                    continue
                if kind == "editor_error":
                    self._editor_failed(payload["path"], payload["error"])
                    continue
                if kind == "player_error":
                    messagebox.showerror("Animation player", str(payload), parent=self)
                    continue
                if kind == "shutdown_complete":
                    self.building = False
                    self.bar["value"] = 0
                    self._discard_build_input_snapshot()
                    self._append_log(f"\n{payload}\n")
                    self._update_queue_status()
                    continue
                if kind in {"done", "failed", "cancelled"}:
                    with self.worker_lock:
                        live_processes = any(
                            process.poll() is None for process in self.procs.values()
                        )
                    self.building = live_processes
                    self.bar["value"] = 0
                    if not live_processes:
                        self._discard_build_input_snapshot()
                    else:
                        self._append_log(
                            "\nA Blender process is still active; its input snapshot was preserved. "
                            "Use Cancel Build again or close the app to retry termination.\n"
                        )
                    if kind == "done":
                        messagebox.showinfo("Complete", str(payload), parent=self)
                    elif kind == "cancelled":
                        messagebox.showinfo("Cancelled", str(payload), parent=self)
                    else:
                        messagebox.showerror("Failed", str(payload), parent=self)
                    self._append_log(f"\n{kind.upper()}: {payload}\n")
                    self._update_queue_status()
                    continue
                elif kind == "stage":
                    stage = str(payload.get("stage", ""))
                    job = str(payload.get("job", "Character"))
                    self.bar["value"] = STAGES.index(stage) + 1 if stage in STAGES else 0
                    self._update_queue_status(f"{job}: {stage}")
                    continue
                self._append_log(str(payload))
        except queue.Empty:
            pass
        if released_processes:
            with self.worker_lock:
                fully_stopped = self.workers_remaining == 0 and not any(
                    process.poll() is None for process in self.procs.values()
                )
            if fully_stopped and self.building:
                messages = self._recover_inactive_queue_items()
                if messages:
                    self._append_log("\n" + "\n".join(messages) + "\n")
                self.building = False
                self.bar["value"] = 0
                self._discard_build_input_snapshot()
                self._update_queue_status()
        self.after(100, self.drain_events)

    def describe_changes(self) -> None:
        path = self.selected()
        if not path:
            return
        if self.llm_busy:
            messagebox.showinfo("LLM proposal", "A proposal is already being prepared.", parent=self)
            return
        if self.building:
            messagebox.showinfo(
                "Build running",
                "Wait for the active build or cancel it before requesting a proposal.",
                parent=self,
            )
            return
        provider = self.settings.get("llm_provider", "none")
        if provider == "none":
            messagebox.showinfo(
                "LLM disabled",
                "Choose Ollama or OpenAI-compatible in Settings first.",
                parent=self,
            )
            return
        prompt = simpledialog.askstring(
            "Describe Changes",
            "Describe what should change in this character job:",
            parent=self,
        )
        if not prompt:
            return
        try:
            job = self.editor_job()
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Invalid job", str(exc), parent=self)
            return

        self.llm_busy = True
        self.bar.configure(mode="indeterminate")
        self.bar.start(12)
        self._update_queue_status("Preparing LLM proposal\u2026")

        def request() -> None:
            try:
                if provider == "ollama":
                    proposal = run_ollama(
                        prompt,
                        self.settings["ollama_base_url"],
                        self.settings["ollama_model"],
                    )
                elif provider == "openai":
                    proposal = run_openai(
                        prompt,
                        self.settings["openai_base_url"],
                        self.settings["openai_model"],
                    )
                else:
                    raise ValueError(f"Unknown LLM provider: {provider}")
            except Exception as exc:
                self.events.put(("llm_error", exc))
                return
            self.events.put(
                (
                    "llm_result",
                    {"path": path, "original": job, "patch": proposal},
                )
            )

        threading.Thread(target=request, daemon=True).start()

    def _end_llm_request(self) -> None:
        self.llm_busy = False
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar["value"] = 0
        self._update_queue_status()

    def _llm_failed(self, error: Exception) -> None:
        self._end_llm_request()
        messagebox.showerror("LLM update failed", str(error), parent=self)

    def _review_llm_proposal(self, path: Path, original: dict, patch: dict) -> None:
        self._end_llm_request()
        if self.current_job_path != path:
            messagebox.showwarning(
                "Proposal is stale",
                "The selected character changed while the proposal was prepared. Request it again.",
                parent=self,
            )
            return
        try:
            if self.editor_job() != original:
                messagebox.showwarning(
                    "Proposal is stale",
                    "The job changed while the proposal was prepared. Review your edits and request it again.",
                    parent=self,
                )
                return
            updated = apply_patch(original, patch)
            errors = validate_job(updated, project_root=ROOT)
            if errors:
                raise ValueError("\n".join(errors))
            differences = proposal_diff(original, patch)
        except Exception as exc:
            messagebox.showerror("LLM proposal is invalid", str(exc), parent=self)
            return
        if not differences:
            messagebox.showinfo("No changes", "The proposal does not change this job.", parent=self)
            return

        window = tk.Toplevel(self)
        window.title("Review LLM Proposal")
        window.geometry("820x620")
        window.minsize(620, 420)
        window.transient(self)
        window.grab_set()
        ttk.Label(
            window,
            text="Review every validated field change before applying it.",
        ).pack(anchor="w", padx=12, pady=(12, 6))
        frame = ttk.Frame(window)
        frame.pack(fill="both", expand=True, padx=12)
        review = tk.Text(frame, wrap="word", font=("Consolas", 10))
        review.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=review.yview)
        scroll.pack(side="right", fill="y")
        review.configure(yscrollcommand=scroll.set)
        for item in differences:
            review.insert(
                tk.END,
                f"{item['field']}:\n  {item['before']}\n\u2192 {item['after']}\n\n",
            )
        review.configure(state="disabled")
        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=12, pady=12)
        ttk.Button(controls, text="Cancel", command=window.destroy).pack(side="right")

        def apply_proposal() -> None:
            if not self._save_current_document(path, updated, parent=window):
                return
            self._replace_editor(updated, saved=True)
            self._update_catalog_record(path)
            window.destroy()
            messagebox.showinfo(
                "Job updated",
                "The character job was updated and validated.",
                parent=self,
            )

        ttk.Button(
            controls,
            text="Apply Validated Changes",
            command=apply_proposal,
        ).pack(side="right", padx=(0, 8))

    def show_preflight(self) -> None:
        jobs = [self.selected()] if self.selected() else []
        report = run_preflight(ROOT, self.settings, [path for path in jobs if path])
        lines = [f"{name}: {value}" for name, value in sorted(report.versions.items())]
        lines.extend(f"[{issue.severity.upper()}] {issue.component}: {issue.message}\nAction: {issue.corrective_action}" for issue in report.issues)
        messagebox.showinfo("Preflight passed" if report.ok else "Preflight needs attention", "\n\n".join(lines) or "All required checks passed.")

    def retry_failed(self) -> None:
        if self.building:
            messagebox.showwarning("Busy", "Wait for the active build or cancel it first.", parent=self)
            return
        path = self.selected()
        candidates = [
            item
            for item in reversed(self.build_queue.snapshot())
            if item.status in {"failed", "cancelled", "interrupted"}
            and (not path or Path(item.job_path).resolve() == path.resolve())
        ]
        if not candidates:
            messagebox.showinfo("Nothing to retry", "No failed or interrupted build is available for this job.")
            return
        item = candidates[0]
        job_path = Path(item.job_path).resolve()
        pending_paths = [
            Path(entry.job_path).resolve()
            for entry in self.build_queue.snapshot()
            if entry.status == "pending"
        ]
        if not self._preflight_jobs(list(dict.fromkeys((*pending_paths, job_path)))):
            return
        stage = item.stage if item.stage in STAGES else None
        try:
            self.build_queue.retry(item.id, stage)
        except Exception as exc:
            self._discard_build_input_snapshot()
            messagebox.showerror("Could not retry build", str(exc), parent=self)
            return
        self.building = True
        self._start_workers()

    def resume_batch(self) -> None:
        if self.building:
            messagebox.showwarning("Busy", "A build is already running.", parent=self)
            return
        with self.worker_lock:
            if any(process.poll() is None for process in self.procs.values()):
                messagebox.showwarning(
                    "Worker still active",
                    "Stop the remaining Blender worker before resuming queue items.",
                    parent=self,
                )
                return
        resumable = [
            item
            for item in self.build_queue.snapshot()
            if item.status in {"failed", "cancelled", "interrupted", "running", "cancelling"}
        ]
        if not resumable:
            messagebox.showinfo("Queue", "No interrupted, failed, or cancelled items need resuming.")
            return
        jobs = sorted(
            {Path(item.job_path).resolve() for item in resumable}
            | {
                Path(item.job_path).resolve()
                for item in self.build_queue.snapshot()
                if item.status == "pending"
            }
        )
        if not self._preflight_jobs(jobs):
            return
        try:
            count = self.build_queue.resume(include_inactive_workers=True)
        except Exception as exc:
            self._discard_build_input_snapshot()
            messagebox.showerror("Could not resume queue", str(exc), parent=self)
            return
        if not count:
            self._discard_build_input_snapshot()
            messagebox.showinfo("Queue", "No interrupted, failed, or cancelled items need resuming.")
            return
        self.building = True
        self._start_workers()

    def _replace_editor(self, job: dict, *, saved: bool = False) -> None:
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", json.dumps(job, indent=2) + "\n")
        self.editor.edit_reset()
        self.editor.edit_modified(not saved)
        self._update_document_status()

    def edit_assets(self) -> None:
        path = self.selected()
        if not path:
            return
        try:
            raw = self.editor_job()
            resolved = resolve_job(raw, ROOT)
            registry = load_registry(ROOT)
        except Exception as exc:
            messagebox.showerror("Cannot edit assets", str(exc), parent=self)
            return
        window = tk.Toplevel(self)
        window.title("Asset & Equipment Editor")
        window.geometry("720x560")
        window.transient(self)
        window.grab_set()
        ttk.Label(window, text="Select compatible registry assets (Ctrl/Shift for multiple)").pack(anchor="w", padx=12, pady=(12, 4))
        list_frame = ttk.Frame(window)
        list_frame.pack(fill="both", expand=True, padx=12)
        listing = tk.Listbox(list_frame, selectmode=tk.EXTENDED, exportselection=False)
        listing.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listing.yview)
        scroll.pack(side="right", fill="y")
        listing.configure(yscrollcommand=scroll.set)
        manifests = sorted(
            (
                item
                for item in registry.manifests
                if resolved["body_template"] in item.compatible_bases
            ),
            key=lambda item: item.asset_id,
        )
        selected_ids = set(resolved.get("source", {}).get("asset_ids", []))
        for index, manifest in enumerate(manifests):
            listing.insert(tk.END, f"{manifest.asset_id}  ·  {manifest.kind}  ·  {', '.join(manifest.semantic_tags)}")
            if manifest.asset_id in selected_ids: listing.selection_set(index)
        ttk.Label(window, text="Equipment ID (blank removes equipment)").pack(anchor="w", padx=12, pady=(8, 2))
        equipment = tk.StringVar(value=resolved.get("weapon") or "")
        ttk.Entry(window, textvariable=equipment).pack(fill="x", padx=12)

        def apply_selection() -> None:
            try:
                chosen = [manifests[index].asset_id for index in listing.curselection()]
                equipment_value = equipment.get().strip() or None
                changes: dict[str, Any] = {}
                if chosen != resolved.get("source", {}).get("asset_ids", []):
                    changes["source"] = {"mode": "assembly", "asset_ids": chosen}
                if equipment_value != resolved.get("weapon"):
                    changes["weapon"] = equipment_value
                editor = JobEditor(raw, ROOT)
                updated = editor.apply(changes) if changes else editor.value
                if not self._save_current_document(path, updated, parent=window):
                    return
                self._replace_editor(updated, saved=True)
                self._update_catalog_record(path)
                window.destroy()
            except Exception as exc:
                messagebox.showerror("Invalid asset selection", str(exc), parent=window)

        ttk.Button(window, text="Apply validated selection", command=apply_selection).pack(anchor="e", padx=12, pady=12)

    def open_3d_editor(self) -> None:
        path = self.selected()
        if not path:
            return
        if path in self.active_editor_paths:
            messagebox.showinfo(
                "3D editor",
                f"An editor is already open for {path.name}.",
                parent=self,
            )
            return
        if self.editor.edit_modified() and not self.save_job(notify=False):
            return
        try:
            job = load_job(path, ROOT)
            glb = self._job_output(path) / f"{job['id']}.glb"
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("3D editor", str(exc), parent=self)
            return
        self.active_editor_paths.add(path)
        if not glb.is_file():
            try:
                editor_window = AdvancedCharacterEditor(
                    self,
                    path,
                    ROOT,
                    lambda edited_path=path: self.show_job(edited_path),
                    lambda edited_path=path: self.browse_results(edited_path),
                )
            except Exception as exc:
                self.active_editor_paths.discard(path)
                messagebox.showerror("3D editor", str(exc), parent=self)
                return
            try:
                exists = bool(editor_window.winfo_exists())
            except tk.TclError:
                exists = False
            if not exists:
                self.active_editor_paths.discard(path)
                return

            def release_editor(event, edited_path=path, window=editor_window) -> None:
                if event.widget is window:
                    self.active_editor_paths.discard(edited_path)

            editor_window.bind("<Destroy>", release_editor, add="+")
            return
        self._update_queue_status("Launching interactive Godot 3D editor\u2026")

        def edit() -> None:
            try:
                result = run_editor(
                    ROOT, path, glb, str(self.settings.get("godot_path", ""))
                )
                self.events.put(("editor_done", {"path": path, "result": result}))
            except Exception as exc:
                self.events.put(("editor_error", {"path": path, "error": exc}))

        threading.Thread(target=edit, daemon=True).start()

    def _editor_finished(self, path: Path, result: dict) -> None:
        self.active_editor_paths.discard(path)
        self._update_queue_status()
        if result.get("saved"):
            self.show_job(path)
            messagebox.showinfo(
                "3D editor",
                f"Saved {result['part_count']} part transforms and "
                f"{result['socket_count']} sockets.",
                parent=self,
            )

    def _editor_failed(self, path: Path, error: Exception) -> None:
        self.active_editor_paths.discard(path)
        self._update_queue_status()
        messagebox.showerror("3D editor", str(error), parent=self)

    def edit_overrides(self) -> None:
        path = self.selected()
        if not path:
            return
        try:
            raw = self.editor_job()
            resolved = resolve_job(raw, ROOT)
        except Exception as exc:
            messagebox.showerror("Cannot edit overrides", str(exc), parent=self)
            return
        window = tk.Toplevel(self); window.title("Part & Palette Overrides"); window.geometry("700x560"); window.transient(self); window.grab_set()
        ttk.Label(window, text="Part mappings (semantic role → source object)").pack(anchor="w", padx=12, pady=(12, 4))
        mappings = tk.Text(window, height=14, undo=True, font=("Consolas", 10)); mappings.pack(fill="both", expand=True, padx=12)
        mappings.insert("1.0", json.dumps(resolved.get("part_overrides", {}), indent=2))
        ttk.Label(window, text="Accent palette (#RRGGBB, comma-separated)").pack(anchor="w", padx=12, pady=(8, 2))
        palette = tk.StringVar(value=", ".join(resolved.get("accent_colors", []))); ttk.Entry(window, textvariable=palette).pack(fill="x", padx=12)
        ttk.Label(window, text="Equipment ID").pack(anchor="w", padx=12, pady=(8, 2))
        equipment = tk.StringVar(value=resolved.get("weapon") or ""); ttk.Entry(window, textvariable=equipment).pack(fill="x", padx=12)
        history = JobEditor(raw, ROOT)
        def render(value: dict) -> None:
            effective = resolve_job(value, ROOT)
            mappings.delete("1.0", tk.END); mappings.insert("1.0", json.dumps(effective.get("part_overrides", {}), indent=2))
            palette.set(", ".join(effective.get("accent_colors", []))); equipment.set(effective.get("weapon") or "")
        controls = ttk.Frame(window); controls.pack(fill="x", padx=12, pady=12)
        def commit_edit() -> bool:
            try:
                colors = [item.strip() for item in palette.get().split(",") if item.strip()]
                changes = {
                    "part_overrides": json.loads(mappings.get("1.0", tk.END)),
                    "accent_colors": colors,
                    "weapon": equipment.get().strip() or None,
                }
                effective = resolve_job(history.value, ROOT)
                changed_fields = {
                    key: value
                    for key, value in changes.items()
                    if effective.get(key) != value
                }
                if not changed_fields:
                    return True
                updated = history.apply(changed_fields)
                render(updated)
                return True
            except Exception as exc:
                messagebox.showerror("Invalid override", str(exc), parent=window)
                return False
        ttk.Button(controls, text="Apply edit", command=commit_edit).pack(side="left")
        ttk.Button(controls, text="Undo", command=lambda: render(history.undo())).pack(side="left", padx=4)
        ttk.Button(controls, text="Redo", command=lambda: render(history.redo())).pack(side="left")
        def save() -> None:
            if not commit_edit():
                return
            try:
                if not self._save_current_document(path, history.value, parent=window):
                    return
                self._replace_editor(history.value, saved=True)
                self._update_catalog_record(path)
                window.destroy()
            except Exception as exc:
                messagebox.showerror("Save failed", str(exc), parent=window)
        ttk.Button(controls, text="Save atomically", command=save).pack(side="right")

    def duplicate_selected(self) -> None:
        path = self.selected()
        if not path:
            return
        if self.editor.edit_modified() and not self.save_job(notify=False):
            return
        new_id = simpledialog.askstring("Duplicate variant", "New lowercase job ID:", parent=self)
        if not new_id:
            return
        new_name = simpledialog.askstring("Duplicate variant", "Display name:", initialvalue=new_id.replace("_", " ").title(), parent=self)
        if not new_name:
            return
        target = path.with_name(new_id + ".json")
        try:
            duplicate_variant(path, target, new_id, new_name, ROOT)
            self.search_value.set("")
            self.game_filter.set("All")
            self._update_catalog_record(target)
            self._load_job(target)
            messagebox.showinfo("Variant created", str(target.relative_to(ROOT)), parent=self)
        except Exception as exc:
            messagebox.showerror("Could not duplicate", str(exc), parent=self)

    def _job_output(self, path: Path) -> Path:
        job = load_job(path, ROOT); slug = job["id"].split("_", 1)[1] if "_" in job["id"] else job["id"]
        return ROOT / "exports" / job["game"] / slug

    def _archive_preview(self, path: Path) -> None:
        try:
            job = load_job(path, ROOT); preview = self._job_output(path) / f"{job['id']}_preview.png"
            if preview.is_file():
                history = ROOT / "exports" / ".history" / job["id"]; history.mkdir(parents=True, exist_ok=True)
                shutil.copy2(preview, history / f"{int(preview.stat().st_mtime)}_before.png")
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            pass

    def browse_results(self, path: Path | None = None) -> None:
        path = path or self.selected()
        if not path:
            return
        try:
            output = self._job_output(path)
            job = load_job(path, ROOT)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Cannot open results", str(exc), parent=self)
            return
        report_path = output / f"{job['id']}_report.json"
        failed_reports = newest_existing(
            (ROOT / "exports" / ".runs" / job["id"]).glob("*/build_report.json")
        )
        if failed_reports:
            try:
                if (
                    not report_path.exists()
                    or failed_reports[0].stat().st_mtime > report_path.stat().st_mtime
                ):
                    report_path = failed_reports[0]
            except OSError:
                pass
        try:
            report = normalize_build_report(
                json.loads(report_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError):
            report = normalize_build_report({
                "diagnostics": [
                    {
                        "severity": "info",
                        "code": "NO_REPORT",
                        "message": "Build the job to create a report.",
                        "corrective_action": "Run Build Selected, then reopen this dashboard.",
                    }
                ]
            })
        window = tk.Toplevel(self)
        window.title(f"Preview & Validation — {job.get('name', job['id'])}")
        window.geometry("1120x740")
        window.minsize(820, 560)
        window.transient(self)
        panes = ttk.Panedwindow(window, orient=tk.HORIZONTAL)
        panes.pack(fill="both", expand=True, padx=10, pady=10)
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=3)
        current_files = newest_existing(output.glob("*.png"))
        history_files = newest_existing(
            (ROOT / "exports" / ".history" / job["id"]).glob("*.png")
        )
        files = current_files + history_files
        labels = [f"Current  ·  {item.name}" for item in current_files] + [
            f"History  ·  {item.name}" for item in history_files
        ]
        glb = output / f"{job['id']}.glb"
        player_button = ttk.Button(left, text="Play Animations", command=lambda: self.open_animation_player(glb, output / f"{job['id']}_report.json", window))
        player_button.pack(fill="x", pady=(0, 8))
        if not glb.is_file(): player_button.state(["disabled"])
        ttk.Button(
            left,
            text="Open Character Export Folder",
            command=lambda: self._open_folder(output),
        ).pack(fill="x", pady=(0, 8))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        listing = tk.Listbox(list_frame, exportselection=False)
        listing.pack(side="left", fill="both", expand=True)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listing.yview)
        list_scroll.pack(side="right", fill="y")
        listing.configure(yscrollcommand=list_scroll.set)
        for label in labels:
            listing.insert(tk.END, label)
        image_label = ttk.Label(right, text="No preview renders are available yet", anchor="center")
        image_label.pack(fill="both", expand=True)
        window._preview_image = None

        def show_image(_event=None) -> None:
            if not listing.curselection():
                return
            try:
                photo = tk.PhotoImage(file=str(files[listing.curselection()[0]])); factor = max(1, max(photo.width() // 700, photo.height() // 520))
                if factor > 1:
                    photo = photo.subsample(factor, factor)
                window._preview_image = photo
                image_label.configure(image=photo, text="")
            except (tk.TclError, OSError) as exc:
                image_label.configure(text=str(exc), image="")

        listing.bind("<<ListboxSelect>>", show_image)
        if files:
            listing.selection_set(0)
            show_image()

        dashboard_frame = ttk.Frame(right)
        dashboard_frame.pack(fill="x", pady=(8, 0))
        dashboard = ttk.Treeview(
            dashboard_frame,
            columns=("severity", "message", "action"),
            show="headings",
            height=8,
        )
        dashboard.heading("severity", text="Severity / Code")
        dashboard.heading("message", text="Message")
        dashboard.heading("action", text="Corrective Action")
        dashboard.column("severity", width=160, stretch=False)
        dashboard.column("message", width=390)
        dashboard.column("action", width=390)
        dashboard.pack(side="left", fill="x", expand=True)
        dashboard_scroll = ttk.Scrollbar(
            dashboard_frame, orient="vertical", command=dashboard.yview
        )
        dashboard_scroll.pack(side="right", fill="y")
        dashboard.configure(yscrollcommand=dashboard_scroll.set)
        for item in report.get("diagnostics", []):
            dashboard.insert(
                "",
                tk.END,
                values=(
                    f"{item.get('severity', '')} {item.get('code', '')}",
                    item.get("message", ""),
                    item.get("corrective_action", ""),
                ),
            )
        for stage in report.get("stages", []):
            if stage.get("status") == "failed":
                dashboard.insert(
                    "",
                    tk.END,
                    values=(
                        "ERROR " + str(stage.get("name", "")),
                        stage.get("error", "Stage failed"),
                        "Fix the reported stage error, then use Retry Failed.",
                    ),
                )

    def open_animation_player(self, glb: Path, report_path: Path, parent) -> None:
        try:
            report = normalize_build_report(json.loads(report_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            report = {}
        def launch() -> None:
            try:
                launch_player(ROOT, glb, report, str(self.settings.get("godot_path", "")))
            except AnimationPlayerError as exc:
                self.events.put(("player_error", exc))
            except Exception as exc:
                self.events.put(("player_error", f"Could not launch Godot: {exc}"))
        threading.Thread(target=launch, daemon=True).start()

    def _open_folder(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror(
                "Could not open folder",
                f"{path}\n\n{exc}",
                parent=self,
            )

    def open_exports(self) -> None:
        self._open_folder(ROOT / "exports")

    def open_settings(self) -> None:
        window = tk.Toplevel(self)
        window.title("Settings")
        window.geometry("780x560")
        window.minsize(640, 480)
        window.transient(self)
        window.grab_set()

        notebook = ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        tools_tab = ttk.Frame(notebook, padding=12)
        ai_tab = ttk.Frame(notebook, padding=12)
        notebook.add(tools_tab, text="Build & Tools")
        notebook.add(ai_tab, text="AI Proposals")
        tools_tab.columnconfigure(0, weight=1)
        ai_tab.columnconfigure(0, weight=1)

        def executable_row(parent, row_number: int, label: str, variable: tk.StringVar, kind: str) -> None:
            ttk.Label(parent, text=label).grid(row=row_number, column=0, sticky="w", pady=(0, 4))
            row = ttk.Frame(parent)
            row.grid(row=row_number + 1, column=0, sticky="ew", pady=(0, 12))
            row.columnconfigure(0, weight=1)
            ttk.Entry(row, textvariable=variable).grid(row=0, column=0, sticky="ew")
            ttk.Button(
                row,
                text="Browse",
                command=lambda: variable.set(
                    filedialog.askopenfilename(
                        parent=window,
                        filetypes=[(kind, "*.exe"), ("All files", "*.*")],
                    )
                    or variable.get()
                ),
            ).grid(row=0, column=1, padx=(8, 0))

        blender_value = tk.StringVar(value=self.settings.get("blender_path", ""))
        godot_value = tk.StringVar(value=self.settings.get("godot_path", ""))
        executable_row(tools_tab, 0, "Blender 4.5+ executable", blender_value, "Blender")
        executable_row(tools_tab, 2, "Godot 4.6.2+ executable (optional)", godot_value, "Godot")
        cache_value = tk.BooleanVar(value=self.settings.get("cache_enabled", True))
        ttk.Checkbutton(
            tools_tab,
            text="Reuse unchanged completed builds",
            variable=cache_value,
        ).grid(row=4, column=0, sticky="w", pady=(4, 12))
        ttk.Label(
            tools_tab,
            text=f"Personal settings: {SETTINGS}",
            wraplength=700,
        ).grid(row=5, column=0, sticky="w")

        provider_value = tk.StringVar(value=self.settings.get("llm_provider", "none"))
        ttk.Label(ai_tab, text="Provider").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Combobox(
            ai_tab,
            textvariable=provider_value,
            values=("none", "ollama", "openai"),
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        ollama_url = tk.StringVar(value=self.settings.get("ollama_base_url", DEFAULT_SETTINGS["ollama_base_url"]))
        ollama_model = tk.StringVar(value=self.settings.get("ollama_model", DEFAULT_SETTINGS["ollama_model"]))
        openai_url = tk.StringVar(value=self.settings.get("openai_base_url", DEFAULT_SETTINGS["openai_base_url"]))
        openai_model = tk.StringVar(value=self.settings.get("openai_model", DEFAULT_SETTINGS["openai_model"]))
        fields = [
            ("Ollama base URL", ollama_url),
            ("Ollama model", ollama_model),
            ("OpenAI-compatible base URL", openai_url),
            ("OpenAI-compatible model", openai_model),
        ]
        for index, (label, variable) in enumerate(fields, start=2):
            ttk.Label(ai_tab, text=label).grid(row=index * 2, column=0, sticky="w", pady=(0, 4))
            ttk.Entry(ai_tab, textvariable=variable).grid(
                row=index * 2 + 1, column=0, sticky="ew", pady=(0, 10)
            )
        ttk.Label(
            ai_tab,
            text="API keys are never stored here. OpenAI-compatible requests read OPENAI_API_KEY from the environment.",
            wraplength=700,
        ).grid(row=12, column=0, sticky="w", pady=(4, 0))

        def commit(*, preflight: bool = False) -> None:
            provider = provider_value.get()
            values = {
                "blender_path": blender_value.get().strip(),
                "godot_path": godot_value.get().strip(),
                "cache_enabled": cache_value.get(),
                "llm_provider": provider,
                "ollama_base_url": ollama_url.get().strip(),
                "ollama_model": ollama_model.get().strip(),
                "openai_base_url": openai_url.get().strip(),
                "openai_model": openai_model.get().strip(),
            }
            if provider not in {"none", "ollama", "openai"}:
                messagebox.showerror("Invalid settings", "Choose a supported LLM provider.", parent=window)
                return
            prefix = "ollama" if provider == "ollama" else "openai"
            if provider != "none":
                base_url = str(values[f"{prefix}_base_url"])
                model = str(values[f"{prefix}_model"])
                if not base_url.startswith(("http://", "https://")) or not model:
                    messagebox.showerror(
                        "Invalid settings",
                        "The selected provider requires an HTTP(S) base URL and model name.",
                        parent=window,
                    )
                    return
            candidate = normalize_settings({**self.settings, **values})
            try:
                save_settings(candidate)
            except OSError as exc:
                messagebox.showerror("Could not save settings", str(exc), parent=window)
                return
            self.settings = candidate
            window.destroy()
            if preflight:
                self.after(0, self.show_preflight)

        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(controls, text="Cancel", command=window.destroy).pack(side="right")
        ttk.Button(controls, text="Save", command=commit).pack(side="right", padx=(0, 8))
        ttk.Button(
            controls,
            text="Save & Run Preflight",
            command=lambda: commit(preflight=True),
        ).pack(side="right", padx=(0, 8))

    def close(self) -> None:
        if not self._confirm_editor_transition():
            return
        if self.building and not messagebox.askyesno(
            "Build running",
            "Stop every active and queued build, then exit?",
            parent=self,
        ):
            return
        preserve_snapshot = False
        if self.building:
            _active, _pending, errors = self._request_build_cancellation(
                pending_reason="Application closed before launch; resume is available.",
                wait=True,
            )
            if errors:
                messagebox.showwarning(
                    "Cancellation state not saved",
                    "Build processes were stopped, but some queue status changes could not be saved:\n\n"
                    + "\n".join(errors),
                    parent=self,
                )
            deadline = time.monotonic() + 5.0
            for thread in self.worker_threads:
                if thread.is_alive():
                    thread.join(timeout=max(0.0, deadline - time.monotonic()))
            alive_threads = [thread for thread in self.worker_threads if thread.is_alive()]
            with self.worker_lock:
                alive_processes = [
                    process for process in self.procs.values() if process.poll() is None
                ]
            preserve_snapshot = bool(alive_threads or alive_processes)
            if preserve_snapshot:
                messagebox.showwarning(
                    "Build shutdown still in progress",
                    "A worker did not stop within the shutdown deadline. Its immutable "
                    "input snapshot was preserved so it cannot lose files mid-build; "
                    "the app will reclaim it after it becomes stale.",
                    parent=self,
                )
        if not preserve_snapshot:
            self._discard_build_input_snapshot()
            lock = self.__dict__.get("instance_lock")
            if lock is not None:
                lock.release()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
