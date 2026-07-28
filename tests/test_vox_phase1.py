from __future__ import annotations

import os
import random
import struct
import tempfile
import unittest
from pathlib import Path

from blender_worker.adapters.vox_reader import VoxError, VoxLimits, read_vox
from blender_worker.adapters.vox_scene import resolve_scene_voxels, voxel_bounds
from blender_worker.geometry.vox_mesher import MeshingVoxel, mesh_voxels


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
    return chunk(b"SIZE", struct.pack("<III", *size)) + chunk(
        b"XYZI", struct.pack("<I", len(voxels)) + b"".join(bytes(item) for item in voxels)
    )


def vox(children: bytes) -> bytes:
    return b"VOX " + struct.pack("<I", 150) + chunk(b"MAIN", b"", children)


def transform_node(node_id: int, child_id: int, layer_id: int, attributes: dict[str, str], frames: list[dict[str, str]]) -> bytes:
    content = struct.pack("<i", node_id) + dictionary(attributes)
    content += struct.pack("<iiii", child_id, -1, layer_id, len(frames))
    return chunk(b"nTRN", content + b"".join(dictionary(frame) for frame in frames))


def group_node(node_id: int, children: list[int], attributes: dict[str, str] | None = None) -> bytes:
    return chunk(b"nGRP", struct.pack("<i", node_id) + dictionary(attributes or {}) + struct.pack("<i", len(children)) + struct.pack(f"<{len(children)}i", *children))


def shape_node(node_id: int, model_ids: list[int], attributes: dict[str, str] | None = None) -> bytes:
    content = struct.pack("<i", node_id) + dictionary(attributes or {}) + struct.pack("<i", len(model_ids))
    return chunk(b"nSHP", content + b"".join(struct.pack("<i", item) + dictionary({}) for item in model_ids))


def animated_shape_node(node_id: int, frames: list[tuple[int, int]]) -> bytes:
    content = struct.pack("<i", node_id) + dictionary({}) + struct.pack("<i", len(frames))
    return chunk(b"nSHP", content + b"".join(struct.pack("<i", model_id) + dictionary({"_f": str(frame)}) for frame, model_id in frames))


class VoxPhase1ReaderTests(unittest.TestCase):
    def read(self, payload: bytes):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fixture.vox"
            path.write_bytes(payload)
            return read_vox(path)

    def test_parses_pack_multiple_models_palette_material_layer_and_unknown_chunk(self) -> None:
        palette = bytes((255, 0, 0, 255)) * 256
        children = chunk(b"PACK", struct.pack("<I", 2))
        children += model((2, 2, 2), [(0, 0, 0, 1)]) + model((1, 1, 1), [(0, 0, 0, 2)])
        children += chunk(b"RGBA", palette)
        children += chunk(b"MATL", struct.pack("<I", 2) + dictionary({"_type": "metal", "_rough": "0.2"}))
        children += chunk(b"LAYR", struct.pack("<I", 7) + dictionary({"_name": "armor"}) + struct.pack("<i", -1))
        children += chunk(b"ZZZZ", b"ignored")
        document = self.read(vox(children))
        self.assertEqual(2, document.pack_count)
        self.assertEqual((2, 2, 2), document.models[0].size)
        self.assertEqual(2, document.models[1].voxels[0].color_index)
        self.assertEqual("metal", document.materials[2].attributes["_type"])
        self.assertEqual("armor", document.layers[7].attributes["_name"])
        self.assertEqual(("ZZZZ",), document.unknown_chunks)

    def test_evaluates_named_layered_scene_transform_and_frame(self) -> None:
        children = model((1, 1, 1), [(0, 0, 0, 4)])
        children += chunk(b"LAYR", struct.pack("<I", 0) + dictionary({"_name": "body"}) + struct.pack("<i", -1))
        children += group_node(0, [1])
        children += transform_node(1, 2, 0, {"_name": "torso"}, [{"_f": "0", "_t": "2 3 4"}, {"_f": "10", "_t": "7 3 4"}])
        children += shape_node(2, [0])
        document = self.read(vox(children))
        first = document.evaluate_scene(frame=0)
        late = document.evaluate_scene(frame=10)
        self.assertEqual("torso", first[0].name)
        self.assertEqual("body", first[0].layer_name)
        self.assertEqual((2, 3, 4), first[0].transform.translation)
        self.assertEqual((7, 3, 4), late[0].transform.translation)
        resolved = resolve_scene_voxels(document)
        self.assertEqual((2, 3, 4), (resolved[0].x, resolved[0].y, resolved[0].z))
        self.assertEqual((2, 3, 4), resolved[0].transform.translation)
        self.assertEqual(((2, 3, 4), (3, 4, 5)), voxel_bounds(resolved))

    def test_hidden_layer_is_excluded_unless_requested(self) -> None:
        children = model((1, 1, 1), [(0, 0, 0, 4)])
        children += chunk(b"LAYR", struct.pack("<I", 0) + dictionary({"_name": "hidden", "_hidden": "1"}) + struct.pack("<i", -1))
        children += transform_node(1, 2, 0, {}, [{}]) + shape_node(2, [0])
        document = self.read(vox(children))
        self.assertEqual((), document.evaluate_scene())
        self.assertFalse(document.evaluate_scene(include_hidden=True)[0].visible)

    def test_scene_rotation_transforms_world_voxel_cells(self) -> None:
        children = model((1, 1, 1), [(0, 0, 0, 4)])
        # 33 encodes a 90-degree orthogonal turn around the Z axis.
        children += transform_node(1, 2, -1, {}, [{"_r": "33"}]) + shape_node(2, [0])
        resolved = resolve_scene_voxels(self.read(vox(children)))
        self.assertEqual((0, -1, 0), (resolved[0].x, resolved[0].y, resolved[0].z))

    def test_shape_model_frame_selection(self) -> None:
        children = model((1, 1, 1), [(0, 0, 0, 1)]) + model((1, 1, 1), [(0, 0, 0, 2)])
        children += transform_node(1, 2, -1, {}, [{}]) + animated_shape_node(2, [(0, 0), (5, 1)])
        document = self.read(vox(children))
        self.assertEqual(0, document.evaluate_scene(0)[0].model_id)
        self.assertEqual(1, document.evaluate_scene(5)[0].model_id)

    def test_bounded_errors_are_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.vox"
            path.write_bytes(b"VOX " + struct.pack("<I", 150) + b"MAIN")
            with self.assertRaisesRegex(VoxError, "truncated"):
                read_vox(path)
            path.write_bytes(vox(model((2, 2, 2), [(0, 0, 0, 1), (1, 1, 1, 1)])))
            with self.assertRaisesRegex(VoxError, "voxel count exceeds"):
                read_vox(path, VoxLimits(max_voxels_per_model=1))

    def test_generated_corrupt_inputs_never_escape_as_struct_errors(self) -> None:
        generator = random.Random(1337)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fuzz.vox"
            for _ in range(100):
                path.write_bytes(os.urandom(generator.randrange(0, 128)))
                try:
                    read_vox(path, VoxLimits(max_file_bytes=1024))
                except VoxError:
                    pass


