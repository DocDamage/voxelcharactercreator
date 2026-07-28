"""Convert typed VOX scene instances into axis-aligned world voxel cells."""

from __future__ import annotations

from dataclasses import dataclass

from .vox_reader import Transform, VoxDocument, VoxError


@dataclass(frozen=True)
class ResolvedVoxel:
    x: int
    y: int
    z: int
    color_index: int
    semantic_part: str
    model_id: int
    layer_id: int | None
    layer_name: str | None
    transform: Transform


def resolve_scene_voxels(document: VoxDocument, *, include_hidden: bool = False) -> tuple[ResolvedVoxel, ...]:
    """Resolve every visible model cell to a transformed world cell.

    MagicaVoxel scene rotations are orthogonal. Transforming all eight cell corners
    and taking the minimum preserves the correct cell position for negative axes.
    """
    models = {model.id: model for model in document.models}
    output: list[ResolvedVoxel] = []
    for instance in document.evaluate_scene(include_hidden=include_hidden):
        model = models.get(instance.model_id)
        if model is None:
            raise VoxError(f"scene references unavailable model {instance.model_id}")
        semantic = instance.name or instance.layer_name or f"model_{model.id}"
        for voxel in model.voxels:
            corners = [
                instance.transform.apply((voxel.x + dx, voxel.y + dy, voxel.z + dz))
                for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)
            ]
            x, y, z = (min(corner[index] for corner in corners) for index in range(3))
            output.append(ResolvedVoxel(x, y, z, voxel.color_index, semantic, model.id, instance.layer_id, instance.layer_name, instance.transform))
    return tuple(output)


def voxel_bounds(voxels: tuple[ResolvedVoxel, ...]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if not voxels:
        raise VoxError("VOX scene has no visible voxels")
    minimum = tuple(min(getattr(voxel, axis) for voxel in voxels) for axis in ("x", "y", "z"))
    maximum = tuple(max(getattr(voxel, axis) + 1 for voxel in voxels) for axis in ("x", "y", "z"))
    return minimum, maximum  # type: ignore[return-value]
