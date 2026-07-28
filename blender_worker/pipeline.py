"""Small stage runner used by the Blender compatibility worker.

Stage functions stay deterministic and receive only the validated, resolved build
plan supplied by the controller. Blender-specific stage implementations can move
into ``blender_worker.stages`` incrementally without changing this contract.
"""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any


class Pipeline:
    def __init__(self, report: dict[str, Any], *, fail_stage: str | None = None, cache_enabled: bool = True):
        self.report = report
        self.fail_stage = fail_stage
        self.cache_enabled = cache_enabled

    def run(self, name: str, action: Callable[[], Any]) -> Any:
        started = perf_counter()
        result = {"name": name, "status": "running"}
        result["cache"] = "miss" if self.cache_enabled else "bypass"
        self.report.setdefault("stages", []).append(result)
        print("VCF_EVENT " + __import__("json").dumps({"type": "stage", "name": name, "status": "running"}), flush=True)
        try:
            if name == self.fail_stage:
                raise RuntimeError(f"Forced stage failure: {name}")
            value = action()
        except Exception as exc:
            result.update({"status": "failed", "duration_seconds": round(perf_counter() - started, 6), "error": str(exc)})
            print("VCF_EVENT " + __import__("json").dumps({"type": "stage", "name": name, "status": "failed", "error": str(exc)}), flush=True)
            raise
        result.update({"status": "passed", "duration_seconds": round(perf_counter() - started, 6)})
        print("VCF_EVENT " + __import__("json").dumps({"type": "stage", "name": name, "status": "passed"}), flush=True)
        return value
