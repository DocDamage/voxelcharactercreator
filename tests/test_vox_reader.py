from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from blender_worker.adapters.vox_reader import read_vox


def chunk(chunk_id: bytes, content: bytes) -> bytes:
    return chunk_id + struct.pack("<II", len(content), 0) + content


class VoxReaderTests(unittest.TestCase):
    def test_reads_minimal_single_model_file(self) -> None:
        children = chunk(b"SIZE", struct.pack("<III", 2, 3, 4)) + chunk(
            b"XYZI", struct.pack("<I", 1) + bytes((1, 2, 3, 7))
        )
        payload = b"VOX " + struct.pack("<I", 150) + b"MAIN" + struct.pack("<II", 0, len(children)) + children
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.vox"
            path.write_bytes(payload)
            model = read_vox(path)
        self.assertEqual(150, model["version"])
        self.assertEqual((2, 3, 4), model["size"])
        self.assertEqual([(1, 2, 3, 7)], model["voxels"])

    def test_rejects_non_vox_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.vox"
            path.write_bytes(b"nope")
            with self.assertRaisesRegex(ValueError, "Not a MagicaVoxel"):
                read_vox(path)


if __name__ == "__main__":
    unittest.main()
