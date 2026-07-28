# Operator Workflow

Phase 5 turns the proven headless pipeline into a recoverable desktop workflow.
The desktop app remains a controller: Blender performs deterministic content
work, while Python services own preflight, queue state, job edits, cache keys,
and proposal review.

## Before a build

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
worker, marks the item cancelled, and relies on transactional promotion to keep
the last successful output untouched.

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
- **Duplicate as Variant** creates a schema-valid job with `variant_of` set.
- **Preview & Validation** browses current renders, the captured before-build
  preview, diagnostics, and failed-stage errors.
- **Describe Changes** asks the configured LLM for structured changes and
  diagnostics. Source paths and executable instructions are rejected. The app
  validates the resulting Job v2, shows the field-level diff, and applies it only
  after explicit operator confirmation.

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
