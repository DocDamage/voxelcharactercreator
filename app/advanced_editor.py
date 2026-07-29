"""Tk spatial character editor backed by canonical Job v2 contracts."""

from __future__ import annotations

import json
import math
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from vcf_core.advanced import SceneEditorDocument
from vcf_core.jobs import resolve_job, validate_job
from vcf_core.operator import atomic_write_json


AXES = ("x", "y", "z")
DEFAULT_TRANSFORM = {
    "location": [0.0, 0.0, 0.0],
    "rotation_degrees": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
}


def positive_finite_number(value: object, label: str) -> float:
    """Return a positive finite numeric UI value or raise an actionable error."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number greater than zero.")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be a finite number greater than zero.")
    return result


def resolve_editor_context(raw_job: dict[str, Any], root: Path) -> tuple[dict[str, Any], list[str]]:
    """Resolve inherited display data without expanding the editable raw document."""

    resolved = resolve_job(raw_job, root)
    source = resolved.get("source", {})
    source_parts = source.get("asset_ids", []) if isinstance(source, dict) else []
    if not isinstance(source_parts, list):
        source_parts = []
    settings = resolved.get("settings_overrides", {})
    transforms = settings.get("part_transforms", {}) if isinstance(settings, dict) else {}

    candidates = [item for item in source_parts if isinstance(item, str)]
    if isinstance(transforms, dict):
        candidates.extend(item for item in transforms if isinstance(item, str))
    parts = list(dict.fromkeys(candidates))
    return resolved, parts or ["body"]


class AdvancedCharacterEditor(tk.Toplevel):
    """Fallback orthographic editor for transforms and socket overrides."""

    def __init__(
        self,
        parent: tk.Misc,
        path: Path,
        root: Path,
        on_saved: Callable[[], object] | None = None,
        on_preview: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.root = root
        self.on_saved = on_saved
        self.on_preview = on_preview
        self._base_title = "3D Character Editor"

        try:
            self._file_snapshot = path.read_bytes()
            raw_job = json.loads(self._file_snapshot.decode("utf-8"))
            self._resolved_job, self.parts = resolve_editor_context(raw_job, root)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            messagebox.showerror("Cannot open 3D editor", str(exc), parent=parent)
            self.destroy()
            return
        self.document = SceneEditorDocument(raw_job)
        self._saved_value = deepcopy(raw_job)
        self.dirty = False
        self.selected = 0

        self.axis = tk.StringVar(value="x")
        self.move_step = tk.DoubleVar(value=0.01)
        self.rotation_step = tk.DoubleVar(value=5.0)
        self.scale_step = tk.DoubleVar(value=0.05)
        self.transform_text = tk.StringVar()
        self.status_text = tk.StringVar(
            value="Orthographic X-Z view; Y is depth. Axis labels do not rely on color."
        )

        self.title(self._base_title)
        self.geometry("1040x720")
        self.minsize(820, 560)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build_ui()
        self.bind("<Control-s>", self._save_shortcut)
        self.bind("<Control-z>", lambda _event: self._history(False))
        self.bind("<Control-y>", lambda _event: self._history(True))
        self._refresh_view()

    def _build_ui(self) -> None:
        sidebar = ttk.Frame(self, padding=10)
        sidebar.pack(side="left", fill="y")
        viewport = ttk.Frame(self, padding=10)
        viewport.pack(side="right", fill="both", expand=True)

        ttk.Label(sidebar, text="Parts").pack(anchor="w")
        list_frame = ttk.Frame(sidebar)
        list_frame.pack(fill="both", expand=True, pady=(2, 6))
        self.list = tk.Listbox(list_frame, width=30, height=10, exportselection=False)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=list_scroll.set)
        self.list.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")
        for item in self.parts:
            self.list.insert(tk.END, item)
        self.list.selection_set(0)
        self.list.bind("<<ListboxSelect>>", self._select)

        axis_row = ttk.Frame(sidebar)
        axis_row.pack(fill="x", pady=(4, 2))
        ttk.Label(axis_row, text="Axis").pack(side="left")
        ttk.Combobox(
            axis_row,
            textvariable=self.axis,
            values=AXES,
            state="readonly",
            width=5,
        ).pack(side="right")

        self._add_step_control(sidebar, "Move step (meters)", self.move_step)
        self._add_action_row(
            sidebar,
            "Move",
            lambda: self._change_transform("move", -1),
            lambda: self._change_transform("move", 1),
        )
        self._add_step_control(sidebar, "Rotation step (degrees)", self.rotation_step)
        self._add_action_row(
            sidebar,
            "Rotate",
            lambda: self._change_transform("rotate", -1),
            lambda: self._change_transform("rotate", 1),
        )
        self._add_step_control(sidebar, "Scale step", self.scale_step)
        self._add_action_row(
            sidebar,
            "Scale",
            lambda: self._change_transform("scale", -1),
            lambda: self._change_transform("scale", 1),
        )

        ttk.Button(sidebar, text="Adjust Socket…", command=self._socket).pack(fill="x", pady=(5, 3))
        history_row = ttk.Frame(sidebar)
        history_row.pack(fill="x")
        ttk.Button(history_row, text="Undo", command=lambda: self._history(False)).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(history_row, text="Redo", command=lambda: self._history(True)).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )
        ttk.Button(sidebar, text="Validate & Save Job", command=self._save).pack(
            fill="x", pady=(12, 0)
        )
        if self.on_preview:
            ttk.Button(sidebar, text="Preview Animations", command=self.on_preview).pack(
                fill="x", pady=3
            )

        self.canvas = tk.Canvas(viewport, bg="#10131a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        ttk.Label(viewport, textvariable=self.transform_text, justify="left").pack(
            anchor="w", pady=(8, 0)
        )
        ttk.Label(viewport, textvariable=self.status_text, wraplength=680).pack(
            anchor="w", pady=(4, 0)
        )

    @staticmethod
    def _add_step_control(parent: tk.Misc, label: str, variable: tk.DoubleVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(5, 1))
        ttk.Label(row, text=label).pack(side="left")
        ttk.Entry(row, textvariable=variable, width=9).pack(side="right")

    @staticmethod
    def _add_action_row(
        parent: tk.Misc,
        label: str,
        negative_command: Callable[[], object],
        positive_command: Callable[[], object],
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(1, 2))
        ttk.Button(row, text=f"− {label}", command=negative_command).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text=f"+ {label}", command=positive_command).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )

    def _select(self, _event: object = None) -> None:
        selection = self.list.curselection()
        if selection:
            self.selected = selection[0]
            self._refresh_view()

    def _selected_part(self) -> str:
        return self.parts[min(self.selected, len(self.parts) - 1)]

    def _transform(self) -> tuple[str, dict[str, list[float]]]:
        part = self._selected_part()
        return part, self._effective_transform(part)

    def _effective_transform(self, part: str) -> dict[str, list[float]]:
        current_settings = self.document.value.get("settings_overrides", {})
        current_transforms = (
            current_settings.get("part_transforms", {})
            if isinstance(current_settings, dict)
            else {}
        )
        if isinstance(current_transforms, dict) and part in current_transforms:
            return deepcopy(current_transforms[part])

        resolved_settings = self._resolved_job.get("settings_overrides", {})
        resolved_transforms = (
            resolved_settings.get("part_transforms", {})
            if isinstance(resolved_settings, dict)
            else {}
        )
        value = resolved_transforms.get(part, DEFAULT_TRANSFORM)
        return deepcopy(value)

    def _read_step(self, variable: tk.DoubleVar, label: str) -> float:
        try:
            value = variable.get()
        except tk.TclError as exc:
            raise ValueError(f"{label} must be a number greater than zero.") from exc
        return positive_finite_number(value, label)

    def _change_transform(self, operation: str, direction: int) -> None:
        try:
            part, value = self._transform()
            axis_index = AXES.index(self.axis.get())
            if operation == "move":
                step = self._read_step(self.move_step, "Move step")
                value["location"][axis_index] += direction * step
            elif operation == "rotate":
                step = self._read_step(self.rotation_step, "Rotation step")
                value["rotation_degrees"][axis_index] += direction * step
            elif operation == "scale":
                step = self._read_step(self.scale_step, "Scale step")
                value["scale"][axis_index] += direction * step
                if value["scale"][axis_index] <= 0:
                    raise ValueError("Scale must remain greater than zero on every axis.")
            else:
                raise ValueError(f"Unsupported transform operation: {operation}")

            self.document.apply_transform(
                part,
                location=value["location"],
                rotation=value["rotation_degrees"],
                scale=value["scale"],
            )
        except Exception as exc:
            messagebox.showerror("Invalid transform", str(exc), parent=self)
            return

        self.status_text.set(f"Updated {part} {operation} on the {self.axis.get().upper()} axis.")
        self._refresh_view()

    def _socket(self) -> None:
        name = simpledialog.askstring("Socket", "Socket name:", parent=self)
        if not name:
            return
        bone = simpledialog.askstring("Socket", "Parent bone:", parent=self)
        if not bone:
            return
        try:
            self.document.set_socket(name, bone, [0.0, 0.0, 0.0])
        except Exception as exc:
            messagebox.showerror("Invalid socket", str(exc), parent=self)
            return
        self.status_text.set(f"Socket {name} → {bone} authored at zero offset.")
        self._refresh_view()

    def _history(self, redo: bool) -> str:
        before = self.document.value
        if redo:
            self.document.redo()
        else:
            self.document.undo()
        changed = self.document.value != before
        action = "Redo" if redo else "Undo"
        self.status_text.set(f"{action} applied." if changed else f"Nothing to {action.lower()}.")
        self._refresh_view()
        return "break"

    def _refresh_view(self) -> None:
        self.dirty = self.document.value != self._saved_value
        self.title(f"{self._base_title}{' *' if self.dirty else ''}")
        self._update_transform_readout()
        self._draw()

    def _update_transform_readout(self) -> None:
        part, value = self._transform()
        location = ", ".join(f"{axis:.4g}" for axis in value["location"])
        rotation = ", ".join(f"{axis:.4g}°" for axis in value["rotation_degrees"])
        scale = ", ".join(f"{axis:.4g}" for axis in value["scale"])
        self.transform_text.set(
            f"Part: {part}\nPosition XYZ: {location}   Rotation XYZ: {rotation}   "
            f"Scale XYZ: {scale}"
        )

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        origin_x = width / 2
        origin_y = height * 0.72

        self.canvas.create_line(origin_x, 20, origin_x, height - 20, fill="#4b78ff", width=2)
        self.canvas.create_line(20, origin_y, width - 20, origin_y, fill="#e55252", width=2)
        self.canvas.create_text(origin_x + 10, 24, text="Z axis", fill="#a9c1ff", anchor="nw")
        self.canvas.create_text(
            width - 24,
            origin_y - 10,
            text="X axis",
            fill="#ffaaaa",
            anchor="se",
        )
        self.canvas.create_text(
            12,
            12,
            text="Y axis = depth (not projected)",
            fill="#d8dee9",
            anchor="nw",
        )

        for index, part in enumerate(self.parts):
            transform = self._effective_transform(part)
            location = transform["location"]
            x = origin_x + location[0] * 220 + (index % 5 - 2) * 42
            y = origin_y - location[2] * 220 - (index // 5) * 38
            color = "#ffd166" if index == self.selected else "#74c0fc"
            self.canvas.create_rectangle(
                x - 16,
                y - 16,
                x + 16,
                y + 16,
                fill=color,
                outline="white",
                width=2 if index == self.selected else 1,
            )
            self.canvas.create_text(x, y + 25, text=part[:18], fill="#d8dee9")

    def _file_is_unchanged(self) -> bool:
        try:
            current = self.path.read_bytes()
        except OSError as exc:
            messagebox.showerror(
                "Cannot save",
                f"Could not re-read the job before saving:\n{exc}",
                parent=self,
            )
            return False
        if current != self._file_snapshot:
            messagebox.showerror(
                "Job changed on disk",
                "This job was modified outside this editor after it was opened. "
                "Your changes were not saved. Close and reopen the editor before editing again.",
                parent=self,
            )
            return False
        return True

    def _save(self) -> bool:
        value = self.document.value
        try:
            errors = validate_job(value, self.root)
        except Exception as exc:
            messagebox.showerror("Validation failed", str(exc), parent=self)
            return False
        if errors:
            messagebox.showerror("Validation failed", "\n".join(errors), parent=self)
            return False
        if not self._file_is_unchanged():
            return False

        try:
            atomic_write_json(self.path, value)
            self._resolved_job, self.parts = resolve_editor_context(value, self.root)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return False

        self._file_snapshot = (json.dumps(value, indent=2) + "\n").encode("utf-8")
        self._saved_value = deepcopy(value)
        self._refresh_view()
        if self.on_saved:
            try:
                self.on_saved()
            except Exception as exc:
                messagebox.showwarning(
                    "Saved with refresh warning",
                    f"The job was saved, but the parent view could not refresh:\n{exc}",
                    parent=self,
                )
        messagebox.showinfo("Saved", "Canonical Job v2 saved atomically.", parent=self)
        return True

    def _save_shortcut(self, _event: object = None) -> str:
        self._save()
        return "break"

    def _close(self) -> None:
        self._refresh_view()
        if not self.dirty:
            self.destroy()
            return

        choice = messagebox.askyesnocancel(
            "Unsaved changes",
            "Save changes before closing the 3D Character Editor?",
            parent=self,
        )
        if choice is None:
            return
        if choice and not self._save():
            return
        self.destroy()
