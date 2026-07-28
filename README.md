# Voxel Character Factory

Windows-first starter for running Blender as an invisible character-processing backend.

## Included

- Tkinter desktop controller
- Blender auto-detection and manual executable selection
- Character JSON jobs
- Headless Blender processing
- Proxy voxel-character generation for pipeline testing
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

Set `source_model` in a character JSON file to a `.glb`, `.gltf`, `.fbx` or `.obj` file. If omitted, the worker builds a proxy figure to test the complete pipeline.

`.vox` files are imported directly as a single optimized surface mesh. The built-in reader supports standard single-model `SIZE`, `XYZI`, and `RGBA` chunks; multi-model scene graphs are not yet supported.

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
python -m unittest discover -v
python -m compileall -q app blender_worker tools tests
```
