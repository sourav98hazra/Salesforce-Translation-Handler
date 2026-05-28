"""Glossary -- "do not translate" and "always translate as" rules.

A glossary protects business-critical terminology from machine
translation.  Two rule kinds are supported:

* **Do-not-translate (DNT) terms** -- the term is shielded by the same
  sentinel mechanism used in :mod:`stx.translate.protect` and round-trips
  exactly.  Use this for brand names (``Bayer``, ``ATLS``), product
  names, and acronyms the auto-CAPS rule would miss.
* **Forced translations** -- a source term is *always* replaced with a
  specific translation (case-insensitive match).  Use this when the
  translator picks an inferior synonym (e.g. ``case`` -> always ``ケース``
  instead of ``事件``).

Glossaries are stored as CSV files for easy editing in Excel:

::

    source,target,do_not_translate
    Bayer,,true
    ATLS,,true
    case,ケース,
    record,レコード,

Empty ``target`` + empty/false ``do_not_translate`` is a no-op row.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Tuple


@dataclass
class GlossaryEntry:
    source: str
    target: str = ""
    do_not_translate: bool = False

    @property
    def is_active(self) -> bool:
        return self.do_not_translate or bool(self.target.strip())


@dataclass
class Glossary:
    """Collection of :class:`GlossaryEntry` rules."""

    entries: List[GlossaryEntry] = field(default_factory=list)

    # ------------------------------------------------------------------ I/O

    @classmethod
    def load_csv(cls, path: Path | str) -> "Glossary":
        """Load a glossary from a CSV with headers ``source,target,do_not_translate``."""
        path = Path(path)
        rows: list[GlossaryEntry] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                source = (raw.get("source") or "").strip()
                if not source:
                    continue
                target = (raw.get("target") or "").strip()
                dnt_raw = (raw.get("do_not_translate") or "").strip().lower()
                dnt = dnt_raw in {"true", "1", "yes", "y"}
                entry = GlossaryEntry(source=source, target=target, do_not_translate=dnt)
                if entry.is_active:
                    rows.append(entry)
        return cls(entries=rows)

    def save_csv(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source", "target", "do_not_translate"])
            for entry in self.entries:
                writer.writerow(
                    [
                        entry.source,
                        entry.target,
                        "true" if entry.do_not_translate else "",
                    ]
                )
        return target

    # ------------------------------------------------------------------ protection

    def protect(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Replace DNT terms in ``text`` with sentinel tokens.

        Returns the rewritten text and a token map compatible with
        :func:`stx.translate.protect.restore_tokens`.
        """
        token_map: List[Tuple[str, str]] = []
        if not text:
            return text, token_map

        protected = text
        for index, entry in enumerate(self._dnt_entries()):
            # Whole-word, case-insensitive match.  The negative look-arounds
            # avoid replacing inside sentinels that the main protector left
            # behind on a previous pass.
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(entry.source)}(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
            token = f"__GLOSS_{index}__"
            new_text, count = pattern.subn(token, protected)
            if count:
                protected = new_text
                # Multiple occurrences share the same sentinel: that's fine
                # because the slow-path restore replaces every occurrence.
                token_map.append((token, entry.source))
        return protected, token_map

    def apply_forced(self, text: str) -> str:
        """Apply forced-translation rules to a translated string."""
        if not text:
            return text
        for entry in self._forced_entries():
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(entry.source)}(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
            text = pattern.sub(entry.target, text)
        return text

    # ------------------------------------------------------------------ helpers

    def _dnt_entries(self) -> Iterable[GlossaryEntry]:
        return (e for e in self.entries if e.do_not_translate)

    def _forced_entries(self) -> Iterable[GlossaryEntry]:
        return (e for e in self.entries if not e.do_not_translate and e.target.strip())

    def __len__(self) -> int:
        return len(self.entries)

    def __bool__(self) -> bool:
        return bool(self.entries)
