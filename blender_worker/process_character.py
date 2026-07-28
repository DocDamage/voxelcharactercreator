from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

import bpy
from mathutils import Vector


ADAPTER_DIR = Path(__file__).resolve().parent / "adapters"
if str(ADAPTER_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTER_DIR))
PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
from blender_worker.pipeline import Pipeline
from blender_worker.stages.animation import apply_animation_packs
from blender_worker.stages.asset_assembly import assemble_assets
from blender_worker.stages.export import export_character
from blender_worker.stages.godot import verify_godot_import
from blender_worker.stages.part_resolution import render_part_map_preview, resolve_scene_parts
from blender_worker.stages.quality import character_content_hash, render_view_set, validate_character
from blender_worker.stages.rigging import align_weapon_to_primary_grip, create_fitted_rig, render_joint_pose_preview, rigid_bind
from blender_worker.stages.vox_ingest import VoxImportOptions, import_vox_scene
from vcf_core.builds import determine_status
from vcf_core.assets import load_registry
from vcf_core.jobs import load_job
from vcf_core.export_profiles import load_export_profile


def parse_args() -> argparse.Namespace:
    blender_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--fail-stage", help="Test-only: force a named stage to fail before it runs.")
    return parser.parse_args(blender_args)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))


def material(name: str, color: str, metal: float = 0.0):
    result = bpy.data.materials.new(name)
    converted = rgb(color)
    result.diffuse_color = (*converted, 1)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*converted, 1)
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = 0.65
    return result


def cube(name: str, location, scale, cube_material):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(cube_material)
    return obj


