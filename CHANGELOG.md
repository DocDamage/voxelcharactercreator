# Changelog

## Unreleased

Version: `0.4.0-factory`

- Completed Phase 6 with five original CC0 body archetypes and a shared registry/rig/build path.
- Added sword/shield, spear, staff, katana, gunblade, firearm, and caster Animation Pack v1 families.
- Added engine-safe baked hair/cape/coat-tail/skirt/robe chain contracts with rigid fallback.
- Added 100/50/25-percent LOD generation, palette material batching, engine compression policy, and content-addressed incremental previews.
- Added atomic bounded queue claims and conservative measured-concurrency recommendations.
- Generalized the Godot import gate to validate each job's declared actions and scale instead of pilot-specific constants.

- Completed Phase 5 with Blender/Godot/Ollama/OpenAI/path/input preflight and actionable corrective diagnostics.
- Added a durable stage-aware desktop build queue with structured progress events, cancellation, interrupted-batch resume, failed-stage retry provenance, and failed-run inspection.
- Added content-addressed completed-build caching over jobs, source assets, manifests, versioned configuration, and tool versions; Build Report v2 records per-stage hits, misses, and bypasses, and `-NoCache` forces a full build.
- Added compatible asset/equipment selection, semantic mapping and palette editing, undo/redo, atomic saves, and schema-valid variant duplication.
- Added current/before rendered-preview browsing and a validation dashboard for QA diagnostics and stage failures.
- Expanded LLM planning to reviewable registry-asset, palette, mapping, animation, export, and correction proposals; unsafe fields and source paths are rejected and validated diffs require explicit approval.

- Added the Phase 0 contract foundation: Job v2 migration and validation, build-report types, and safety policies.
- Added Phase 2 Asset Manifest v1, registry validation and lookup, and the original CC0 Heavy Sword Hero assembly job.
- Added 24 modular VOX source assets, including side-specific gloves, boots, and pauldrons, with per-asset thumbnails, provenance, source hashes, and headless Blender assembly verification.
- Added Phase 3 semantic taxonomy/resolution, template-driven fitted rigid binding, validated socket/carry transforms, mesh-space grip and BVH clearance checks, part-map and joint-pose previews, stricter Job/Rig Template contracts, and headless Blender rig verification.
- Added Phase 4 Animation Pack v1 contracts and the production `idle`, `walk`, `run`, and `heavy_sword_attack_1` actions with frame-rate, loop, event, root-motion, curve, foot-sliding, and required-bone validation.
- Added stable character QA diagnostics and export-profile budgets for detached parts, pivots, grounding, intersections, geometry/material counts, actions, and artifact completeness.
- Added fixed front, side, rear, three-quarter, skeleton, socket, part-map, joint-pose, and eight-frame turntable previews with a versioned visual baseline policy.
- Added versioned Godot, Unity, and Unreal export profiles, character-only export selection, deterministic semantic content hashing, and a Godot 4.6.2 headless GLB import gate.
- Fixed Godot Mono discovery on WinGet installations by resolving the real console executable beside its .NET assemblies instead of launching the WinGet symlink.
