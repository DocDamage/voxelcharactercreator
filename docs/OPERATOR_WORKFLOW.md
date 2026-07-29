# Operator Workflow

Phase 5 turns the proven headless pipeline into a recoverable desktop workflow.
The desktop app remains a controller: Blender performs deterministic content
work, while Python services own preflight, queue state, job edits, cache keys,
and proposal review.

## Before a build

Use the library search box and game filter to narrow the 140-character catalog.
The editor keeps the open document active even if a filter hides its row, marks
unsaved JSON with `*`, and offers Save/Discard/Cancel before selection changes or
shutdown. `Ctrl+S` saves, `Ctrl+F` focuses search, and `F5` validates the open job.

Use **Preflight** or start a build. The same check runs in both paths and reports
the detected Blender/Godot versions, LLM availability, writable output paths,
canonical job errors, and corrupt VOX inputs. Every issue includes a corrective
action. Blender 4.5 LTS is required. Godot 4.6.2 is optional for general use but
required when the selected job uses `godot_character`.

## Queue and recovery

Builds are persisted in `exports/.queue/queue.json`. Each item records its job,
state, active stage, failure, and optional retry stage. If the app closes during
a build, the item becomes `interrupted` on the next launch. **Resume Batch**
requeues interrupted, failed, and cancelled items. **Retry Failed Stage** records
the failed stage and replays deterministic prerequisites before that stage; this
avoids restoring an invalid partial Blender session. Cancelling terminates the
active workers, cancels all not-yet-claimed items, stops workers from claiming
more jobs, and relies on transactional promotion to keep the last successful
output untouched. Retry and resume repeat canonical validation and preflight
before any queue state changes. A corrupt queue file is preserved beside the
new queue as `queue.json.corrupt-*` instead of being silently overwritten.
Re-selecting a job that is already pending does not duplicate it. Pending
recovered work can also be cancelled while no worker is active.
One desktop app owns the project queue at a time. A second instance exits with an
actionable message, and a restarted app waits for any surviving Blender worker
from the prior session instead of rewriting its queue or inputs.

Each launch batch freezes its tool/cache settings and copies jobs, inheritance
parents, registered assets, configuration, worker code, and Godot gate scripts
into an ignored immutable input snapshot. Preflight runs against that exact
snapshot, and every Blender worker executes the snapshotted code and data while
promoting artifacts only to the real project output. Snapshots are removed after
completion or cancellation; retry and resume always create and validate a new one.
Process leases keep a snapshot safe across multiple app instances and during a
slow worker shutdown. Abandoned owned snapshots are reclaimed after 24 hours.

The worker emits `VCF_EVENT` JSON lines for stage start/pass/failure. The desktop
app uses them for determinate progress and durable queue updates. Failed Build
Report v2 files remain under `exports/.runs/<job-id>/`; **Preview & Validation**
opens the newest promoted or failed report and surfaces its diagnostics.

## Cache behavior

Completed builds are indexed by a SHA-256 over the canonical job, referenced
source assets, manifests, versioned JSON configuration, and tool versions. A hit
keeps the already promoted output and creates a new run report whose prior stages
are marked `cached` with zero duration. Misses and bypasses are recorded on every
executed stage. Failed and partial runs are never cached.
Before reuse, the cache rechecks the completion gate, canonical output namespace,
exact artifact file set, byte sizes, and SHA-256 hashes. Any mismatch forces a
fresh build, so stale files from a different export profile cannot leak into a hit.

Disable reuse in Settings or run a fully evaluated command:

```powershell
./tools/build.ps1 -Job characters/original/heavy_sword_hero.json -NoCache
```

Retry provenance is available from the CLI as well:

```powershell
./tools/build.ps1 -Job characters/original/heavy_sword_hero.json -RetryStage rig
```

A retry always bypasses cache reads and records `retry_from_stage` in Build
Report v2.

## Editing and review

- **Asset & Equipment Editor** selects compatible registry assets and equipment.
- **Part & Palette Overrides** edits semantic mappings, accent colors, and
  equipment with undo/redo before an atomic save.
- **3D Editor** uses the built GLB when Godot is available, or a guarded
  orthographic transform/socket editor before the first build. Both preserve
  compact variant inheritance and refuse to overwrite a file changed elsewhere.
- **Duplicate as Variant** creates a schema-valid job with `variant_of` set.
- **Preview & Validation** browses current renders, the captured before-build
preview, diagnostics, and failed-stage errors.
- **Play Animations** imports the promoted GLB into the standalone Godot player
  and exposes all 108 exported clips, their authored events, timeline, loop setting,
playback speed, orbit camera, and skeleton/socket diagnostics.
  Enabling **Traversal sandbox** activates the reference controller and test
  course for jump/double-jump, slide, roll, dash, air attacks, ladders, walls,
  swimming, rope swing, ledges, and grapple movement.
- **Describe Changes** asks the configured LLM for structured changes and
  diagnostics without blocking the desktop. Source paths and executable
  instructions are rejected. The app rejects stale proposals if the job changes,
  validates the resulting Job v2, shows a scrollable field-level diff, and applies
  it only after explicit operator confirmation.

Settings stores machine-specific paths and optional provider configuration in
`%APPDATA%\VoxelCharacterFactory\settings.json` on Windows. API keys remain in
the environment and are never written by the app.

Raw JSON remains available as an expert editor, but routine pilot correction no
longer requires it or an interactive Blender session.

## Reusable factory workflow

The character list includes five Phase 6 examples. Duplicate the closest job,
replace its compatible registry assets, and select a weapon animation family.
`secondary_motion` chains always declare a rigid fallback. `optimization`
defaults to 100/50/25-percent LODs, palette batching, engine compression, and
incremental preview reuse. A preview-only change rerenders; animation-only work
can reuse unchanged diagnostic images even during an uncached build.

Parallel claims are atomic and limited to four. Keep concurrency at one until
representative performance reports contain peak-memory measurements; the
factory recommendation uses half the logical CPUs, available memory after a
2 GB reserve, and a hard four-worker ceiling.

The animation player requires a successful GLB build and the configured Godot
executable. It runs out of process, so closing or restarting it cannot mutate the
job, Blender source, queue, or promoted export.
