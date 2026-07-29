# Phase 8 advanced-character production

Phase 8 extends the production path without weakening its deterministic gates.
Run the complete acceptance matrix with:

```powershell
./tools/verify.ps1 -Phase8
```

The command regenerates and validates the tracked-original fixtures, builds the
quadruped, flying, multi-arm, and composite final-boss jobs without cache, runs
their Blender QA and Godot import gates, and verifies the 120-model production
plan. Successful jobs promote 20 hashed artifacts each.

The complete 120-model release gate is separate so it can resume safely:

```powershell
./tools/verify.ps1 -FullCast
```

This resolves 120 tracked Job v2 files, builds up to four at a time using isolated
Godot import projects, resumes current successful reports, writes a release ledger,
then re-hashes every job, implementation source tree, report, and artifact.

## Contracts and fallbacks

- `config/advanced_rigs/*.v1.json` declares acyclic topology bones, semantic
  roles, sockets, bone budgets, the complete engine-check set, and a rigid
  fallback template.
- `settings_overrides.deformation` selects rigid or deform binding, limits each
  vertex to four normalized influences, controls baked spring motion, and always
  requires `fallback: rigid`.
- `settings_overrides.boss_composition` limits attachment depth to four, object
  count to 64, phases to eight, and records engine budgets.
- Generated images or voxels begin as `review_required` proposals. Only files in
  `assets/generated` or `assets/incoming` can be proposed; approval records the
  reviewer, author, license, semantic tags, prompt hash, and content hash before
  ordinary asset-manifest authoring.

`tools/image_to_voxel.py` implements that workflow for non-interlaced RGB/RGBA
PNG input. It decodes PNG scanline filters, performs deterministic alpha/depth and
palette conversion, emits a normal MagicaVoxel file, and publishes only after the
separate image and voxel approvals.

## Spatial editor

The desktop **3D Character Editor** launches a real Godot 3D viewport for orbit,
zoom, direct XYZ part placement/rotation/scaling, existing-socket adjustment, rig
inspection, and animation playback. It returns an edit result to Python, where
canonical Job v2 validation and atomic saving occur. A Tk orthographic editor is
retained as the no-build fallback.

## Large-cast production

`config/production/large_cast.v1.json` references 120 canonical model jobs in six
bounded resumable batches. `full_cast_release.v1.json` is generated only from
their promoted reports; every release record carries unique semantic content,
implementation/job/report hashes, tool versions, artifact counts, and the parts,
rig, animation, export, and Godot completion matrix. The 2026-07-28 release audit
passed all 120 jobs, found 120 distinct semantic hashes, and found no unsafe
mesh-export warnings in their logs.
