# Next Phase

The next milestone is one real, editable, rigged, animated, Godot-tested voxel character built end to end without opening Blender interactively.

The dependency-ordered backlog, acceptance gates, architecture, estimates, and deferred scope are maintained in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Immediate work:

1. Lock the pilot, coordinate, binding, Godot, and IP decisions in an ADR.
2. Replace the obsolete bootstrap workflow with validation CI.
3. Extract versioned build/stage contracts from the Blender worker.
4. Add Job v2 migrations and transactional build outputs.
5. Complete MagicaVoxel scene-graph support and greedy meshing.
6. Asset Manifest v1 and the original Heavy Sword Hero registry fixture are implemented; Phase 3 begins semantic part resolution and rigid rigging.

Do not expand the UI, full cast, or image-generation workflow until the engine-tested vertical-slice gate passes.
