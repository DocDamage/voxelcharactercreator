from __future__ import annotations
import json
import os
import urllib.request
from copy import deepcopy

SYSTEM_PROMPT = """You propose reviewable corrections to a voxel character Job v2.
Return JSON only as {"changes": {...}, "diagnostics": [{"message": "...", "corrective_action": "..."}]}.
Allowed change keys: body_template, rig_template, animation_profile, animation_packs,
weapon, height_voxels, target_height_meters, palette_profile, accent_colors,
export_formats, export_profile, render_profile, notes, part_overrides, settings_overrides,
and source (assembly mode with asset_ids only). Suggest catalog assets when useful.
Never propose source paths, credentials, code, or unstructured commands. The operator
will inspect a validated diff before explicitly applying it."""

ALLOWED_KEYS = {
    "body_template", "rig_template", "animation_profile", "animation_packs", "weapon",
    "height_voxels", "target_height_meters", "palette_profile", "accent_colors",
    "export_formats", "export_profile", "render_profile", "notes", "part_overrides",
    "settings_overrides", "source",
}

def _post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))

def run_ollama(prompt: str, base_url: str, model: str) -> dict:
    result = _post_json(
        base_url.rstrip("/") + "/api/chat",
        {
            "model": model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        }
    )
    return json.loads(result["message"]["content"])

def run_openai(prompt: str, base_url: str, model: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    result = _post_json(
        base_url.rstrip("/") + "/chat/completions",
        {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        },
        {"Authorization": f"Bearer {api_key}"}
    )
    return json.loads(result["choices"][0]["message"]["content"])

def normalize_proposal(patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise TypeError("proposal must be a JSON object")
    changes = patch.get("changes", patch)
    diagnostics = patch.get("diagnostics", []) if "changes" in patch else []
    if not isinstance(changes, dict) or not isinstance(diagnostics, list):
        raise TypeError("proposal changes must be an object and diagnostics must be an array")
    unknown = sorted(set(changes) - ALLOWED_KEYS)
    if unknown:
        raise ValueError("proposal contains unsupported fields: " + ", ".join(unknown))
    source = changes.get("source")
    if source is not None and (not isinstance(source, dict) or source.get("mode") != "assembly" or set(source) - {"mode", "asset_ids"}):
        raise ValueError("LLM proposals may only select registry asset_ids in assembly mode")
    return {"changes": changes, "diagnostics": diagnostics}


def proposal_diff(job: dict, proposal: dict) -> list[dict]:
    normalized = normalize_proposal(proposal)
    return [{"field": key, "before": job.get(key), "after": value}
            for key, value in sorted(normalized["changes"].items()) if job.get(key) != value]


def apply_patch(job: dict, patch: dict) -> dict:
    if not isinstance(job, dict) or not isinstance(patch, dict):
        raise TypeError("job and patch must be JSON objects")
    proposal = normalize_proposal(patch)
    updated = deepcopy(job)
    for key, value in proposal["changes"].items():
        updated[key] = value
    return updated
