"""Bounded MagicaVoxel ``.vox`` decoding and scene-graph evaluation.

This module deliberately has no Blender dependency so malformed input can be
rejected before the worker starts creating scene objects.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


DEFAULT_PALETTE = tuple((index, index, index, 255) for index in range(256))


class VoxError(ValueError):
    """An actionable error while decoding an untrusted VOX file."""


@dataclass(frozen=True)
class VoxLimits:
    max_file_bytes: int = 64 * 1024 * 1024
    max_chunk_bytes: int = 32 * 1024 * 1024
    max_chunks: int = 100_000
    max_models: int = 1_024
    max_voxels_per_model: int = 1_000_000
    max_total_voxels: int = 2_000_000
    max_dimension: int = 2_048


@dataclass(frozen=True)
class VoxVoxel:
    x: int
    y: int
    z: int
    color_index: int


@dataclass(frozen=True)
class VoxModel:
    id: int
    size: tuple[int, int, int]
    voxels: tuple[VoxVoxel, ...]


@dataclass(frozen=True)
class VoxMaterial:
    id: int
    attributes: dict[str, str]


@dataclass(frozen=True)
class VoxLayer:
    id: int
    attributes: dict[str, str]
    hidden: bool


@dataclass(frozen=True)
class Transform:
    rotation: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]
    translation: tuple[int, int, int]

    @classmethod
    def identity(cls) -> "Transform":
        return cls(((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0, 0, 0))

    def apply(self, point: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(
            sum(self.rotation[row][column] * point[column] for column in range(3)) + self.translation[row]
            for row in range(3)
        )  # type: ignore[return-value]

    def compose(self, child: "Transform") -> "Transform":
        rotation = tuple(
            tuple(sum(self.rotation[row][mid] * child.rotation[mid][column] for mid in range(3)) for column in range(3))
            for row in range(3)
        )
        return Transform(rotation, self.apply(child.translation))  # type: ignore[arg-type]


@dataclass(frozen=True)
class TransformNode:
    id: int
    attributes: dict[str, str]
    child_id: int
    layer_id: int
    frames: tuple[tuple[tuple[int, int], dict[str, str]], ...]


@dataclass(frozen=True)
class GroupNode:
    id: int
    attributes: dict[str, str]
    children: tuple[int, ...]


@dataclass(frozen=True)
class ShapeNode:
    id: int
    attributes: dict[str, str]
    models: tuple[tuple[int, dict[str, str]], ...]


@dataclass(frozen=True)
class SceneInstance:
    model_id: int
    name: str
    layer_id: int | None
    layer_name: str | None
    visible: bool
    transform: Transform
    attributes: dict[str, str]


@dataclass
class VoxDocument:
    version: int
    models: tuple[VoxModel, ...]
    palette: tuple[tuple[int, int, int, int], ...]
    materials: dict[int, VoxMaterial] = field(default_factory=dict)
    layers: dict[int, VoxLayer] = field(default_factory=dict)
    transform_nodes: dict[int, TransformNode] = field(default_factory=dict)
    group_nodes: dict[int, GroupNode] = field(default_factory=dict)
    shape_nodes: dict[int, ShapeNode] = field(default_factory=dict)
    pack_count: int | None = None
    unknown_chunks: tuple[str, ...] = ()

    # Compatibility with the original public dictionary reader. New callers should
    # use the typed attributes above.
    def __getitem__(self, key: str):
        first = self.models[0] if self.models else None
        values = {
            "version": self.version,
            "size": first.size if first else None,
            "voxels": [(item.x, item.y, item.z, item.color_index) for item in first.voxels] if first else [],
            "palette": list(self.palette),
        }
        return values[key]

    def evaluate_scene(self, frame: int = 0, *, include_hidden: bool = False) -> tuple[SceneInstance, ...]:
        """Resolve nTRN/nGRP/nSHP to world-space model instances."""
        if not self.shape_nodes:
            return tuple(
                SceneInstance(model.id, f"model_{model.id}", None, None, True, Transform.identity(), {})
                for model in self.models
            )
        child_ids = {child for node in self.transform_nodes.values() for child in (node.child_id,)}
        child_ids.update(child for node in self.group_nodes.values() for child in node.children)
        roots = sorted((set(self.transform_nodes) | set(self.group_nodes) | set(self.shape_nodes)) - child_ids)
        if not roots:
            raise VoxError("VOX scene graph has no root node (cycle or corrupt references)")
        instances: list[SceneInstance] = []

        def visit(node_id: int, world: Transform, inherited_name: str, layer_id: int | None, visible: bool, stack: set[int]) -> None:
            if node_id in stack:
                raise VoxError(f"VOX scene graph cycle detected at node {node_id}")
            next_stack = stack | {node_id}
            transform_node = self.transform_nodes.get(node_id)
            if transform_node:
                attributes = transform_node.attributes
                selected = _select_frame(transform_node.frames, frame)
                local = _transform_from_attributes(selected)
                node_layer = transform_node.layer_id if transform_node.layer_id >= 0 else layer_id
                layer = self.layers.get(node_layer) if node_layer is not None else None
                node_visible = visible and not _is_hidden(attributes) and not (layer.hidden if layer else False)
                name = attributes.get("_name", inherited_name)
                visit(transform_node.child_id, world.compose(local), name, node_layer, node_visible, next_stack)
                return
            group_node = self.group_nodes.get(node_id)
            if group_node:
                node_visible = visible and not _is_hidden(group_node.attributes)
                name = group_node.attributes.get("_name", inherited_name)
                for child in group_node.children:
                    visit(child, world, name, layer_id, node_visible, next_stack)
                return
            shape_node = self.shape_nodes.get(node_id)
            if shape_node:
                node_visible = visible and not _is_hidden(shape_node.attributes)
                name = shape_node.attributes.get("_name", inherited_name or f"shape_{node_id}")
                layer = self.layers.get(layer_id) if layer_id is not None else None
                for model_id, attributes in _select_shape_models(shape_node.models, frame):
                    instance_visible = node_visible and not _is_hidden(attributes)
                    if include_hidden or instance_visible:
                        instances.append(SceneInstance(model_id, name, layer_id, layer.attributes.get("_name") if layer else None, instance_visible, world, attributes))
                return
            raise VoxError(f"VOX scene graph references missing node {node_id}")

        for root in roots:
            visit(root, Transform.identity(), "", None, True, set())
        return tuple(instances)


def _is_hidden(attributes: dict[str, str]) -> bool:
    return attributes.get("_hidden") in {"1", "true", "True"}


def _select_frame(frames: tuple[tuple[tuple[int, int], dict[str, str]], ...], requested: int) -> dict[str, str]:
    if not frames:
        return {}
    candidates = sorted(frames, key=lambda item: item[0])
    exact = [attrs for key, attrs in candidates if key[0] == requested]
    if exact:
        return exact[0]
    before = [attrs for key, attrs in candidates if key[0] <= requested]
    return before[-1] if before else candidates[0][1]


def _select_shape_models(models: tuple[tuple[int, dict[str, str]], ...], requested: int) -> tuple[tuple[int, dict[str, str]], ...]:
    """Select animated nSHP model references at the requested frame."""
    timed: list[tuple[int, tuple[int, dict[str, str]]]] = []
    for model in models:
        marker = model[1].get("_f")
        if marker is not None:
            try:
                timed.append((int(marker), model))
            except ValueError as exc:
                raise VoxError(f"invalid nSHP frame {marker!r}") from exc
    if not timed:
        return models
    available = [item for item in timed if item[0] <= requested]
    selected_frame = max(item[0] for item in available) if available else min(item[0] for item in timed)
    return tuple(model for marker, model in timed if marker == selected_frame)


def _transform_from_attributes(attributes: dict[str, str]) -> Transform:
    translation = (0, 0, 0)
    if "_t" in attributes:
        try:
            parts = tuple(int(item) for item in attributes["_t"].split())
        except ValueError as exc:
            raise VoxError(f"invalid nTRN translation {attributes['_t']!r}") from exc
        if len(parts) != 3:
            raise VoxError("nTRN translation must contain three integers")
        translation = parts  # type: ignore[assignment]
    encoded = 4
    if "_r" in attributes:
        try:
            encoded = int(attributes["_r"])
        except ValueError as exc:
            raise VoxError(f"invalid nTRN rotation {attributes['_r']!r}") from exc
    return Transform(_decode_rotation(encoded), translation)


def _decode_rotation(encoded: int) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    if not 0 <= encoded <= 255:
        raise VoxError("nTRN rotation must be an unsigned 8-bit integer")
    first_axis, second_axis = encoded & 0x3, (encoded >> 2) & 0x3
    if first_axis > 2 or second_axis > 2 or first_axis == second_axis:
        raise VoxError(f"invalid nTRN rotation encoding: {encoded}")
    third_axis = 3 - first_axis - second_axis
    signs = (-1 if encoded & (1 << 4) else 1, -1 if encoded & (1 << 5) else 1, -1 if encoded & (1 << 6) else 1)
    rows = []
    for axis, sign in zip((first_axis, second_axis, third_axis), signs):
        row = [0, 0, 0]
        row[axis] = sign
        rows.append(tuple(row))
    return tuple(rows)  # type: ignore[return-value]


class _Reader:
    def __init__(self, data: bytes, limits: VoxLimits):
        self.data, self.limits, self.chunks = data, limits, 0

    def require(self, start: int, length: int, context: str) -> None:
        if start < 0 or length < 0 or start + length > len(self.data):
            raise VoxError(f"truncated VOX data while reading {context}")

    def u32(self, offset: int, context: str) -> int:
        self.require(offset, 4, context)
        return struct.unpack_from("<I", self.data, offset)[0]

    def i32(self, offset: int, context: str) -> int:
        self.require(offset, 4, context)
        return struct.unpack_from("<i", self.data, offset)[0]

    def dictionary(self, offset: int, end: int, context: str) -> tuple[dict[str, str], int]:
        if offset + 4 > end:
            raise VoxError(f"truncated dictionary in {context}")
        count = self.i32(offset, context)
        offset += 4
        if not 0 <= count <= 10_000:
            raise VoxError(f"invalid dictionary entry count in {context}: {count}")
        values: dict[str, str] = {}
        for _ in range(count):
            key, offset = self.string(offset, end, context)
            value, offset = self.string(offset, end, context)
            values[key] = value
        return values, offset

    def string(self, offset: int, end: int, context: str) -> tuple[str, int]:
        if offset + 4 > end:
            raise VoxError(f"truncated string length in {context}")
        length = self.i32(offset, context)
        offset += 4
        if length < 0 or length > 1_000_000 or offset + length > end:
            raise VoxError(f"invalid string length in {context}")
        try:
            value = self.data[offset : offset + length].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VoxError(f"invalid UTF-8 string in {context}") from exc
        return value, offset + length

    def chunks_in(self, start: int, end: int) -> Iterator[tuple[str, int, int, int, int]]:
        offset = start
        while offset < end:
            self.require(offset, 12, "chunk header")
            if offset + 12 > end:
                raise VoxError("chunk header extends past parent chunk")
            self.chunks += 1
            if self.chunks > self.limits.max_chunks:
                raise VoxError(f"VOX contains more than {self.limits.max_chunks} chunks")
            chunk_id = self.data[offset : offset + 4].decode("ascii", errors="replace")
            content_size, children_size = self.u32(offset + 4, "chunk sizes"), self.u32(offset + 8, "chunk sizes")
            if content_size > self.limits.max_chunk_bytes or children_size > self.limits.max_chunk_bytes:
                raise VoxError(f"chunk {chunk_id} exceeds configured size limit")
            content_start = offset + 12
            content_end = content_start + content_size
            children_end = content_end + children_size
            if children_end > end:
                raise VoxError(f"chunk {chunk_id} extends past parent chunk")
            yield chunk_id, content_start, content_end, content_end, children_end
            offset = children_end
        if offset != end:
            raise VoxError("invalid VOX chunk alignment")


def read_vox(path: Path, limits: VoxLimits | None = None) -> VoxDocument:
    limits = limits or VoxLimits()
    try:
        size = path.stat().st_size
        if size > limits.max_file_bytes:
            raise VoxError(f"VOX file exceeds configured size limit ({limits.max_file_bytes} bytes)")
        data = path.read_bytes()
    except OSError as exc:
        raise VoxError(f"could not read VOX file {path}: {exc}") from exc
    if len(data) < 8 or data[:4] != b"VOX ":
        raise VoxError("Not a MagicaVoxel VOX file")
    reader = _Reader(data, limits)
    version = reader.u32(4, "VOX version")
    reader.require(8, 12, "MAIN chunk")
    if data[8:12] != b"MAIN":
        raise VoxError("Invalid VOX MAIN chunk")
    main_content, main_children = reader.u32(12, "MAIN sizes"), reader.u32(16, "MAIN sizes")
    if main_content:
        raise VoxError("MAIN chunk must not contain payload data")
    start, end = 20, 20 + main_children
    reader.require(start, main_children, "MAIN children")
    if end != len(data):
        raise VoxError("trailing or truncated data after MAIN chunk")

    models: list[VoxModel] = []
    pending_size: tuple[int, int, int] | None = None
    palette = DEFAULT_PALETTE
    materials: dict[int, VoxMaterial] = {}
    layers: dict[int, VoxLayer] = {}
    transforms: dict[int, TransformNode] = {}
    groups: dict[int, GroupNode] = {}
    shapes: dict[int, ShapeNode] = {}
    unknown: list[str] = []
    pack_count: int | None = None
    total_voxels = 0

    for chunk_id, content_start, content_end, children_start, children_end in reader.chunks_in(start, end):
        content = data[content_start:content_end]
        if children_start != children_end:
            # Known scene chunks have no nested child chunks. Still parse arbitrary
            # nested payload safely so unknown exporters do not desynchronise input.
            list(reader.chunks_in(children_start, children_end))
        if chunk_id == "PACK":
            if len(content) != 4:
                raise VoxError("PACK chunk must be four bytes")
            pack_count = struct.unpack("<I", content)[0]
            if pack_count > limits.max_models:
                raise VoxError(f"PACK declares more than {limits.max_models} models")
        elif chunk_id == "SIZE":
            if len(content) != 12:
                raise VoxError("SIZE chunk must be twelve bytes")
            pending_size = struct.unpack("<III", content)
            if any(dimension == 0 or dimension > limits.max_dimension for dimension in pending_size):
                raise VoxError(f"SIZE dimensions must be from 1 to {limits.max_dimension}")
        elif chunk_id == "XYZI":
            if pending_size is None:
                raise VoxError("XYZI chunk appears before SIZE")
            if len(content) < 4:
                raise VoxError("truncated XYZI chunk")
            count = struct.unpack_from("<I", content)[0]
            if count > limits.max_voxels_per_model or total_voxels + count > limits.max_total_voxels:
                raise VoxError("VOX voxel count exceeds configured limit")
            if len(content) != 4 + count * 4:
                raise VoxError("XYZI voxel count does not match chunk size")
            voxels = tuple(VoxVoxel(*content[index : index + 4]) for index in range(4, len(content), 4))
            bounds = pending_size
            if any(voxel.x >= bounds[0] or voxel.y >= bounds[1] or voxel.z >= bounds[2] or voxel.color_index == 0 for voxel in voxels):
                raise VoxError("XYZI contains an out-of-bounds voxel or palette index 0")
            if len(models) >= limits.max_models:
                raise VoxError(f"VOX contains more than {limits.max_models} models")
            models.append(VoxModel(len(models), pending_size, voxels))
            pending_size = None
            total_voxels += count
        elif chunk_id == "RGBA":
            if len(content) != 1024:
                raise VoxError("RGBA chunk must contain 256 colors")
            palette = tuple(tuple(content[index : index + 4]) for index in range(0, 1024, 4))  # type: ignore[assignment]
        elif chunk_id == "MATL":
            if len(content) < 4:
                raise VoxError("truncated MATL chunk")
            material_id = struct.unpack_from("<I", content)[0]
            attributes, offset = reader.dictionary(content_start + 4, content_end, "MATL")
            if offset != content_end:
                raise VoxError("extra bytes in MATL chunk")
            materials[material_id] = VoxMaterial(material_id, attributes)
        elif chunk_id == "LAYR":
            if len(content) < 8:
                raise VoxError("truncated LAYR chunk")
            layer_id = struct.unpack_from("<I", content)[0]
            attributes, offset = reader.dictionary(content_start + 4, content_end, "LAYR")
            if offset + 4 != content_end:
                raise VoxError("invalid LAYR reserved field")
            layers[layer_id] = VoxLayer(layer_id, attributes, _is_hidden(attributes))
        elif chunk_id == "nTRN":
            node_id, attributes, child_id, layer_id, frames = _parse_transform_node(reader, content_start, content_end)
            transforms[node_id] = TransformNode(node_id, attributes, child_id, layer_id, frames)
        elif chunk_id == "nGRP":
            node_id, attributes, children = _parse_group_node(reader, content_start, content_end)
            groups[node_id] = GroupNode(node_id, attributes, children)
        elif chunk_id == "nSHP":
            node_id, attributes, model_refs = _parse_shape_node(reader, content_start, content_end)
            shapes[node_id] = ShapeNode(node_id, attributes, model_refs)
        else:
            unknown.append(chunk_id)
    if pending_size is not None:
        raise VoxError("SIZE chunk is missing its XYZI chunk")
    if not models:
        raise VoxError("VOX file contains no SIZE/XYZI model")
    if pack_count is not None and pack_count != len(models):
        raise VoxError(f"PACK declares {pack_count} models but file contains {len(models)}")
    known_model_ids = {model.id for model in models}
    for shape in shapes.values():
        for model_id, _attributes in shape.models:
            if model_id not in known_model_ids:
                raise VoxError(f"nSHP node {shape.id} references missing model {model_id}")
    return VoxDocument(version, tuple(models), palette, materials, layers, transforms, groups, shapes, pack_count, tuple(unknown))


def _parse_transform_node(reader: _Reader, start: int, end: int):
    if start + 16 > end:
        raise VoxError("truncated nTRN chunk")
    node_id = reader.i32(start, "nTRN")
    attributes, offset = reader.dictionary(start + 4, end, "nTRN")
    if offset + 16 > end:
        raise VoxError("truncated nTRN links")
    child_id, _reserved, layer_id, count = (reader.i32(offset + delta, "nTRN") for delta in (0, 4, 8, 12))
    offset += 16
    if count < 0 or count > 10_000:
        raise VoxError("invalid nTRN frame count")
    frames = []
    for index in range(count):
        attributes_frame, offset = reader.dictionary(offset, end, f"nTRN frame {index}")
        try:
            frame = int(attributes_frame.get("_f", index))
        except ValueError as exc:
            raise VoxError(f"invalid nTRN frame {attributes_frame.get('_f')!r}") from exc
        frames.append(((frame, index), attributes_frame))
    if offset != end:
        raise VoxError("extra bytes in nTRN chunk")
    return node_id, attributes, child_id, layer_id, tuple(frames)


def _parse_group_node(reader: _Reader, start: int, end: int):
    if start + 8 > end:
        raise VoxError("truncated nGRP chunk")
    node_id = reader.i32(start, "nGRP")
    attributes, offset = reader.dictionary(start + 4, end, "nGRP")
    if offset + 4 > end:
        raise VoxError("truncated nGRP child count")
    count = reader.i32(offset, "nGRP")
    offset += 4
    if count < 0 or count > 100_000 or offset + count * 4 != end:
        raise VoxError("invalid nGRP child list")
    return node_id, attributes, tuple(reader.i32(offset + index * 4, "nGRP") for index in range(count))


def _parse_shape_node(reader: _Reader, start: int, end: int):
    if start + 8 > end:
        raise VoxError("truncated nSHP chunk")
    node_id = reader.i32(start, "nSHP")
    attributes, offset = reader.dictionary(start + 4, end, "nSHP")
    if offset + 4 > end:
        raise VoxError("truncated nSHP model count")
    count = reader.i32(offset, "nSHP")
    offset += 4
    if count < 0 or count > 1_024:
        raise VoxError("invalid nSHP model count")
    models = []
    for _ in range(count):
        if offset + 4 > end:
            raise VoxError("truncated nSHP model id")
        model_id = reader.i32(offset, "nSHP")
        attributes_model, offset = reader.dictionary(offset + 4, end, "nSHP")
        models.append((model_id, attributes_model))
    if offset != end:
        raise VoxError("extra bytes in nSHP chunk")
    return node_id, attributes, tuple(models)