class VoxMesherTests(unittest.TestCase):
    def test_face_winding_points_outward(self) -> None:
        mesh = mesh_voxels([MeshingVoxel(0, 0, 0, 1)], "greedy")
        for face in mesh.faces:
            points = [mesh.vertices[index] for index in face]
            first, second, third = points[:3]
            edge_a = tuple(second[index] - first[index] for index in range(3))
            edge_b = tuple(third[index] - first[index] for index in range(3))
            normal = (
                edge_a[1] * edge_b[2] - edge_a[2] * edge_b[1],
                edge_a[2] * edge_b[0] - edge_a[0] * edge_b[2],
                edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0],
            )
            center = tuple(sum(point[index] for point in points) / 4 for index in range(3))
            outward = tuple(center[index] - 0.5 for index in range(3))
            self.assertGreater(sum(normal[index] * outward[index] for index in range(3)), 0)

    def test_greedy_merges_surface_faces_without_internal_faces(self) -> None:
        voxels = [MeshingVoxel(0, 0, 0, 1, "torso"), MeshingVoxel(1, 0, 0, 1, "torso")]
        cubes = mesh_voxels(voxels, "cubes")
        surface = mesh_voxels(voxels, "surface")
        greedy = mesh_voxels(voxels, "greedy")
        self.assertEqual(10, len(cubes.faces))
        self.assertEqual(10, len(surface.faces))
        self.assertEqual(6, len(greedy.faces))
        self.assertEqual(40, len(cubes.vertices))
        self.assertLess(len(surface.vertices), len(cubes.vertices))
        self.assertEqual({1}, set(greedy.material_indices))

    def test_greedy_never_crosses_semantic_or_material_boundaries(self) -> None:
        semantic_split = mesh_voxels([MeshingVoxel(0, 0, 0, 1, "torso"), MeshingVoxel(1, 0, 0, 1, "arm")], "greedy")
        material_split = mesh_voxels([MeshingVoxel(0, 0, 0, 1, "torso"), MeshingVoxel(1, 0, 0, 2, "torso")], "greedy")
        self.assertEqual(10, len(semantic_split.faces))
        self.assertEqual(10, len(material_split.faces))


if __name__ == "__main__":
    unittest.main()
