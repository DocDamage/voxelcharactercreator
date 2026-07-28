from __future__ import annotations
import struct
from pathlib import Path

DEFAULT_PALETTE = [(i, i, i, 255) for i in range(256)]

def read_vox(path: Path):
    data = path.read_bytes()
    if data[:4] != b"VOX ":
        raise ValueError("Not a MagicaVoxel VOX file")
    version = struct.unpack_from("<I", data, 4)[0]
    offset = 8
    if data[offset:offset+4] != b"MAIN":
        raise ValueError("Invalid VOX MAIN chunk")
    _, children_size = struct.unpack_from("<II", data, offset + 4)
    offset += 12
    end = offset + children_size
    size = None
    voxels = []
    palette = DEFAULT_PALETTE[:]
    while offset < end:
        cid = data[offset:offset+4]
        content_size, child_size = struct.unpack_from("<II", data, offset+4)
        content = data[offset+12:offset+12+content_size]
        if cid == b"SIZE":
            size = struct.unpack_from("<III", content, 0)
        elif cid == b"XYZI":
            count = struct.unpack_from("<I", content, 0)[0]
            voxels = [tuple(content[4+i*4:8+i*4]) for i in range(count)]
        elif cid == b"RGBA":
            palette = [tuple(content[i*4:(i+1)*4]) for i in range(256)]
        offset += 12 + content_size + child_size
    if size is None:
        raise ValueError("VOX file contains no SIZE chunk")
    return {"version": version, "size": size, "voxels": voxels, "palette": palette}
