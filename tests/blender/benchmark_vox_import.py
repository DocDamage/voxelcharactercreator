"""Record Phase 1 100k-voxel Blender import metrics without hardware gating."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender_worker.stages.vox_ingest import VoxImportOptions, import_vox_scene


def _working_set_bytes() -> int | None:
    if os.name != "nt":
        try:
            import resource
            # Linux reports KiB; macOS reports bytes.
            value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return int(value if sys.platform == "darwin" else value * 1024)
        except (ImportError, AttributeError):
            return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_memory_info = psapi.GetProcessMemoryInfo
    get_memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_memory_info.restype = wintypes.BOOL
    process = ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentProcess()
    success = get_memory_info(process, ctypes.byref(counters), counters.cb)
    return int(counters.PeakWorkingSetSize) if success else None


def _chunk(chunk_id: bytes, content: bytes, children: bytes = b"") -> bytes:
    return chunk_id + struct.pack("<II", len(content), len(children)) + content + children


def _fixture() -> bytes:
    body = b"".join(bytes((x, y, z, 1 if z < 5 else 2)) for z in range(10) for y in range(100) for x in range(100))
    children = _chunk(b"SIZE", struct.pack("<III", 100, 100, 10)) + _chunk(b"XYZI", struct.pack("<I", 100_000) + body)
    return b"VOX " + struct.pack("<I", 150) + _chunk(b"MAIN", b"", children)


def _material(name: str, color: str):
    return bpy.data.materials.new(name)


def main() -> None:
    temporary = tempfile.TemporaryDirectory()
    path = Path(temporary.name) / "benchmark.vox"
    path.write_bytes(_fixture())
    started = time.perf_counter()
    objects = import_vox_scene(path, _material, VoxImportOptions(meshing_mode="greedy"))
    result = {
        "fixture": "original_100k_voxel_proxy",
        "seconds_after_blender_startup": round(time.perf_counter() - started, 6),
        "peak_working_set_bytes": _working_set_bytes(),
        "objects": len(objects),
        "faces": sum(len(item.data.polygons) for item in objects),
        "reference_targets": {"seconds": 15, "bytes": 1_000_000_000},
    }
    print(json.dumps(result, indent=2))
    output = os.environ.get("VCF_BENCHMARK_OUTPUT")
    if output:
        Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
