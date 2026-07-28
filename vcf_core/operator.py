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
    "rigid_bind", "animate", "qa", "render", "export", "godot_import",
)


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


def run_preflight(root: Path, settings: dict[str, Any], jobs: Iterable[Path] = ()) -> PreflightReport:
    jobs = tuple(jobs)
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

    for folder in (root / "exports", root / "logs"):
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


class BuildQueue:
    """Small durable FIFO. Interrupted running items become resumable."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.items: list[QueueItem] = []
        self.load()

    def load(self) -> None:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {"items": []}
            self.items = [QueueItem(**item) for item in payload.get("items", [])]
            for item in self.items:
                if item.status in {"running", "cancelling"}:
                    item.status, item.error = "interrupted", "Application stopped during this build; resume is available."
            self._save()

    def _save(self) -> None:
        atomic_write_json(self.path, {"schema_version": 1, "items": [asdict(item) for item in self.items]})

    def add(self, job_path: Path) -> QueueItem:
        with self._lock:
            item = QueueItem(uuid.uuid4().hex, str(job_path))
            self.items.append(item); self._save(); return item

    def update(self, item_id: str, **values: Any) -> QueueItem:
        with self._lock:
            item = next(item for item in self.items if item.id == item_id)
            for key, value in values.items():
                setattr(item, key, value)
            item.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return item

    def next_pending(self) -> QueueItem | None:
        return next((item for item in self.items if item.status == "pending"), None)

    def retry(self, item_id: str, stage: str | None = None) -> QueueItem:
        if stage is not None and stage not in STAGES:
            raise ValueError(f"unknown pipeline stage: {stage}")
        return self.update(item_id, status="pending", stage=None, retry_from_stage=stage, error=None)

    def resume(self) -> int:
        count = 0
        for item in self.items:
            if item.status in {"failed", "cancelled", "interrupted"}:
                self.update(item.id, status="pending", stage=None, error=None); count += 1
        return count


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
        path = self.path / f"{key}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        output = self.root / value.get("promoted_output", "")
        return value if output.is_dir() else None

    def put(self, key: str, report: dict[str, Any]) -> None:
        atomic_write_json(self.path / f"{key}.json", report)
