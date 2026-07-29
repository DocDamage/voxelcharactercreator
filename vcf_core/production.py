"""Phase 7 production-planning contracts with no Blender dependency."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PILOT_CHECKS = (
    "parts_resolved", "islands_valid", "grounded", "joint_pivots_valid",
    "weapon_sockets_valid", "budgets_valid", "actions_valid", "engine_import_valid",
    "artifacts_hashed", "deterministic_rebuild",
)
CAST_GAMES = tuple(f"ff{number}" for number in range(4, 11))


class ProductionValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class CapacityEstimate:
    sample_size: int
    median_hours: float
    p90_hours: float
    characters_per_person_month: float


def load_pilot_matrix(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if value.get("schema_version") != 1:
        errors.append("pilot matrix schema_version must be 1")
    entries = value.get("characters")
    if not isinstance(entries, list) or len(entries) != 10:
        errors.append("pilot matrix must contain exactly ten converted characters")
        entries = []
    identifiers: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"characters[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        identifier = entry.get("job_id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            errors.append(f"{prefix}.job_id must be unique")
        else:
            identifiers.add(identifier)
        if entry.get("source_policy") not in {"tracked_original", "user_supplied"}:
            errors.append(f"{prefix}.source_policy must preserve the approved licensing boundary")
        checks = entry.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(PILOT_CHECKS):
            errors.append(f"{prefix}.checks must contain the complete pilot acceptance matrix")
        elif any(state not in {"pending", "passed", "failed"} for state in checks.values()):
            errors.append(f"{prefix}.checks use an invalid state")
        hours = entry.get("content_hours")
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours <= 0:
            errors.append(f"{prefix}.content_hours must be a positive measured number")
    if errors:
        raise ProductionValidationError(errors)
    return value


def capacity_estimate(matrix: dict[str, Any], *, person_month_hours: float = 120.0) -> CapacityEstimate:
    records = matrix.get("characters", [])
    hours = sorted(float(item["content_hours"]) for item in records)
    if len(hours) < 10 or person_month_hours <= 0:
        raise ProductionValidationError(["capacity planning requires ten measured conversions and positive monthly capacity"])
    position = max(0, math.ceil(0.9 * len(hours)) - 1)
    p90 = hours[position]
    return CapacityEstimate(len(hours), statistics.median(hours), p90, person_month_hours / p90)


def load_cast_database(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if value.get("schema_version") != 1:
        errors.append("cast database schema_version must be 1")
    entries = value.get("characters")
    if not isinstance(entries, list):
        errors.append("cast database characters must be an array")
        entries = []
    games = {entry.get("game") for entry in entries if isinstance(entry, dict)}
    missing = sorted(set(CAST_GAMES) - games)
    if missing:
        errors.append("cast database must represent FFIV through FFX: " + ", ".join(missing))
    ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"id", "display_name", "game", "production_state", "asset_policy"}:
            errors.append(f"characters[{index}] fields do not match cast database v1")
            continue
        if entry["id"] in ids:
            errors.append(f"duplicate cast id: {entry['id']}")
        ids.add(entry["id"])
        if entry["production_state"] not in {"converted", "backlog", "blocked_assets"}:
            errors.append(f"characters[{index}].production_state is invalid")
        if entry["asset_policy"] not in {"tracked_original", "user_supplied_required"}:
            errors.append(f"characters[{index}].asset_policy is invalid")
    if errors:
        raise ProductionValidationError(errors)
    return value


def plan_reference_analysis(observation: dict[str, Any], base_job_id: str) -> dict[str, Any]:
    """Turn reviewed multi-view observations into data requests, never executable code."""
    views = observation.get("views")
    if not isinstance(views, list) or len(views) < 2:
        raise ProductionValidationError(["reference analysis requires at least two views"])
    allowed_views = {"front", "back", "left", "right", "three_quarter"}
    labels = [item.get("view") for item in views if isinstance(item, dict)]
    if len(labels) != len(views) or len(set(labels)) != len(labels) or any(label not in allowed_views for label in labels):
        raise ProductionValidationError(["reference views must have unique supported labels"])
    parts: dict[str, dict[str, Any]] = {}
    for view in views:
        for part in view.get("parts", []):
            if not isinstance(part, dict) or not isinstance(part.get("semantic"), str):
                raise ProductionValidationError(["each observed part requires a semantic label"])
            current = parts.setdefault(part["semantic"], {"semantic": part["semantic"], "observed_in": [], "notes": []})
            current["observed_in"].append(view["view"])
            if isinstance(part.get("note"), str) and part["note"]:
                current["notes"].append(part["note"])
    return {
        "schema_version": 1,
        "status": "review_required",
        "base_job_id": base_job_id,
        "job_proposal": {"variant_of": base_job_id, "accent_colors": observation.get("accent_colors", [])},
        "part_requests": sorted(parts.values(), key=lambda item: item["semantic"]),
        "prohibited_output": ["blender_code", "source_paths"],
    }


def visual_similarity(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded, explicitly advisory score over reviewed numeric features."""
    features = ("silhouette", "palette", "landmarks")
    scores: dict[str, float] = {}
    for feature in features:
        left, right = reference.get(feature), candidate.get(feature)
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right) or not left:
            raise ProductionValidationError([f"{feature} features must be non-empty equal-length arrays"])
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in (*left, *right)):
            raise ProductionValidationError([f"{feature} features must be normalized numbers from 0 to 1"])
        distance = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)) / len(left))
        scores[feature] = max(0.0, 1.0 - distance)
    score = sum(scores.values()) / len(scores)
    return {"score": round(score, 6), "components": scores, "advisory": True, "blocking": False}


def similarity_false_positive_rate(outcomes: Iterable[dict[str, Any]], *, threshold: float = 0.8) -> dict[str, Any]:
    values = list(outcomes)
    positives = [item for item in values if float(item["score"]) >= threshold]
    false = [item for item in positives if item.get("review") == "reject"]
    return {"samples": len(values), "predicted_positive": len(positives), "false_positive_rate": len(false) / len(positives) if positives else 0.0}


def validate_packaging_strategy(value: dict[str, Any]) -> None:
    errors: list[str] = []
    if value.get("schema_version") != 1 or value.get("platform") != "windows-x64":
        errors.append("packaging strategy must be Windows x64 schema v1")
    for key in ("migration", "update", "rollback", "dependencies", "signing"):
        if not isinstance(value.get(key), dict):
            errors.append(f"packaging strategy requires {key}")
    if value.get("rollback", {}).get("preserve_previous") is not True:
        errors.append("rollback must preserve the previous installation")
    if value.get("signing", {}).get("release_requires_authenticode") is not True:
        errors.append("release packaging must require Authenticode signing")
    if errors:
        raise ProductionValidationError(errors)


def package_source_distribution(root: Path, output: Path, includes: Iterable[Path]) -> dict[str, Any]:
    """Create a deterministic source distribution and return its update manifest."""
    files = sorted({path.resolve() for path in includes}, key=lambda path: path.relative_to(root.resolve()).as_posix())
    output.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(root.resolve()).as_posix()
            data = path.read_bytes()
            info = zipfile.ZipInfo(relative, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
            entries.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return {"schema_version": 1, "artifact": output.name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "files": entries}
