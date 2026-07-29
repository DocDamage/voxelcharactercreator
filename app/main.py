from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

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
from vcf_core.operator import BuildQueue, STAGES, atomic_write_json, run_preflight
from vcf_core.factory import measured_parallelism
from vcf_core.viewer import AnimationPlayerError, launch_player


SETTINGS = ROOT / "config" / "settings.json"


def load_settings() -> dict:
    defaults = {"blender_path": "", "godot_path": "", "render_resolution": 768, "llm_provider": "none", "cache_enabled": True, "performance_metrics": [], "available_memory_gb": None}
    try:
        loaded = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    return {**defaults, **loaded}


def save_settings(data: dict) -> None:
    SETTINGS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
        self.geometry("1080x720")
        self.minsize(900, 600)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.settings = load_settings()
        self.settings["blender_path"] = self.settings.get("blender_path") or detect_blender()
        self.jobs = sorted((ROOT / "characters").glob("*/*.json"))
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.build_queue = BuildQueue(ROOT / "exports" / ".queue" / "queue.json")
        self.active_item_id: str | None = None
        self.proc: subprocess.Popen[str] | None = None
        self.procs: dict[str, subprocess.Popen[str]] = {}
        self.worker_lock = threading.RLock()
        self.workers_remaining = 0
        self.worker_errors: list[str] = []
        self.building = False

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        left = ttk.Frame(self, padding=12)
        left.grid(row=0, column=0, sticky="ns")
        ttk.Label(left, text="Pilot Cast", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.list = tk.Listbox(left, width=29, height=25, exportselection=False)
        self.list.pack(fill="y", expand=True, pady=10)
        for path in self.jobs:
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                label = f"{job.get('game', '?').upper()}  •  {job.get('name', path.stem)}"
            except (OSError, json.JSONDecodeError):
                label = f"INVALID  •  {path.stem}"
            self.list.insert(tk.END, label)
        self.list.bind("<<ListboxSelect>>", lambda _event: self.show_job())

        actions = [
            ("Build Character", self.build_one),
            ("Build All", self.build_all),
            ("Cancel Build", self.cancel_build),
            ("Preflight", self.show_preflight),
            ("Retry Failed Stage", self.retry_failed),
            ("Resume Batch", self.resume_batch),
            ("Asset & Equipment Editor", self.edit_assets),
            ("Part & Palette Overrides", self.edit_overrides),
            ("Duplicate as Variant", self.duplicate_selected),
            ("Preview & Validation", self.browse_results),
            ("Describe Changes", self.describe_changes),
            ("Open Exports", self.open_exports),
            ("Settings", self.open_settings),
        ]
        for label, command in actions:
            ttk.Button(left, text=label, command=command).pack(fill="x", pady=3)

        main = ttk.Frame(self, padding=12)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        ttk.Label(main, text="Character Job", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.editor = tk.Text(main, wrap="none", font=("Consolas", 10), undo=True)
        self.editor.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        ttk.Button(main, text="Save Job Changes", command=self.save_job).grid(row=2, column=0, sticky="e")

        box = ttk.LabelFrame(main, text="Build Log", padding=8)
        box.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        box.columnconfigure(0, weight=1)
        self.log = tk.Text(box, height=11, bg="#111", fg="#eee", insertbackground="white", font=("Consolas", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        self.stage_label = ttk.Label(box, text="Ready")
        self.stage_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.bar = ttk.Progressbar(box, mode="determinate", maximum=len(STAGES))
        self.bar.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        if self.jobs:
            self.list.selection_set(0)
            self.show_job()
        self.after(100, self.drain_events)

    def selected(self) -> Path | None:
        selection = self.list.curselection()
        return self.jobs[selection[0]] if selection else None

    def show_job(self) -> None:
        path = self.selected()
        if path:
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", path.read_text(encoding="utf-8"))
            self.editor.edit_reset()

    def editor_job(self) -> dict:
        job = json.loads(self.editor.get("1.0", tk.END))
        errors = validate_job(job, project_root=ROOT)
        if errors:
            raise ValueError("\n".join(f"• {error}" for error in errors))
        return job

    def save_job(self, *, notify: bool = True) -> bool:
        path = self.selected()
        if not path:
            return False
        try:
            job = self.editor_job()
            atomic_write_json(path, job)
            self.editor.edit_modified(False)
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
        if self.save_job(notify=False):
            self.start(self.jobs)

    def start(self, jobs: list[Path]) -> None:
        if self.building:
            messagebox.showwarning("Busy", "A build is already running.")
            return
        invalid: list[str] = []
        for path in jobs:
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                invalid.extend(f"{path.name}: {error}" for error in validate_job(job, project_root=ROOT))
            except (OSError, json.JSONDecodeError) as exc:
                invalid.append(f"{path.name}: {exc}")
        if invalid:
            messagebox.showerror("Invalid jobs", "\n".join(invalid))
            return

        self.settings["blender_path"] = self.settings.get("blender_path") or detect_blender()
        preflight = run_preflight(ROOT, self.settings, jobs)
        if not preflight.ok:
            messagebox.showerror("Preflight blocked the build", "\n\n".join(f"{issue.message}\nAction: {issue.corrective_action}" for issue in preflight.issues if issue.severity == "error"))
            return
        save_settings(self.settings)
        for path in jobs:
            self._archive_preview(path)
            self.build_queue.add(path)
        self.building = True
        self.bar["value"] = 0
        self._start_workers()

    def _start_workers(self) -> None:
        worker_count = measured_parallelism(
            self.settings.get("performance_metrics", []),
            memory_gb=self.settings.get("available_memory_gb"),
        )
        self.workers_remaining = worker_count
        self.worker_errors = []
        self.events.put(("log", f"\nStarting {worker_count} measured queue worker(s).\n"))
        for _index in range(worker_count):
            threading.Thread(target=self.worker, daemon=True).start()

    def worker(self) -> None:
        try:
            while claimed := self.build_queue.claim_pending(1):
                item = claimed[0]
                path = Path(item.job_path)
                self.active_item_id = item.id
                self.events.put(("log", f"\n=== {path.stem} ===\n"))
                command = [
                    self.settings["blender_path"],
                    "--background",
                    "--python",
                    str(ROOT / "blender_worker" / "process_character.py"),
                    "--",
                    "--job",
                    str(path),
                    "--project-root",
                    str(ROOT),
                ]
                if item.retry_from_stage:
                    command.extend(["--retry-stage", item.retry_from_stage])
                if not self.settings.get("cache_enabled", True):
                    command.append("--no-cache")
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                child_environment = os.environ.copy()
                if self.settings.get("godot_path"):
                    child_environment["VCF_GODOT"] = self.settings["godot_path"]
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
                self.proc = process
                with self.worker_lock:
                    self.procs[item.id] = process
                if process.stdout:
                    for line in process.stdout:
                        if line.startswith("VCF_EVENT "):
                            try:
                                event = json.loads(line[len("VCF_EVENT "):])
                                if event.get("type") == "stage":
                                    stage = event.get("name")
                                    self.build_queue.update(item.id, stage=stage)
                                    self.events.put(("stage", str(stage)))
                            except (ValueError, KeyError):
                                pass
                        self.events.put(("log", line))
                code = process.wait()
                if code:
                    current = next(entry for entry in self.build_queue.items if entry.id == item.id)
                    if current.status == "cancelling":
                        self.build_queue.update(item.id, status="cancelled", error="Cancelled by operator; no output was promoted.")
                        self.worker_errors.append(f"{path.name}: build cancelled")
                    else:
                        self.build_queue.update(item.id, status="failed", error=f"Blender exited with code {code}")
                        self.worker_errors.append(f"{path.name}: Blender exited with code {code}")
                else:
                    self.build_queue.update(item.id, status="complete")
                with self.worker_lock:
                    self.procs.pop(item.id, None)
        except Exception as exc:
            self.worker_errors.append(str(exc))
        finally:
            self.proc = None
            self.active_item_id = None
            with self.worker_lock:
                self.workers_remaining -= 1
                if self.workers_remaining == 0:
                    if self.worker_errors:
                        self.events.put(("failed", "\n".join(self.worker_errors)))
                    else:
                        self.events.put(("done", "Builds completed."))

    def cancel_build(self) -> None:
        active = list(self.procs.items())
        if active:
            for item_id, process in active:
                if process.poll() is None:
                    self.build_queue.update(item_id, status="cancelling")
                    process.terminate()
            self.events.put(("log", "\nCancellation requested.\n"))

    def drain_events(self) -> None:
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind in {"done", "failed"}:
                    self.building = False
                    self.bar["value"] = 0
                    if kind == "done":
                        messagebox.showinfo("Complete", text)
                    else:
                        messagebox.showerror("Failed", text)
                    text = f"\n{kind.upper()}: {text}\n"
                elif kind == "stage":
                    self.stage_label["text"] = f"Stage: {text}"
                    self.bar["value"] = STAGES.index(text) + 1 if text in STAGES else 0
                    continue
                self.log.insert(tk.END, text)
                self.log.see(tk.END)
        except queue.Empty:
            pass
        self.after(100, self.drain_events)

    def describe_changes(self) -> None:
        path = self.selected()
        if not path:
            return
        provider = self.settings.get("llm_provider", "none")
        if provider == "none":
            messagebox.showinfo("LLM disabled", "Set llm_provider to ollama or openai in config/settings.json.")
            return
        prompt = simpledialog.askstring("Describe Changes", "Describe what should change in this character job:")
        if not prompt:
            return
        try:
            job = self.editor_job()
            if provider == "ollama":
                patch = run_ollama(prompt, self.settings["ollama_base_url"], self.settings["ollama_model"])
            elif provider == "openai":
                patch = run_openai(prompt, self.settings["openai_base_url"], self.settings["openai_model"])
            else:
                raise ValueError(f"Unknown LLM provider: {provider}")
            updated = apply_patch(job, patch)
            errors = validate_job(updated, project_root=ROOT)
            if errors:
                raise ValueError("\n".join(errors))
            differences = proposal_diff(job, patch)
            if not differences:
                messagebox.showinfo("No changes", "The proposal does not change this job.")
                return
            preview = "\n".join(f"{item['field']}:\n  {item['before']}\n→ {item['after']}" for item in differences)
            if not messagebox.askyesno("Review LLM proposal", preview + "\n\nApply these validated changes?"):
                return
            atomic_write_json(path, updated)
            self.show_job()
            messagebox.showinfo("Job updated", "The character job was updated and validated.")
        except Exception as exc:
            messagebox.showerror("LLM update failed", str(exc))

    def show_preflight(self) -> None:
        jobs = [self.selected()] if self.selected() else []
        report = run_preflight(ROOT, self.settings, [path for path in jobs if path])
        lines = [f"{name}: {value}" for name, value in sorted(report.versions.items())]
        lines.extend(f"[{issue.severity.upper()}] {issue.component}: {issue.message}\nAction: {issue.corrective_action}" for issue in report.issues)
        messagebox.showinfo("Preflight passed" if report.ok else "Preflight needs attention", "\n\n".join(lines) or "All required checks passed.")

    def retry_failed(self) -> None:
        path = self.selected()
        candidates = [item for item in reversed(self.build_queue.items) if item.status in {"failed", "cancelled", "interrupted"} and (not path or Path(item.job_path) == path)]
        if not candidates:
            messagebox.showinfo("Nothing to retry", "No failed or interrupted build is available for this job.")
            return
        item = candidates[0]
        stage = item.stage if item.stage in STAGES else None
        self.build_queue.retry(item.id, stage)
        if not self.building:
            self.building = True
            self._start_workers()

    def resume_batch(self) -> None:
        count = self.build_queue.resume()
        if not count:
            messagebox.showinfo("Queue", "No interrupted, failed, or cancelled items need resuming.")
            return
        if not self.building:
            self.building = True
            self._start_workers()

    def _replace_editor(self, job: dict) -> None:
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", json.dumps(job, indent=2) + "\n")

    def edit_assets(self) -> None:
        path = self.selected()
        if not path: return
        try:
            job = self.editor_job(); registry = load_registry(ROOT)
        except Exception as exc:
            messagebox.showerror("Cannot edit assets", str(exc)); return
        window = tk.Toplevel(self); window.title("Asset & Equipment Editor"); window.geometry("680x520"); window.transient(self); window.grab_set()
        ttk.Label(window, text="Select compatible registry assets (Ctrl/Shift for multiple)").pack(anchor="w", padx=12, pady=(12, 4))
        listing = tk.Listbox(window, selectmode=tk.EXTENDED, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12)
        manifests = sorted((item for item in registry.manifests if job["body_template"] in item.compatible_bases), key=lambda item: item.asset_id)
        selected_ids = set(job.get("source", {}).get("asset_ids", []))
        for index, manifest in enumerate(manifests):
            listing.insert(tk.END, f"{manifest.asset_id}  ·  {manifest.kind}  ·  {', '.join(manifest.semantic_tags)}")
            if manifest.asset_id in selected_ids: listing.selection_set(index)
        ttk.Label(window, text="Equipment ID (blank removes equipment)").pack(anchor="w", padx=12, pady=(8, 2))
        equipment = tk.StringVar(value=job.get("weapon") or "")
        ttk.Entry(window, textvariable=equipment).pack(fill="x", padx=12)
        def apply_selection() -> None:
            try:
                chosen = [manifests[index].asset_id for index in listing.curselection()]
                editor = JobEditor(job, ROOT)
                updated = editor.apply({"source": {"mode": "assembly", "asset_ids": chosen}, "weapon": equipment.get().strip() or None})
                editor.save(path); self._replace_editor(updated); window.destroy()
            except Exception as exc: messagebox.showerror("Invalid asset selection", str(exc), parent=window)
        ttk.Button(window, text="Apply validated selection", command=apply_selection).pack(anchor="e", padx=12, pady=12)

    def edit_overrides(self) -> None:
        path = self.selected()
        if not path: return
        try: job = self.editor_job()
        except Exception as exc: messagebox.showerror("Cannot edit overrides", str(exc)); return
        window = tk.Toplevel(self); window.title("Part & Palette Overrides"); window.geometry("700x560"); window.transient(self); window.grab_set()
        ttk.Label(window, text="Part mappings (semantic role → source object)").pack(anchor="w", padx=12, pady=(12, 4))
        mappings = tk.Text(window, height=14, undo=True, font=("Consolas", 10)); mappings.pack(fill="both", expand=True, padx=12)
        mappings.insert("1.0", json.dumps(job.get("part_overrides", {}), indent=2))
        ttk.Label(window, text="Accent palette (#RRGGBB, comma-separated)").pack(anchor="w", padx=12, pady=(8, 2))
        palette = tk.StringVar(value=", ".join(job.get("accent_colors", []))); ttk.Entry(window, textvariable=palette).pack(fill="x", padx=12)
        ttk.Label(window, text="Equipment ID").pack(anchor="w", padx=12, pady=(8, 2))
        equipment = tk.StringVar(value=job.get("weapon") or ""); ttk.Entry(window, textvariable=equipment).pack(fill="x", padx=12)
        history = JobEditor(job, ROOT)
        def render(value: dict) -> None:
            mappings.delete("1.0", tk.END); mappings.insert("1.0", json.dumps(value.get("part_overrides", {}), indent=2))
            palette.set(", ".join(value.get("accent_colors", []))); equipment.set(value.get("weapon") or "")
        controls = ttk.Frame(window); controls.pack(fill="x", padx=12, pady=12)
        def commit_edit() -> None:
            try:
                colors = [item.strip() for item in palette.get().split(",") if item.strip()]
                updated = history.apply({"part_overrides": json.loads(mappings.get("1.0", tk.END)), "accent_colors": colors, "weapon": equipment.get().strip() or None})
                render(updated)
            except Exception as exc: messagebox.showerror("Invalid override", str(exc), parent=window)
        ttk.Button(controls, text="Apply edit", command=commit_edit).pack(side="left")
        ttk.Button(controls, text="Undo", command=lambda: render(history.undo())).pack(side="left", padx=4)
        ttk.Button(controls, text="Redo", command=lambda: render(history.redo())).pack(side="left")
        def save() -> None:
            try: history.save(path); self._replace_editor(history.value); window.destroy()
            except Exception as exc: messagebox.showerror("Save failed", str(exc), parent=window)
        ttk.Button(controls, text="Save atomically", command=save).pack(side="right")

    def duplicate_selected(self) -> None:
        path = self.selected()
        if not path: return
        new_id = simpledialog.askstring("Duplicate variant", "New lowercase job ID:", parent=self)
        if not new_id: return
        new_name = simpledialog.askstring("Duplicate variant", "Display name:", initialvalue=new_id.replace("_", " ").title(), parent=self)
        if not new_name: return
        target = path.with_name(new_id + ".json")
        try:
            duplicate_variant(path, target, new_id, new_name, ROOT)
            self.jobs.append(target); self.jobs.sort(); self.list.insert(tk.END, f"VARIANT  •  {new_name}")
            messagebox.showinfo("Variant created", str(target.relative_to(ROOT)))
        except Exception as exc: messagebox.showerror("Could not duplicate", str(exc))

    def _job_output(self, path: Path) -> Path:
        job = json.loads(path.read_text(encoding="utf-8")); slug = job["id"].split("_", 1)[1] if "_" in job["id"] else job["id"]
        return ROOT / "exports" / job["game"] / slug

    def _archive_preview(self, path: Path) -> None:
        try:
            job = json.loads(path.read_text(encoding="utf-8")); preview = self._job_output(path) / f"{job['id']}_preview.png"
            if preview.is_file():
                history = ROOT / "exports" / ".history" / job["id"]; history.mkdir(parents=True, exist_ok=True)
                shutil.copy2(preview, history / f"{int(preview.stat().st_mtime)}_before.png")
        except (OSError, KeyError, json.JSONDecodeError): pass

    def browse_results(self) -> None:
        path = self.selected()
        if not path: return
        output = self._job_output(path); job = json.loads(path.read_text(encoding="utf-8"))
        report_path = output / f"{job['id']}_report.json"
        failed_reports = sorted((ROOT / "exports" / ".runs" / job["id"]).glob("*/build_report.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        if failed_reports and (not report_path.exists() or failed_reports[0].stat().st_mtime > report_path.stat().st_mtime):
            report_path = failed_reports[0]
        try: report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): report = {"diagnostics": [{"code": "NO_REPORT", "message": "Build the job to create a report."}]}
        window = tk.Toplevel(self); window.title("Preview & Validation Dashboard"); window.geometry("1050x700")
        panes = ttk.Panedwindow(window, orient=tk.HORIZONTAL); panes.pack(fill="both", expand=True, padx=10, pady=10)
        left = ttk.Frame(panes); right = ttk.Frame(panes); panes.add(left, weight=1); panes.add(right, weight=3)
        files = sorted(output.glob("*.png")) + sorted((ROOT / "exports" / ".history" / job["id"]).glob("*.png"))
        glb = output / f"{job['id']}.glb"
        player_button = ttk.Button(left, text="Play Animations", command=lambda: self.open_animation_player(glb, output / f"{job['id']}_report.json", window))
        player_button.pack(fill="x", pady=(0, 8))
        if not glb.is_file(): player_button.state(["disabled"])
        listing = tk.Listbox(left, exportselection=False); listing.pack(fill="both", expand=True)
        for image_path in files: listing.insert(tk.END, image_path.name)
        image_label = ttk.Label(right, text="Select a current or before-build render"); image_label.pack(fill="both", expand=True)
        window._preview_image = None
        def show_image(_event=None) -> None:
            if not listing.curselection(): return
            try:
                photo = tk.PhotoImage(file=str(files[listing.curselection()[0]])); factor = max(1, max(photo.width() // 700, photo.height() // 520))
                if factor > 1: photo = photo.subsample(factor, factor)
                window._preview_image = photo; image_label.configure(image=photo, text="")
            except tk.TclError as exc: image_label.configure(text=str(exc), image="")
        listing.bind("<<ListboxSelect>>", show_image)
        dashboard = ttk.Treeview(right, columns=("severity", "message"), show="headings", height=7); dashboard.heading("severity", text="Severity / Code"); dashboard.heading("message", text="Message")
        dashboard.column("severity", width=180); dashboard.column("message", width=620); dashboard.pack(fill="x", pady=(8, 0))
        for item in report.get("diagnostics", []): dashboard.insert("", tk.END, values=(f"{item.get('severity', '')} {item.get('code', '')}", item.get("message", "")))
        for stage in report.get("stages", []):
            if stage.get("status") == "failed": dashboard.insert("", tk.END, values=("ERROR " + stage.get("name", ""), stage.get("error", "Stage failed")))

    def open_animation_player(self, glb: Path, report_path: Path, parent) -> None:
        try: report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): report = {}
        def launch() -> None:
            try:
                launch_player(ROOT, glb, report, str(self.settings.get("godot_path", "")))
            except AnimationPlayerError as exc:
                self.after(0, lambda: messagebox.showerror("Animation player", str(exc), parent=parent))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Animation player", f"Could not launch Godot: {exc}", parent=parent))
        threading.Thread(target=launch, daemon=True).start()

    def open_exports(self) -> None:
        path = ROOT / "exports"
        path.mkdir(exist_ok=True)
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def open_settings(self) -> None:
        window = tk.Toplevel(self)
        window.title("Settings")
        window.geometry("760x300")
        window.transient(self)
        window.grab_set()
        ttk.Label(window, text="Blender executable").pack(anchor="w", padx=12, pady=(12, 4))
        value = tk.StringVar(value=self.settings.get("blender_path", ""))
        row = ttk.Frame(window)
        row.pack(fill="x", padx=12)
        ttk.Entry(row, textvariable=value).pack(side="left", fill="x", expand=True)
        ttk.Button(
            row,
            text="Browse",
            command=lambda: value.set(
                filedialog.askopenfilename(
                    filetypes=[("Blender", "blender.exe"), ("Executable", "*.exe"), ("All", "*.*")]
                )
                or value.get()
            ),
        ).pack(side="left", padx=(8, 0))
        ttk.Label(window, text="Godot executable (optional)").pack(anchor="w", padx=12, pady=(12, 4))
        godot_value = tk.StringVar(value=self.settings.get("godot_path", ""))
        ttk.Entry(window, textvariable=godot_value).pack(fill="x", padx=12)
        cache_value = tk.BooleanVar(value=self.settings.get("cache_enabled", True))
        ttk.Checkbutton(window, text="Reuse unchanged completed builds", variable=cache_value).pack(anchor="w", padx=12, pady=(12, 0))

        def commit() -> None:
            self.settings["blender_path"] = value.get().strip()
            self.settings["godot_path"] = godot_value.get().strip()
            self.settings["cache_enabled"] = cache_value.get()
            save_settings(self.settings)
            window.destroy()

        ttk.Button(window, text="Save", command=commit).pack(anchor="e", padx=12, pady=18)

    def close(self) -> None:
        if self.building and not messagebox.askyesno("Build running", "Stop the build and exit?"):
            return
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
