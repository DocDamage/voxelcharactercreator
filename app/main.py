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

try:
    from app.services.job_validator import validate_job
    from app.services.llm_client import apply_patch, run_ollama, run_openai
except ModuleNotFoundError:  # Support launching with ``python app/main.py``.
    from services.job_validator import validate_job
    from services.llm_client import apply_patch, run_ollama, run_openai


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.json"


def load_settings() -> dict:
    defaults = {"blender_path": "", "render_resolution": 768, "llm_provider": "none"}
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
        self.proc: subprocess.Popen[str] | None = None
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
        self.bar = ttk.Progressbar(box, mode="indeterminate")
        self.bar.grid(row=1, column=0, sticky="ew", pady=(8, 0))

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
            path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
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

        blender = self.settings.get("blender_path") or detect_blender()
        if not blender or not Path(blender).is_file():
            messagebox.showerror("Blender not found", "Open Settings and select blender.exe.")
            return
        self.settings["blender_path"] = blender
        save_settings(self.settings)
        self.building = True
        self.bar.start(10)
        threading.Thread(target=self.worker, args=(jobs,), daemon=True).start()

    def worker(self, jobs: list[Path]) -> None:
        try:
            for index, path in enumerate(jobs, 1):
                self.events.put(("log", f"\n=== [{index}/{len(jobs)}] {path.stem} ===\n"))
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
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self.proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=ROOT,
                    creationflags=flags,
                )
                if self.proc.stdout:
                    for line in self.proc.stdout:
                        self.events.put(("log", line))
                code = self.proc.wait()
                if code:
                    raise RuntimeError(f"Blender exited with code {code}")
            self.events.put(("done", "Builds completed."))
        except Exception as exc:
            self.events.put(("failed", str(exc)))
        finally:
            self.proc = None

    def cancel_build(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.events.put(("log", "\nCancellation requested.\n"))

    def drain_events(self) -> None:
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind in {"done", "failed"}:
                    self.building = False
                    self.bar.stop()
                    if kind == "done":
                        messagebox.showinfo("Complete", text)
                    else:
                        messagebox.showerror("Failed", text)
                    text = f"\n{kind.upper()}: {text}\n"
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
            path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
            self.show_job()
            messagebox.showinfo("Job updated", "The character job was updated and validated.")
        except Exception as exc:
            messagebox.showerror("LLM update failed", str(exc))

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
        window.geometry("760x170")
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

        def commit() -> None:
            self.settings["blender_path"] = value.get().strip()
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
