"""Validate all repository contracts without requiring Blender."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from jsonschema.exceptions import SchemaError
    from jsonschema.validators import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.exceptions import NoSuchResource
except ImportError:  # Reported as a validation failure below with install guidance.
    SchemaError = None
    Draft202012Validator = None
    Registry = None
    Resource = None
    NoSuchResource = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcf_core.jobs import JobValidationError, migrate_job, validate_job
from vcf_core.assets import AssetValidationError, load_registry
from vcf_core.rigging import PartResolutionError, load_rig_template
from vcf_core.animation import AnimationPackError, load_animation_pack
from vcf_core.export_profiles import ExportProfileError, load_export_profile
from vcf_core.production import ProductionValidationError, load_cast_database, load_pilot_matrix, validate_packaging_strategy
from vcf_core.advanced import AdvancedValidationError, cast_quality_summary, load_cast_plan, load_cast_release, load_topology_rig, validate_boss_composition


JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_INSTANCE_GLOBS = {
    "job.v2.schema.json": ("characters/**/*.json",),
    "asset_manifest.v1.schema.json": ("assets/manifests/*.json",),
    "rig_template.v1.schema.json": ("config/rig_templates/*.v1.json",),
    "advanced_rig.v1.schema.json": ("config/advanced_rigs/*.v1.json",),
    "animation_pack.v1.schema.json": ("config/animation_packs/*.v1.json",),
    "export_profile.v1.schema.json": ("config/export_profiles/*.v1.json",),
    "large_cast.v1.schema.json": ("config/production/large_cast.v1.json",),
    "full_cast_release.v1.schema.json": ("config/production/full_cast_release.v1.json",),
}


def _resolve_local_schema_ref(document: dict, reference: str) -> bool:
    if not isinstance(reference, str):
        return False
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or parsed.path or parsed.query or not reference.startswith("#"):
        return False
    fragment = unquote(parsed.fragment)
    if not fragment:
        return True
    if not fragment.startswith("/"):
        return any(
            node.get("$anchor") == fragment or node.get("$dynamicAnchor") == fragment
            for node in _schema_nodes(document)
        )
    current: object = document
    for raw_part in fragment[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list) and (
            part == "0" or (part.isdigit() and not part.startswith("0"))
        ):
            index = int(part)
            if index < len(current):
                current = current[index]
                continue
        else:
            return False
        return False
    return True


def _schema_nodes(value: object):
    """Yield only real schema resources, excluding literal const/default data."""

    if not isinstance(value, dict):
        return
    if Resource is None:
        yield value
        return
    try:
        pending = [Resource.from_contents(value)]
    except Exception:
        yield value
        return
    while pending:
        resource = pending.pop()
        if isinstance(resource.contents, dict):
            yield resource.contents
        pending.extend(resource.subresources())


def _invalid_schema_references(document: dict) -> list[tuple[str, object]]:
    invalid: list[tuple[str, object]] = []
    for node in _schema_nodes(document):
        for keyword in ("$ref", "$dynamicRef"):
            if keyword in node and not _resolve_local_schema_ref(document, node[keyword]):
                invalid.append((keyword, node[keyword]))
    return invalid


def _reject_remote_schema(reference: str):
    if NoSuchResource is None:  # pragma: no cover - dependency gate reports this first.
        raise RuntimeError(f"schema retrieval is disabled: {reference}")
    raise NoSuchResource(ref=reference)


def validate_schema_documents(root: Path) -> list[str]:
    """Parse and meta-validate every published Draft 2020-12 schema."""
    schema_paths = sorted((root / "schemas").glob("*.json"))
    if not schema_paths:
        return ["no published JSON schemas found"]
    failures: list[str] = []
    if Draft202012Validator is None:
        return [
            "JSON Schema meta-validation requires the pinned validation dependencies; "
            "run: python -m pip install -r requirements-validation.txt"
        ]
    identifiers: dict[str, Path] = {}
    for path in schema_paths:
        relative = path.relative_to(root)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            failures.append(f"{relative}: invalid published schema JSON: {exc}")
            continue
        if not isinstance(document, dict):
            failures.append(f"{relative}: published schema must be a JSON object")
            continue
        try:
            Draft202012Validator.check_schema(document)
        except SchemaError as exc:
            location = "/".join(str(item) for item in exc.absolute_schema_path)
            suffix = f" at {location}" if location else ""
            failures.append(
                f"{relative}: invalid Draft 2020-12 schema{suffix}: {exc.message}"
            )
            continue
        if document.get("$schema") != JSON_SCHEMA_DIALECT:
            failures.append(f"{relative}: published schema must use JSON Schema draft 2020-12")
        if not isinstance(document.get("title"), str) or not document["title"].strip():
            failures.append(f"{relative}: published schema requires a non-empty title")
        if document.get("type") != "object" or not isinstance(document.get("properties"), dict):
            failures.append(f"{relative}: published schema root must describe an object with properties")
        identifier = document.get("$id")
        if identifier is not None:
            if not isinstance(identifier, str) or not identifier.startswith("https://"):
                failures.append(f"{relative}: published schema $id must be an HTTPS URL")
            elif identifier in identifiers:
                failures.append(f"{relative}: duplicate published schema $id also used by {identifiers[identifier].relative_to(root)}")
            else:
                identifiers[identifier] = path
        for node in _schema_nodes(document):
            required = node.get("required")
            if required is not None and (
                not isinstance(required, list)
                or any(not isinstance(item, str) for item in required)
                or len(required) != len(set(required))
            ):
                failures.append(f"{relative}: schema required entries must be unique strings")
                break
            properties = node.get("properties")
            if required is not None and isinstance(required, list) and isinstance(properties, dict):
                missing = sorted(set(required) - set(properties))
                if missing:
                    failures.append(f"{relative}: required fields lack property schemas: {', '.join(missing)}")
                    break
        invalid_references = _invalid_schema_references(document)
        if invalid_references:
            keyword, reference = invalid_references[0]
            failures.append(
                f"{relative}: unresolved or nonlocal schema reference in {keyword}: {reference!r}"
            )
    return failures


def validate_schema_instances(
    root: Path, mappings: dict[str, tuple[str, ...]] | None = None
) -> list[str]:
    """Apply every published schema to each repository document it governs."""

    if Draft202012Validator is None:
        return []  # validate_schema_documents reports the missing dependency once.
    failures: list[str] = []
    active_mappings = SCHEMA_INSTANCE_GLOBS if mappings is None else mappings
    published = {path.name for path in (root / "schemas").glob("*.json")}
    mapped = set(active_mappings)
    for schema_name in sorted(published - mapped):
        failures.append(f"schemas/{schema_name}: published schema has no governed instance mapping")
    for schema_name in sorted(mapped - published):
        failures.append(f"schemas/{schema_name}: instance mapping references a missing published schema")
    for schema_name, patterns in active_mappings.items():
        schema_path = root / "schemas" / schema_name
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as exc:
            failures.append(f"{schema_path.relative_to(root)}: cannot validate instances: {exc}")
            continue
        invalid_references = _invalid_schema_references(schema)
        if invalid_references:
            keyword, reference = invalid_references[0]
            failures.append(
                f"{schema_path.relative_to(root)}: cannot validate instances with "
                f"unresolved or nonlocal {keyword}: {reference!r}"
            )
            continue
        paths = sorted({path for pattern in patterns for path in root.glob(pattern)})
        if not paths:
            failures.append(f"{schema_path.relative_to(root)}: no governed repository instances found")
            continue
        registry = Registry(retrieve=_reject_remote_schema)
        validator = Draft202012Validator(schema, registry=registry)
        for path in paths:
            try:
                instance = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                failures.append(f"{path.relative_to(root)}: cannot read schema instance: {exc}")
                continue
            if schema_name == "job.v2.schema.json":
                try:
                    instance = migrate_job(instance)
                except JobValidationError as exc:
                    failures.extend(
                        f"{path.relative_to(root)} [job migration]: {message}"
                        for message in exc.errors
                    )
                    continue
            try:
                instance_errors = sorted(
                    validator.iter_errors(instance),
                    key=lambda item: list(item.absolute_path),
                )
            except Exception as exc:
                failures.append(
                    f"{path.relative_to(root)} [{schema_name}]: could not resolve or apply schema: {exc}"
                )
                continue
            for error in instance_errors:
                location = "/".join(str(item) for item in error.absolute_path) or "<root>"
                failures.append(
                    f"{path.relative_to(root)} [{schema_name} at {location}]: {error.message}"
                )
    return failures


def main() -> int:
    failures: list[str] = []
    failures.extend(validate_schema_documents(ROOT))
    failures.extend(validate_schema_instances(ROOT))
    try:
        registry = load_registry(ROOT)
    except AssetValidationError as exc:
        failures.extend(exc.errors)
        registry = None
    jobs = sorted((ROOT / "characters").glob("*/*.json"))
    if not jobs:
        failures.append("no character jobs found")
    for path in jobs:
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
            continue
        errors = validate_job(job, ROOT)
        if errors:
            failures.extend(f"{path.relative_to(ROOT)}: {error}" for error in errors)
        else:
            migrate_job(job)
    for path in (ROOT / "config").glob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
    rig_templates = sorted((ROOT / "config" / "rig_templates").glob("*.v1.json"))
    if not rig_templates:
        failures.append("no rig templates found")
    for path in rig_templates:
        try:
            load_rig_template(path)
        except PartResolutionError as exc:
            failures.extend(f"{path.relative_to(ROOT)}: {error}" for error in exc.errors)
    advanced_rigs = sorted((ROOT / "config" / "advanced_rigs").glob("*.v1.json"))
    if {path.stem.removesuffix(".v1") for path in advanced_rigs} != {"quadruped_standard", "flying_standard", "multi_arm_standard", "final_boss_composite"}:
        failures.append("Phase 8 requires quadruped, flying, multi-arm, and final-boss rig templates")
    for path in advanced_rigs:
        try: load_topology_rig(path)
        except AdvancedValidationError as exc: failures.extend(f"{path.relative_to(ROOT)}: {error}" for error in exc.errors)
    animation_packs = sorted((ROOT / "config" / "animation_packs").glob("*.v1.json"))
    for path in animation_packs:
        try: load_animation_pack(path)
        except AnimationPackError as exc: failures.extend(f"{path.relative_to(ROOT)}: {error}" for error in exc.errors)
    export_profiles = sorted((ROOT / "config" / "export_profiles").glob("*.v1.json"))
    for path in export_profiles:
        try: load_export_profile(ROOT, path.name.removesuffix(".v1.json"))
        except ExportProfileError as exc: failures.append(f"{path.relative_to(ROOT)}: {exc}")
    try:
        load_pilot_matrix(ROOT / "config" / "production" / "pilot_ten.v1.json")
        load_cast_database(ROOT / "config" / "production" / "cast_ff4_ff10.v1.json")
        validate_packaging_strategy(json.loads((ROOT / "config" / "production" / "windows_packaging.v1.json").read_text(encoding="utf-8")))
        boss = json.loads((ROOT / "config" / "production" / "final_boss.v1.json").read_text(encoding="utf-8"))
        boss_errors = validate_boss_composition({key:value for key,value in boss.items() if key != "schema_version"})
        if boss.get("schema_version") != 1 or boss_errors: failures.extend(boss_errors or ["final boss schema_version must be 1"])
        summary = cast_quality_summary(load_cast_plan(ROOT / "config" / "production" / "large_cast.v1.json"))
        if summary["model_count"] < 100 or not summary["resumable"]: failures.append("large-cast plan is not production-scale and resumable")
        release_path=ROOT / "config" / "production" / "full_cast_release.v1.json"
        if release_path.is_file(): load_cast_release(release_path,load_cast_plan(ROOT / "config" / "production" / "large_cast.v1.json"))
    except (OSError, json.JSONDecodeError, ProductionValidationError) as exc:
        failures.extend(getattr(exc, "errors", [str(exc)]))
    if failures:
        print("Validation failed:", *failures, sep="\n- ")
        return 1
    asset_count = len(registry.manifests) if registry else 0
    print(f"Validated {len(jobs)} jobs, {asset_count} registry assets, {len(rig_templates)} humanoid and {len(advanced_rigs)} advanced rig templates, {len(animation_packs)} animation packs, {len(export_profiles)} export profiles, and the 120-model production plan; v1 jobs are readable and migrate to Job v2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
