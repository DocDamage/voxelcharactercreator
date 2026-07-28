from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


CURRENT_JOB_SCHEMA_VERSION = 2
V1_REQUIRED = {"id", "name", "game", "role", "body_template", "rig_template", "animation_profile"}
V2_REQUIRED = V1_REQUIRED | {"schema_version", "source"}
ROLES = {"hero", "villain", "support", "boss"}
EXPORT_FORMATS = {"glb", "fbx"}
SOURCE_FORMATS = {".vox", ".glb", ".gltf", ".fbx", ".obj"}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
SAFE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

V1_KEYS = V1_REQUIRED | {
    "weapon", "source_model", "height_voxels", "palette_profile", "accent_colors",
    "export_formats", "render_profile", "render_resolution", "notes",
}
V2_KEYS = V1_KEYS - {"source_model"} | {
    "schema_version", "source", "asset_assembly", "variant_of", "part_overrides",
    "animation_packs", "export_profile", "target_height_meters", "settings_overrides",
}


class JobValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_path(value: Any, key: str, project_root: Path | None, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value:
        errors.append(f"{key} must be a non-empty relative path or null")
        return
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"{key} must be a relative path inside an approved import root")
        return
    if candidate.suffix.lower() not in SOURCE_FORMATS:
        errors.append(f"{key} must use one of: {', '.join(sorted(SOURCE_FORMATS))}")
        return
    if project_root:
        resolved = (project_root / candidate).resolve()
        approved = [project_root / "assets" / "original", project_root / "assets" / "incoming"]
        if not any(_within(resolved, root) for root in approved):
            errors.append(f"{key} must be inside assets/original or assets/incoming")
        elif not resolved.is_file():
            errors.append(f"{key} does not exist: {value}")


def migrate_job(job: dict[str, Any]) -> dict[str, Any]:
    """Return a lossless v2 representation of a v1 job."""
    if not isinstance(job, dict):
        raise JobValidationError(["job must be a JSON object"])
    version = job.get("schema_version", 1)
    if version == CURRENT_JOB_SCHEMA_VERSION:
        return deepcopy(job)
    if version != 1:
        raise JobValidationError([f"unsupported future job schema_version: {version}"])
    result = deepcopy(job)
    source_model = result.pop("source_model", None)
    result["schema_version"] = CURRENT_JOB_SCHEMA_VERSION
    result["source"] = {"mode": "model", "path": source_model} if source_model else {"mode": "proxy"}
    return result


def validate_job(job: dict[str, Any], project_root: Path | None = None, *, migrate: bool = True) -> list[str]:
    if not isinstance(job, dict):
        return ["job must be a JSON object"]
    errors: list[str] = []
    version = job.get("schema_version", 1)
    if version not in {1, CURRENT_JOB_SCHEMA_VERSION}:
        return [f"unsupported future job schema_version: {version}"]
    allowed = V1_KEYS if version == 1 else V2_KEYS
    unknown = sorted(set(job) - allowed)
    if unknown:
        errors.append(f"unknown job fields: {', '.join(unknown)}")
    required = V1_REQUIRED if version == 1 else V2_REQUIRED
    for key in sorted(required):
        value = job.get(key)
        if key in {"source", "schema_version"}:
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key} must be a non-empty string")
    job_id = job.get("id")
    if isinstance(job_id, str) and job_id and not SLUG_PATTERN.fullmatch(job_id):
        errors.append("id must contain only lowercase letters, numbers, and underscores")
    if job.get("role") not in ROLES:
        errors.append(f"role must be one of: {', '.join(sorted(ROLES))}")
    height = job.get("height_voxels", 44)
    if isinstance(height, bool) or not isinstance(height, int) or not 16 <= height <= 128:
        errors.append("height_voxels must be an integer from 16 to 128")
    resolution = job.get("render_resolution", 768)
    if isinstance(resolution, bool) or not isinstance(resolution, int) or not 64 <= resolution <= 4096:
        errors.append("render_resolution must be an integer from 64 to 4096")
    formats = job.get("export_formats", ["glb"])
    if not isinstance(formats, list) or not formats:
        errors.append("export_formats must be a non-empty array")
    elif len(formats) != len(set(formats)):
        errors.append("export_formats must not contain duplicates")
    else:
        unsupported = sorted(str(item) for item in formats if not isinstance(item, str) or item not in EXPORT_FORMATS)
        if unsupported:
            errors.append(f"unsupported export formats: {', '.join(unsupported)}")
    colors = job.get("accent_colors", [])
    if not isinstance(colors, list) or any(not isinstance(color, str) or not COLOR_PATTERN.fullmatch(color) for color in colors):
        errors.append("accent_colors must be an array of #RRGGBB strings")
    for key in ("body_template", "rig_template", "animation_profile", "palette_profile", "render_profile", "weapon"):
        value = job.get(key)
        if value is not None and (not isinstance(value, str) or not SAFE_ID_PATTERN.fullmatch(value)):
            errors.append(f"{key} must be a safe catalog ID")
    if version == 1:
        _safe_path(job.get("source_model"), "source_model", project_root, errors)
    else:
        source = job.get("source")
        if not isinstance(source, dict) or set(source) - {"mode", "path", "asset_ids"}:
            errors.append("source must be an object with mode and optional path or asset_ids")
        elif source.get("mode") not in {"proxy", "model", "assembly"}:
            errors.append("source.mode must be one of: proxy, model, assembly")
        elif source.get("mode") == "model":
            _safe_path(source.get("path"), "source.path", project_root, errors)
        elif source.get("mode") == "assembly":
            asset_ids = source.get("asset_ids")
            if not isinstance(asset_ids, list) or not asset_ids or any(not isinstance(item, str) or not SAFE_ID_PATTERN.fullmatch(item) for item in asset_ids):
                errors.append("source.asset_ids must be a non-empty array of safe catalog IDs")
            elif project_root:
                from vcf_core.assets import AssetValidationError, load_registry
                try:
                    load_registry(project_root).resolve(asset_ids, body_template=job.get("body_template", ""))
                except AssetValidationError as exc:
                    errors.extend(exc.errors)
        elif source.get("mode") == "proxy" and (source.get("path") or source.get("asset_ids")):
            errors.append("proxy source must not declare path or asset_ids")
        overrides = job.get("part_overrides", {})
        if not isinstance(overrides, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in overrides.items()):
            errors.append("part_overrides must map semantic names to source part names")
        settings = job.get("settings_overrides", {})
        if not isinstance(settings, dict):
            errors.append("settings_overrides must be an object")
        elif "vox_meshing_mode" in settings and settings["vox_meshing_mode"] not in {"greedy", "surface", "cubes"}:
            errors.append("settings_overrides.vox_meshing_mode must be greedy, surface, or cubes")
    return errors


def load_job(path: Path, project_root: Path | None = None) -> dict[str, Any]:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobValidationError([f"could not read job {path}: {exc}"]) from exc
    errors = validate_job(job, project_root)
    if errors:
        raise JobValidationError(errors)
    return migrate_job(job)
