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
- Builds one mesh containing only exposed voxel faces, avoiding hidden interior geometry.
- Does not yet classify limbs automatically.

Production optimization can add greedy meshing, scene-graph support, part tags, and modular rigid-body assignment.