def create_rig():
    data = bpy.data.armatures.new("VCF_Rig")
    armature = bpy.data.objects.new("VCF_Rig", data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = {
        "root": ((0, 0, 0), (0, 0, 0.5)),
        "pelvis": ((0, 0, 0.5), (0, 0, 1)),
        "spine": ((0, 0, 1), (0, 0, 2.5)),
        "head": ((0, 0, 2.5), (0, 0, 3.5)),
        "upper_arm.L": ((0, 0, 2.2), (1.1, 0, 2.1)),
        "forearm.L": ((1.1, 0, 2.1), (1.9, 0, 1.9)),
        "upper_arm.R": ((0, 0, 2.2), (-1.1, 0, 2.1)),
        "forearm.R": ((-1.1, 0, 2.1), (-1.9, 0, 1.9)),
        "thigh.L": ((0.45, 0, 0.8), (0.5, 0, -0.8)),
        "shin.L": ((0.5, 0, -0.8), (0.5, 0, -2)),
        "thigh.R": ((-0.45, 0, 0.8), (-0.5, 0, -0.8)),
        "shin.R": ((-0.5, 0, -0.8), (-0.5, 0, -2)),
        "weapon_socket.R": ((-1.9, 0, 1.9), (-2.4, 0, 1.7)),
    }
    for name, (head, tail) in bones.items():
        bone = data.edit_bones.new(name)
        bone.head = head
        bone.tail = tail
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def bind(obj, armature, bone: str) -> None:
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_parent_inverse = armature.matrix_world.inverted()


def build_proxy(job: dict, armature) -> None:
    colors = job.get("accent_colors") or ["#888888", "#333333", "#dddddd"]
    primary = material("Primary", colors[0], 0.15)
    secondary = material("Secondary", colors[1] if len(colors) > 1 else colors[0], 0.2)
    accent = material("Accent", colors[2] if len(colors) > 2 else colors[0], 0.55)
    skin = material("Skin", "#D8A175")
    heavy = "heavy" in job.get("rig_template", "") or job.get("body_template") in {"large_villain", "dragoon"}
    width = 1.2 if heavy else 0.95
    parts = [
        (cube("torso", (0, 0, 1.8), (width, 0.55, 0.85), primary), "spine"),
        (cube("pelvis", (0, 0, 0.65), (0.75, 0.5, 0.45), secondary), "pelvis"),
        (cube("head", (0, 0, 3.15), (0.72, 0.62, 0.68), skin), "head"),
    ]
    for side, sign in (("L", 1), ("R", -1)):
        parts.extend(
            [
                (cube(f"upper_arm.{side}", (sign * 1.25, 0, 2.05), (0.42, 0.42, 0.7), primary), f"upper_arm.{side}"),
                (cube(f"forearm.{side}", (sign * 2, 0, 1.85), (0.36, 0.36, 0.65), secondary), f"forearm.{side}"),
                (cube(f"thigh.{side}", (sign * 0.48, 0, -0.25), (0.42, 0.48, 0.85), primary), f"thigh.{side}"),
                (cube(f"shin.{side}", (sign * 0.5, 0, -1.55), (0.38, 0.52, 0.7), secondary), f"shin.{side}"),
            ]
        )
    for obj, bone in parts:
        bind(obj, armature, bone)
    if job.get("weapon"):
        profile = job.get("animation_profile", "")
        name = job["weapon"]
        if "spear" in name or "lance" in name:
            scale = (0.14, 0.14, 2.45)
        elif "buster" in name or "heavy" in profile:
            scale = (0.32, 0.16, 2)
        elif "masamune" in name or "katana" in profile:
            scale = (0.12, 0.08, 2.7)
        else:
            scale = (0.18, 0.1, 1.7)
        weapon = cube("weapon", (-2.6, 0, 1), scale, accent)
        bind(weapon, armature, "weapon_socket.R")


def import_source(path: Path, vox_meshing_mode: str = "greedy"):
    suffix = path.suffix.lower()
    if suffix == ".vox":
        return import_vox_scene(path, material, VoxImportOptions(meshing_mode=vox_meshing_mode))
    if suffix in {".glb", ".gltf"}:
        return bpy.ops.import_scene.gltf(filepath=str(path))
    if suffix == ".fbx":
        return bpy.ops.import_scene.fbx(filepath=str(path))
    if suffix == ".obj":
        return bpy.ops.wm.obj_import(filepath=str(path))
    raise ValueError(f"Unsupported source format: {suffix}")


def animate(armature) -> None:
    armature.animation_data_create()
    action = bpy.data.actions.new("Idle")
    armature.animation_data.action = action
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")
    for frame, value in ((1, -0.025), (20, 0.025), (40, -0.025)):
        bone_by_role = armature.get("vcf.bone_by_role", {})
        bone = armature.pose.bones[str(bone_by_role.get("torso", "spine"))]
        bone.rotation_mode = "XYZ"
        bone.rotation_euler[1] = value
        bone.keyframe_insert("rotation_euler", frame=frame)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 40


def configure_render(path: Path, resolution: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    visible_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not obj.hide_render]
    if not visible_meshes:
        raise ValueError("RENDER_MISSING_GEOMETRY: no visible mesh objects are available for preview")
    corners = [obj.matrix_world @ Vector(corner) for obj in visible_meshes for corner in obj.bound_box]
    minimum = Vector(tuple(min(corner[index] for corner in corners) for index in range(3)))
    maximum = Vector(tuple(max(corner[index] for corner in corners) for index in range(3)))
    target = (minimum + maximum) / 2
    extent = max(maximum[index] - minimum[index] for index in range(3))
    bpy.ops.object.camera_add(location=target + Vector((extent * 1.6, -extent * 2.2, extent * 0.8)))
    camera = bpy.context.object
    scene.camera = camera
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 56
    for location, energy, size in [((4, -5, 8), 1200, 5), ((-4, -2, 4), 700, 4), ((0, 4, 6), 900, 3)]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.size = size
    scene.world.color = (0.025, 0.025, 0.035)


def main() -> None:
    arguments = parse_args()
    root = Path(arguments.project_root).resolve()
    job_path = Path(arguments.job).resolve()
    job = load_job(job_path, root)
    slug = job["id"]
    character_slug = slug.split("_", 1)[1] if "_" in slug else slug
    final_output = root / "exports" / job["game"] / character_slug
    job_hash = hashlib.sha256(job_path.read_bytes()).hexdigest()
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}-{job_hash[:12]}"
    run_dir = root / "exports" / ".runs" / slug / run_id
    output = run_dir / "artifacts"
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 2,
        "run_id": run_id,
        "job": slug,
        "job_schema_version": job["schema_version"],
        "status": "started",
        "input_hashes": {"job": job_hash},
        "tool_versions": {"blender": bpy.app.version_string},
        "stages": [],
        "checks": {},
        "diagnostics": [],
        "artifacts": [],
    }
    pipeline = Pipeline(report, fail_stage=arguments.fail_stage)
    try:
        pipeline.run("prepare", clear_scene)
        source = job["source"]
        assembly_objects: list[bpy.types.Object] = []
        if source["mode"] == "model":
            armature = pipeline.run("rig", create_rig)
            source_path = root / source["path"]
            overrides = job.get("settings_overrides", {})
            vox_meshing_mode = overrides.get("vox_meshing_mode", "greedy") if isinstance(overrides, dict) else "greedy"
            if vox_meshing_mode not in {"greedy", "surface", "cubes"}:
                raise ValueError("settings_overrides.vox_meshing_mode must be greedy, surface, or cubes")
            pipeline.run("ingest", lambda: import_source(source_path, vox_meshing_mode))
            report["checks"]["source_imported"] = True
            report["diagnostics"].append({
                "code": "RIG_UNBOUND_SOURCE", "severity": "error", "stage": "rig",
                "message": "Imported geometry is not rig-bound by the compatibility worker.",
                "corrective_action": "Add explicit part mappings and run the rigid-bind stage.",
            })
            report["status"] = determine_status(
                uses_proxy=False, has_unbound_geometry=True, blocking_checks_passed=True
            ).value
        elif source["mode"] == "proxy":
            armature = pipeline.run("rig", create_rig)
            pipeline.run("assemble_proxy", lambda: build_proxy(job, armature))
            report["checks"]["proxy_generated"] = True
            report["diagnostics"].append({
                "code": "PROXY_GEOMETRY", "severity": "warning", "stage": "assemble_proxy",
                "message": "No approved source asset was supplied; a pipeline proxy was generated.",
                "corrective_action": "Use an approved original asset or registry assembly for a production build.",
            })
            report["status"] = determine_status(
                uses_proxy=True, has_unbound_geometry=False, blocking_checks_passed=True
            ).value
        elif source["mode"] == "assembly":
            registry = load_registry(root)
            assembly_objects = pipeline.run("assemble_assets", lambda: assemble_assets(job, registry, root, material))
            resolutions, trace = pipeline.run("resolve_parts", lambda: resolve_scene_parts(assembly_objects, job))
            report["part_resolution"] = trace
            armature, rig_checks = pipeline.run("rig", lambda: create_fitted_rig(assembly_objects, resolutions, job))
            socket_checks = pipeline.run("align_sockets", lambda: align_weapon_to_primary_grip(assembly_objects, armature, resolutions))
            pipeline.run("rigid_bind", lambda: rigid_bind(assembly_objects, armature, resolutions))
            bound = all(
                obj.parent == armature and obj.parent_type == "BONE" and obj.get("vcf.bind_mode") == "rigid"
                for obj in assembly_objects
            )
            report["checks"].update({
                "registry_assets_resolved": {obj.get("vcf.asset_id") for obj in assembly_objects} == set(source["asset_ids"]),
                "registry_asset_count": len(assembly_objects),
                "registry_editable_objects": all("vcf.asset_id" in obj for obj in assembly_objects),
                "part_resolution_complete": len(resolutions) == len(assembly_objects),
                "rigid_binding_complete": bound,
                **rig_checks,
                **socket_checks,
            })
            weapon_checks_required = bool(job.get("weapon"))
            blocking_socket_checks = not weapon_checks_required or (
                bool(socket_checks.get("weapon_present"))
                and all(bool(socket_checks.get(key)) for key in (
                    "weapon_socket_metadata_complete", "weapon_socket_bones_present", "primary_grip_aligned",
                    "carry_alignment_declared", "carry_alignment_valid", "weapon_body_clear",
                ))
            )
            blocking_assembly_checks = all(bool(report["checks"][key]) for key in (
                "registry_assets_resolved", "registry_editable_objects", "part_resolution_complete", "rigid_binding_complete",
            ))
            report["status"] = determine_status(
                uses_proxy=False,
                has_unbound_geometry=not bound,
                blocking_checks_passed=blocking_assembly_checks and all(rig_checks.values()) and blocking_socket_checks,
            ).value
        else:
            raise ValueError("Asset-registry assembly is not implemented by the compatibility worker")

        if assembly_objects:
            actions, animation_checks = pipeline.run("animate", lambda: apply_animation_packs(armature, job, root))
            report["checks"].update(animation_checks)
            report["animation"] = {
                "packs": list(armature.get("vcf.animation_packs", ())),
                "actions": [
                    {"name": action.name, "frame_start": action.get("vcf.frame_start"), "frame_end": action.get("vcf.frame_end"), "loop": action.get("vcf.loop"), "root_motion": action.get("vcf.root_motion"), "events": json.loads(action.get("vcf.events", "[]"))}
                    for action in actions
                ],
            }
        else:
            pipeline.run("animate", lambda: animate(armature))
            actions = [armature.animation_data.action]
        export_profile = load_export_profile(root, job.get("export_profile", "godot_character"))
        report["export_profile"] = {"id": export_profile.profile_id, "engine": export_profile.engine, "scale": export_profile.scale, "forward_axis": export_profile.forward_axis, "up_axis": export_profile.up_axis}
        if assembly_objects:
            qa_checks, qa_diagnostics = pipeline.run("qa", lambda: validate_character(assembly_objects, armature, actions, export_profile))
            report["checks"].update(qa_checks)
            report["diagnostics"].extend(qa_diagnostics)
            if qa_diagnostics:
                raise ValueError("QA_BLOCKING_FAILURE: " + ", ".join(item["code"] for item in qa_diagnostics))
        preview = output / f"{slug}_preview.png"
        def render_and_save() -> None:
            configure_render(preview, int(job.get("render_resolution", 768)))
            bpy.context.scene.frame_set(1)
            bpy.ops.render.render(write_still=True)
            if assembly_objects:
                render_part_map_preview(assembly_objects, output / f"{slug}_part_map.png")
                render_joint_pose_preview(armature, output / f"{slug}_joint_pose.png")
                view_paths = render_view_set(output, slug, armature)
                report["visual_previews"] = [path.name for path in view_paths]
            bpy.ops.wm.save_as_mainfile(filepath=str(output / f"{slug}_processed.blend"))
        pipeline.run("render", render_and_save)

        formats = job.get("export_formats", ["glb"])
        def export() -> None:
            character_objects = assembly_objects or [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
            export_character(output, slug, formats, character_objects, armature, export_profile)
        pipeline.run("export", export)
        if assembly_objects and export_profile.engine == "godot" and "glb" in formats:
            godot_checks = pipeline.run("godot_import", lambda: verify_godot_import(root, output / f"{slug}.glb"))
            report["checks"].update(godot_checks)
            report["tool_versions"]["godot"] = godot_checks["godot_version"]
        report["checks"].update(
            {
                "armature_exists": "VCF_Rig" in bpy.data.objects,
                "preview_rendered": preview.exists(),
                "part_map_rendered": (output / f"{slug}_part_map.png").exists() if assembly_objects else None,
                "joint_pose_rendered": (output / f"{slug}_joint_pose.png").exists() if assembly_objects else None,
                "view_set_rendered": all((output / f"{slug}_{name}.png").exists() for name in ("front", "side", "rear", "three_quarter", "skeleton", "socket")) if assembly_objects else None,
                "turntable_rendered": all((output / f"{slug}_turntable_{index:02d}.png").exists() for index in range(8)) if assembly_objects else None,
                "glb_exported": (output / f"{slug}.glb").exists() if "glb" in formats else None,
                "fbx_exported": (output / f"{slug}.fbx").exists() if "fbx" in formats else None,
            }
        )
        expected = {f"{slug}_processed.blend", f"{slug}_preview.png", *(f"{slug}.{extension}" for extension in formats)}
        if assembly_objects:
            expected.update({f"{slug}_part_map.png", f"{slug}_joint_pose.png", *(f"{slug}_{name}.png" for name in ("front", "side", "rear", "three_quarter", "skeleton", "socket")), *(f"{slug}_turntable_{index:02d}.png" for index in range(8))})
            report["content_hash"] = character_content_hash(assembly_objects, armature, actions)
        missing_artifacts = sorted(name for name in expected if not (output / name).is_file())
        report["checks"]["artifact_completeness"] = not missing_artifacts
        if missing_artifacts:
            raise ValueError("QA_ARTIFACT_MISSING: " + ", ".join(missing_artifacts))
        for artifact in sorted(path for path in output.iterdir() if path.is_file()):
            report["artifacts"].append({
                "name": artifact.name,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "size_bytes": artifact.stat().st_size,
            })
        if report["status"] in {"prototype", "complete"}:
            final_output.parent.mkdir(parents=True, exist_ok=True)
            backup = final_output.with_name(f".{final_output.name}.previous-{run_id}")
            if final_output.exists():
                final_output.replace(backup)
            try:
                output.replace(final_output)
            except Exception:
                if backup.exists() and not final_output.exists():
                    backup.replace(final_output)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            report["promoted_output"] = str(final_output.relative_to(root))
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        (run_dir / "build_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if report["status"] in {"prototype", "complete"} and final_output.exists():
            (final_output / f"{slug}_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Blender can otherwise exit successfully after logging a Python traceback,
        # which makes external orchestration report a false-green build.
        sys.exit(1)
