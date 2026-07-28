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
- Versioned production animation pack (`idle`, `walk`, `run`, `heavy_sword_attack_1`) with events and validation
- Transparent, fixed-angle diagnostic, and eight-angle turntable previews
- GLB and FBX export
- Godot 4.6.2 headless import gate and JSON Build Report v2
- Dependency/capability preflight with actionable corrections
- Durable stage-aware queue with safe cancellation, retry, resume, and failed-run inspection
- Content-addressed completed-build cache with per-stage decisions and `-NoCache`
- Asset/equipment, semantic mapping, palette, variant, preview, and validation UI workflows
- Reviewable LLM asset/palette/correction proposals with validated field-level diffs
- Pilot jobs for Cecil, Kain, Rydia, Golbez, Terra, Kefka, Cloud, Sephiroth, Squall and Ultimecia

## Run

1. Install Blender 4.5 LTS or newer.
2. Install Python 3.11 or newer.
3. Double-click `launch_windows.bat`.
4. Open Settings and choose `blender.exe` if it is not found automatically.
5. Select a character and click **Build Character**.

The app runs preflight before enqueueing. Use **Asset & Equipment Editor** and
**Part & Palette Overrides** for routine corrections, **Preview & Validation**
to inspect renders and QA, and **Retry Failed Stage** or **Resume Batch** for
recovery. Full instructions are in
[docs/OPERATOR_WORKFLOW.md](docs/OPERATOR_WORKFLOW.md).

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

The non-Blender components use the standard-library test runner:

```powershell
./tools/verify.ps1 -Unit
```

`tools/validate.ps1` validates the versioned job and asset-manifest contracts without Blender. `tools/verify.ps1 -Unit` also verifies the deterministic public pilot source corpus.
`tools/build.ps1 -Job characters/ff7/cloud.json`
runs the compatibility worker. Proxy jobs deliberately report `prototype`; an
imported but unbound model reports `incomplete` and never `complete`. Build outputs
are staged under `exports/.runs/` and successful `prototype` or `complete` builds are
atomically promoted to the public export location. The build wrapper discovers a
standard Windows Blender installation; use `-Blender C:/path/to/blender.exe` or
`VCF_BLENDER` to override it.

To build the original modular pilot, run:

```powershell
./tools/build.ps1 -Job characters/original/heavy_sword_hero.json
```

It assembles 24 tracked CC0 assets, including independently rigged left/right
gloves, boots, and pauldrons; resolves every part; fits and rigid-binds the
template-driven production rig; aligns its declared sword sockets; and reports
`complete`. Production builds also run the Godot 4.6.2 headless import gate; set
`VCF_GODOT` if Godot is not discoverable through `PATH`.

The Godot Mono build must be launched from its real installation directory so it
can locate its `.NET` assemblies. The build and verification wrappers resolve
WinGet symlinks to the adjacent `*_console.exe` automatically.

The current Phase 4 action set is intentionally small: `idle`, `walk`, `run`, and
`heavy_sword_attack_1`. Add new clips as versioned Animation Pack v1 data under
`config/animation_packs/`; incompatible bone requirements fail before export.

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

Phases 0-5 and the operator-workflow gate are complete. See the dependency-ordered
[implementation plan](docs/IMPLEMENTATION_PLAN.md) and [next phase](docs/NEXT_PHASE.md)
for Phase 6 reusable-factory work.
