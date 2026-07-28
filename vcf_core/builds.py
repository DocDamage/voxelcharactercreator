"""Build-stage contracts that can be used without Blender installed."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path
from time import time
from typing import Any


class BuildStatus(str, Enum):
    PROTOTYPE = "prototype"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    FAILED = "failed"


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
