# ADR-001: Pilot, coordinate system, binding, and public-IP boundary

Status: accepted for the Phase 0 implementation baseline. Owner: repository maintainer.

The pilot is the original **Heavy Sword Hero**, not a game character. Public builds may contain only original or redistributable assets with recorded provenance. Existing fan profiles remain data-only examples and are not release content.

Blender source uses right-handed Z-up coordinates, meters, with the ground plane at Z=0 and the character facing -Y. GLB export preserves these coordinates for the pinned Godot 4.x test project. Voxel geometry is rigidly parented to named bones; deformation is deferred. Actions use lowercase snake case (`idle`, `walk`, `run`, `heavy_sword_attack_1`). MagicaVoxel `.vox` is the pilot authoring format.

The Phase 4 baseline is Blender 4.5.5 LTS and Godot 4.6.2. Export axes, scale, material behavior, root motion, compression, and numeric content budgets live in versioned export profiles rather than Blender constants.
