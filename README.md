# Voxel Character Factory

Windows-first starter for running Blender as an invisible character-processing backend.

## Included

- Tkinter desktop controller
- Blender auto-detection and manual executable selection
- Character JSON jobs
- Headless Blender processing
- Proxy voxel-character generation for pipeline testing and a registry-assembled original Heavy Sword Hero fixture
- VOX, GLB, GLTF, FBX and OBJ source import
- Standard rigid humanoid armature
- Basic idle animation
- Transparent preview render
- GLB and FBX export
- JSON validation report
- Pilot jobs for Cecil, Kain, Rydia, Golbez, Terra, Kefka, Cloud, Sephiroth, Squall and Ultimecia

## Run

1. Install Blender 4.5 LTS or newer.
2. Install Python 3.11 or newer.
3. Double-click `launch_windows.bat`.
4. Open Settings and choose `blender.exe` if it is not found automatically.
5. Select a character and click **Build Character**.

## Source models

Set `source_model` in a character JSON file to a `.glb`, `.gltf`, `.fbx` or `.obj` file. If omitted, the worker builds a proxy figure to test the complete pipeline. The original `characters/original/heavy_sword_hero.json` uses Job v2 `source.mode: assembly` to resolve versioned, CC0 manifests under `assets/manifests/`; its component objects preserve semantic tags, pivots, sockets, palette roles, and origins for later rigging.

`.vox` files are decoded with bounded parsing, support multi-model MagicaVoxel scene
graphs and palette/layer/material metadata, then import as normalized named meshes.
The `greedy` default merges compatible exposed faces; `surface` and `cubes` are
available diagnostics.

## Output

`exports/<game>/<character>/`

- processed `.blend`
- `.glb`
- `.fbx`
- transparent preview `.png`
- validation report `.json`

## Advanced-phase additions

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

`tools/validate.ps1` validates the versioned job and asset-manifest contracts without Blender. `python tools/generate_pilot_assets.py --check` verifies the deterministic public pilot source corpus.
`tools/build.ps1 -Job characters/ff7/cloud.json -Blender C:/path/to/blender.exe`
runs the compatibility worker. Proxy jobs deliberately report `prototype`; an
imported but unbound model reports `incomplete` and never `complete`. Build outputs
are staged under `exports/.runs/` and only a successful proxy compatibility build is
atomically promoted to the public export location.

To build the original modular pilot, run:

```powershell
./tools/build.ps1 -Job characters/original/heavy_sword_hero.json -Blender C:/path/to/blender.exe
```

It assembles 21 tracked CC0 assets and exports editable artifacts, but intentionally
reports `incomplete` until Phase 3 provides semantic resolution and rigid binding.

For transactional-output regression testing, the worker accepts the test-only
`--fail-stage <stage>` switch; failed runs are retained under `exports/.runs/` and
do not replace the last promoted export.

## Roadmap

See the dependency-ordered [implementation plan](docs/IMPLEMENTATION_PLAN.md) for the next vertical slice, acceptance gates, architecture, and issue-ready backlog.
