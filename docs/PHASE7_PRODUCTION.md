# Phase 7 production hardening

Phase 7 converts the ten legacy metadata profiles into Job v2 variants of
tracked-original CC0 assemblies. The profiles remain data-only fan examples: the
repository does not contain official artwork, ripped models, textures, or audio.
Every resolved job enters the same assembly, resolver, rig, animation, QA, export,
and Godot gate used by the original acceptance fixtures.

## Variant inheritance

A compact variant requires `schema_version`, `id`, `name`, and `variant_of`, then
declares only its overrides. `load_job` resolves the parent by unique repository
job ID, recursively merges overrides, rejects missing parents and cycles, and
validates the fully resolved Job v2. Cache keys hash that resolved representation,
so a parent change invalidates every dependent build.

The ten conversions deliberately reuse proven original geometry. They do not
claim to be original recreations of copyrighted character designs; their names,
palette suggestions, and metadata remain data-only examples.

## Completion and capacity

`config/production/pilot_ten.v1.json` records the complete ten-check acceptance
matrix and timed conversion effort for each profile. Capacity uses the measured
90th-percentile effort rather than the fastest case. `cast_ff4_ff10.v1.json`
separates converted profiles from backlog records and requires user-supplied
assets for backlog fan entries.

## Reference planning and visual similarity

`vcf_core.production.plan_reference_analysis` accepts reviewed observations from
two or more labeled views and emits a `review_required` job proposal plus semantic
part requests. It cannot emit Blender code or source paths.

Visual similarity consumes normalized silhouette, palette, and landmark features.
Its result always contains `advisory: true` and `blocking: false`. Review outcomes
can be accumulated to measure false-positive rate before any future policy change.

## Windows distribution

The versioned Windows strategy requires pre-replacement migration validation,
hash and Authenticode verification before atomic promotion, preservation of one
previous installation for rollback, and external dependency preflight. Run:

```powershell
./tools/package_windows.ps1
```

This produces a byte-for-byte deterministic development source ZIP for an
identical selected working tree and an update manifest under
`exports/packages/`. It is deliberately marked unsigned. Release publication is
fail-closed until an Authenticode certificate and timestamp service are supplied;
the repository never creates a fake signature or silently installs dependencies.
By default, the package contains only Git-indexed files and rejects likely secret
material. For local development snapshots, pass
`--include-untracked-development-files` directly to `tools/package_windows.py`;
the resulting manifest is visibly marked as including untracked content.

Run all ten uncached Blender/Godot completion builds and verify their promoted
reports with `./tools/verify.ps1 -Phase7`.
