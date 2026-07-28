# Changelog

## Unreleased

- Added the Phase 0 contract foundation: Job v2 migration and validation, build-report types, and safety policies.
- Added Phase 2 Asset Manifest v1, registry validation and lookup, and the original CC0 Heavy Sword Hero assembly job.
- Added 24 modular VOX source assets, including side-specific gloves, boots, and pauldrons, with per-asset thumbnails, provenance, source hashes, and headless Blender assembly verification.
- Added Phase 3 semantic taxonomy/resolution, template-driven fitted rigid binding, validated socket/carry transforms, mesh-space grip and BVH clearance checks, part-map and joint-pose previews, stricter Job/Rig Template contracts, and headless Blender rig verification.
- Added Phase 4 Animation Pack v1 contracts and the production `idle`, `walk`, `run`, and `heavy_sword_attack_1` actions with frame-rate, loop, event, root-motion, curve, foot-sliding, and required-bone validation.
- Added stable character QA diagnostics and export-profile budgets for detached parts, pivots, grounding, intersections, geometry/material counts, actions, and artifact completeness.
- Added fixed front, side, rear, three-quarter, skeleton, socket, part-map, joint-pose, and eight-frame turntable previews with a versioned visual baseline policy.
- Added versioned Godot, Unity, and Unreal export profiles, character-only export selection, deterministic semantic content hashing, and a Godot 4.6.2 headless GLB import gate.
- Fixed Godot Mono discovery on WinGet installations by resolving the real console executable beside its .NET assemblies instead of launching the WinGet symlink.
