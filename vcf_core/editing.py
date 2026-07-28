"""Schema-valid, atomic, and undo-friendly job editing primitives."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from vcf_core.jobs import validate_job
from vcf_core.operator import atomic_write_json


class JobEditor:
    def __init__(self, job: dict[str, Any], root: Path):
        self.root = root
        self._states = [deepcopy(job)]
        self._cursor = 0

    @property
    def value(self) -> dict[str, Any]:
        return deepcopy(self._states[self._cursor])

    def apply(self, changes: dict[str, Any]) -> dict[str, Any]:
        candidate = self.value
        for key, value in changes.items():
            if key == "source.asset_ids":
                candidate.setdefault("source", {})["asset_ids"] = value
            elif key == "settings_overrides.palette":
                candidate.setdefault("settings_overrides", {})["palette"] = value
            else:
                candidate[key] = value
        errors = validate_job(candidate, self.root)
        if errors:
            raise ValueError("\n".join(errors))
        self._states = self._states[: self._cursor + 1] + [candidate]
        self._cursor += 1
        return self.value

    def undo(self) -> dict[str, Any]:
        if self._cursor > 0: self._cursor -= 1
        return self.value

    def redo(self) -> dict[str, Any]:
        if self._cursor + 1 < len(self._states): self._cursor += 1
        return self.value

    def save(self, path: Path) -> None:
        atomic_write_json(path, self.value)


def duplicate_variant(source: Path, target: Path, new_id: str, new_name: str, root: Path) -> dict[str, Any]:
    original = json.loads(source.read_text(encoding="utf-8"))
    variant = deepcopy(original)
    variant.update({"id": new_id, "name": new_name, "variant_of": original["id"]})
    errors = validate_job(variant, root)
    if errors: raise ValueError("\n".join(errors))
    if target.exists(): raise FileExistsError(target)
    atomic_write_json(target, variant)
    return variant
