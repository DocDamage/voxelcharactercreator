# Asset provenance policy

Tracked assets must have a manifest recording asset ID, source hash, author, license, provenance URL or creation statement, and permitted use. `assets/original/` is reserved for original or redistributable source content. `assets/incoming/` is local, ignored input for operator-provided files and must never be committed.

The Phase 2 Heavy Sword Hero corpus is original CC0 content. Its 21 deterministic `.vox` source files and individual SVG thumbnails live under `assets/original/heavy_sword_hero/`; the corresponding versioned records are in `assets/manifests/heavy_sword_hero.assets.v1.json`. Regenerate only with `python tools/generate_pilot_assets.py`, then use `--check` to verify the committed corpus and hashes.

Do not commit official artwork, ripped models, game textures, audio, or other proprietary game assets. Fan-character jobs are metadata examples only until a licensing decision authorizes their packaging.
