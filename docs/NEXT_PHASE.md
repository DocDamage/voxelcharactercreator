# Next Phase

Phases 0-5, the first vertical slice, and its operator workflow are implemented and verified on Blender
4.5.5 LTS and Godot 4.6.2. The original Heavy Sword Hero now builds, animates,
passes QA, exports, and imports into Godot without opening Blender interactively.

The dependency-ordered backlog, acceptance gates, architecture, estimates, and
deferred scope are maintained in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Immediate Phase 6 work:

1. Add female, heavy, mage/robe, large-villain, and child/small base archetypes.
2. Add engine-safe secondary-motion segment rigs with rigid fallbacks.
3. Add sword/shield, spear, staff, katana, gunblade, firearm, and caster packs.
4. Measure and add LOD, atlas/material batching, compression, incremental previews, and safe queue parallelism.
5. Evaluate an out-of-process Godot viewer only if rendered previews prove insufficient.

The broader animation library is Phase 6 work. Additional attacks, guard,
damage, death, victory, and archetype-specific movement should use Animation Pack
v1 rather than introducing pilot-specific Blender code.
