"""Phase 6 export optimization shared by every archetype."""

from __future__ import annotations

from typing import Any

import bpy

from vcf_core.factory import OptimizationPolicy


def optimize_for_export(objects: list[bpy.types.Object], policy: OptimizationPolicy) -> tuple[list[bpy.types.Object], dict[str, Any]]:
    canonical: dict[tuple[float, ...], bpy.types.Material] = {}
    if policy.material_batching == "palette_atlas":
        for obj in objects:
            for index, material in enumerate(obj.data.materials):
                if material:
                    key = tuple(round(float(channel), 5) for channel in material.diffuse_color)
                    canonical.setdefault(key, material)
                    obj.data.materials[index] = canonical[key]
    lods: list[bpy.types.Object] = []
    for ratio in policy.lod_ratios[1:]:
        for source in objects:
            duplicate = source.copy(); duplicate.data = source.data.copy(); duplicate.name = f"{source.name}_LOD{int(ratio * 100):02d}"
            bpy.context.collection.objects.link(duplicate)
            modifier = duplicate.modifiers.new("VCF_LOD", "DECIMATE"); modifier.ratio = ratio
            bpy.context.view_layer.objects.active = duplicate; duplicate.select_set(True)
            try: bpy.ops.object.modifier_apply(modifier=modifier.name)
            finally: duplicate.select_set(False)
            duplicate["vcf.lod_ratio"] = ratio; lods.append(duplicate)
    return [*objects, *lods], {"lod_levels": list(policy.lod_ratios), "lod_object_count": len(lods), "material_batch_count": len(canonical), "compression_policy": policy.compression}
