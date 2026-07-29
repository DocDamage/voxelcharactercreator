"""Blender-independent Phase 5 operator services.

The desktop UI and tests share these contracts so queue recovery, preflight, and
cache decisions never depend on Tk or Blender being importable.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from vcf_core.jobs import load_job


STAGES = (
    "prepare", "ingest", "assemble_proxy", "assemble_assets", "resolve_parts", "rig", "align_sockets",
    "rigid_bind", "secondary_motion", "animate", "qa", "render", "optimize", "export", "godot_import",
)

QUEUE_STATUSES = (
    "pending", "running", "cancelling", "cancelled", "failed", "interrupted", "complete",
)


class SingleInstanceLock:
    """Process-held advisory lock used to give one desktop app queue ownership."""

    def __init__(self, path: Path):
        self.path = path
        self._handle = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise RuntimeError(
                "another Voxel Character Factory app is already using this project"
            ) from exc
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.release()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


@dataclass(frozen=True)
class PreflightIssue:
    code: str
    severity: str
    component: str
    message: str
    corrective_action: str


@dataclass
class PreflightReport:
    ok: bool
    versions: dict[str, str] = field(default_factory=dict)
    capabilities: dict[str, bool] = field(default_factory=dict)
    issues: list[PreflightIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "versions": self.versions, "capabilities": self.capabilities,
                "issues": [asdict(issue) for issue in self.issues]}


def _command_version(command: list[str], timeout: float = 8.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    text = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, (text[0] if text else "unknown")


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".vcf-write-", delete=True):
            pass
        return True
    except OSError:
        return False


def run_preflight(
    root: Path,
    settings: dict[str, Any],
    jobs: Iterable[Path] = (),
    *,
    output_root: Path | None = None,
) -> PreflightReport:
    """Validate immutable inputs while optionally checking a separate output root."""

    jobs = tuple(jobs)
    output_root = output_root or root
    issues: list[PreflightIssue] = []
    versions: dict[str, str] = {}
    capabilities: dict[str, bool] = {}
    blender = str(settings.get("blender_path") or shutil.which("blender") or "")
    blender_ok = bool(blender and Path(blender).is_file())
    if blender_ok:
        blender_ok, version = _command_version([blender, "--version"])
        if blender_ok:
            versions["blender"] = version
            numbers = tuple(int(value) for value in re.findall(r"\d+", version)[:3])
            if numbers < (4, 5):
                blender_ok = False
                issues.append(PreflightIssue("PREFLIGHT_BLENDER_VERSION", "error", "Blender",
                    f"Unsupported Blender version: {version}", "Install Blender 4.5 LTS or newer."))
    capabilities["blender"] = blender_ok
    if not blender_ok:
        issues.append(PreflightIssue("PREFLIGHT_BLENDER", "error", "Blender",
            "A working Blender executable was not found.", "Open Settings and select Blender 4.5 LTS or newer."))

    godot = str(settings.get("godot_path") or os.environ.get("VCF_GODOT") or shutil.which("godot") or shutil.which("godot.exe") or "")
    if godot and Path(godot).exists():
        resolved = Path(godot).resolve()
        consoles = sorted(resolved.parent.glob("*console.exe")) if os.name == "nt" else []
        godot = str(consoles[0] if consoles else resolved)
    godot_ok = bool(godot and Path(godot).is_file())
    if godot_ok:
        godot_ok, version = _command_version([godot, "--version"])
        if godot_ok:
            versions["godot"] = version
            numbers = tuple(int(value) for value in re.findall(r"\d+", version)[:3])
            if numbers < (4, 6, 2):
                godot_ok = False
                issues.append(PreflightIssue("PREFLIGHT_GODOT_VERSION", "warning", "Godot",
                    f"Godot is older than the pinned 4.6.2 gate: {version}", "Install Godot 4.6.2 or newer for production Godot builds."))
    capabilities["godot"] = godot_ok
    if not godot_ok:
        issues.append(PreflightIssue("PREFLIGHT_GODOT", "warning", "Godot",
            "Godot was not found; non-Godot jobs can still build.", "Install Godot 4.6.2 or set VCF_GODOT/godot_path."))

    provider = settings.get("llm_provider", "none")
    capabilities["llm"] = provider == "none"
    if provider == "ollama":
        base = str(settings.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
        try:
            import urllib.request
            with urllib.request.urlopen(base + "/api/tags", timeout=2) as response:
                capabilities["llm"] = response.status == 200
        except Exception:
            capabilities["llm"] = False
            issues.append(PreflightIssue("PREFLIGHT_OLLAMA", "warning", "Ollama",
                "The configured Ollama service is unavailable.", "Start Ollama or choose another LLM provider in Settings."))
    elif provider == "openai":
        capabilities["llm"] = bool(os.environ.get("OPENAI_API_KEY"))
        if not capabilities["llm"]:
            issues.append(PreflightIssue("PREFLIGHT_OPENAI_KEY", "warning", "OpenAI",
                "OPENAI_API_KEY is not set.", "Set OPENAI_API_KEY before requesting an LLM proposal."))

    for folder in (output_root / "exports", output_root / "logs"):
        if not _writable(folder):
            issues.append(PreflightIssue("PREFLIGHT_PATH_WRITABLE", "error", "Filesystem",
                f"The output path is not writable: {folder}", "Grant write access or move the project to a writable directory."))
    for job_path in jobs:
        try:
            job = load_job(job_path, root)
            source = job.get("source", {})
            if source.get("mode") == "model" and str(source.get("path", "")).lower().endswith(".vox"):
                from blender_worker.adapters.vox_reader import read_vox
                read_vox(root / source["path"])
        except Exception as exc:
            issues.append(PreflightIssue("PREFLIGHT_JOB_INVALID", "error", "Input",
                f"{job_path.name}: {exc}", "Correct the job or source asset before building."))
    requires_godot = False
    for job_path in jobs:
        try:
            requires_godot = requires_godot or load_job(job_path, root).get("export_profile") == "godot_character"
        except Exception:
            pass
    if requires_godot and not godot_ok:
        issues.append(PreflightIssue("PREFLIGHT_GODOT_REQUIRED", "error", "Godot",
            "A selected production job requires the Godot import gate.", "Install Godot 4.6.2 or set VCF_GODOT/godot_path before building."))
    return PreflightReport(not any(issue.severity == "error" for issue in issues), versions, capabilities, issues)


@dataclass
class QueueItem:
    id: str
    job_path: str
    status: str = "pending"
    stage: str | None = None
    retry_from_stage: str | None = None
    error: str | None = None
    run_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class QueueValidationError(ValueError):
    """A persisted build queue does not match the supported durable format."""


def _queue_item_from_mapping(value: Any, index: int) -> QueueItem:
    if not isinstance(value, dict):
        raise QueueValidationError(f"queue items[{index}] must be an object")
    fields = {
        "id", "job_path", "status", "stage", "retry_from_stage", "error", "run_id",
        "created_at", "updated_at",
    }
    unknown = sorted(set(value) - fields)
    missing = sorted({"id", "job_path"} - set(value))
    if unknown or missing:
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        if unknown:
            details.append("unknown fields: " + ", ".join(unknown))
        raise QueueValidationError(f"queue items[{index}] " + "; ".join(details))
    identifier = value.get("id")
    job_path = value.get("job_path")
    if not isinstance(identifier, str) or not identifier.strip():
        raise QueueValidationError(f"queue items[{index}].id must be a non-empty string")
    if not isinstance(job_path, str) or not job_path.strip():
        raise QueueValidationError(f"queue items[{index}].job_path must be a non-empty string")
    status = value.get("status", "pending")
    if status not in QUEUE_STATUSES:
        raise QueueValidationError(f"queue items[{index}].status is invalid: {status!r}")
    for key in ("stage", "retry_from_stage"):
        stage = value.get(key)
        if stage is not None and stage not in STAGES:
            raise QueueValidationError(f"queue items[{index}].{key} is invalid: {stage!r}")
    for key in ("error", "run_id"):
        if value.get(key) is not None and not isinstance(value[key], str):
            raise QueueValidationError(f"queue items[{index}].{key} must be a string or null")
    for key in ("created_at", "updated_at"):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise QueueValidationError(f"queue items[{index}].{key} must be a non-empty string")
    return QueueItem(**value)


class BuildQueue:
    """Small durable FIFO. Interrupted running items become resumable."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.items: list[QueueItem] = []
        self.quarantined_path: Path | None = None
        self.load()

    def load(self) -> None:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                self.items = []
                self._save()
                return
            except OSError:
                # Permission and device errors are not evidence of corrupt data.
                # Failing closed avoids moving or replacing a queue we could not read.
                raise
            except (UnicodeError, json.JSONDecodeError) as exc:
                self._recover_corrupt_queue(str(exc))
                return
            try:
                self.items = self._validate_payload(payload)
            except QueueValidationError as exc:
                self._recover_corrupt_queue(str(exc))
                return
            recovered = False
            for item in self.items:
                if item.status in {"running", "cancelling"}:
                    item.status, item.error = "interrupted", "Application stopped during this build; resume is available."
                    item.updated_at = datetime.now(timezone.utc).isoformat()
                    recovered = True
            # Re-save recovered items and normalize legacy files which omitted
            # schema_version. Valid current files are left untouched on read.
            if recovered or "schema_version" not in payload:
                self._save()

    @staticmethod
    def _validate_payload(payload: Any) -> list[QueueItem]:
        if not isinstance(payload, dict):
            raise QueueValidationError("queue must be a JSON object")
        unknown = sorted(set(payload) - {"schema_version", "items"})
        if unknown:
            raise QueueValidationError("unknown queue fields: " + ", ".join(unknown))
        version = payload.get("schema_version", 1)
        if isinstance(version, bool) or version != 1:
            raise QueueValidationError(f"unsupported queue schema_version: {version!r}")
        values = payload.get("items")
        if not isinstance(values, list):
            raise QueueValidationError("queue items must be an array")
        items = [_queue_item_from_mapping(value, index) for index, value in enumerate(values)]
        identifiers = [item.id for item in items]
        if len(identifiers) != len(set(identifiers)):
            raise QueueValidationError("queue item IDs must be unique")
        return items

    def _recover_corrupt_queue(self, reason: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        quarantine = self.path.with_name(f"{self.path.name}.corrupt-{timestamp}-{uuid.uuid4().hex[:8]}")
        try:
            self.path.rename(quarantine)
        except OSError as exc:
            raise QueueValidationError(f"could not quarantine corrupt queue ({reason}): {exc}") from exc
        self.quarantined_path = quarantine
        self.items = []
        self._save()

    def _save(self) -> None:
        atomic_write_json(self.path, {"schema_version": 1, "items": [asdict(item) for item in self.items]})

    def add(self, job_path: Path) -> QueueItem:
        return self.add_many((job_path,))[0]

    def add_many(self, job_paths: Iterable[Path]) -> list[QueueItem]:
        """Append a batch atomically and persist it with one queue write."""
        with self._lock:
            added = [QueueItem(uuid.uuid4().hex, str(job_path)) for job_path in job_paths]
            if not added:
                return []
            previous_length = len(self.items)
            self.items.extend(added)
            try:
                self._save()
            except Exception:
                del self.items[previous_length:]
                raise
            return added

    def update(self, item_id: str, **values: Any) -> QueueItem:
        with self._lock:
            item = next(item for item in self.items if item.id == item_id)
            previous = QueueItem(**asdict(item))
            try:
                for key, value in values.items():
                    setattr(item, key, value)
                item.updated_at = datetime.now(timezone.utc).isoformat()
                self._save()
            except Exception:
                for key, value in asdict(previous).items():
                    setattr(item, key, value)
                raise
            return item

    def next_pending(self) -> QueueItem | None:
        with self._lock:
            return next((item for item in self.items if item.status == "pending"), None)

    def snapshot(self) -> tuple[QueueItem, ...]:
        """Return detached queue records for lock-safe UI reads."""
        with self._lock:
            return tuple(QueueItem(**asdict(item)) for item in self.items)

    def status_counts(self) -> dict[str, int]:
        """Return a stable count for every supported queue status."""
        with self._lock:
            return {status: sum(item.status == status for item in self.items) for status in QUEUE_STATUSES}

    def claim_pending(self, limit: int) -> list[QueueItem]:
        """Atomically claim up to ``limit`` jobs for a measured worker pool."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 4:
            raise ValueError("queue claim limit must be an integer from 1 to 4")
        with self._lock:
            claimed = [item for item in self.items if item.status == "pending"][:limit]
            previous = [QueueItem(**asdict(item)) for item in claimed]
            for item in claimed:
                item.status = "running"
                item.stage = "prepare"
                item.updated_at = datetime.now(timezone.utc).isoformat()
            try:
                self._save()
            except Exception:
                for item, saved in zip(claimed, previous):
                    for key, value in asdict(saved).items():
                        setattr(item, key, value)
                raise
            return claimed

    def retry(self, item_id: str, stage: str | None = None) -> QueueItem:
        if stage is not None and stage not in STAGES:
            raise ValueError(f"unknown pipeline stage: {stage}")
        return self.update(item_id, status="pending", stage=None, retry_from_stage=stage, error=None)

    def resume(self, *, include_inactive_workers: bool = False) -> int:
        """Requeue recoverable items after the caller proves no worker owns them."""

        if not isinstance(include_inactive_workers, bool):
            raise ValueError("include_inactive_workers must be a boolean")
        with self._lock:
            statuses = {"failed", "cancelled", "interrupted"}
            if include_inactive_workers:
                statuses.update({"running", "cancelling"})
            resumable = [item for item in self.items if item.status in statuses]
            previous = [QueueItem(**asdict(item)) for item in resumable]
            timestamp = datetime.now(timezone.utc).isoformat()
            for item in resumable:
                item.status, item.stage, item.error, item.updated_at = "pending", None, None, timestamp
            if resumable:
                try:
                    self._save()
                except Exception:
                    for item, saved in zip(resumable, previous):
                        for key, value in asdict(saved).items():
                            setattr(item, key, value)
                    raise
            return len(resumable)

    def cancel_pending(self, reason: str) -> int:
        """Cancel every job that has not been claimed, recording an operator reason."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("cancellation reason must be a non-empty string")
        with self._lock:
            pending = [item for item in self.items if item.status == "pending"]
            previous = [QueueItem(**asdict(item)) for item in pending]
            timestamp = datetime.now(timezone.utc).isoformat()
            for item in pending:
                item.status, item.stage, item.error, item.updated_at = "cancelled", None, reason.strip(), timestamp
            if pending:
                try:
                    self._save()
                except Exception:
                    for item, saved in zip(pending, previous):
                        for key, value in asdict(saved).items():
                            setattr(item, key, value)
                    raise
            return len(pending)


class BuildCache:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "exports" / ".cache" / "builds"

    def key(self, job_path: Path, tool_versions: dict[str, str]) -> str:
        job = load_job(job_path, self.root)
        digest = hashlib.sha256()
        digest.update(json.dumps(job, sort_keys=True, separators=(",", ":")).encode())
        for folder in (self.root / "assets" / "manifests", self.root / "config"):
            for path in sorted(folder.rglob("*.json")):
                if path.name == "settings.json":
                    continue
                digest.update(str(path.relative_to(self.root)).encode()); digest.update(path.read_bytes())
        for folder in (self.root / "blender_worker", self.root / "vcf_core"):
            for path in sorted(folder.rglob("*.py")):
                digest.update(str(path.relative_to(self.root)).encode()); digest.update(path.read_bytes())
        for path in (
            self.root / "tests" / "godot" / "project.godot",
            self.root / "tests" / "godot" / "verify_import.gd",
        ):
            digest.update(str(path.relative_to(self.root)).encode()); digest.update(path.read_bytes())
        version_file = self.root / "VERSION.txt"
        if version_file.is_file():
            digest.update(version_file.read_bytes())
        if job["source"]["mode"] == "assembly":
            from vcf_core.assets import load_registry
            for manifest in load_registry(self.root).resolve(job["source"]["asset_ids"], body_template=job["body_template"]):
                digest.update((self.root / manifest.source_path).read_bytes())
        elif job["source"]["mode"] == "model":
            digest.update((self.root / job["source"]["path"]).read_bytes())
        digest.update(json.dumps(tool_versions, sort_keys=True).encode())
        return digest.hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            return None
        path = self.path / f"{key}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or value.get("status") not in {"prototype", "complete"}:
            return None
        blocking = value.get("blocking_checks")
        if (
            not isinstance(blocking, dict)
            or blocking.get("passed") is not True
            or blocking.get("failed") != []
            or blocking.get("missing") != []
            or not isinstance(blocking.get("required"), list)
        ):
            return None
        promoted = value.get("promoted_output")
        if not isinstance(promoted, str) or not promoted:
            return None
        relative = Path(promoted)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        exports = (self.root / "exports").resolve()
        output = (self.root / relative).resolve()
        if output == exports or exports not in output.parents or not output.is_dir():
            return None
        artifacts = value.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            return None
        names: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                return None
            name = artifact.get("name")
            size = artifact.get("size_bytes")
            expected_hash = artifact.get("sha256")
            if (
                not isinstance(name, str)
                or not name
                or Path(name).name != name
                or name in names
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size < 0
                or not isinstance(expected_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            ):
                return None
            names.add(name)
            artifact_path = (output / name).resolve()
            if artifact_path.parent != output or not artifact_path.is_file():
                return None
            try:
                if artifact_path.stat().st_size != size:
                    return None
                digest = hashlib.sha256()
                with artifact_path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected_hash:
                    return None
            except OSError:
                return None
        report_job = value.get("job")
        if not isinstance(report_job, str) or not re.fullmatch(
            r"[a-z0-9]+(?:_[a-z0-9]+)*", report_job
        ):
            return None
        allowed_names = names | {f"{report_job}_report.json"}
        try:
            output_entries = list(output.iterdir())
        except OSError:
            return None
        if (
            {entry.name for entry in output_entries} != allowed_names
            or any(entry.is_symlink() or not entry.is_file() for entry in output_entries)
        ):
            return None
        return value

    def put(self, key: str, report: dict[str, Any]) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("cache key must be a lowercase SHA-256 digest")
        atomic_write_json(self.path / f"{key}.json", report)
