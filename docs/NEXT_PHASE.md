# Next Phase

Phases 0-3 are implemented and verified on Blender 4.5.5 LTS. The next milestone
is one real, editable, rigged, animated, Godot-tested voxel character built end
to end without opening Blender interactively.

The dependency-ordered backlog, acceptance gates, architecture, estimates, and
deferred scope are maintained in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Immediate Phase 4 work:

1. Define Animation Pack v1, action naming, frame-rate, loop, event, and root-motion contracts.
2. Produce and validate `idle`, `walk`, `run`, and `heavy_sword_attack_1` for the fitted rig.
3. Add stable geometry, rig, animation, artifact, and visual QA diagnostics.
4. Render the full fixed-camera and skeleton/socket preview set with reviewed baselines.
5. Add versioned export profiles and a pinned Godot 4.x headless import test.
6. Gate the vertical slice on deterministic rebuilds and a loadable, correctly scaled, animated GLB.

Do not expand the UI, full cast, or image-generation workflow until the
engine-tested vertical-slice gate passes.
