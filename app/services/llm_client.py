from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path

SYSTEM_PROMPT = """You convert natural-language voxel character build requests into strict JSON job patches.
Return JSON only. Allowed keys:
body_template, rig_template, animation_profile, weapon, source_model,
height_voxels, palette_profile, accent_colors, export_formats, render_profile, notes.
Never include markdown or explanations."""

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

def apply_patch(job: dict, patch: dict) -> dict:
    allowed = {
        "body_template","rig_template","animation_profile","weapon","source_model",
        "height_voxels","palette_profile","accent_colors","export_formats","render_profile","notes"
    }
    for key, value in patch.items():
        if key in allowed:
            job[key] = value
    return job
