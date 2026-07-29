# Phase 9 Release Readiness Plan

Status: planned

Phase 9 closes four known gaps between the completed Phase 8 production system
and a release-ready project. It replaces rigid per-part "deform" weights with
measured smooth skinning, makes animation quality objectively reviewable, runs
the real Blender/Godot gates in CI, and records an explicit repository-license
decision.

This phase does not expand the cast, add new topology families, or select a
license on the owner's behalf. Rigid binding remains a supported deterministic
mode and the mandatory fallback for failed smooth binding.

## Outcomes

Phase 9 is complete when:

1. `deform` means normalized multi-bone vertex weighting near articulated
   joints, with deterministic output, bounded influences, validation, reporting,
   and a tested rigid fallback.
2. Every release animation passes versioned motion-quality thresholds in
   addition to the existing action, event, export, and engine-contract checks.
3. Trusted changes and scheduled builds execute pinned Blender and Godot
   integration gates on a suitably isolated runner, retaining useful failure
   artifacts.
4. The repository owner has accepted a documented licensing decision and the
   repository, package, asset notices, and release documentation consistently
   implement it.

## Workstream A: deterministic smooth skinning

The current implementation creates one weight group per object and assigns every
vertex to one bone at weight `1.0`. That is valid Armature binding but remains
rigid per-part weighting. Phase 9 must not report smooth skinning until vertices
inside reviewed joint envelopes can receive weights from multiple related bones.

| ID | Size | Depends on | Deliverable |
| --- | --- | --- | --- |
| SKIN-901 | M | - | Version the deformation policy with algorithm, joint-envelope, falloff, influence, quantization, and fallback settings. Reject unknown or unsafe combinations before Blender starts. |
| SKIN-902 | L | SKIN-901 | Build deterministic candidate-bone selection from the rig hierarchy and semantic part mapping. Generate weights from distance to bone segments, restrict blending to joint envelopes, sort ties by bone name, cap influences, quantize, renormalize, and verify each vertex totals `1.0`. |
| SKIN-903 | M | SKIN-902 | Preserve hard voxel regions outside joint envelopes, remove empty groups, validate modifier/armature ownership, and fall back atomically to rigid binding when any invariant fails. |
| SKIN-904 | M | SKIN-902 | Add weight-distribution, zero-weight, over-influence, normalization, deformation-range, and semantic-neighbor checks to Build Report v2. Record requested mode, applied algorithm, fallback reason, and per-object statistics. |
| SKIN-905 | L | SKIN-903, SKIN-904 | Add Blender fixtures for humanoid shoulders/elbows/knees plus representative quadruped, wing, and multi-arm joints. Verify rest pose, extreme poses, deterministic rebuilds, GLB weight retention, and rigid fallback. |

Implementation rules:

- Only a bone assigned to the part or its reviewed parent/child neighbors may
  influence that part. Unrelated bones never become candidates merely because
  they are spatially close.
- Weight generation must be independent of object iteration order and Blender
  selection state. Stable sorting and versioned rounding are part of the
  algorithm contract and content fingerprint.
- The configured maximum remains one to four influences. Smooth fixtures must
  prove that at least two bones influence vertices in each intended joint blend
  zone; a one-bone result cannot be labeled smooth.
- A failure must remove partial deform modifiers and groups before invoking the
  existing rigid binder. The report must distinguish user-requested rigid mode
  from automatic fallback.
- Golden weight summaries and posed bounds are tracked; `.blend` files remain
  generated artifacts rather than source fixtures.

Acceptance gate:

- All fixture vertices have finite, non-negative weights that normalize to
  `1.0` within the versioned tolerance and do not exceed `max_influences`.
- Joint-envelope fixtures contain verified multi-bone vertices while protected
  rigid regions retain their intended single-bone weights.
- Two clean builds produce identical weight summaries and semantic content
  hashes.
- Deliberately invalid policies and solver failures produce a clean, complete
  rigid result with a machine-readable fallback diagnostic.
- Blender export and Godot import retain the expected joints, weights, actions,
  bounds, and scale.

