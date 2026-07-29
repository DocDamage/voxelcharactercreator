"""Blender-independent Phase 6 reusable-factory contracts."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


BODY_ARCHETYPES = frozenset({"female_heroic", "male_heavy", "mage_robe", "large_villain", "child_small"})
WEAPON_FAMILIES = frozenset({"sword_shield", "spear", "staff", "katana", "gunblade", "firearm", "caster"})
SECONDARY_KINDS = frozenset({"hair", "cape", "coat_tail", "skirt", "robe"})


class FactoryValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class SecondaryMotionChain:
    chain_id: str
    kind: str
    segments: tuple[str, ...]
    parent_bone: str
    stiffness: float
    damping: float
    max_angle_degrees: float
    fallback: str


@dataclass(frozen=True)
class OptimizationPolicy:
    lod_ratios: tuple[float, ...] = (1.0, 0.5, 0.25)
    material_batching: str = "palette_atlas"
    compression: str = "engine"
    incremental_previews: bool = True

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.lod_ratios or self.lod_ratios[0] != 1.0 or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1
            for value in self.lod_ratios
        ) or any(left <= right for left, right in zip(self.lod_ratios, self.lod_ratios[1:])):
            errors.append("optimization.lod_ratios must start at 1.0 and strictly decrease")
        if self.material_batching not in {"none", "palette_atlas"}:
            errors.append("optimization.material_batching must be none or palette_atlas")
        if self.compression not in {"none", "engine", "meshopt"}:
            errors.append("optimization.compression must be none, engine, or meshopt")
        return errors


def validate_secondary_motion(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return ["secondary_motion must be an array"]
    errors: list[str] = []
    identifiers: set[str] = set()
    for index, item in enumerate(value):
        prefix = f"secondary_motion[{index}]"
        required = {"chain_id", "kind", "segments", "parent_bone", "stiffness", "damping", "max_angle_degrees", "fallback"}
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"{prefix} fields must exactly match the secondary-motion contract")
            continue
        chain_id = item.get("chain_id")
        if not isinstance(chain_id, str) or not chain_id or chain_id in identifiers:
            errors.append(f"{prefix}.chain_id must be a unique non-empty string")
        else:
            identifiers.add(chain_id)
        if item.get("kind") not in SECONDARY_KINDS:
            errors.append(f"{prefix}.kind is unsupported")
        segments = item.get("segments")
        if not isinstance(segments, list) or not segments or len(segments) != len(set(segments)) or any(not isinstance(segment, str) or not segment for segment in segments):
            errors.append(f"{prefix}.segments must be a non-empty unique string array")
        if not isinstance(item.get("parent_bone"), str) or not item["parent_bone"]:
            errors.append(f"{prefix}.parent_bone must be non-empty")
        for name in ("stiffness", "damping"):
            number = item.get(name)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number <= 1:
                errors.append(f"{prefix}.{name} must be between 0 and 1")
        angle = item.get("max_angle_degrees")
        if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not 0 < angle <= 90:
            errors.append(f"{prefix}.max_angle_degrees must be above 0 and at most 90")
        if item.get("fallback") != "rigid":
            errors.append(f"{prefix}.fallback must be rigid")
    return errors


def parse_optimization(settings: dict[str, Any]) -> OptimizationPolicy:
    value = settings.get("optimization", {})
    if not isinstance(value, dict):
        raise FactoryValidationError(["settings_overrides.optimization must be an object"])
    unknown = sorted(set(value) - {"lod_ratios", "material_batching", "compression", "incremental_previews"})
    if unknown:
        raise FactoryValidationError([f"unknown optimization fields: {', '.join(unknown)}"])
    policy = OptimizationPolicy(
        lod_ratios=tuple(float(item) for item in value.get("lod_ratios", (1.0, 0.5, 0.25))) if isinstance(value.get("lod_ratios", ()), (list, tuple)) else (),
        material_batching=value.get("material_batching", "palette_atlas"),
        compression=value.get("compression", "engine"),
        incremental_previews=value.get("incremental_previews", True),
    )
    errors = policy.validate()
    if not isinstance(policy.incremental_previews, bool):
        errors.append("optimization.incremental_previews must be boolean")
    if errors:
        raise FactoryValidationError(errors)
    return policy


def preview_fingerprint(job: dict[str, Any], inputs: Iterable[Path]) -> str:
    """Hash resolved visual state while excluding animation/export-only changes."""
    settings = job.get("settings_overrides", {})
    if isinstance(settings, dict):
        # Optimization is applied after previews are rendered. Everything else
        # in settings_overrides can affect assembled geometry, rig/socket views,
        # deformation, or the diagnostic pose and must invalidate cached images.
        render_settings: Any = {key: value for key, value in settings.items() if key != "optimization"}
    else:
        # Invalid jobs are rejected before a build, but retaining the raw value
        # makes this helper deterministic and fail-safe for standalone callers.
        render_settings = settings
    render_state = {
        "source": job.get("source"),
        "asset_assembly": job.get("asset_assembly"),
        "body_template": job.get("body_template"),
        "weapon": job.get("weapon"),
        "height_voxels": job.get("height_voxels"),
        "target_height_meters": job.get("target_height_meters"),
        "palette_profile": job.get("palette_profile"),
        "accent_colors": job.get("accent_colors"),
        "part_overrides": job.get("part_overrides"),
        "rig_template": job.get("rig_template"),
        "render_profile": job.get("render_profile"),
        "render_resolution": job.get("render_resolution"),
        "settings_overrides": render_settings,
    }
    digest = hashlib.sha256(json.dumps(render_state, sort_keys=True, separators=(",", ":")).encode())
    for path in sorted(inputs, key=lambda item: str(item)):
        digest.update(str(path).encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


def measured_parallelism(metrics: Iterable[dict[str, Any]], *, cpu_count: int | None = None, memory_gb: float | None = None) -> int:
    """Choose safe worker count from measured Blender peak memory and CPU count."""
    records = list(metrics)
    cpu = max(1, cpu_count or os.cpu_count() or 1)
    peaks = [float(item["peak_memory_gb"]) for item in records if isinstance(item.get("peak_memory_gb"), (int, float)) and item["peak_memory_gb"] > 0]
    if not records or not peaks or memory_gb is None:
        return 1
    by_memory = max(1, int(max(0.0, memory_gb - 2.0) / max(peaks)))
    return max(1, min(cpu // 2 or 1, by_memory, 4))
