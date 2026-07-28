# Asset provenance policy

Tracked assets must have a manifest recording asset ID, source hash, author, license, provenance URL or creation statement, and permitted use. `assets/original/` is reserved for original or redistributable source content. `assets/incoming/` is local, ignored input for operator-provided files and must never be committed.

The Phase 2 Heavy Sword Hero corpus is original CC0 content. Its 24 deterministic `.vox` source files and individual SVG thumbnails live under `assets/original/heavy_sword_hero/`; the corresponding versioned records are in `assets/manifests/heavy_sword_hero.assets.v1.json`. Gloves, boots, and pauldrons are side-specific so Phase 3 can rigid-bind them independently. Regenerate only with `python tools/generate_pilot_assets.py`, then use `--check` to verify the committed corpus and hashes.

Phase 4 animations, export profiles, visual-baseline policy, Godot test project,
and generated previews contain no third-party character, texture, or audio data.
Generated build artifacts remain ignored under `exports/`, and the temporary GLB
copied into `tests/godot/imported/` is ignored as well.

The Phase 6 corpus is also original CC0 content. It contains five generated body
archetypes, their weapon fixtures, a sword/shield pair, and shared gunblade and
firearm fixtures under `assets/original/phase6/`. Versioned records live in
`assets/manifests/phase6_*.assets.v1.json`. Regenerate and verify the complete
corpus with `python tools/generate_phase6_assets.py --check`.

Do not commit official artwork, ripped models, game textures, audio, or other proprietary game assets. Fan-character jobs are metadata examples only until a licensing decision authorizes their packaging.
