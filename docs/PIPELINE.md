# Pipeline

The LLM acts as the planner. It edits a validated character job. Tested Python scripts perform Blender operations deterministically.

1. Load job.
2. Resolve a versioned registry assembly, import an approved source, or generate a proxy.
3. Resolve semantic parts using reviewed overrides, manifests, names/layers, markers, then conservative spatial fallback.
4. Fit a versioned rig template, rigid-bind every resolved part, and align declared weapon sockets.
5. Apply animation profile.
6. Configure camera and lighting.
7. Render preview.
8. Export GLB and FBX.
9. Save processed Blend file.
10. Write validation report.

## Phase 2-3 registry assembly and rigid rig

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

Run `python tools/generate_pilot_assets.py --check` to verify the deterministic
CC0 pilot corpus, and `./tools/verify.ps1 -Blender` for the registry and
fitted-rig integration tests.

The intended user workflow is select, build, review, approve. Blender never needs to be opened manually.
