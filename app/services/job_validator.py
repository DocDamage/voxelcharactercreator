from __future__ import annotations

import re
from pathlib import Path


REQUIRED = ["id", "name", "game", "role", "body_template", "rig_template", "animation_profile"]
ROLES = {"hero", "villain", "support", "boss"}
EXPORT_FORMATS = {"glb", "fbx"}
SOURCE_FORMATS = {".vox", ".glb", ".gltf", ".fbx", ".obj"}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_job(job: dict, project_root: Path | None = None) -> list[str]:
    """Return all actionable validation errors for a character job."""
    if not isinstance(job, dict):
        return ["job must be a JSON object"]

    errors: list[str] = []
    for key in REQUIRED:
        value = job.get(key)
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
    else:
        unsupported = sorted({str(item) for item in formats if not isinstance(item, str) or item not in EXPORT_FORMATS})
        if unsupported:
            errors.append(f"unsupported export formats: {', '.join(map(str, unsupported))}")

    colors = job.get("accent_colors", [])
    if not isinstance(colors, list) or any(not isinstance(color, str) or not COLOR_PATTERN.fullmatch(color) for color in colors):
        errors.append("accent_colors must be an array of #RRGGBB strings")

    source = job.get("source_model")
    if source is not None and not isinstance(source, str):
        errors.append("source_model must be a path string or null")
    elif source:
        source_path = Path(source)
        if source_path.suffix.lower() not in SOURCE_FORMATS:
            errors.append(f"source_model must use one of: {', '.join(sorted(SOURCE_FORMATS))}")
        resolved = source_path if source_path.is_absolute() else (project_root / source_path if project_root else source_path)
        if not resolved.is_file():
            errors.append(f"source_model does not exist: {source}")
    return errors
