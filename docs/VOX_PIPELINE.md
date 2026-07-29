# VOX Pipeline

Phase 1 decodes MagicaVoxel VOX files into typed, Blender-independent models before
anything is imported. It supports `PACK`, multiple `SIZE`/`XYZI` models, `RGBA`,
`MATL`, `LAYR`, dictionaries, and safely records unknown chunks. File, chunk, model,
dimension, and voxel limits turn corrupt input into actionable `VoxError` messages.

`nTRN`, `nGRP`, and `nSHP` scene graphs resolve named, layered model instances with
visibility, frame selection, translations, and orthogonal rotations. The Blender
adapter preserves model/layer/semantic identity in collections and custom properties,
normalizes the visible scene to a Z=0 ground plane, and emits palette materials.

Meshing modes are explicit:

- `greedy` merges coplanar exposed faces only when material and semantic part match.
- `surface` retains exposed quads with shared vertices.
- `cubes` is a diagnostic mode with independent face vertices, but still removes internal faces.

Run `./tools/verify.ps1 -Performance` for the original 100k-voxel benchmark. It
records mesh and Blender-import metrics in `logs/` without gating hardware-sensitive
limits.

VOX metadata remains addressable through part resolution, rigid binding,
animation, QA, and export. Production completion is gated downstream: a valid VOX
mesh alone cannot report `complete` unless every visible part is resolved and
bound and the selected animation/export profile passes.
