# Next Phase

Phases 0-8 are implemented. Ten legacy profiles resolve as Job v2 variants of
tracked-original assemblies, and four original advanced-topology fixtures cover
quadruped, flying, multi-arm, and composite final-boss production.

Phase 8 also added deform binding with rigid fallback, reviewable generated-asset
provenance, the desktop 3D Character Editor, and a governed 120-model cast in six
resumable batches. The release ledger is backed by 120/120 passing Blender/Godot
reports with distinct semantic hashes. Its reproducible acceptance commands are:

```powershell
./tools/verify.ps1 -Phase8
./tools/verify.ps1 -FullCast
```

Implementation details are in [PHASE8_ADVANCED.md](PHASE8_ADVANCED.md), while the
dependency history and acceptance gates remain in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Phase 9 is the release-readiness phase. Its prioritized workstreams replace
rigid per-part "deform" weights with deterministic multi-bone smooth skinning,
add measured animation-quality gates, run Blender/Godot integration on a secure
capable CI runner, and resolve the owner-controlled repository license decision.

The work items, dependencies, security constraints, measurable acceptance gates,
and delivery order are defined in
[PHASE9_RELEASE_READINESS.md](PHASE9_RELEASE_READINESS.md). Future content
expansion remains outside that phase until these release-readiness gates close.
