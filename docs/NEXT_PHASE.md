# Next Phase

Phases 0-4 and the first vertical slice are implemented and verified on Blender
4.5.5 LTS and Godot 4.6.2. The original Heavy Sword Hero now builds, animates,
passes QA, exports, and imports into Godot without opening Blender interactively.

The dependency-ordered backlog, acceptance gates, architecture, estimates, and
deferred scope are maintained in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Immediate Phase 5 work:

1. Add Blender/Godot/Ollama dependency and capability preflight with corrective actions.
2. Make the queue stage-aware with safe cancellation, retry, resume, and failed-run inspection.
3. Cache stages by input, configuration, and tool hashes, including an explicit `--no-cache` path.
4. Add asset selection, semantic mapping, palette/equipment, and undoable job-editing workflows.
5. Surface previews, QA diagnostics, stage progress, and retry actions in the desktop UI.
6. Extend the LLM planner with schema-valid asset suggestions and reviewable corrections.

The broader animation library remains Phase 6 work. Additional attacks, guard,
damage, death, victory, and archetype-specific movement should use Animation Pack
v1 rather than introducing pilot-specific Blender code.
