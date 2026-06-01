"""In-memory data model for an STF document.

A :class:`Document` is the canonical representation that flows through every
phase of the workflow.  All parsers, writers, exporters and importers
ultimately produce or consume :class:`Document` instances, which keeps the
pipeline format-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Entry:
    """A single STF translation row.

    Attributes
    ----------
    key:
        The fully-qualified Salesforce metadata key (e.g.
        ``CustomApp.Sales_Leader.Description``).
    label:
        The source-language label.
    translation:
        The target-language translation, or an empty string if untranslated.
    """

    key: str
    label: str
    translation: str = ""
    approved: bool = False

    @property
    def component_type(self) -> str:
        """First dotted segment of ``key`` (e.g. ``CustomApp``).

        Falls back to ``"Unknown"`` when the key has no dotted prefix.
        """
        if "." in self.key:
            head = self.key.split(".", 1)[0]
            return head if head else "Unknown"
        return self.key or "Unknown"

    @property
    def status(self) -> str:
        """Return the translation status.

        * ``"Approved"`` if approved *and* a non-blank translation exists.
        * ``"Translated"`` if a non-blank translation exists (but not approved).
        * ``"Untranslated"`` otherwise.
        """
        if self.approved and self.translation.strip():
            return "Approved"
        return "Translated" if self.translation.strip() else "Untranslated"

    @property
    def logical_sheet_name(self) -> str:
        """Logical worksheet name used by the Excel exporter (``<Component>_<Status>``).

        Approved entries group as ``Translated`` (not ``Approved``) so the
        Excel layout stays stable regardless of approval state.
        """
        base_status = "Translated" if self.translation.strip() else "Untranslated"
        return f"{self.component_type}_{base_status}"


@dataclass
class Document:
    """A parsed STF document.

    The document tracks the metadata header (language, language code,
    STF type, translation type) and the ordered list of :class:`Entry`
    rows.  Entry order is preserved through the entire pipeline.
    """

    language: str = ""
    language_code: str = ""
    stf_type: str = "Bilingual"
    translation_type: str = "Metadata"
    entries: List[Entry] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers

    def translated(self) -> List[Entry]:
        """Return only entries with a non-blank translation."""
        return [e for e in self.entries if e.translation.strip()]

    def untranslated(self) -> List[Entry]:
        """Return only entries with a blank translation."""
        return [e for e in self.entries if not e.translation.strip()]

    def stats(self) -> dict:
        """Return a small dictionary of counts useful for UI display."""
        total = len(self.entries)
        translated = len(self.translated())
        return {
            "total": total,
            "translated": translated,
            "untranslated": total - translated,
            "components": len({e.component_type for e in self.entries}),
        }
