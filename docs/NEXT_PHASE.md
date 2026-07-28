# Next Phase

Phases 0-6 are implemented and verified on Blender 4.5.5 LTS and Godot 4.6.2.
Five Phase 6 archetypes build through the same registry, rig, animation, QA,
optimization, export, and engine-import path.

The dependency-ordered backlog, acceptance gates, architecture, estimates, and
deferred scope are maintained in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Immediate Phase 7 work:

1. Convert the ten metadata profiles one at a time using original or user-supplied assets.
2. Measure content-production time and promote only proven variant/schema needs.
3. Keep reference analysis and similarity scoring advisory and reviewable.
4. Define packaging, signing, migration, update, and rollback strategy.

Additional attacks, guard, damage, death, victory, and archetype-specific
movement should continue to use Animation Pack v1. Rendered previews remain
sufficient for mapping/approval, so Phase 6 intentionally did not add an embedded
viewer; Godot stays an out-of-process automated gate.
