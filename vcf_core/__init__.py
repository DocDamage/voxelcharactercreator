"""Versioned, Blender-independent contracts for Voxel Character Factory."""

from .builds import BuildReport, BuildStatus, Diagnostic, StageResult, determine_status
from .operator import BuildCache, BuildQueue, PreflightIssue, PreflightReport, run_preflight
from .assets import AssetManifest, AssetRegistry, AssetValidationError, load_registry
from .jobs import CURRENT_JOB_SCHEMA_VERSION, JobValidationError, load_job, migrate_job, validate_job

__all__ = [
    "BuildReport",
    "BuildCache", "BuildQueue", "PreflightIssue", "PreflightReport", "run_preflight",
    "AssetManifest",
    "AssetRegistry",
    "AssetValidationError",
    "BuildStatus",
    "CURRENT_JOB_SCHEMA_VERSION",
    "Diagnostic",
    "JobValidationError",
    "StageResult",
    "determine_status",
    "load_job",
    "load_registry",
    "migrate_job",
    "validate_job",
]
