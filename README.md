# Voxel Character Factory

Windows-first starter for running Blender as an invisible character-processing backend.

## Included

- Tkinter desktop controller
- Blender auto-detection and manual executable selection
- Character JSON jobs
- Headless Blender processing
- Proxy voxel-character generation for pipeline testing and a registry-assembled original Heavy Sword Hero fixture
- VOX, GLB, GLTF, FBX and OBJ source import
- Versioned fitted humanoid rig with deterministic semantic part resolution and rigid binding
- Eight versioned style families with exactly 24 clips per type, plus a 24-clip universal traversal pack
- Out-of-process Godot animation player with clip selection, scrubbing, looping, speed, orbit camera, events, and rig/socket overlays
- Transparent, fixed-angle diagnostic, and eight-angle turntable previews
- GLB and FBX export
- Godot 4.6.2 headless import gate and JSON Build Report v2
- Dependency/capability preflight with actionable corrections
- Durable stage-aware queue with immutable preflighted inputs, safe cancellation, retry, resume, and failed-run inspection
- Searchable 140-character library with game filtering, keyboard shortcuts, dirty-document protection, and compact-variant-safe editing
- Content-addressed completed-build cache with per-stage decisions and `-NoCache`
- Asset/equipment, semantic mapping, palette, variant, preview, and validation UI workflows
- Reviewable LLM asset/palette/correction proposals with validated field-level diffs
- Five reusable body archetypes (female, heavy, mage/robe, large villain, and child/small)
- Eight versioned weapon/animation families with engine-safe baked secondary motion and rigid fallback
- Three-level LOD generation, palette material batching, engine compression policy, incremental preview reuse, and measured queue-concurrency contracts
- Pilot jobs for Cecil, Kain, Rydia, Golbez, Terra, Kefka, Cloud, Sephiroth, Squall and Ultimecia
- Compact, cycle-safe Job v2 variant inheritance exercised by all ten converted profiles
- Reviewable multi-view part planning, non-blocking similarity QA, pilot-ten capacity metrics, and an FFIV-FFX production catalog
- Reproducible Windows source packaging with migration, update, rollback, dependency, and release-signing gates
- Data-driven quadruped, flying, multi-arm, and composite-boss rigs with original CC0 acceptance fixtures
- Optional deform binding with a mandatory deterministic rigid fallback
- Review-gated generated-asset provenance, a 3D part/socket editor, and a governed 120-model plan

## Run

1. Install Blender 4.5 LTS or newer.
2. Install Python 3.11 or newer.
3. Double-click `launch_windows.bat`.
4. Open Settings and choose `blender.exe` if it is not found automatically.
5. Select a character and click **Build Character**.

The app runs preflight before enqueueing. Use **Asset & Equipment Editor** and
**Part & Palette Overrides** for routine corrections, **Preview & Validation**
to inspect renders and QA, **3D Character Editor** for direct part/socket
placement, and **Retry Failed Stage** or **Resume Batch** for
recovery. Full instructions are in
[docs/OPERATOR_WORKFLOW.md](docs/OPERATOR_WORKFLOW.md).

Personal Blender, Godot, cache, and optional LLM-provider settings are stored
outside the repository under `%APPDATA%\VoxelCharacterFactory\settings.json`
on Windows. `config/settings.json` remains the portable default configuration,
so normal app use no longer dirties or packages machine-specific paths. Set
`VCF_SETTINGS_PATH` to override the personal settings location.

Windows source packages include only Git-indexed files by default and fail if
likely credentials are detected. Untracked development files require the explicit
`--include-untracked-development-files` opt-in and are labeled in the manifest.

## Source models

In Job v2, set `source.mode` to `model` and `source.path` to an approved `.vox`,
`.glb`, `.gltf`, `.fbx`, or `.obj` under `assets/original/` or
`assets/incoming/`. Use `source.mode: proxy` for compatibility testing. The
original `characters/original/heavy_sword_hero.json` uses `source.mode: assembly`
to resolve versioned CC0 manifests under `assets/manifests/`; its component
objects preserve semantic tags, pivots, sockets, palette roles, and origins.

`.vox` files are decoded with bounded parsing, support multi-model MagicaVoxel scene
graphs and palette/layer/material metadata, then import as normalized named meshes.
The `greedy` default merges compatible exposed faces; `surface` and `cubes` are
available diagnostics.

