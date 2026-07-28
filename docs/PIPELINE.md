# Pipeline

The LLM acts as an optional planner. It proposes a validated character-job diff;
an operator must approve that diff. Tested Python scripts perform Blender
operations deterministically.

Before Blender starts, the controller validates dependencies/capabilities,
writable paths, the canonical job, and VOX integrity. It persists the item in a
stage-aware queue and computes a cache key from jobs, sources, manifests,
configuration, and tool versions. A completed cache hit records every reused
stage in a new report; `-NoCache` performs a full evaluation.

1. Load job.
2. Resolve a versioned registry assembly, import an approved source, or generate a proxy.
3. Resolve semantic parts using reviewed overrides, manifests, names/layers, markers, then conservative spatial fallback.
4. Fit a versioned rig template, rigid-bind every resolved part, and align declared weapon sockets.
5. Resolve and validate versioned animation packs against the fitted rig.
6. Create the declared actions and validate curves, seams, foot sliding, events, required bones, and root motion.
7. Run stable-code geometry, rig, animation, profile-budget, and artifact QA.
8. Configure camera and lighting and render the fixed views, diagnostic views, and turntable.
9. Save the editable processed Blend file.
10. Export only the character meshes and armature through the selected engine profile.
11. For the production Godot profile, import the GLB into the pinned headless test project and verify its scene, skeleton, materials, actions, bounds, orientation, and scale.
12. Hash every artifact, record the semantic content hash, write Build Report v2, and atomically promote a successful run.

## Phase 2-4 production vertical slice

`characters/original/heavy_sword_hero.json` is the first public registry job. Its
`source.mode` is `assembly`, so validation resolves all declared IDs from
`assets/manifests/` before Blender starts. Each source asset is content-hash and
license checked, then imported as an individual editable Blender object carrying
its asset ID/version, semantic tags, pivots, palette roles, sockets, and declared
placement. Phase 3 resolves all 24 pilot objects to an explicit semantic role,
records an explanation trace, fits `config/rig_templates/humanoid_standard.v1.json`,
rigid-binds every object (including independent left/right garments), and aligns
the heavy sword to its declared mesh-space grip. Missing, ambiguous, or
low-confidence mappings stop the build rather than guessing.

Rig Template v1 reserves the exact `#FF0001`-`#FF001C` VOX palette range for
semantic markers in taxonomy order. The VOX importer converts those colors into
role candidates; reviewed job overrides and manifest tags still take precedence.

The successful pilot reports `complete`, writes a color-coded `*_part_map.png`,
and checks target body height, ground contact, symmetry, template joints/sockets,
rigid parenting, grip/carry transforms, and BVH-confirmed weapon/body clearance.
Reviewed corrections can be persisted
atomically with `python tools/save_part_mapping.py --job <job> --mapping <mapping.json>`;
subsequent builds replay that Job v2 `part_overrides` mapping exactly.

`config/animation_packs/heavy_sword_core.v1.json` supplies the Phase 4 actions:
`idle`, `walk`, `run`, and `heavy_sword_attack_1`. The attack declares trail and
hit windows; locomotion declares footstep events. Every action remains separately
addressable in Blender and exports as a named Godot animation.

`config/export_profiles/` holds the Godot, Unity, and Unreal scale, axis,
material, animation, texture, compression, and content-budget policies. The pilot
uses `godot_character`; only the 24 editable meshes and fitted armature are
exported. Preview cameras and lights never enter the GLB/FBX.

The render stage produces the transparent hero preview, part map, joint pose,
front/side/rear/three-quarter views, skeleton/socket diagnostics, and eight fixed
turntable frames. The versioned baseline policy is
`config/visual_baselines/heavy_sword_hero.v1.json`.

Run `python tools/generate_pilot_assets.py --check` to verify the deterministic
CC0 pilot corpus, and `./tools/verify.ps1 -Blender` for the registry and
fitted-rig and Phase 4 animation/QA integration tests. Use
`./tools/verify.ps1 -Visual` for the complete preview set and
`./tools/verify.ps1 -Godot` for the engine import gate.

The intended user workflow is select, build, review, approve. Blender never needs to be opened manually.

Phase 5 adds structured asset/equipment and part/palette editors, atomic undoable
job changes, variant duplication, determinate stage progress, failed-run
diagnostics, current/before-preview browsing, cancellation, deterministic retry,
and batch resume. See [OPERATOR_WORKFLOW.md](OPERATOR_WORKFLOW.md) for the operator
contract and recovery semantics.
