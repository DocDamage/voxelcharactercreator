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
- transparent preview, color-coded part-map, and joint-pose `.png` files
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
`complete`.

For transactional-output regression testing, the worker accepts the test-only
`--fail-stage <stage>` switch; failed runs are retained under `exports/.runs/` and
do not replace the last promoted export.

## Roadmap

See the dependency-ordered [implementation plan](docs/IMPLEMENTATION_PLAN.md) for the next vertical slice, acceptance gates, architecture, and issue-ready backlog.
