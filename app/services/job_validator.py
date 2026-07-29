"""Compatibility wrapper for the canonical VCF Job v2 validator."""

from pathlib import Path

from vcf_core.jobs import validate_job

__all__ = ["validate_job", "Path"]
