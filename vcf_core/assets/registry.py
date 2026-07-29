"""Asset Manifest v1 validation and registry lookup.

The registry intentionally resolves only repository-owned source assets.  It is
usable by the controller and unit tests, before Blender is allowed to ingest any
geometry.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ASSET_MANIFEST_VERSION = 1
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SOURCE_FORMATS = {"vox": ".vox", "glb": ".glb", "gltf": ".gltf", "fbx": ".fbx", "obj": ".obj"}
KINDS = {"body_part", "hair", "garment", "accessory", "weapon"}
APPROVED_LICENSES = {"CC0-1.0", "CC-BY-4.0"}
REQUIRED = {
    "schema_version", "asset_id", "version", "kind", "source_path", "format",
    "semantic_tags", "compatible_bases", "pivots", "palette_roles", "author",
    "license", "provenance", "source_sha256", "thumbnail_path",
}
OPTIONAL = {"sockets", "placement_voxels", "scale_metadata", "notes"}


class AssetValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_path(value: Any, key: str, root: Path, errors: list[str], *, extension: str | None = None) -> Path | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{key} must be a non-empty repository-relative path")
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"{key} must be inside assets/original")
        return None
    resolved = (root / path).resolve()
    original = root / "assets" / "original"
    if not _inside(resolved, original):
        errors.append(f"{key} must be inside assets/original")
    elif not resolved.is_file():
        errors.append(f"{key} does not exist: {value}")
    elif extension and resolved.suffix.lower() != extension:
        errors.append(f"{key} must use {extension}")
    return resolved


def _triplet(value: Any, key: str, errors: list[str]) -> None:
    if not isinstance(value, list) or len(value) != 3 or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        errors.append(f"{key} must be a three-number coordinate")


def _voxel_components(cells: set[tuple[int, int, int]]) -> int:
    """Return six-connected components without a Blender dependency."""
    remaining = set(cells)
    components = 0
    while remaining:
        components += 1
        frontier = [remaining.pop()]
        while frontier:
            x, y, z = frontier.pop()
            for neighbor in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    frontier.append(neighbor)
    return components


def _validate_vox_geometry(path: Path, semantic_tags: Any, errors: list[str]) -> None:
    """Keep the Phase 2 source gate deterministic and independent of Blender."""
    try:
        from blender_worker.adapters.vox_reader import VoxError, read_vox
        document = read_vox(path)
    except (ImportError, OSError, ValueError) as exc:
        errors.append(f"could not inspect VOX source: {exc}")
        return
    if not document.models:
        errors.append("VOX source contains no models")
        return
    try:
        names = {instance.name for instance in document.evaluate_scene(include_hidden=True)}
    except VoxError as exc:
        errors.append(f"VOX scene graph is invalid: {exc}")
        return
    expected = set(semantic_tags) if isinstance(semantic_tags, list) else set()
    if expected and not expected.issubset(names):
        errors.append(f"VOX semantic names do not declare all manifest tags: {', '.join(sorted(expected - names))}")
    for model in document.models:
        cells = {(voxel.x, voxel.y, voxel.z) for voxel in model.voxels}
        if not cells:
            errors.append(f"VOX model {model.id} has no voxels")
            continue
        if min(coordinate for coordinate, _y, _z in cells) != 0 or min(coordinate for _x, coordinate, _z in cells) != 0 or min(coordinate for _x, _y, coordinate in cells) != 0:
            errors.append(f"VOX model {model.id} must use a zero-based local origin")
        if _voxel_components(cells) != 1:
            errors.append(f"VOX model {model.id} contains disconnected voxel islands")


@dataclass(frozen=True)
class AssetManifest:
    asset_id: str
    version: str
    kind: str
    source_path: str
    format: str
    semantic_tags: tuple[str, ...]
    compatible_bases: tuple[str, ...]
    pivots: dict[str, tuple[float, float, float]]
    palette_roles: tuple[str, ...]
    author: str
    license: str
    provenance: str
    source_sha256: str
    thumbnail_path: str
    sockets: dict[str, tuple[float, float, float]]
    placement_voxels: tuple[float, float, float]
    scale_metadata: dict[str, Any]
    notes: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.asset_id, self.version

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AssetManifest":
        return cls(
            asset_id=payload["asset_id"], version=payload["version"], kind=payload["kind"],
            source_path=payload["source_path"], format=payload["format"],
            semantic_tags=tuple(payload["semantic_tags"]), compatible_bases=tuple(payload["compatible_bases"]),
            pivots={key: tuple(value) for key, value in payload["pivots"].items()},
            palette_roles=tuple(payload["palette_roles"]), author=payload["author"], license=payload["license"],
            provenance=payload["provenance"], source_sha256=payload["source_sha256"],
            thumbnail_path=payload["thumbnail_path"], sockets={key: tuple(value) for key, value in payload.get("sockets", {}).items()},
            placement_voxels=tuple(payload.get("placement_voxels", [0, 0, 0])),
            scale_metadata=dict(payload.get("scale_metadata", {})), notes=payload.get("notes"),
        )


def validate_manifest(payload: Any, root: Path) -> list[str]:
    if not isinstance(payload, dict):
        return ["asset manifest must be an object"]
    errors: list[str] = []
    unknown = sorted(set(payload) - REQUIRED - OPTIONAL)
    missing = sorted(REQUIRED - set(payload))
    if missing:
        errors.append(f"missing asset manifest fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"unknown asset manifest fields: {', '.join(unknown)}")
    if payload.get("schema_version") != ASSET_MANIFEST_VERSION:
        errors.append(f"asset manifest schema_version must be {ASSET_MANIFEST_VERSION}")
    for key in ("asset_id", "version"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{key} must be a non-empty string")
    if isinstance(payload.get("asset_id"), str) and not SAFE_ID.fullmatch(payload["asset_id"]):
        errors.append("asset_id must be a safe catalog ID")
    if isinstance(payload.get("version"), str) and not SEMVER.fullmatch(payload["version"]):
        errors.append("version must use semantic versioning (major.minor.patch)")
    if payload.get("kind") not in KINDS:
        errors.append(f"kind must be one of: {', '.join(sorted(KINDS))}")
    fmt = payload.get("format")
    if fmt not in SOURCE_FORMATS:
        errors.append(f"format must be one of: {', '.join(sorted(SOURCE_FORMATS))}")
    source = _safe_path(payload.get("source_path"), "source_path", root, errors, extension=SOURCE_FORMATS.get(fmt))
    thumbnail = _safe_path(payload.get("thumbnail_path"), "thumbnail_path", root, errors)
    if thumbnail and thumbnail.suffix.lower() not in {".png", ".svg"}:
        errors.append("thumbnail_path must use .png or .svg")
    tags = payload.get("semantic_tags")
    if not isinstance(tags, list) or not tags or len(tags) != len(set(tags)) or any(not isinstance(tag, str) or not SAFE_ID.fullmatch(tag) for tag in tags):
        errors.append("semantic_tags must be a non-empty, unique array of safe IDs")
    bases = payload.get("compatible_bases")
    if not isinstance(bases, list) or not bases or len(bases) != len(set(bases)) or any(not isinstance(base, str) or not SAFE_ID.fullmatch(base) for base in bases):
        errors.append("compatible_bases must be a non-empty, unique array of safe IDs")
    for map_key in ("pivots", "sockets"):
        value = payload.get(map_key, {})
        if not isinstance(value, dict):
            errors.append(f"{map_key} must be an object")
        else:
            for name, coordinate in value.items():
                if not isinstance(name, str) or not SAFE_ID.fullmatch(name):
                    errors.append(f"{map_key} keys must be safe IDs")
                _triplet(coordinate, f"{map_key}.{name}", errors)
    if not isinstance(payload.get("pivots"), dict) or not payload.get("pivots"):
        errors.append("pivots must declare at least one named pivot")
    _triplet(payload.get("placement_voxels", [0, 0, 0]), "placement_voxels", errors)
    roles = payload.get("palette_roles")
    if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or not SAFE_ID.fullmatch(role) for role in roles):
        errors.append("palette_roles must be a non-empty array of safe IDs")
    for key in ("author", "provenance"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            errors.append(f"{key} must be a non-empty string")
    if payload.get("license") not in APPROVED_LICENSES:
        errors.append(f"license is not approved: {payload.get('license')!r}")
    digest = payload.get("source_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        errors.append("source_sha256 must be a lowercase SHA-256 hex digest")
    elif source and source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        errors.append("source_sha256 does not match source_path")
    if source and source.is_file() and fmt == "vox":
        _validate_vox_geometry(source, payload.get("semantic_tags"), errors)
    if not isinstance(payload.get("scale_metadata", {}), dict):
        errors.append("scale_metadata must be an object")
    return errors


class AssetRegistry:
    def __init__(self, manifests: list[AssetManifest]):
        self._by_key = {manifest.key: manifest for manifest in manifests}
        self._by_id: dict[str, list[AssetManifest]] = {}
        for manifest in manifests:
            self._by_id.setdefault(manifest.asset_id, []).append(manifest)
        for choices in self._by_id.values():
            choices.sort(key=lambda item: tuple(int(value) for value in item.version.split(".")), reverse=True)

    def get(self, asset_id: str, version: str | None = None) -> AssetManifest:
        if version:
            result = self._by_key.get((asset_id, version))
            if result:
                return result
            raise AssetValidationError([f"unknown asset version: {asset_id}@{version}"])
        choices = self._by_id.get(asset_id, [])
        if not choices:
            raise AssetValidationError([f"unknown catalog asset: {asset_id}"])
        return choices[0]

    def resolve(self, asset_ids: list[str], *, body_template: str) -> list[AssetManifest]:
        errors: list[str] = []
        resolved: list[AssetManifest] = []
        for asset_id in asset_ids:
            try:
                manifest = self.get(asset_id)
            except AssetValidationError as exc:
                errors.extend(exc.errors)
                continue
            if body_template not in manifest.compatible_bases:
                errors.append(f"asset {asset_id} is incompatible with body_template {body_template}")
            resolved.append(manifest)
        if len(asset_ids) != len(set(asset_ids)):
            errors.append("asset assembly contains duplicate asset IDs")
        if errors:
            raise AssetValidationError(errors)
        return resolved

    def find_by_tags(self, tags: set[str], *, body_template: str | None = None) -> list[AssetManifest]:
        """Return latest compatible records containing every requested semantic tag."""
        if not tags or any(not SAFE_ID.fullmatch(tag) for tag in tags):
            raise AssetValidationError(["asset tag lookup requires one or more safe semantic tags"])
        results = []
        for asset_id in sorted(self._by_id):
            manifest = self.get(asset_id)
            if tags.issubset(manifest.semantic_tags) and (body_template is None or body_template in manifest.compatible_bases):
                results.append(manifest)
        return results

    @property
    def manifests(self) -> tuple[AssetManifest, ...]:
        return tuple(self._by_key.values())


def load_registry(root: Path) -> AssetRegistry:
    manifest_dir = root / "assets" / "manifests"
    errors: list[str] = []
    manifests: list[AssetManifest] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(manifest_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(root)}: could not read manifest: {exc}")
            continue
        entries = payload.get("assets") if isinstance(payload, dict) and "assets" in payload else [payload]
        if not isinstance(entries, list):
            errors.append(f"{path.relative_to(root)}: assets must be an array")
            continue
        for index, entry in enumerate(entries):
            prefix = f"{path.relative_to(root)}[{index}]"
            entry_errors = validate_manifest(entry, root)
            if entry_errors:
                errors.extend(f"{prefix}: {error}" for error in entry_errors)
                continue
            manifest = AssetManifest.from_dict(entry)
            if manifest.key in seen:
                errors.append(f"{prefix}: duplicate asset ID/version: {manifest.asset_id}@{manifest.version}")
            seen.add(manifest.key)
            manifests.append(manifest)
    if errors:
        raise AssetValidationError(errors)
    return AssetRegistry(manifests)
