from __future__ import annotations
import argparse, json
from pathlib import Path
from app.services.llm_client import run_ollama, run_openai, apply_patch
from app.services.job_validator import validate_job

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--provider", choices=["ollama","openai"], required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    path = Path(args.job)
    job = json.loads(path.read_text(encoding="utf-8"))
    patch = run_ollama(args.prompt, args.base_url, args.model) if args.provider == "ollama" else run_openai(args.prompt, args.base_url, args.model)
    updated = apply_patch(job, patch)
    errors = validate_job(updated)
    if errors:
        raise SystemExit("Validation failed:\n- " + "\n- ".join(errors))
    path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    print(json.dumps({"updated_job": str(path), "patch": patch}, indent=2))

if __name__ == "__main__":
    main()
