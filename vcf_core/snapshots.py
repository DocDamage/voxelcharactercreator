"""Immutable, per-batch input snapshots for deterministic Blender workers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from vcf_core.assets import load_registry
from vcf_core.jobs import load_job


SNAPSHOT_DIRECTORIES = (
    Path("blender_worker"),
    Path("vcf_core"),
    Path("characters"),
    Path("config"),
    Path("assets/manifests"),
)

SNAPSHOT_FILES = (
    Path("VERSION.txt"),
    Path("tests/godot/project.godot"),
    Path("tests/godot/verify_import.gd"),
)
SNAPSHOT_MARKER = ".vcf-build-input-snapshot"
SNAPSHOT_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SNAPSHOT_LEASE_PREFIX = ".vcf-build-input-lease-"
SNAPSHOT_LEASE_PATTERN = re.compile(r"^\.vcf-build-input-lease-([1-9][0-9]*)$")


@dataclass(frozen=True)
class BuildInputSnapshot:
    root: Path
    jobs: dict[Path, Path]

    def job_path(self, original: Path) -> Path:
        try:
            return self.jobs[original.resolve()]
        except KeyError as exc:
            raise KeyError(f"job was not included in this input snapshot: {original}") from exc


def _project_relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"build input escapes the project root: {path}") from exc


def _copy_file(root: Path, staging: Path, path: Path) -> None:
    relative = _project_relative(path, root)
    target = staging / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def _lease_path(snapshot_root: Path, pid: int) -> Path:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("snapshot lease PID must be a positive integer")
    root = snapshot_root.resolve()
    if not (root / SNAPSHOT_MARKER).is_file():
        raise ValueError(f"refusing to lease an unowned build snapshot: {root}")
    return root / f"{SNAPSHOT_LEASE_PREFIX}{pid}"


def lease_build_input_snapshot(snapshot_root: Path, pid: int | None = None) -> Path:
    """Protect a snapshot while the owning app or one of its workers is alive."""

    owner_pid = os.getpid() if pid is None else pid
    lease = _lease_path(snapshot_root, owner_pid)
    identity = _process_identity(owner_pid)
    if identity is None:
        raise ProcessLookupError(f"cannot lease a snapshot to exited process {owner_pid}")
    temporary = lease.with_name(f".{lease.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(identity, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, lease)
    return lease


def release_build_input_snapshot_lease(snapshot_root: Path, pid: int | None = None) -> None:
    """Release one exact process lease without touching other active workers."""

    owner_pid = os.getpid() if pid is None else pid
    lease = _lease_path(snapshot_root, owner_pid)
    try:
        lease.unlink()
    except FileNotFoundError:
        pass


def _process_identity(pid: int) -> dict[str, object] | None:
    """Return a PID-reuse-safe process identity using only platform APIs."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error in {87, 1168}:  # invalid PID / process no longer exists
                return None
            raise OSError(error, f"could not inspect process {pid}")
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                error = ctypes.get_last_error()
                raise OSError(error, f"could not read process state for {pid}")
            if exit_code.value != still_active:
                return None
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                error = ctypes.get_last_error()
                raise OSError(error, f"could not read process creation time for {pid}")
            process_started_at = (created.dwHighDateTime << 32) | created.dwLowDateTime
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            executable = ""
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                executable = os.path.normcase(str(Path(buffer.value).resolve()))
            return {
                "pid": pid,
                "creation_token": str(process_started_at),
                "executable": executable,
            }
        finally:
            kernel32.CloseHandle(handle)

    proc = Path("/proc") / str(pid)
    if proc.exists():
        try:
            stat = (proc / "stat").read_text(encoding="utf-8")
            closing = stat.rfind(")")
            fields = stat[closing + 2 :].split()
            if fields[0] == "Z":
                return None
            creation_token = fields[19]
            executable = os.path.normcase(os.readlink(proc / "exe"))
        except FileNotFoundError:
            return None
        return {
            "pid": pid,
            "creation_token": creation_token,
            "executable": executable,
        }

    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart=,comm=,stat="],
        capture_output=True,
        text=True,
        check=False,
    )
    identity = result.stdout.strip()
    if result.returncode or not identity or identity.split()[-1].startswith("Z"):
        return None
    return {"pid": pid, "creation_token": identity, "executable": ""}


def _has_live_snapshot_lease(snapshot_root: Path) -> bool:
    return bool(_live_snapshot_lease_pids(snapshot_root))


