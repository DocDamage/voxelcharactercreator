"""Phase 2 registry-asset assembly stage."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector

from blender_worker.stages.vox_ingest import VoxImportOptions, import_vox_scene
from vcf_core.assets import AssetRegistry


def assemble_assets(job: dict, registry: AssetRegistry, root: Path, make_material) -> list[bpy.types.Object]:
    """Import and place each declared registry asset without flattening its identity.

    Parts remain distinct Blender objects and carry the manifest identifiers,
    pivots, sockets, palette roles, and declared placement for later resolution
    and rig stages.
    """
    manifests = registry.resolve(job["source"]["asset_ids"], body_template=job["body_template"])
    created: list[bpy.types.Object] = []
    for manifest in manifests:
        path = root / manifest.source_path
        if manifest.format != "vox":
            raise ValueError(f"registry assembly currently supports VOX sources only: {manifest.asset_id}")
        unit = manifest.scale_metadata.get("voxel_unit_meters", 0.12)
        if isinstance(unit, bool) or not isinstance(unit, (int, float)) or unit <= 0:
            raise ValueError(f"asset {manifest.asset_id} has invalid voxel_unit_meters")
        imported = import_vox_scene(path, make_material, VoxImportOptions(meshing_mode="greedy", voxel_unit_meters=float(unit)))
        if not imported:
            raise ValueError(f"asset {manifest.asset_id} did not create geometry")
        for index, obj in enumerate(imported, start=1):
            obj.name = manifest.asset_id if len(imported) == 1 else f"{manifest.asset_id}.{index:03d}"
            obj.location += Vector(tuple(value * unit for value in manifest.placement_voxels))
            obj["vcf.asset_id"] = manifest.asset_id
            obj["vcf.asset_version"] = manifest.version
            obj["vcf.asset_kind"] = manifest.kind
            obj["vcf.semantic_tags"] = list(manifest.semantic_tags)
            obj["vcf.asset_pivots"] = {name: list(value) for name, value in manifest.pivots.items()}
            obj["vcf.asset_sockets"] = {name: list(value) for name, value in manifest.sockets.items()}
            obj["vcf.palette_roles"] = list(manifest.palette_roles)
            obj["vcf.declared_placement_voxels"] = list(manifest.placement_voxels)
            obj["vcf.voxel_unit_meters"] = float(unit)
            created.append(obj)
    _ground(created)
    return created


def _ground(objects: list[bpy.types.Object]) -> None:
    """Ground the visible assembled character while preserving per-part metadata."""
    bpy.context.view_layer.update()
    lowest = min((obj.matrix_world @ Vector(corner)).z for obj in objects for corner in obj.bound_box)
    for obj in objects:
        obj.location.z -= lowest
    # Matrix-world bounds are consumed immediately by Phase 3 fitting. Ensure
    # the dependency graph exposes the declared placements and grounding shift.
    bpy.context.view_layer.update()