## Workstream B: measured animation quality

Contract correctness remains necessary, but action names and keyframes alone do
not prove that a clip looks production-ready. Motion QA will sample evaluated
poses and emit measurements into the build report using thresholds stored in a
versioned QA profile.

| ID | Size | Depends on | Deliverable |
| --- | --- | --- | --- |
| MOTION-901 | M | - | Define Motion QA Profile v1 with sampling rate, contact bones, ground/contact tolerances, loop tolerances, joint limits, root-motion policy, intersection policy, and severity per metric. |
| MOTION-902 | L | MOTION-901 | Evaluate every required action at deterministic sample times and measure foot/limb contact drift, ground penetration, airborne clearance, root discontinuity, loop seam error, joint-limit violations, and non-finite transforms. |
| MOTION-903 | M | MOTION-902 | Add topology-aware collision proxies and self-intersection summaries for high-risk body regions. Keep the existing broad intersection check only as a compatibility field until measured checks replace it. |
| MOTION-904 | M | MOTION-902 | Produce per-action diagnostics, worst-frame references, metric summaries, and deterministic contact-sheet or short preview artifacts for human review. |
| MOTION-905 | M | MOTION-903, MOTION-904 | Establish approved baselines for humanoid traversal/weapon actions and the four advanced topologies. Tune profile thresholds from those reviewed fixtures, never from a single character. |

Measurement rules:

- Contact intervals come from authored contact events when present; otherwise a
  deterministic height-and-velocity classifier may infer them and must report
  that inference.
- Foot sliding is horizontal world-space movement during a planted interval,
  normalized by character height so one profile can compare small and large
  rigs. Absolute meter limits may additionally protect engine-scale errors.
- Loop quality compares the first and last evaluated root and major-joint poses,
  accounting for declared root motion. Non-looping attacks are not forced to
  close.
- Joint limits come from the selected rig template or QA profile. Missing limits
  on a release fixture are a configuration error, not an automatic pass.
- Numeric gates catch regressions; review artifacts remain required for pose
  appeal, silhouette, timing, and intentional exaggeration that cannot be
  reduced safely to one score.

Acceptance gate:

- Every required action has a complete metric record and no error-severity
  threshold violation.
- Seeded negative fixtures reliably fail for sliding, ground penetration, loop
  discontinuity, invalid joint angles, and non-finite transforms.
- Approved baseline clips pass on two clean runs with identical sampled metric
  summaries.
- A reviewer can identify each worst frame directly from the report and retained
  preview artifacts without opening Blender.

## Workstream C: Blender and Godot integration CI

Hosted Python validation remains the fast required check. A separate workflow
will exercise the existing `tools/verify.ps1` Blender and Godot entry points on a
runner with the pinned applications installed.

| ID | Size | Depends on | Deliverable |
| --- | --- | --- | --- |
| CI-901 | M | - | Document and provision an isolated runner labeled for VCF 3D integration. Pin supported Blender/Godot versions, verify executable hashes or trusted installers, use a non-admin service identity, and clean the workspace between jobs. |
| CI-902 | M | CI-901 | Add a trusted-change smoke workflow that runs unit validation plus `-Blender` and `-Godot` against the pilot and uploads reports, previews, and engine logs on failure. |
| CI-903 | M | CI-901 | Add a scheduled and manually dispatchable matrix for Phase 8 topology fixtures, visual checks, performance capture, and cache-disabled determinism checks. |
| CI-904 | S | CI-902, CI-903 | Add concurrency cancellation, timeouts, retention limits, runner/tool version reporting, and branch-protection documentation. |
| CI-905 | M | CI-902 | Prove the workflow with controlled Blender-stage, Godot-import, and artifact-upload failures before making the smoke gate required. |

Runner security rules:

- Do not execute untrusted fork pull-request code automatically on a persistent
  self-hosted runner.
- Do not use `pull_request_target` to check out and run a contributor's branch.
  Forks require maintainer approval and an isolated/ephemeral execution path.
- The runner receives no release credentials. The workflow keeps `contents:
  read`, uses pinned action revisions, and grants additional permissions only to
  a separate publishing job if one is added later.
