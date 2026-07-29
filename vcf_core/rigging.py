"""Phase 3 semantic-part and Rig Template v1 contracts.

This module deliberately has no Blender dependency.  The resolver can therefore
be used to validate a build plan before Blender opens, while the Blender stages
can use the same vocabulary and bone mapping at execution time.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


RIG_TEMPLATE_VERSION = 1

# A role is either required by the humanoid pilot or is an optional, but still
# addressable, piece of character content.  Every role maps to exactly one
# parent bone in the rigid pilot bind mode.
REQUIRED_HUMANOID_ROLES = (
    "head", "torso", "pelvis", "upper_arm_l", "upper_arm_r",
    "lower_arm_l", "lower_arm_r", "hand_l", "hand_r", "upper_leg_l",
    "upper_leg_r", "lower_leg_l", "lower_leg_r", "foot_l", "foot_r",
)
OPTIONAL_ROLES = (
    "hair", "coat", "cape", "cloth", "glove_l", "glove_r", "boot_l", "boot_r",
    "pauldron_l", "pauldron_r",
    "weapon", "shield", "accessory",
)
SEMANTIC_ROLES = frozenset(REQUIRED_HUMANOID_ROLES + OPTIONAL_ROLES)
# Rig Template v1 reserves #FF0001 through #FF001C as exact semantic
# marker colors in the stable taxonomy order. Import adapters remove ambiguity
# by converting these palette values to role labels before resolution.
MARKER_ROLE_BY_RGB = {
    (255, 0, index): role
    for index, role in enumerate(REQUIRED_HUMANOID_ROLES + OPTIONAL_ROLES, start=1)
}

REQUIRED_TEMPLATE_JOINTS = frozenset({
    "root", "pelvis", "spine", "neck", "head",
    "shoulder.L", "elbow.L", "wrist.L", "shoulder.R", "elbow.R", "wrist.R",
    "hip.L", "knee.L", "ankle.L", "hip.R", "knee.R", "ankle.R",
})
REQUIRED_SOCKET_BONES = frozenset({
    "weapon_socket.R", "off_hand_socket.L", "back_socket", "waist_socket",
    "effect_socket", "projectile_socket",
})
SAFE_TEMPLATE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _valid_vector(value: object) -> bool:
    return isinstance(value, (tuple, list)) and len(value) == 3 and all(_finite_number(axis) for axis in value)

BONE_BY_ROLE = {
    "head": "head", "hair": "head",
    "torso": "spine", "coat": "spine", "cape": "spine", "cloth": "spine",
    "pelvis": "pelvis", "accessory": "pelvis",
    "upper_arm_l": "upper_arm.L", "upper_arm_r": "upper_arm.R",
    "lower_arm_l": "forearm.L", "lower_arm_r": "forearm.R",
    "hand_l": "hand.L", "hand_r": "hand.R", "glove_l": "hand.L", "glove_r": "hand.R",
    "upper_leg_l": "thigh.L", "upper_leg_r": "thigh.R",
    "lower_leg_l": "shin.L", "lower_leg_r": "shin.R",
    "foot_l": "foot.L", "foot_r": "foot.R", "boot_l": "foot.L", "boot_r": "foot.R",
    "pauldron_l": "upper_arm.L", "pauldron_r": "upper_arm.R",
    "weapon": "weapon_socket.R", "shield": "off_hand_socket.L",
}

# Historical profile strings use either compact or Blender-like names.  These
# aliases are considered only after explicit job and manifest data.
NAME_ALIASES = {
    "upper_arm.l": "upper_arm_l", "upper_arm.r": "upper_arm_r",
    "forearm.l": "lower_arm_l", "forearm.r": "lower_arm_r",
    "thigh.l": "upper_leg_l", "thigh.r": "upper_leg_r",
    "shin.l": "lower_leg_l", "shin.r": "lower_leg_r",
    "heavy_sword": "weapon", "sword": "weapon",
}


class PartResolutionError(ValueError):
    """Raised where a required role cannot be resolved deterministically."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class PartCandidate:
    """Blender-independent description of one editable source object."""

    name: str
    asset_id: str | None = None
    semantic_tags: tuple[str, ...] = ()
    layer_name: str | None = None
    marker_colors: tuple[str, ...] = ()
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    component_count: int = 1


