"""Searchable character-catalog records for the desktop application.

This module deliberately has no Tk dependency so catalog discovery, filtering,
and invalid-job handling can be tested without a graphical display.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from vcf_core.jobs import load_job


@dataclass(frozen=True)
class CharacterRecord:
    """One character file and the metadata needed by the library browser."""

    path: Path
    job_id: str
    name: str
    game: str
    role: str
    variant_of: str | None
    valid: bool = True
    error: str = ""

    @property
    def label(self) -> str:
        if not self.valid:
            return f"INVALID  \u2022  {self.path.stem}"
        return f"{self.game.upper()}  \u2022  {self.name}"

    @property
    def search_text(self) -> str:
        return " ".join(
            value
            for value in (
                self.job_id,
                self.name,
                self.game,
                self.role,
                self.variant_of or "",
                self.path.stem,
            )
            if value
        ).casefold()


def load_character_record(
    path: Path, root: Path, *, validate: bool = True
) -> CharacterRecord:
    """Load one character record, converting validation failures into metadata."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("job must be a JSON object")
        resolved = load_job(path, root) if validate else raw
        return CharacterRecord(
            path=path,
            job_id=str(resolved.get("id", path.stem)),
            name=str(resolved.get("name", path.stem)),
            game=str(resolved.get("game", "unknown")),
            role=str(resolved.get("role", "unknown")),
            variant_of=(str(raw["variant_of"]) if raw.get("variant_of") else None),
        )
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return CharacterRecord(
            path=path,
            job_id=path.stem,
            name=path.stem.replace("_", " ").title(),
            game="invalid",
            role="invalid",
            variant_of=None,
            valid=False,
            error=str(exc),
        )


def load_character_catalog(
    root: Path, *, validate: bool = False
) -> list[CharacterRecord]:
    """Load every character job in stable path order, retaining invalid rows.

    The desktop uses the fast metadata-only default so a large cast does not
    block startup. Build, save, and editor actions still perform canonical
    validation. Validation tools and tests can opt into a full catalog pass.
    """

    records = [
        load_character_record(path, root, validate=validate)
        for path in sorted((root / "characters").glob("*/*.json"))
    ]
    if validate:
        return records

    by_id = {record.job_id: record for record in records if record.valid}

    def inherited_role(record: CharacterRecord, seen: frozenset[str] = frozenset()) -> str:
        if record.role != "unknown" or not record.variant_of or record.job_id in seen:
            return record.role
        parent = by_id.get(record.variant_of)
        if parent is None:
            return record.role
        return inherited_role(parent, seen | {record.job_id})

    return [
        replace(record, role=inherited_role(record)) if record.valid else record
        for record in records
    ]


def filter_character_catalog(
    records: list[CharacterRecord], query: str = "", game: str = "All"
) -> list[CharacterRecord]:
    """Filter records by game and whitespace-separated search terms."""

    terms = tuple(term for term in query.casefold().split() if term)
    game_filter = game.casefold()
    return [
        record
        for record in records
        if (game_filter == "all" or record.game.casefold() == game_filter)
        and all(term in record.search_text for term in terms)
    ]


def catalog_games(records: list[CharacterRecord]) -> tuple[str, ...]:
    """Return display-ready game filter values."""

    return ("All", *sorted({record.game.upper() for record in records if record.valid}))