def _live_snapshot_lease_pids(snapshot_root: Path) -> set[int]:
    try:
        children = list(snapshot_root.iterdir())
    except OSError:
        return {-1}
    live: set[int] = set()
    for child in children:
        match = SNAPSHOT_LEASE_PATTERN.fullmatch(child.name)
        if match and child.is_file():
            pid = int(match.group(1))
            try:
                expected = json.loads(child.read_text(encoding="utf-8"))
                current = _process_identity(pid)
            except (OSError, UnicodeError, json.JSONDecodeError):
                # An unreadable lease cannot safely authorize deletion.
                live.add(pid)
                continue
            if (
                isinstance(expected, dict)
                and expected.get("pid") == pid
                and isinstance(expected.get("creation_token"), str)
                and current is not None
                and current.get("creation_token") == expected["creation_token"]
            ):
                live.add(pid)
    return live


def live_build_input_snapshot_pids(parent: Path) -> set[int]:
    """Return live owners/workers across every owned snapshot under ``parent``."""

    root = parent.resolve()
    if not root.is_dir():
        return set()
    live: set[int] = set()
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        valid_name = bool(SNAPSHOT_NAME_PATTERN.fullmatch(child.name)) or child.name.startswith(
            ".building-"
        )
        if valid_name and (child / SNAPSHOT_MARKER).is_file():
            live.update(_live_snapshot_lease_pids(child))
    return live


def create_build_input_snapshot(
    root: Path, job_paths: Iterable[Path], parent: Path
) -> BuildInputSnapshot:
    """Copy every worker-readable input into one atomically published directory."""

    root = root.resolve()
    jobs = list(dict.fromkeys(Path(path).resolve() for path in job_paths))
    if not jobs:
        raise ValueError("at least one job is required for an input snapshot")
    job_relatives: dict[Path, Path] = {}
    for job in jobs:
        relative = _project_relative(job, root)
        if not relative.parts or relative.parts[0] != "characters":
            raise ValueError(f"build job must be inside the project characters directory: {job}")
        job_relatives[job] = relative
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".building-", dir=parent))
    final = parent / uuid.uuid4().hex
    try:
        (staging / SNAPSHOT_MARKER).write_text("Voxel Character Factory build input\n", encoding="utf-8")
        lease_build_input_snapshot(staging)
        for relative in SNAPSHOT_DIRECTORIES:
            source = root / relative
            if not source.is_dir():
                raise FileNotFoundError(f"required build input directory is missing: {relative}")
            shutil.copytree(
                source,
                staging / relative,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        for relative in SNAPSHOT_FILES:
            source = root / relative
            if not source.is_file():
                raise FileNotFoundError(f"required build input file is missing: {relative}")
            _copy_file(root, staging, source)

        registry = load_registry(root)
        # Registry loading intentionally validates the entire catalog. Preserve its
        # declared files so the worker sees the same valid catalog, even when the
        # selected jobs use only a subset of those assets.
        for manifest in registry.manifests:
            _copy_file(root, staging, root / manifest.source_path)
            _copy_file(root, staging, root / manifest.thumbnail_path)
        for job_path in jobs:
            job = load_job(job_path, root)
            source = job["source"]
            if source["mode"] == "model":
                _copy_file(root, staging, root / source["path"])

        os.replace(staging, final)
        mapped = {
            job: final / relative
            for job, relative in job_relatives.items()
        }
        return BuildInputSnapshot(final, mapped)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if final.is_dir():
            shutil.rmtree(final, ignore_errors=True)
        raise


def remove_build_input_snapshot(path: Path, parent: Path) -> None:
    """Remove one exact snapshot while refusing broad or escaped targets."""

    target = path.resolve()
    allowed_parent = parent.resolve()
    if (
        target.parent != allowed_parent
        or not SNAPSHOT_NAME_PATTERN.fullmatch(target.name)
        or not (target / SNAPSHOT_MARKER).is_file()
    ):
        raise ValueError(f"refusing to remove an unsafe build snapshot path: {target}")
    live_workers = _live_snapshot_lease_pids(target) - {os.getpid()}
    if live_workers:
        rendered = ", ".join(str(pid) for pid in sorted(live_workers))
        raise RuntimeError(f"build snapshot is still leased by active worker process(es): {rendered}")
    if target.is_dir():
        shutil.rmtree(target)


def prune_stale_build_input_snapshots(
    parent: Path, *, max_age_seconds: float = 24 * 60 * 60
) -> list[Path]:
    """Remove old owned snapshots/staging directories from the exact queue parent."""

    if max_age_seconds <= 0:
        raise ValueError("snapshot maximum age must be positive")
    parent = parent.resolve()
    if not parent.is_dir():
        return []
    cutoff = time.time() - max_age_seconds
    removed: list[Path] = []
    for child in parent.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        owned = (child / SNAPSHOT_MARKER).is_file()
        valid_name = bool(SNAPSHOT_NAME_PATTERN.fullmatch(child.name)) or child.name.startswith(
            ".building-"
        )
        try:
            stale = child.stat().st_mtime < cutoff
        except OSError:
            continue
        if owned and valid_name and stale and not _has_live_snapshot_lease(child):
            shutil.rmtree(child)
            removed.append(child)
    return removed
