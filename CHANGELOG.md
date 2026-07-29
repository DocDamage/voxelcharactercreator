# Changelog

## Unreleased

Version: `0.6.0-phase8`

- Hardened the desktop operator experience with a searchable/filterable character library, scrollable grouped controls, dirty-document prompts, safe list refresh, full-catalog build confirmation, keyboard shortcuts, and an expanded validation dashboard.
- Preserved compact Job v2 inheritance across asset, override, and fallback spatial editing instead of flattening resolved parents into child jobs.
- Made cancellation stop active and pending work even when queue persistence fails, closed pre-launch races, hardened corrupt-queue recovery, added guarded retry/resume preflight, and ensured shutdown terminates every tracked worker.
- Moved machine-specific settings to the per-user application-data directory, exposed Blender/Godot and optional LLM configuration in-app, and made LLM proposals non-blocking with stale-edit detection and a scrollable review gate.
- Added fast metadata-only catalog startup, complete render-affecting preview fingerprints, Draft 2020-12 metaschema checks, generator drift checks in CI, and fail-closed Windows verification wrappers.
- Restricted source packages to Git-indexed files by default, added explicit labeling for untracked development snapshots, and added a pre-package secret scan.
- Added per-batch immutable input snapshots so Blender consumes the exact jobs, assets, configuration, code, and Godot gates that passed preflight.
- Guarded concurrent 3D editor sessions, made editor completion path-aware, handled folder-launch errors, and expanded prefixed-credential detection across all indexed paths.
- Made queue transitions transactional on persistence failures and protected active input snapshots with per-process leases across concurrent app instances.
- Enforced canonical output namespaces, exact cache artifact sets and hashes, matching executed-code provenance, strict final completion gates, and nonzero exits for incomplete builds.
- Applied every published schema to its governed instances (including migrated Job v1 inputs) and scanned both staged Git blobs and tracked working-tree bytes for quoted or unquoted credentials.

- Completed Phase 8 with data-driven quadruped, flying, multi-arm, and composite-boss rigs and original CC0 fixtures.
- Added bounded multi-phase boss composition and topology-aware Blender/Godot gates.
- Added optional deform binding, advanced secondary-motion policy, and mandatory rigid fallback.
- Added review-required generated-asset provenance, the 3D Character Editor, and a governed 120-model production catalog.
- Built and independently audited all 120 canonical cast jobs with distinct semantic hashes, current report/artifact hashes, passed completion matrices, and no unsafe mesh-export warnings.
- Added `tools/verify.ps1 -Phase8` for the four advanced fixtures and `tools/verify.ps1 -FullCast` for the resumable 120-model release gate.

- Completed Phase 7 by converting all ten legacy profiles into compact Job v2 variants backed by tracked-original CC0 assemblies and the shared completion matrix.
- Added deterministic, cycle-safe variant resolution and inherited-build cache invalidation.
- Added reviewable multi-view reference planning, explicitly advisory visual-similarity scoring, and false-positive measurement.
- Added the measured pilot-ten capacity model and governed FFIV-FFX production database.
- Added deterministic Windows source packaging plus fail-closed migration, update, rollback, dependency, Authenticode, and timestamp policies.

- Formalized Phase 8 around nonhuman and final-boss rigs, deforming meshes, reviewable generative image-to-voxel workflows, a full 3D character editor, and governed 100-plus-model production.
- Expanded all eight weapon families to exactly 24 validated animations each: 16 shared gameplay states and eight type-specific moves.
- Added an out-of-process Godot animation player with play/pause, restart, loop control, timeline scrubbing, speed control, orbit/zoom camera, authored event display, frame stepping, and skeleton/socket overlays.
- Added **Play Animations** to the desktop Preview & Validation dashboard and a headless player smoke test to Godot verification.
- Added a separate 24-clip humanoid traversal pack covering slide, roll, double jump, four air attacks, dash, ladders, wall movement, swimming, rope movement, grappling, and ledges while preserving exactly 24 clips in each type pack.
- Added four reusable shared packs: 16-directional locomotion, 16 traversal transitions, 12 interactions, and 16 combat reactions. Production characters now export 108 uniquely named actions.
- Added a playable Godot traversal sandbox and reference CharacterBody3D controller for those mechanics.

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
