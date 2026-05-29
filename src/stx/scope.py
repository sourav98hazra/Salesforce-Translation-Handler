"""Translation scope -- which rows actually go through the translator.

A :class:`Scope` is the union of three filters:

1. **Component types** the user has explicitly selected (e.g. only
   ``CustomLabel`` and ``ButtonOrLink``).  Default: all components.
2. **Status filter** -- ``UNTRANSLATED`` (default), ``ALL``, or
   ``TRANSLATED``.  Untranslated-only is the common case.
3. **Key allowlist / denylist** -- exact keys plus glob-style patterns
   (``*`` and ``?`` wildcards via :mod:`fnmatch`).  Both lists are
   optional; an empty allowlist means "no exact-key restriction".

The scope is serialisable as a small JSON file (``.stxscope.json``)
that can live next to the source STF / Excel and be auto-discovered on
load -- this implements the "store a list of keys somewhere which
should be translated" feature.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional, Set

from .model import Document, Entry


class StatusFilter(str, Enum):
    """Which entries to include based on translation status."""

    ALL = "all"
    UNTRANSLATED = "untranslated"
    TRANSLATED = "translated"


@dataclass
class Scope:
    """Filter that decides whether an entry should be translated."""

    components: Optional[Set[str]] = None
    """Set of component types to include.  ``None`` means *all* components."""

    status: StatusFilter = StatusFilter.UNTRANSLATED
    """Which translation statuses to include."""

    include_keys: List[str] = field(default_factory=list)
    """Exact keys explicitly opted in.  Empty means "no exact-key restriction"."""

    include_patterns: List[str] = field(default_factory=list)
    """Glob patterns (``CustomLabel.*``).  Empty means "no pattern restriction"."""

    exclude_keys: List[str] = field(default_factory=list)
    """Exact keys explicitly opted out -- always wins over include rules."""

    exclude_patterns: List[str] = field(default_factory=list)
    """Glob exclusion patterns -- always win over include rules."""

    name: str = "Default scope"
    """Human-readable label, surfaced in the UI."""

    # ------------------------------------------------------------------ matching

    def includes(self, entry: Entry) -> bool:
        """Return ``True`` if ``entry`` should be translated under this scope."""

        # 1. Component filter
        if self.components is not None and entry.component_type not in self.components:
            return False

        # 2. Status filter
        if self.status == StatusFilter.UNTRANSLATED and entry.translation.strip():
            return False
        if self.status == StatusFilter.TRANSLATED and not entry.translation.strip():
            return False

        # 3. Exclude lists win over include lists.
        if entry.key in self.exclude_keys:
            return False
        if any(fnmatch.fnmatchcase(entry.key, p) for p in self.exclude_patterns):
            return False

        # 4. Include lists -- only enforced if any are configured.
        has_includes = bool(self.include_keys) or bool(self.include_patterns)
        if has_includes:
            if entry.key in self.include_keys:
                return True
            return any(fnmatch.fnmatchcase(entry.key, p) for p in self.include_patterns)

        return True

    def filter_entries(self, entries: Iterable[Entry]) -> List[Entry]:
        """Return only the entries that pass the scope."""
        return [e for e in entries if self.includes(e)]

    def estimate_count(self, doc: Document) -> int:
        """Number of entries from ``doc`` that the scope would translate."""
        return sum(1 for e in doc.entries if self.includes(e))

    # ------------------------------------------------------------------ persistence

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "name": self.name,
            "components": sorted(self.components) if self.components is not None else None,
            "status": self.status.value,
            "include_keys": list(self.include_keys),
            "include_patterns": list(self.include_patterns),
            "exclude_keys": list(self.exclude_keys),
            "exclude_patterns": list(self.exclude_patterns),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Scope":
        components = data.get("components")
        return cls(
            components=set(components) if components else None,
            status=StatusFilter(data.get("status", StatusFilter.UNTRANSLATED.value)),
            include_keys=list(data.get("include_keys") or []),
            include_patterns=list(data.get("include_patterns") or []),
            exclude_keys=list(data.get("exclude_keys") or []),
            exclude_patterns=list(data.get("exclude_patterns") or []),
            name=str(data.get("name") or "Loaded scope"),
        )

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: Path | str) -> "Scope":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def discover(near: Path | str) -> Optional[Path]:
        """Return the path of an auto-discoverable scope file, if any.

        Looks for, in order:

        1. ``<near>.stxscope.json`` (full path with extension appended).
        2. ``<near with .stxscope.json suffix>``.
        3. ``<near's parent>/.stxscope.json``.

        Used by the GUI to pre-fill the scope picker when a user opens a
        source file that already has a saved scope alongside it.
        """
        path = Path(near)
        candidates = [
            path.with_suffix(path.suffix + ".stxscope.json"),
            path.with_suffix(".stxscope.json"),
            path.parent / ".stxscope.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    # ------------------------------------------------------------------ helpers

    @classmethod
    def all_components_of(
        cls,
        doc: Document,
        status: StatusFilter = StatusFilter.UNTRANSLATED,
    ) -> "Scope":
        """Build a scope including every component type present in ``doc``."""
        components = sorted({e.component_type for e in doc.entries})
        return cls(components=set(components), status=status)
