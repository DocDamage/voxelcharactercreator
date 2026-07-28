"""Deterministic exposed-face and greedy meshing for voxel data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MeshingMode = Literal["greedy", "surface", "cubes"]


class MeshingError(ValueError):
    pass


@dataclass(frozen=True)
class MeshingVoxel:
    x: int
    y: int
    z: int
    color_index: int
    semantic_part: str = "default"


@dataclass(frozen=True)
class MeshData:
    vertices: tuple[tuple[int, int, int], ...]
    faces: tuple[tuple[int, int, int, int], ...]
    material_indices: tuple[int, ...]
    semantic_parts: tuple[str, ...]


_DIRECTIONS = (
    (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1),
)


def mesh_voxels(voxels: list[MeshingVoxel] | tuple[MeshingVoxel, ...], mode: MeshingMode = "greedy") -> MeshData:
    """Mesh voxel data without crossing material or semantic-part boundaries.

    All modes remove internal faces. ``cubes`` intentionally retains independent
    face vertices for diagnostic parity with simple cube importers; ``surface``
    de-duplicates those vertices; ``greedy`` merges coplanar quads.
    """
    if mode not in {"greedy", "surface", "cubes"}:
        raise MeshingError(f"unsupported meshing mode: {mode}")
    occupied: dict[tuple[int, int, int], MeshingVoxel] = {}
    for voxel in voxels:
        coordinate = (voxel.x, voxel.y, voxel.z)
        if coordinate in occupied:
            raise MeshingError(f"duplicate voxel at {coordinate}")
        if not 1 <= voxel.color_index <= 256:
            raise MeshingError(f"invalid palette index at {coordinate}: {voxel.color_index}")
        occupied[coordinate] = voxel
    if mode == "greedy":
        quads = _greedy_quads(occupied)
        return _build_mesh(quads, deduplicate=True)
    quads = _surface_quads(occupied)
    return _build_mesh(quads, deduplicate=mode == "surface")


def _surface_quads(occupied: dict[tuple[int, int, int], MeshingVoxel]):
    quads = []
    for coordinate in sorted(occupied):
        voxel = occupied[coordinate]
        for direction in _DIRECTIONS:
            neighbour = tuple(coordinate[index] + direction[index] for index in range(3))
            if neighbour not in occupied:
                quads.append((_unit_quad(coordinate, direction), voxel.color_index, voxel.semantic_part))
    return quads


def _greedy_quads(occupied: dict[tuple[int, int, int], MeshingVoxel]):
    planes: dict[tuple[int, int], dict[tuple[int, int], tuple[int, str]]] = {}
    for coordinate, voxel in occupied.items():
        x, y, z = coordinate
        for direction_index, direction in enumerate(_DIRECTIONS):
            neighbour = (x + direction[0], y + direction[1], z + direction[2])
            if neighbour in occupied:
                continue
            if direction_index in (0, 1):
                plane, point = x + (1 if direction_index == 1 else 0), (y, z)
            elif direction_index in (2, 3):
                plane, point = y + (1 if direction_index == 3 else 0), (x, z)
            else:
                plane, point = z + (1 if direction_index == 5 else 0), (x, y)
            planes.setdefault((direction_index, plane), {})[point] = (voxel.color_index, voxel.semantic_part)
    quads = []
    for (direction, plane), cells in sorted(planes.items()):
        remaining = dict(cells)
        while remaining:
            (u, v), key = min(remaining.items())
            width = 1
            while remaining.get((u + width, v)) == key:
                width += 1
            height = 1
            while all(remaining.get((u + du, v + height)) == key for du in range(width)):
                height += 1
            for du in range(width):
                for dv in range(height):
                    del remaining[(u + du, v + dv)]
            quads.append((_rectangle_quad(direction, plane, u, v, u + width, v + height), key[0], key[1]))
    return quads


def _unit_quad(coordinate: tuple[int, int, int], direction: tuple[int, int, int]):
    x, y, z = coordinate
    dx, dy, dz = direction
    if dx == -1:
        return ((x, y, z), (x, y, z + 1), (x, y + 1, z + 1), (x, y + 1, z))
    if dx == 1:
        return ((x + 1, y, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x + 1, y, z + 1))
    if dy == -1:
        return ((x, y, z), (x + 1, y, z), (x + 1, y, z + 1), (x, y, z + 1))
    if dy == 1:
        return ((x, y + 1, z), (x, y + 1, z + 1), (x + 1, y + 1, z + 1), (x + 1, y + 1, z))
    if dz == -1:
        return ((x, y, z), (x, y + 1, z), (x + 1, y + 1, z), (x + 1, y, z))
    return ((x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1))


def _rectangle_quad(direction: int, plane: int, u0: int, v0: int, u1: int, v1: int):
    if direction == 0:  # -X; u=Y, v=Z
        return ((plane, u0, v0), (plane, u0, v1), (plane, u1, v1), (plane, u1, v0))
    if direction == 1:  # +X
        return ((plane, u0, v0), (plane, u1, v0), (plane, u1, v1), (plane, u0, v1))
    if direction == 2:  # -Y; u=X, v=Z
        return ((u0, plane, v0), (u1, plane, v0), (u1, plane, v1), (u0, plane, v1))
    if direction == 3:  # +Y
        return ((u0, plane, v0), (u0, plane, v1), (u1, plane, v1), (u1, plane, v0))
    if direction == 4:  # -Z; u=X, v=Y
        return ((u0, v0, plane), (u0, v1, plane), (u1, v1, plane), (u1, v0, plane))
    return ((u0, v0, plane), (u1, v0, plane), (u1, v1, plane), (u0, v1, plane))


def _build_mesh(quads, *, deduplicate: bool) -> MeshData:
    vertices: list[tuple[int, int, int]] = []
    faces: list[tuple[int, int, int, int]] = []
    materials: list[int] = []
    semantics: list[str] = []
    vertex_indices: dict[tuple[int, int, int], int] = {}
    for quad, material, semantic in quads:
        face = []
        for vertex in quad:
            if deduplicate:
                index = vertex_indices.setdefault(vertex, len(vertices))
                if index == len(vertices):
                    vertices.append(vertex)
            else:
                index = len(vertices)
                vertices.append(vertex)
            face.append(index)
        faces.append(tuple(face))
        materials.append(material)
        semantics.append(semantic)
    return MeshData(tuple(vertices), tuple(faces), tuple(materials), tuple(semantics))
