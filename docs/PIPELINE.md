# Pipeline

The LLM acts as the planner. It edits a validated character job. Tested Python scripts perform Blender operations deterministically.

1. Load job.
2. Resolve a versioned registry assembly, import an approved source, or generate a proxy.
3. Build rig.
4. Attach rigid body parts and weapon.
5. Apply animation profile.
6. Configure camera and lighting.
7. Render preview.
8. Export GLB and FBX.
9. Save processed Blend file.
10. Write validation report.

## Phase 2 registry assembly

`characters/original/heavy_sword_hero.json` is the first public registry job. Its
`source.mode` is `assembly`, so validation resolves all declared IDs from
`assets/manifests/` before Blender starts. Each source asset is content-hash and
license checked, then imported as an individual editable Blender object carrying
its asset ID/version, semantic tags, pivots, palette roles, sockets, and declared
placement. Assembly grounds the visible character but does not rigid-bind it; that
is intentionally deferred to Phase 3, and the build report remains `incomplete`.

Run `python tools/generate_pilot_assets.py --check` to verify the deterministic
CC0 pilot corpus, and `./tools/verify.ps1 -Blender` for the registry integration
test.

The intended user workflow is select, build, review, approve. Blender never needs to be opened manually.
