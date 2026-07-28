# VOX Pipeline

The advanced starter includes a minimal reader for MagicaVoxel VOX files.

Supported:

- Standard `SIZE`
- Standard `XYZI`
- Standard `RGBA`
- Single-model voxel files

Current limits:

- Does not yet process multi-model scene graphs.
- Does not yet merge adjacent voxels into optimized meshes.
- Imports one cube per voxel, which is reliable but inefficient.
- Does not yet classify limbs automatically.

Production optimization will add greedy meshing, scene-graph support, part tags, and modular rigid-body assignment.
