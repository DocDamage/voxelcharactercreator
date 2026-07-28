# Adding characters

New characters use data and assets; they do not require a Blender-worker fork.

1. Copy the closest `characters/original/phase6_*.json` fixture and change its
   `id`, `name`, and catalog choices.
2. Put original/redistributable `.vox` sources under `assets/original/` and add
   Asset Manifest v1 entries with semantic tags, compatible base, placement,
   SHA-256, author, license, provenance, and thumbnail.
3. List the asset IDs in `source.asset_ids`. A production humanoid needs the 15
   required body roles; optional hair, garments, weapon, shield, and accessories
   remain separate editable objects.
4. Choose a compatible `rig_template` and one or more versioned
   `animation_packs`. Use `target_height_meters` and bounded
   `limb_length_overrides` for proportions.
5. Optionally declare `secondary_motion` chains. Each chain must name its
   segments, parent, stiffness/damping, angle limit, and `rigid` fallback.
6. Keep or adjust `optimization` LOD ratios, material batching, compression, and
   incremental-preview policy.
7. Run `./tools/validate.ps1`, `./tools/verify.ps1 -Unit`, then an uncached build.

Use `python tools/generate_phase6_assets.py` as a deterministic content example,
not as a requirement for hand-authored assets. Unknown, incompatible, unhashed,
or unlicensed assets fail before Blender starts.
