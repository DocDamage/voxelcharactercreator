"""Phase 8 advanced-character, authoring, and large-cast contracts.

The types in this module intentionally avoid Blender.  They are the approval
boundary shared by the desktop editor, validation CLI, and Blender worker.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


TOPOLOGIES = frozenset({"quadruped", "flying", "multi_arm", "boss"})
ENGINE_CHECKS = frozenset({"parts", "rig", "animation", "export", "godot"})
BIND_MODES = frozenset({"rigid", "deform"})


class AdvancedValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _safe_id(value: object) -> bool:
    return isinstance(value, str) and bool(value) and all(
        character.islower() or character.isdigit() or character in "_.-" for character in value
    ) and value[0].isalnum()


def _vector(value: object) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(
        not isinstance(axis, bool) and isinstance(axis, (int, float)) and math.isfinite(float(axis)) for axis in value
    )


@dataclass(frozen=True)
class TopologyRig:
    template_id: str
    topology: str
    required_roles: tuple[str, ...]
    bones: dict[str, str | None]
    role_bones: dict[str, str]
    sockets: dict[str, tuple[str, tuple[float, float, float]]]
    engine_checks: frozenset[str]
    max_bones: int
    fallback_template: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not _safe_id(self.template_id): errors.append("advanced rig template_id must be a safe catalog ID")
        if self.topology not in TOPOLOGIES: errors.append("advanced rig topology is unsupported")
        if not self.required_roles or len(self.required_roles) != len(set(self.required_roles)):
            errors.append("advanced rig required_roles must be non-empty and unique")
        missing_roles = sorted(set(self.required_roles) - set(self.role_bones))
        if missing_roles: errors.append("advanced rig lacks role bones: " + ", ".join(missing_roles))
        if "root" not in self.bones or self.bones.get("root") is not None:
            errors.append("advanced rig must contain one parentless root bone")
        for bone, parent in self.bones.items():
            if not _safe_id(bone): errors.append(f"advanced rig has invalid bone name: {bone}")
            if parent is not None and parent not in self.bones: errors.append(f"advanced rig bone {bone} has unknown parent {parent}")
            seen: set[str] = set()
            cursor: str | None = bone
            while cursor is not None and cursor in self.bones:
                if cursor in seen:
                    errors.append(f"advanced rig bone hierarchy contains a cycle at {bone}")
                    break
                seen.add(cursor); cursor = self.bones[cursor]
        if any(bone not in self.bones for bone in self.role_bones.values()):
            errors.append("advanced rig role_bones reference unknown bones")
        if any(parent not in self.bones for parent, _offset in self.sockets.values()):
            errors.append("advanced rig sockets reference unknown bones")
        if self.engine_checks != ENGINE_CHECKS: errors.append("advanced rig must require the complete Blender/Godot gate")
        if isinstance(self.max_bones, bool) or not 1 <= self.max_bones <= 256 or len(self.bones) > self.max_bones:
            errors.append("advanced rig exceeds its bounded bone budget")
        if not _safe_id(self.fallback_template): errors.append("advanced rig requires a safe rigid fallback template")
        return errors


def load_topology_rig(path: Path) -> TopologyRig:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise AdvancedValidationError([f"could not read advanced rig {path}: {exc}"]) from exc
    required = {"schema_version", "template_id", "topology", "required_roles", "bones", "role_bones", "sockets", "engine_checks", "max_bones", "fallback_template"}
    errors: list[str] = []
    if not isinstance(value, dict) or set(value) != required: errors.append("advanced rig fields must exactly match schema v1")
    if value.get("schema_version") != 1: errors.append("advanced rig schema_version must be 1")
    bones = value.get("bones", {})
    sockets = value.get("sockets", {})
    if not isinstance(bones, dict) or any(not isinstance(k, str) or (v is not None and not isinstance(v, str)) for k, v in bones.items()): errors.append("advanced rig bones must map names to parent names or null")
    if not isinstance(sockets, dict) or any(not isinstance(v, dict) or set(v) != {"bone", "offset"} or not isinstance(v["bone"], str) or not _vector(v["offset"]) for v in sockets.values()): errors.append("advanced rig sockets must declare bone and finite offset")
    if errors: raise AdvancedValidationError(errors)
    result = TopologyRig(value["template_id"], value["topology"], tuple(value["required_roles"]), dict(bones), dict(value["role_bones"]), {k:(v["bone"], tuple(float(x) for x in v["offset"])) for k,v in sockets.items()}, frozenset(value["engine_checks"]), value["max_bones"], value["fallback_template"])
    errors = result.validate()
    if errors: raise AdvancedValidationError(errors)
    return result


def validate_boss_composition(value: Any) -> list[str]:
    if value is None: return []
    if not isinstance(value, dict): return ["boss_composition must be an object"]
    required = {"composition_id", "attachments", "phases", "budgets"}
    errors: list[str] = []
    if set(value) != required: errors.append("boss_composition fields must exactly match the Phase 8 contract")
    if not _safe_id(value.get("composition_id")): errors.append("boss_composition composition_id must be a safe catalog ID")
    attachments = value.get("attachments", [])
    if not isinstance(attachments, list) or not 1 <= len(attachments) <= 64: errors.append("boss_composition attachments must contain 1 to 64 entries"); attachments = []
    ids: set[str] = set(); parents: dict[str, str | None] = {}
    for index, item in enumerate(attachments):
        if not isinstance(item, dict) or set(item) != {"id", "asset_id", "parent", "socket"}: errors.append(f"boss_composition.attachments[{index}] is invalid"); continue
        identifier = item["id"]
        if not _safe_id(identifier) or identifier in ids: errors.append(f"boss attachment {index} id must be unique and safe"); continue
        ids.add(identifier); parents[identifier] = item["parent"]
        if not _safe_id(item["asset_id"]) or not _safe_id(item["socket"]): errors.append(f"boss attachment {identifier} has invalid catalog references")
    roots = [name for name, parent in parents.items() if parent is None]
    if len(roots) != 1: errors.append("boss_composition must have exactly one root attachment")
    for name in parents:
        seen: set[str] = set(); cursor: str | None = name; depth = 0
        while cursor is not None:
            if cursor in seen: errors.append(f"boss attachment hierarchy contains a cycle at {name}"); break
            seen.add(cursor); cursor = parents.get(cursor, "__missing__"); depth += 1
            if cursor == "__missing__": errors.append(f"boss attachment {name} references an unknown parent"); break
            if depth > 4: errors.append(f"boss attachment {name} exceeds maximum depth 4"); break
    phases = value.get("phases", [])
    if not isinstance(phases, list) or not 2 <= len(phases) <= 8: errors.append("boss_composition phases must contain 2 to 8 variants")
    else:
        phase_ids=[]
        for index,item in enumerate(phases):
            if not isinstance(item,dict) or set(item)!={"phase_id","enabled"} or not _safe_id(item.get("phase_id")) or not isinstance(item.get("enabled"),list) or not item["enabled"] or len(item["enabled"])!=len(set(item["enabled"])) or not set(item["enabled"]).issubset(ids): errors.append(f"boss phase {index} must reference a unique, non-empty subset of attachments")
            else: phase_ids.append(item["phase_id"])
        if len(phase_ids)!=len(set(phase_ids)): errors.append("boss phase IDs must be unique")
    budgets = value.get("budgets", {})
    if not isinstance(budgets, dict) or set(budgets) != {"max_bones", "max_objects", "max_triangles"} or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in budgets.values()): errors.append("boss_composition budgets must be positive integer bone, object, and triangle limits")
    return errors


def validate_deformation(value: Any) -> list[str]:
    if value is None: return []
    required = {"mode", "max_influences", "normalize_weights", "secondary_solver", "bake", "fallback"}
    if not isinstance(value, dict) or set(value) != required: return ["deformation fields must exactly match the Phase 8 contract"]
    errors: list[str] = []
    if value["mode"] not in BIND_MODES: errors.append("deformation.mode must be rigid or deform")
    if isinstance(value["max_influences"], bool) or not isinstance(value["max_influences"], int) or not 1 <= value["max_influences"] <= 4: errors.append("deformation.max_influences must be from 1 to 4")
    if value["normalize_weights"] is not True: errors.append("deformation weights must be normalized")
    if value["secondary_solver"] not in {"none", "spring_bones"}: errors.append("deformation.secondary_solver is unsupported")
    if not isinstance(value["bake"], bool): errors.append("deformation.bake must be boolean")
    if value["fallback"] != "rigid": errors.append("deformation.fallback must be rigid")
    return errors


def validate_spring_motion(value: Any) -> list[str]:
    if value is None:return []
    if not isinstance(value,list) or not 1<=len(value)<=8:return ["spring_motion must contain 1 to 8 chains"]
    errors=[]; chains=set(); used=set(); required={"chain_id","bones","stiffness","damping","max_angle_degrees","solver","bake","fallback"}
    for index,item in enumerate(value):
        prefix=f"spring_motion[{index}]"
        if not isinstance(item,dict) or set(item)!=required:errors.append(f"{prefix} fields must exactly match the spring-motion contract");continue
        if not _safe_id(item["chain_id"]) or item["chain_id"] in chains:errors.append(f"{prefix}.chain_id must be unique and safe")
        chains.add(item["chain_id"])
        bones=item["bones"]
        if not isinstance(bones,list) or not bones or len(bones)!=len(set(bones)) or any(not _safe_id(bone) for bone in bones):errors.append(f"{prefix}.bones must be a non-empty unique bone list")
        elif used.intersection(bones):errors.append(f"{prefix}.bones overlap another spring chain")
        else:used.update(bones)
        for name in ("stiffness","damping"):
            if isinstance(item[name],bool) or not isinstance(item[name],(int,float)) or not 0<=item[name]<=1:errors.append(f"{prefix}.{name} must be from 0 to 1")
        if isinstance(item["max_angle_degrees"],bool) or not isinstance(item["max_angle_degrees"],(int,float)) or not 0<item["max_angle_degrees"]<=90:errors.append(f"{prefix}.max_angle_degrees must be above 0 and at most 90")
        if item["solver"]!="deterministic_spring" or item["bake"] is not True or item["fallback"]!="rigid":errors.append(f"{prefix} must use baked deterministic_spring with rigid fallback")
    return errors


def deterministic_weights(distances: dict[str, float], max_influences: int = 4) -> dict[str, float]:
    """Create stable inverse-distance weights, including exact-hit behavior."""
    if not distances or not 1 <= max_influences <= 4 or any(not _safe_id(k) or not isinstance(v, (int,float)) or isinstance(v,bool) or not math.isfinite(v) or v < 0 for k,v in distances.items()):
        raise AdvancedValidationError(["weight inputs require safe bones, finite distances, and 1 to 4 influences"])
    ordered = sorted(distances.items(), key=lambda item: (item[1], item[0]))[:max_influences]
    exact = [name for name, distance in ordered if distance == 0]
    if exact: return {name: round(1 / len(exact), 8) for name in exact}
    inverse = [(name, 1 / distance) for name, distance in ordered]; total = sum(value for _name, value in inverse)
    result = {name: round(value / total, 8) for name, value in inverse}
    first = next(iter(result)); result[first] = round(result[first] + (1.0 - sum(result.values())), 8)
    return result


def create_generation_proposal(*, prompt: str, generator: str, outputs: Iterable[Path], root: Path) -> dict[str, Any]:
    paths = list(outputs)
    approved_roots = ((root / "assets" / "generated").resolve(), (root / "assets" / "incoming").resolve())
    records = []
    for path in paths:
        resolved = path.resolve()
        if not path.is_file() or not any(resolved.is_relative_to(base) for base in approved_roots):
            raise AdvancedValidationError([f"generated output is missing or outside approved roots: {path}"])
        data = path.read_bytes(); records.append({"path": resolved.relative_to(root.resolve()).as_posix(), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return {"schema_version":1, "status":"review_required", "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(), "generator":generator, "outputs":records, "approval":None, "prohibited_actions":["job_apply", "manifest_publish", "license_inference"]}


def approve_generated_asset(proposal: dict[str, Any], *, reviewer: str, asset_id: str, author: str, license_id: str, semantic_tags: list[str]) -> dict[str, Any]:
    if proposal.get("status") != "review_required" or proposal.get("approval") is not None: raise AdvancedValidationError(["only an unreviewed generation proposal can be approved"])
    if not all(_safe_id(item) for item in (asset_id, license_id)) or not reviewer.strip() or not author.strip() or not semantic_tags: raise AdvancedValidationError(["approval requires reviewer, author, safe asset/license IDs, and semantic tags"])
    result = deepcopy(proposal); result["status"] = "approved"; result["approval"] = {"reviewer":reviewer, "asset_id":asset_id, "author":author, "license":license_id, "semantic_tags":list(semantic_tags)}
    return result


class SceneEditorDocument:
    """Undoable direct-placement model used by the 3D editor UI."""
    def __init__(self, job: dict[str, Any]): self._states = [deepcopy(job)]; self._cursor = 0
    @property
    def value(self) -> dict[str, Any]: return deepcopy(self._states[self._cursor])
    def apply_transform(self, part: str, *, location: list[float], rotation: list[float], scale: list[float]) -> dict[str, Any]:
        if not _safe_id(part) or not all(_vector(value) for value in (location, rotation, scale)) or any(axis <= 0 for axis in scale): raise AdvancedValidationError(["editor transform requires a safe part and finite location/rotation/positive scale vectors"])
        candidate = self.value; transforms = candidate.setdefault("settings_overrides", {}).setdefault("part_transforms", {}); transforms[part] = {"location":location, "rotation_degrees":rotation, "scale":scale}; return self._commit(candidate)
    def set_socket(self, name: str, bone: str, offset: list[float]) -> dict[str, Any]:
        if not _safe_id(name) or not _safe_id(bone) or not _vector(offset): raise AdvancedValidationError(["editor socket requires safe names and a finite offset"])
        candidate = self.value; candidate.setdefault("settings_overrides", {}).setdefault("socket_overrides", {})[name] = {"bone":bone,"offset":offset}; return self._commit(candidate)
    def _commit(self, value: dict[str, Any]) -> dict[str, Any]: self._states = self._states[:self._cursor+1] + [value]; self._cursor += 1; return self.value
    def undo(self) -> dict[str, Any]: self._cursor=max(0,self._cursor-1); return self.value
    def redo(self) -> dict[str, Any]: self._cursor=min(len(self._states)-1,self._cursor+1); return self.value


def validate_editor_settings(settings: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    transforms = settings.get("part_transforms", {})
    if not isinstance(transforms, dict): errors.append("part_transforms must be an object"); transforms = {}
    for name, value in transforms.items():
        if not _safe_id(name) or not isinstance(value, dict) or set(value) != {"location","rotation_degrees","scale"} or not all(_vector(value.get(key)) for key in ("location","rotation_degrees","scale")) or any(axis <= 0 for axis in value.get("scale", [])):
            errors.append(f"part_transforms.{name} must declare finite location, rotation_degrees, and positive scale vectors")
    sockets = settings.get("socket_overrides", {})
    if not isinstance(sockets, dict): errors.append("socket_overrides must be an object"); sockets = {}
    for name, value in sockets.items():
        if not _safe_id(name) or not isinstance(value, dict) or set(value) != {"bone","offset"} or not _safe_id(value.get("bone")) or not _vector(value.get("offset")):
            errors.append(f"socket_overrides.{name} must declare a safe bone and finite offset")
    return errors


def load_cast_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8")); errors: list[str] = []
    if value.get("schema_version") != 1: errors.append("large-cast plan schema_version must be 1")
    entries = value.get("characters", [])
    if not isinstance(entries, list) or len(entries) < 100: errors.append("large-cast plan must contain at least 100 models"); entries=[]
    ids = [item.get("id") for item in entries if isinstance(item, dict)]
    if len(ids) != len(entries) or len(set(ids)) != len(ids) or any(not _safe_id(item) for item in ids): errors.append("large-cast character IDs must be unique and safe")
    required = {"id","job_path","topology","batch","owner","state","checks","measured_hours"}
    root=path.resolve().parents[2]
    for index,item in enumerate(entries):
        if set(item) != required: errors.append(f"large-cast characters[{index}] fields are invalid"); continue
        job_path=item.get("job_path")
        if not isinstance(job_path,str) or Path(job_path).is_absolute() or ".." in Path(job_path).parts or not (root/job_path).is_file(): errors.append(f"large-cast characters[{index}] job_path must name a tracked job")
        else:
            try:
                from vcf_core.jobs import load_job
                if load_job(root/job_path,root).get("id")!=item["id"]: errors.append(f"large-cast characters[{index}] job ID does not match its record")
            except Exception as exc: errors.append(f"large-cast characters[{index}] job is invalid: {exc}")
        if item.get("topology") not in TOPOLOGIES: errors.append(f"large-cast characters[{index}] topology is invalid")
        if item["state"] not in {"ready","building","complete","failed"}: errors.append(f"large-cast characters[{index}] state is invalid")
        if set(item["checks"]) != ENGINE_CHECKS or any(v not in {"pending","passed","failed"} for v in item["checks"].values()): errors.append(f"large-cast characters[{index}] requires the full completion matrix")
        if not isinstance(item["measured_hours"], (int,float)) or isinstance(item["measured_hours"],bool) or item["measured_hours"] <= 0: errors.append(f"large-cast characters[{index}] requires measured capacity")
    governance=value.get("governance",{})
    if set(governance) != {"max_batch_size","resume","duplicate_policy","release_requires_all_checks"} or not 1 <= governance.get("max_batch_size",0) <= 25 or governance.get("resume") is not True or governance.get("duplicate_policy") != "reject" or governance.get("release_requires_all_checks") is not True: errors.append("large-cast governance must enforce bounded resumable release batches")
    batches: dict[str,int]={}
    for item in entries:
        if not _safe_id(item.get("batch")) or not _safe_id(item.get("owner")): errors.append(f"large-cast entry {item.get('id')} requires safe batch and owner IDs")
        batches[item.get("batch")]=batches.get(item.get("batch"),0)+1
    if governance and any(count>governance.get("max_batch_size",0) for count in batches.values()): errors.append("large-cast batch exceeds max_batch_size")
    if errors: raise AdvancedValidationError(errors)
    return value


def cast_quality_summary(plan: dict[str, Any]) -> dict[str, Any]:
    entries=plan["characters"]; complete=[item for item in entries if item["state"]=="complete" and all(v=="passed" for v in item["checks"].values())]
    hours=sorted(float(item["measured_hours"]) for item in entries); batches=sorted({item["batch"] for item in entries})
    return {"model_count":len(entries),"release_ready":len(complete),"consistent":len(complete)==len(entries),"batch_count":len(batches),"median_hours":hours[len(hours)//2],"resumable":plan["governance"]["resume"]}


def load_cast_release(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8")); errors=[]
    if value.get("schema_version")!=1: errors.append("cast release schema_version must be 1")
    records=value.get("characters",[]); planned={item["id"]:item for item in plan["characters"]}
    if not isinstance(records,list) or len(records)!=len(planned): errors.append("cast release must contain every planned character"); records=[]
    hashes=set()
    required={"id","job_path","implementation_hash","content_hash","report_sha256","artifact_count","checks","tool_versions"}
    for index,item in enumerate(records):
        if not isinstance(item,dict) or set(item)!=required: errors.append(f"cast release characters[{index}] fields are invalid"); continue
        if item["id"] not in planned or item["job_path"]!=planned[item["id"]]["job_path"]: errors.append(f"cast release characters[{index}] does not match the plan")
        digest=item.get("content_hash")
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest): errors.append(f"cast release characters[{index}] content_hash is invalid")
        elif digest in hashes: errors.append(f"cast release content hash is not unique: {digest}")
        hashes.add(digest)
        if not isinstance(item.get("implementation_hash"),str) or len(item["implementation_hash"])!=64:errors.append(f"cast release characters[{index}] implementation hash is invalid")
        if not isinstance(item.get("report_sha256"),str) or len(item["report_sha256"])!=64: errors.append(f"cast release characters[{index}] report hash is invalid")
        if not isinstance(item.get("artifact_count"),int) or item["artifact_count"]<20: errors.append(f"cast release characters[{index}] has incomplete artifacts")
        if set(item.get("checks",{}))!=ENGINE_CHECKS or any(state!="passed" for state in item["checks"].values()): errors.append(f"cast release characters[{index}] has incomplete checks")
        if not {"blender","godot"}.issubset(item.get("tool_versions",{})): errors.append(f"cast release characters[{index}] lacks tool versions")
    if errors: raise AdvancedValidationError(errors)
    return value


def resume_cast(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic resume plan without mutating the governed source."""
    load_errors=[]
    if plan.get("governance",{}).get("resume") is not True: load_errors.append("large-cast plan does not permit resume")
    if load_errors: raise AdvancedValidationError(load_errors)
    result=deepcopy(plan)
    for item in result.get("characters",[]):
        if item.get("state") in {"building","failed"}: item["state"]="ready"
    return result