## Output

Successful artifacts remain in `exports/<game>/<character>/`. Operator metadata
is stored in ignored `exports/.queue/`, `exports/.cache/`, `exports/.history/`,
and `exports/.runs/` directories.

- processed `.blend`
- `.glb`
- `.fbx`
- transparent preview, part-map, joint-pose, six fixed diagnostic views, and eight turntable `.png` files
- Build Report v2 `.json` with checks, actions/events, stage timings, artifact hashes, tool versions, and semantic content hash

## Additional capabilities

- Built-in minimal MagicaVoxel `.vox` reader.
- Natural-language job patching through Ollama or OpenAI-compatible APIs.
- Job validation service.
- Shared palette definition.
- Standard attachment socket specification.
- Clear separation between LLM planning and deterministic Blender execution.

## Validate the project

Install the pinned JSON Schema validator once, then run the non-Blender checks:

```powershell
python -m pip install -r requirements-validation.txt
./tools/verify.ps1 -Unit
```

`tools/validate.ps1` meta-validates every published schema against JSON Schema
Draft 2020-12 and applies all eight published schemas to every governed repository
instance without Blender, migrating supported Job v1 inputs before the v2 schema
gate. `tools/verify.ps1 -Unit` also verifies the deterministic public pilot source
corpus and scans both Git index blobs and tracked working-tree text for likely
credentials.
`tools/build.ps1 -Job characters/ff7/cloud.json`
resolves the compact profile against its tracked-original production parent and
runs the complete assembly worker. Proxy jobs deliberately report `prototype`; an
imported but unbound model reports `incomplete` and never `complete`. Build outputs
are staged under `exports/.runs/` and successful `prototype` or `complete` builds are
atomically promoted to the public export location. The build wrapper discovers a
standard Windows Blender installation; use `-Blender C:/path/to/blender.exe` or
`VCF_BLENDER` to override it.

To build the original modular pilot, run:

```powershell
./tools/build.ps1 -Job characters/original/heavy_sword_hero.json
```

To create another character at any time, copy one of the
`characters/original/phase6_*.json` jobs, give it a new safe ID, and select
compatible versioned assets from the registry. New original `.vox` components
need Asset Manifest v1 records with hashes/provenance; proportions, rig,
secondary motion, animation family, LODs, and export behavior remain data-driven.
See [docs/ADDING_CHARACTERS.md](docs/ADDING_CHARACTERS.md).

It assembles 24 tracked CC0 assets, including independently rigged left/right
gloves, boots, and pauldrons; resolves every part; fits and rigid-binds the
template-driven production rig; aligns its declared sword sockets; and reports
`complete`. Production builds also run the Godot 4.6.2 headless import gate; set
`VCF_GODOT` if Godot is not discoverable through `PATH`.

The Godot Mono build must be launched from its real installation directory so it
can locate its `.NET` assemblies. The build and verification wrappers resolve
WinGet symlinks to the adjacent `*_console.exe` automatically.

Each weapon type contains 16 shared gameplay clips and eight type-specific moves.
Production jobs add 24 traversal clips plus 60 shared locomotion, transition,
interaction, and reaction clips for 108 exported actions per character.
After building, open **Preview & Validation** and click **Play Animations**.
See [docs/ANIMATIONS.md](docs/ANIMATIONS.md) for the complete catalog and controls.

For transactional-output regression testing, the worker accepts the test-only
`--fail-stage <stage>` switch; failed runs are retained under `exports/.runs/` and
do not replace the last promoted export.

Unchanged completed builds are reused by default. The cache key covers the job,
referenced inputs, manifests, configuration, and tool versions; Build Report v2
records every hit, miss, or bypass. Force a full build with:

```powershell
./tools/build.ps1 -Job characters/original/heavy_sword_hero.json -NoCache
```

## Roadmap

Phases 0-8 are complete. Phase 8's release ledger is backed by 120/120 passing,
semantically distinct Blender/Godot builds. See the
[implementation plan](docs/IMPLEMENTATION_PLAN.md) and
[Phase 8 guide](docs/PHASE8_ADVANCED.md) for the advanced-rig, deforming-mesh,
reviewable generation, 3D editing, and large-cast acceptance gates.
