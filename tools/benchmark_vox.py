"""Repeatable Phase 1 meshing benchmark (records, never gates, timing)."""

from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender_worker.geometry.vox_mesher import MeshingVoxel, mesh_voxels


def fixture() -> list[MeshingVoxel]:
    """Original 100k-voxel rectangular character-proxy benchmark fixture."""
    return [MeshingVoxel(x, y, z, 1 if z < 5 else 2, "lower" if z < 5 else "upper") for z in range(10) for y in range(100) for x in range(100)]


def measure(mode: str, voxels: list[MeshingVoxel]) -> dict[str, int | float]:
    tracemalloc.start()
    started = time.perf_counter()
    mesh = mesh_voxels(voxels, mode)  # type: ignore[arg-type]
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"seconds": round(elapsed, 6), "peak_python_bytes": peak, "faces": len(mesh.faces), "vertices": len(mesh.vertices)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="Optional JSON result path")
    args = parser.parse_args()
    voxels = fixture()
    results = {"fixture": "original_100k_voxel_proxy", "voxel_count": len(voxels), "surface": measure("surface", voxels), "greedy": measure("greedy", voxels)}
    results["expectations"] = {"greedy_faces_less_than_surface": results["greedy"]["faces"] < results["surface"]["faces"], "reference_seconds_target": 15, "reference_memory_target_bytes": 1_000_000_000}
    print(json.dumps(results, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
