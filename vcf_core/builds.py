"""Build-stage contracts that can be used without Blender installed."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path
import re
from time import time
from typing import Any, Iterable


QA_BUDGET_CHECKS = frozenset({
    "qa_object_budget", "qa_face_budget", "qa_material_budget", "qa_color_budget",
})
BLOCKING_QA_CHECKS = frozenset({
    "qa_no_missing_or_detached_parts", "qa_valid_pivots", "qa_ground_penetration",
    "qa_intersections_checked", "qa_object_budget", "qa_face_budget", "qa_material_budget",
    "qa_color_budget", "qa_animation_presence",
})
OUTPUT_SEGMENT_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def implementation_hash(root: Path) -> str:
    """Hash executable pipeline sources for build/release provenance."""
    digest=sha256()
    for folder in (root/"blender_worker",root/"vcf_core"):
        for path in sorted(folder.rglob("*.py")):
            if "__pycache__" in path.parts:continue
            digest.update(path.relative_to(root).as_posix().encode());digest.update(path.read_bytes())
    for path in (root/"tests"/"godot"/"project.godot", root/"tests"/"godot"/"verify_import.gd"):
        digest.update(path.relative_to(root).as_posix().encode());digest.update(path.read_bytes())
    return digest.hexdigest()


class BuildStatus(str, Enum):
    PROTOTYPE = "prototype"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    FAILED = "failed"


def successful_build_status(status: str | BuildStatus) -> bool:
    """Return whether a worker may exit successfully for this report status."""

    return str(getattr(status, "value", status)) in {
        BuildStatus.PROTOTYPE.value,
        BuildStatus.COMPLETE.value,
    }


def safe_output_directory(root: Path, game: str, character_slug: str) -> Path:
    """Resolve one canonical character output below ``root/exports``."""

    if not isinstance(game, str) or not OUTPUT_SEGMENT_PATTERN.fullmatch(game):
        raise ValueError("game must be a canonical lowercase underscore slug")
    if not isinstance(character_slug, str) or not OUTPUT_SEGMENT_PATTERN.fullmatch(character_slug):
        raise ValueError("character output name must be a canonical lowercase underscore slug")

    exports = (root / "exports").resolve()
    candidate = (exports / game / character_slug).resolve()
    if candidate == exports or exports not in candidate.parents:
        raise ValueError("character output path escapes the project exports directory")
    return candidate


def require_matching_input_provenance(executing_root: Path, input_root: Path) -> None:
    """Reject a worker whose executed code differs from its hashed input tree."""

    if executing_root.resolve() != input_root.resolve():
        raise ValueError(
            "worker code root must match the build input root used for provenance and cache keys"
        )


def determine_status(*, uses_proxy: bool, has_unbound_geometry: bool, blocking_checks_passed: bool) -> BuildStatus:
    """Apply the non-negotiable Phase 0 completion gate.

    A proxy can demonstrate plumbing but is never production complete. Likewise,
    visible unbound geometry or any failed blocking check prevents false-green
    success reports.
    """
    if uses_proxy:
        return BuildStatus.PROTOTYPE
    if has_unbound_geometry or not blocking_checks_passed:
        return BuildStatus.INCOMPLETE
    return BuildStatus.COMPLETE


def summarize_blocking_checks(checks: dict[str, Any], required: Iterable[str]) -> dict[str, Any]:
    """Classify a strict boolean completion gate for a build report."""
    names = sorted(set(required))
    missing = [name for name in names if name not in checks]
    failed = [name for name in names if name in checks and checks[name] is not True]
    return {"passed": not missing and not failed, "required": names, "missing": missing, "failed": failed}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    corrective_action: str
    stage: str | None = None


@dataclass(frozen=True)
class Artifact:
    name: str
    path: str
    sha256: str
    size_bytes: int

    @classmethod
    def from_path(cls, name: str, path: Path) -> "Artifact":
        digest = sha256(path.read_bytes()).hexdigest()
        return cls(name=name, path=str(path), sha256=digest, size_bytes=path.stat().st_size)


@dataclass
class StageResult:
    name: str
    status: str
    started_at: float = field(default_factory=time)
    finished_at: float | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)

    def finish(self, status: str = "passed") -> None:
        self.status = status
        self.finished_at = time()

    @property
    def duration_seconds(self) -> float | None:
        return None if self.finished_at is None else round(self.finished_at - self.started_at, 6)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["duration_seconds"] = self.duration_seconds
        return result


@dataclass
class BuildReport:
    """Machine-readable Build Report v2.

    Timestamps are intentionally excluded from deterministic content comparisons.
    """

    run_id: str
    job_id: str
    status: BuildStatus
    job_schema_version: int
    tool_versions: dict[str, str] = field(default_factory=dict)
    input_hashes: dict[str, str] = field(default_factory=dict)
    stages: list[StageResult] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "status": self.status.value,
            "job_schema_version": self.job_schema_version,
            "tool_versions": self.tool_versions,
            "input_hashes": self.input_hashes,
            "stages": [stage.to_dict() for stage in self.stages],
            "diagnostics": [asdict(item) for item in self.diagnostics],
            "artifacts": [asdict(item) for item in self.artifacts],
        }