@dataclass(frozen=True)
class ResolutionTrace:
    role: str
    source: str
    candidate: str | None
    confidence: float
    detail: str


@dataclass(frozen=True)
class PartResolution:
    role: str
    candidate: str
    confidence: float
    source: str
    parent_bone: str
    trace: tuple[ResolutionTrace, ...] = ()


@dataclass(frozen=True)
class RigTemplate:
    schema_version: int
    template_id: str
    required_roles: tuple[str, ...]
    bone_by_role: dict[str, str]
    normalized_joints: dict[str, tuple[float, float, float]]
    sockets: dict[str, tuple[str, tuple[float, float, float]]]
    tolerances: dict[str, float]
    bind_modes: tuple[str, ...] = ("rigid",)
    scale_policy: str = "target_height"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.schema_version != RIG_TEMPLATE_VERSION:
            errors.append(f"rig template schema_version must be {RIG_TEMPLATE_VERSION}")
        if not isinstance(self.template_id, str) or not SAFE_TEMPLATE_ID.fullmatch(self.template_id):
            errors.append("rig template template_id must be a safe catalog ID")
        if not self.required_roles or len(self.required_roles) != len(set(self.required_roles)):
            errors.append("rig template required_roles must be a non-empty unique list")
        unknown_required = sorted(set(self.required_roles) - SEMANTIC_ROLES)
        if unknown_required:
            errors.append(f"rig template has unknown required roles: {', '.join(unknown_required)}")
        missing = sorted(SEMANTIC_ROLES - set(self.bone_by_role))
        if missing:
            errors.append(f"rig template lacks semantic bone mapping for: {', '.join(missing)}")
        if any(not isinstance(bone, str) or not bone for bone in self.bone_by_role.values()):
            errors.append("rig template bone names must be non-empty strings")
        required_bone_names = [self.bone_by_role[role] for role in self.required_roles if role in self.bone_by_role]
        if "root" in required_bone_names or len(required_bone_names) != len(set(required_bone_names)):
            errors.append("rig template required semantic roles must map to distinct bones")
        missing_joints = sorted(REQUIRED_TEMPLATE_JOINTS - set(self.normalized_joints))
        if missing_joints:
            errors.append(f"rig template lacks normalized joints: {', '.join(missing_joints)}")
        if any(not _valid_vector(point) for point in self.normalized_joints.values()):
            errors.append("rig template normalized joints must contain finite three-number coordinates")
        missing_sockets = sorted(REQUIRED_SOCKET_BONES - set(self.sockets))
        if missing_sockets:
            errors.append(f"rig template lacks required sockets: {', '.join(missing_sockets)}")
        constructed_bones = {"root", *required_bone_names}
        invalid_socket_parents = sorted(name for name, (parent, _offset) in self.sockets.items() if parent not in constructed_bones)
        if invalid_socket_parents:
            errors.append(f"rig template sockets reference unmapped parent bones: {', '.join(invalid_socket_parents)}")
        if any(not _valid_vector(offset) for _parent, offset in self.sockets.values()):
            errors.append("rig template socket offsets must contain finite three-number coordinates")
        expected_tolerances = {"ground_meters", "symmetry_meters", "socket_alignment_meters", "min_limb_scale", "max_limb_scale"}
        if set(self.tolerances) != expected_tolerances or any(not _finite_number(value) or value <= 0 for value in self.tolerances.values()):
            errors.append("rig template tolerances must be finite positive numbers")
        elif self.tolerances["min_limb_scale"] > self.tolerances["max_limb_scale"]:
            errors.append("rig template min_limb_scale must not exceed max_limb_scale")
        if "rigid" not in self.bind_modes:
            errors.append("rig template must support rigid binding")
        if self.scale_policy != "target_height":
            errors.append("rig template scale_policy must be target_height")
        return errors