- Generated exports, imported Godot state, and caches are job-local and removed
  after artifact collection.

Acceptance gate:

- A trusted pull request cannot merge when the pilot Blender or Godot smoke gate
  fails.
- The scheduled matrix runs all selected fixtures without relying on developer
  machine state and records exact Python, Blender, Godot, workflow, and commit
  versions.
- Failed engine jobs retain reports, console logs, and bounded review artifacts;
  successful jobs do not retain bulky intermediate caches.
- A documented runner-loss procedure leaves hosted Python CI operational and
  makes the unavailable integration gate visible rather than silently skipped.

## Workstream D: repository license decision

The repository currently contains asset-level license and provenance metadata
but no project-level license file. Asset permissions do not automatically grant
permission to use the source code, documentation, trademarks, or release
packages. The owner must make this decision before a public release is declared.

| ID | Size | Depends on | Deliverable |
| --- | --- | --- | --- |
| LEGAL-901 | S | - | Inventory code authorship, dependencies, bundled/generated assets, names/marks, and intended distribution. Separate project-code terms from per-asset terms. |
| LEGAL-902 | S | LEGAL-901 | Record an owner-approved ADR choosing the distribution model and exact license text, or explicitly choosing not to grant a public license. Capture approver, date, scope, exceptions, and compatibility findings. |
| LEGAL-903 | S | LEGAL-902 | Add the approved `LICENSE` or other owner-directed legal notice, third-party notices if required, and consistent README/package/release references. Do not synthesize or guess legal terms. |
| LEGAL-904 | S | LEGAL-903 | Add validation that required legal files and asset provenance are present and that package output includes the approved notices. |

Decision gate:

- The owner identifies whether the intended model is closed/internal,
  permissive open source, copyleft, dual-licensed, or another counsel-approved
  arrangement.
- The decision explicitly addresses contributions, generated content,
  third-party dependencies, asset licenses, fan-character/profile data, and any
  project name or trademark restrictions.
- No release is labeled open source and no license badge is added until the
  accepted text exists in the repository.
- This workstream is complete only when the owner-approved files are present;
  documenting that the decision is still pending is not completion.

## Delivery order

| Milestone | Scope | Exit condition |
| --- | --- | --- |
| M1 - Contracts and baselines | SKIN-901, MOTION-901, LEGAL-901, runner design from CI-901 | Versioned contracts validate; representative baseline inputs and decision owners are recorded. |
| M2 - Measured deformation and motion | SKIN-902 through SKIN-905; MOTION-902 through MOTION-905 | Smooth weights and motion metrics pass deterministic Blender fixtures and negative tests. |
| M3 - Continuous engine gates | CI-901 through CI-905 | Trusted PR smoke and scheduled matrices run on the isolated integration runner with useful artifacts. |
| M4 - Release decision | LEGAL-902 through LEGAL-904 | Owner-approved legal terms are installed, validated, and included in packages. |
| M5 - Phase closeout | All workstreams | One cache-disabled pilot build and the selected topology matrix pass unit, Blender, Godot, motion, determinism, packaging, provenance, and legal-presence gates. |

M1 workstreams may proceed in parallel. CI should first automate the current
engine baseline, then require the new smooth-skinning and motion gates as they
stabilize. The legal decision does not block engineering experiments, but it does
block a public release declaration.

## Definition of done

Every Phase 9 work item must include normal-Python contract tests where possible,
headless Blender/Godot coverage where engine behavior is involved, structured
diagnostics with corrective actions, documentation, and deterministic report
fields. New thresholds and algorithms belong in versioned configuration and must
participate in cache/build fingerprints.

The final local and CI acceptance sequence is expected to remain behind the
stable verification entry point:

```powershell
./tools/verify.ps1 -Unit
./tools/verify.ps1 -Blender -Godot
./tools/verify.ps1 -Phase8
./tools/verify.ps1 -Visual -Performance
```

Phase 9 implementation may add a dedicated `-Motion` or `-Release` switch, but it
must compose existing checks rather than create a second validation system.
