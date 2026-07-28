# ADR-001: Pilot, coordinate system, binding, and public-IP boundary

Status: accepted for the Phase 0 implementation baseline. Owner: repository maintainer.

The pilot is the original **Heavy Sword Hero**, not a game character. Public builds may contain only original or redistributable assets with recorded provenance. Existing fan profiles remain data-only examples and are not release content.

Blender source uses right-handed Z-up coordinates, meters, with the ground plane at Z=0 and the character facing -Y. GLB export preserves these coordinates for the pinned Godot 4.x test project. Voxel geometry is rigidly parented to named bones; deformation is deferred. Actions use lowercase snake case (`idle`, `walk`, `run`, `heavy_sword_attack_1`). MagicaVoxel `.vox` is the pilot authoring format.

Open decisions, before their dependent work begins: exact supported Blender LTS patch and Godot patch; material batching/vertex-color representation; numeric rig and export tolerances. Those values belong in versioned profiles, not Blender constants.