def standard_male_template() -> RigTemplate:
    """Return the versioned humanoid pilot template in normalized body space."""
    joints = {
        "root": (0.0, 0.0, 0.0), "pelvis": (0.0, 0.0, 0.43), "spine": (0.0, 0.0, 0.58),
        "neck": (0.0, 0.0, 0.78), "head": (0.0, 0.0, 0.91),
        "shoulder.L": (0.18, 0.0, 0.75), "elbow.L": (0.31, 0.0, 0.57), "wrist.L": (0.38, 0.0, 0.43),
        "shoulder.R": (-0.18, 0.0, 0.75), "elbow.R": (-0.31, 0.0, 0.57), "wrist.R": (-0.38, 0.0, 0.43),
        "hip.L": (0.10, 0.0, 0.40), "knee.L": (0.11, 0.0, 0.20), "ankle.L": (0.11, 0.0, 0.04),
        "hip.R": (-0.10, 0.0, 0.40), "knee.R": (-0.11, 0.0, 0.20), "ankle.R": (-0.11, 0.0, 0.04),
    }
    return RigTemplate(
        schema_version=RIG_TEMPLATE_VERSION,
        template_id="humanoid_standard",
        required_roles=REQUIRED_HUMANOID_ROLES,
        bone_by_role=dict(BONE_BY_ROLE),
        normalized_joints=joints,
        sockets={
            "weapon_socket.R": ("hand.R", (0.0, 0.0, 0.0)),
            "off_hand_socket.L": ("hand.L", (0.0, 0.0, 0.0)),
            "back_socket": ("spine", (0.0, 0.16, 0.10)),
            "waist_socket": ("pelvis", (0.0, 0.13, 0.0)),
            "effect_socket": ("hand.R", (0.0, -0.08, 0.0)),
            "projectile_socket": ("hand.R", (0.0, -0.18, 0.0)),
        },
        tolerances={"ground_meters": 0.002, "symmetry_meters": 0.03, "socket_alignment_meters": 0.001, "min_limb_scale": 0.5, "max_limb_scale": 1.5},
    )


def get_rig_template(template_id: str) -> RigTemplate:
    # Heavy is intentionally an alias until a distinct body topology requires a
    # new template.  This keeps legacy jobs valid while preserving a single v1
    # humanoid contract.
    if template_id in {"humanoid_standard", "humanoid_heavy", "humanoid_female", "humanoid_mage", "humanoid_large", "humanoid_small"}:
        source = Path(__file__).resolve().parents[1] / "config" / "rig_templates" / "humanoid_standard.v1.json"
        template = load_rig_template(source) if source.is_file() else standard_male_template()
        if template_id != template.template_id:
            return RigTemplate(**{**template.__dict__, "template_id": template_id})
        return template
    raise PartResolutionError([f"unknown rig template: {template_id}"])


