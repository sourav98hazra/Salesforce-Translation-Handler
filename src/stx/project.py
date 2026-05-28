"""Project file -- save and resume an entire pipeline run.

A ``.stxproject`` file captures every artifact path and configuration
choice the user made during a run, so the GUI can re-open a saved
project and land directly on Phase N rather than starting over.

The format is JSON; paths are stored relative to the project file when
possible so projects remain portable when copied between machines.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class StxProject:
    """Persistent representation of a pipeline run."""

    name: str = "Untitled project"

    # File artifacts -- absolute paths are normalised to relative on save.
    source_stf_path: Optional[str] = None
    organized_xlsx_path: Optional[str] = None
    translated_xlsx_path: Optional[str] = None
    reviewed_xlsx_path: Optional[str] = None
    output_dir: Optional[str] = None

    # Translation configuration
    source_language_code: str = "en"
    target_language_code: str = "ja"
    target_language_name: str = "Japanese"
    target_languages_batch: List[str] = field(default_factory=list)
    backend: str = "google"

    # Optional integrations
    scope_path: Optional[str] = None
    glossary_path: Optional[str] = None
    memory_path: Optional[str] = None

    # Metadata
    last_phase: int = 0
    schema_version: int = 1

    # ------------------------------------------------------------------ I/O

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        # Resolve paths to be relative to the project file when possible.
        for field_name in (
            "source_stf_path",
            "organized_xlsx_path",
            "translated_xlsx_path",
            "reviewed_xlsx_path",
            "output_dir",
            "scope_path",
            "glossary_path",
            "memory_path",
        ):
            value = data.get(field_name)
            if value is None:
                continue
            try:
                rel = Path(value).resolve().relative_to(target.parent.resolve())
                data[field_name] = str(rel)
            except (ValueError, OSError):
                # Path lives outside the project folder -- keep it absolute.
                pass

        target.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: Path | str) -> "StxProject":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Resolve paths relative to the project file.
        base = path.parent.resolve()
        for field_name in (
            "source_stf_path",
            "organized_xlsx_path",
            "translated_xlsx_path",
            "reviewed_xlsx_path",
            "output_dir",
            "scope_path",
            "glossary_path",
            "memory_path",
        ):
            value = data.get(field_name)
            if value is None:
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = base / candidate
            data[field_name] = str(candidate)

        # Drop unknown fields so additions don't break older projects.
        known = {f for f in cls.__dataclass_fields__}
        cleaned = {k: v for k, v in data.items() if k in known}
        return cls(**cleaned)

    # ------------------------------------------------------------------ helpers

    def to_dict(self) -> dict:
        return asdict(self)
