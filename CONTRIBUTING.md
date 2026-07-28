# Contributing

Run `./tools/verify.ps1 -Unit` before submitting changes. Pipeline changes should
also pass `./tools/verify.ps1 -Blender`; production export changes should pass
`./tools/verify.ps1 -Godot`, and preview changes should pass
`./tools/verify.ps1 -Visual`. The reference versions are Blender 4.5.5 LTS and
Godot 4.6.2.

Keep contracts versioned, add regression coverage for behavior changes, and do
not commit generated outputs, caches, logs, Godot imports, or proprietary inputs.
New tracked assets require the provenance record described in
`docs/ASSET_PROVENANCE.md`. Animation and engine behavior belong in versioned
packs/profiles under `config/`, not hard-coded pilot branches.