def load_rig_template(path: Path) -> RigTemplate:
    """Load and validate a versioned Rig Template v1 document."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PartResolutionError([f"could not read rig template {path}: {exc}"]) from exc
    if not isinstance(payload, dict):
        raise PartResolutionError(["rig template must be a JSON object"])
    required = {"schema_version", "template_id", "required_roles", "bone_by_role", "normalized_joints", "sockets", "tolerances", "bind_modes", "scale_policy"}
    errors = []
    if set(payload) != required:
        errors.append("rig template fields must exactly match Rig Template v1")
    if not isinstance(payload.get("required_roles"), list) or any(not isinstance(role, str) for role in payload.get("required_roles", [])):
        errors.append("rig template required_roles must be a string array")
    if not isinstance(payload.get("bone_by_role"), dict) or any(not isinstance(role, str) or not isinstance(bone, str) for role, bone in payload.get("bone_by_role", {}).items()):
        errors.append("rig template bone_by_role must map strings to strings")
    joints = payload.get("normalized_joints", {})
    if not isinstance(joints, dict) or any(not isinstance(point, list) or len(point) != 3 or any(isinstance(axis, bool) or not isinstance(axis, (int, float)) or not math.isfinite(float(axis)) for axis in point) for point in joints.values()):
        errors.append("rig template normalized_joints must map to three-number coordinates")
    sockets = payload.get("sockets", {})
    if not isinstance(sockets, dict) or any(
        not isinstance(value, dict)
        or set(value) != {"bone", "offset"}
        or not isinstance(value["bone"], str)
        or not value["bone"]
        or not isinstance(value["offset"], list)
        or len(value["offset"]) != 3
        or any(isinstance(axis, bool) or not isinstance(axis, (int, float)) or not math.isfinite(float(axis)) for axis in value["offset"])
        for value in sockets.values()
    ):
        errors.append("rig template sockets must declare a bone and three-number offset")
    if not isinstance(payload.get("bind_modes"), list) or any(not isinstance(mode, str) for mode in payload.get("bind_modes", [])):
        errors.append("rig template bind_modes must be a string array")
    tolerances = payload.get("tolerances", {})
    required_tolerances = {"ground_meters", "symmetry_meters", "socket_alignment_meters", "min_limb_scale", "max_limb_scale"}
    if not isinstance(tolerances, dict) or set(tolerances) != required_tolerances or any(isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0 for value in tolerances.values()) or tolerances.get("min_limb_scale", 1) > tolerances.get("max_limb_scale", 0):
        errors.append("rig template tolerances must declare valid ground, symmetry, socket, and limb-scale limits")
    if payload.get("scale_policy") != "target_height":
        errors.append("rig template scale_policy must be target_height")
    if errors:
        raise PartResolutionError(errors)
    template = RigTemplate(
        schema_version=payload["schema_version"], template_id=payload["template_id"], required_roles=tuple(payload["required_roles"]),
        bone_by_role=dict(payload["bone_by_role"]), normalized_joints={name: tuple(value) for name, value in joints.items()},
        sockets={name: (value["bone"], tuple(float(axis) for axis in value["offset"])) for name, value in sockets.items()}, tolerances={name: float(value) for name, value in tolerances.items()}, bind_modes=tuple(payload["bind_modes"]), scale_policy=payload["scale_policy"],
    )
    errors = template.validate()
    if errors:
        raise PartResolutionError(errors)
    return template


def _normalized(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _name_role(candidate: PartCandidate) -> str | None:
    values = (candidate.name, candidate.asset_id or "", candidate.layer_name or "")
    for value in values:
        clean = _normalized(value)
        if clean in SEMANTIC_ROLES:
            return clean
        if clean in NAME_ALIASES:
            return NAME_ALIASES[clean]
        for alias, role in NAME_ALIASES.items():
            if clean.endswith("_" + alias):
                return role
        for role in SEMANTIC_ROLES:
            if clean.endswith("_" + role) or clean == role:
                return role
    return None


def _spatial_guess(candidates: Iterable[PartCandidate], role: str) -> PartCandidate | None:
    """Conservative fallback for untagged simple humanoid pieces.

    It is deliberately narrow: only head/feet and paired limbs with a clearly
    separated center are inferred.  Everything else is returned as ambiguous.
    """
    bounded = [candidate for candidate in candidates if candidate.bounds]
    if not bounded:
        return None
    center = lambda item: tuple((item.bounds[0][axis] + item.bounds[1][axis]) / 2 for axis in range(3))  # type: ignore[index]
    if role == "head":
        return max(bounded, key=lambda item: center(item)[2])
    if role in {"foot_l", "foot_r"}:
        lowest = sorted(bounded, key=lambda item: center(item)[2])[:2]
        if len(lowest) == 2 and abs(center(lowest[0])[0] - center(lowest[1])[0]) > 0.01:
            return max(lowest, key=lambda item: center(item)[0]) if role.endswith("_l") else min(lowest, key=lambda item: center(item)[0])
    return None


def resolve_parts(
    candidates: Iterable[PartCandidate],
    *,
    part_overrides: dict[str, str] | None = None,
    template: RigTemplate | None = None,
    confidence_threshold: float = 0.75,
) -> tuple[dict[str, PartResolution], list[ResolutionTrace]]:
    """Resolve each source object once using the Phase 3 precedence contract.

    Conflicting explicit candidates and low-confidence heuristics raise a
    structured error rather than allowing a plausible but incorrect bind.
    """
    template = template or standard_male_template()
    errors = template.validate()
    candidates = list(candidates)
    names = {item.name for item in candidates}
    if len(names) != len(candidates):
        duplicates = sorted(name for name in names if sum(item.name == name for item in candidates) > 1)
        errors.append(f"PART_CONFLICT: duplicate source part names: {', '.join(duplicates)}")
    overrides = part_overrides or {}
    unknown_overrides = sorted(set(overrides) - SEMANTIC_ROLES)
    if unknown_overrides:
        errors.append(f"part_overrides use unknown semantic roles: {', '.join(unknown_overrides)}")
    missing_override_sources = sorted(value for value in overrides.values() if value not in names)
    if missing_override_sources:
        errors.append(f"part_overrides reference unknown source parts: {', '.join(missing_override_sources)}")
    if errors:
        raise PartResolutionError(errors)

    resolutions: dict[str, PartResolution] = {}
    traces: list[ResolutionTrace] = []
    used: set[str] = set()
    all_roles = tuple(template.required_roles) + tuple(role for role in OPTIONAL_ROLES if role not in template.required_roles)
    for role in all_roles:
        source = ""
        confidence = 0.0
        selected: PartCandidate | None = None
        if role in overrides:
            selected = next(item for item in candidates if item.name == overrides[role])
            source, confidence = "job_override", 1.0
        else:
            tagged = []
            for item in candidates:
                normalized_tags = {_normalized(tag) for tag in item.semantic_tags}
                if role in normalized_tags or any(NAME_ALIASES.get(tag) == role for tag in normalized_tags):
                    tagged.append(item)
            if len(tagged) == 1:
                selected, source, confidence = tagged[0], "asset_manifest", 1.0
            elif len(tagged) > 1:
                errors.append(f"PART_CONFLICT: {role} has multiple manifest-tagged candidates: {', '.join(item.name for item in tagged)}")
                continue
            else:
                named = [item for item in candidates if _name_role(item) == role]
                if len(named) == 1:
                    selected, source, confidence = named[0], "name_or_layer", 0.9
                elif len(named) > 1:
                    errors.append(f"PART_CONFLICT: {role} has multiple name/layer candidates: {', '.join(item.name for item in named)}")
                    continue
                else:
                    marker = [item for item in candidates if role in {_normalized(color) for color in item.marker_colors}]
                    if len(marker) == 1:
                        selected, source, confidence = marker[0], "color_marker", 0.8
                    else:
                        selected = _spatial_guess((item for item in candidates if item.name not in used), role)
                        if selected:
                            source, confidence = "spatial_heuristic", 0.6
        if not selected:
            if role in template.required_roles:
                errors.append(f"PART_MISSING: required semantic part {role} was not resolved; add part_overrides.{role}")
            continue
        trace = ResolutionTrace(
            role, source, selected.name, confidence,
            f"resolved {selected.name} via {source}; mesh_components={selected.component_count}",
        )
        traces.append(trace)
        if confidence < confidence_threshold:
            errors.append(f"PART_NEEDS_MAPPING: {role} resolved to {selected.name} at {confidence:.2f}; add part_overrides.{role}")
            continue
        if selected.name in used:
            errors.append(f"PART_CONFLICT: source part {selected.name} was assigned to more than one semantic role")
            continue
        used.add(selected.name)
        parent_bone = template.bone_by_role.get(role)
        if not parent_bone:
            errors.append(f"PART_UNSUPPORTED_ROLE: rig template {template.template_id} has no bone for {role}")
            continue
        resolutions[role] = PartResolution(role, selected.name, confidence, source, parent_bone, (trace,))

    # Any pilot asset which did not map to a taxonomy role is a hard failure;
    # silently leaving it unbound violates the Phase 0 status contract.
    unresolved = sorted(names - used)
    if unresolved:
        errors.append(f"PART_NEEDS_MAPPING: source parts have no semantic role: {', '.join(unresolved)}")
    if errors:
        raise PartResolutionError(errors)
    return resolutions, traces


def persist_part_overrides(job: dict[str, Any], resolutions: dict[str, PartResolution]) -> dict[str, Any]:
    """Return a schema-valid Job v2 copy whose mappings replay identically."""
    copied = dict(job)
    existing = copied.get("part_overrides", {})
    if not isinstance(existing, dict):
        raise PartResolutionError(["part_overrides must be an object before mappings can be persisted"])
    copied["part_overrides"] = {**existing, **{role: resolution.candidate for role, resolution in resolutions.items()}}
    return copied


def candidate_from_mapping(value: dict[str, Any]) -> PartCandidate:
    """Convenience adapter for JSON-like previews and unit tests."""
    bounds = value.get("bounds")
    return PartCandidate(
        name=str(value["name"]), asset_id=value.get("asset_id"),
        semantic_tags=tuple(value.get("semantic_tags", ())), layer_name=value.get("layer_name"),
        marker_colors=tuple(value.get("marker_colors", ())),
        bounds=tuple(tuple(float(axis) for axis in corner) for corner in bounds) if bounds else None,  # type: ignore[arg-type]
        component_count=int(value.get("component_count", 1)),
    )
