from __future__ import annotations
from pathlib import Path

REQUIRED = ["id","name","game","role","body_template","rig_template","animation_profile"]

def validate_job(job: dict) -> list[str]:
    errors = []
    for key in REQUIRED:
        if not job.get(key):
            errors.append(f"Missing required field: {key}")
    if job.get("role") not in {"hero","villain","support","boss"}:
        errors.append("role must be hero, villain, support, or boss")
    height = job.get("height_voxels", 44)
    if not isinstance(height, int) or not 16 <= height <= 128:
        errors.append("height_voxels must be an integer from 16 to 128")
    formats = job.get("export_formats", [])
    unsupported = [x for x in formats if x not in {"glb","fbx"}]
    if unsupported:
        errors.append(f"Unsupported export formats: {unsupported}")
    source = job.get("source_model")
    if source and not Path(source).exists():
        errors.append(f"source_model does not exist: {source}")
    return errors
