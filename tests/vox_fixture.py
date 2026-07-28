"""Original deterministic binary fixtures shared by VOX unit/integration tests."""

from __future__ import annotations

import struct


def chunk(chunk_id: bytes, content: bytes, children: bytes = b"") -> bytes:
    return chunk_id + struct.pack("<II", len(content), len(children)) + content + children


def dictionary(values: dict[str, str]) -> bytes:
    result = struct.pack("<i", len(values))
    for key, value in values.items():
        for item in (key, value):
            encoded = item.encode("utf-8")
            result += struct.pack("<i", len(encoded)) + encoded
    return result


def model(size: tuple[int, int, int], voxels: list[tuple[int, int, int, int]]) -> bytes:
    return chunk(b"SIZE", struct.pack("<III", *size)) + chunk(b"XYZI", struct.pack("<I", len(voxels)) + b"".join(bytes(item) for item in voxels))


def scene_graph_fixture() -> bytes:
    palette = bytes((255, 0, 0, 255, 0, 255, 0, 255)) + bytes((0, 0, 255, 255)) * 254
    children = chunk(b"PACK", struct.pack("<I", 2))
    children += model((1, 1, 1), [(0, 0, 0, 1)]) + model((1, 1, 1), [(0, 0, 0, 2)]) + chunk(b"RGBA", palette)
    children += chunk(b"LAYR", struct.pack("<I", 0) + dictionary({"_name": "body"}) + struct.pack("<i", -1))
    children += chunk(b"nGRP", struct.pack("<i", 0) + dictionary({"_name": "hero"}) + struct.pack("<i", 2) + struct.pack("<ii", 1, 3))
    children += _transform(1, 2, "torso", "0 0 0") + _shape(2, 0)
    children += _transform(3, 4, "hair", "2 0 1") + _shape(4, 1)
    return b"VOX " + struct.pack("<I", 150) + chunk(b"MAIN", b"", children)


def _transform(node_id: int, child_id: int, name: str, translation: str) -> bytes:
    content = struct.pack("<i", node_id) + dictionary({"_name": name}) + struct.pack("<iiii", child_id, -1, 0, 1) + dictionary({"_t": translation})
    return chunk(b"nTRN", content)


def _shape(node_id: int, model_id: int) -> bytes:
    return chunk(b"nSHP", struct.pack("<i", node_id) + dictionary({}) + struct.pack("<i", 1) + struct.pack("<i", model_id) + dictionary({}))
