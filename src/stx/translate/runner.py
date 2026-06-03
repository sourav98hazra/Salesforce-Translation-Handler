"""Drive translation across an entire :class:`Document`.

The runner consumes a :class:`Document`, mutates it in place by filling
in missing translations, and yields progress callbacks suitable for both
CLI progress bars and Qt thread signals.

The output structure (:class:`SheetSummary`, :class:`StatusEntry`) maps
directly onto the ``Translation_Summary`` and ``Translation_Status_Log``
sheets emitted by the legacy translator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Callable, List, Optional

from ..model import Document, Entry
from .base import Translator

LOGGER = logging.getLogger(__name__)


@dataclass
class SheetSummary:
    """Per-sheet counts, mirrored into the audit workbook."""

    sheet_name: str
    total_rows: int = 0
    translated_rows: int = 0
    skipped_rows: int = 0

    def as_audit_row(self) -> dict:
        return {
            "Sheet Name": self.sheet_name,
            "Total Rows": self.total_rows,
            "Translated Rows": self.translated_rows,
            "Skipped Rows": self.skipped_rows,
        }


@dataclass
class StatusEntry:
    """Per-row translation outcome for the audit log."""

    sheet_name: str
    row_index: int
    key: str
    label: str
    status: str

    def as_audit_row(self) -> dict:
        return {
            "Sheet Name": self.sheet_name,
            "Row Index": self.row_index,
            "Key": self.key,
            "Label": self.label,
            "Status": self.status,
        }


@dataclass
class TranslationProgress:
    """Progress event emitted while translating."""

    completed: int
    total: int
    sheet: str
    key: str
    status: str

    @property
    def percent(self) -> int:
        return int(self.completed * 100 / self.total) if self.total else 0


@dataclass
class TranslationResult:
    """Outcome of :func:`translate_document`."""

    document: Document
    summaries: List[SheetSummary] = field(default_factory=list)
    statuses: List[StatusEntry] = field(default_factory=list)
    translated_count: int = 0
    skipped_count: int = 0
    
    # Detailed translation method counts
    api_count: int = 0
    cached_count: int = 0  # Via Translation Memory
    deduped_count: int = 0  # Via repeated label
    fuzzy_accepted_count: int = 0  # Via fuzzy match subset of cached
    imported_reuse_count: int = 0  # Via imported reference
    infile_reuse_count: int = 0  # Via in-file label match
    resumed_count: int = 0  # Pre-existing (unchanged)
    failed_count: int = 0
    
    @property
    def rows_attempted(self) -> int:
        """Total rows that were attempted for translation (excludes pre-existing)."""
        return self.translated_count + self.failed_count
    
    @property
    def total_with_translation(self) -> int:
        """Total rows that have a translation (including pre-existing)."""
        return self.translated_count + self.resumed_count
    
    @property
    def total_rows_processed(self) -> int:
        """Total rows in the document."""
        return self.translated_count + self.resumed_count + self.skipped_count + self.failed_count
    
    def format_summary(self) -> str:
        """Format the improved summary with separated pre-existing and attempted rows."""
        lines = []
        
        # Top section - attempted vs pre-existing
        lines.append(f"Rows attempted:              {self.rows_attempted:,}")
        lines.append(f"Rows translated:             {self.translated_count:,}")
        lines.append(f"Rows failed:                 {self.failed_count:,}")
        lines.append("")
        
        # Successfully translated breakdown
        lines.append(f"Successfully Translated:     {self.translated_count:,}")
        if self.api_count > 0:
            lines.append(f"├─ Via Translation API:      {self.api_count:,}")
        if self.cached_count > 0:
            cache_line = f"├─ Via cached translation:   {self.cached_count:,}"
            if self.fuzzy_accepted_count > 0:
                cache_line += f"  (via fuzzy match: {self.fuzzy_accepted_count})"
            lines.append(cache_line)
        if self.deduped_count > 0:
            lines.append(f"├─ Via repeated label:       {self.deduped_count:,}")
        if self.infile_reuse_count > 0:
            lines.append(f"├─ Via in-file label match:  {self.infile_reuse_count:,}")
        if self.imported_reuse_count > 0:
            lines.append(f"├─ Via imported reference:   {self.imported_reuse_count:,}")
        lines.append("")
        
        # Pre-existing and totals
        lines.append(f"Pre-existing (kept as-is): {self.resumed_count:,}")
        lines.append(f"Failed Translations:       {self.failed_count:,}")
        lines.append(f"Total with translation:   {self.total_with_translation:,} / {self.total_rows_processed:,}")
        
        return "\n".join(lines)


ProgressCallback = Callable[[TranslationProgress], None]


def translate_document(
    doc: Document,
    translator: Translator,
    *,
    source_lang: str = "en",
    target_lang: str = "ja",
    retranslate_all: bool = False,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> TranslationResult:
    """Translate every untranslated entry in ``doc`` in place.

    Parameters
    ----------
    doc:
        Document to translate.  Modified in place.
    translator:
        Backend to use.
    source_lang, target_lang:
        Language codes passed verbatim to the translator backend.
    progress:
        Optional callback receiving :class:`TranslationProgress` events.
    cancel:
        Optional predicate; if it returns ``True`` between rows the run
        is aborted gracefully (already-translated rows are kept).
    """

    summaries: dict[str, SheetSummary] = {}
    statuses: List[StatusEntry] = []
    translated_count = 0
    skipped_count = 0
    api_count = 0
    cached_count = 0
    deduped_count = 0
    fuzzy_accepted_count = 0
    imported_reuse_count = 0
    infile_reuse_count = 0
    resumed_count = 0
    failed_count = 0
    total_rows = len(doc.entries)

    new_entries: List[Entry] = []

    for index, entry in enumerate(doc.entries):
        sheet_name = entry.logical_sheet_name
        summary = summaries.setdefault(sheet_name, SheetSummary(sheet_name=sheet_name))
        summary.total_rows += 1

        if cancel is not None and cancel():
            new_entries.append(entry)
            statuses.append(
                StatusEntry(
                    sheet_name=sheet_name,
                    row_index=index + 2,  # +1 header, +1 to be 1-indexed
                    key=entry.key,
                    label=entry.label,
                    status="Cancelled",
                )
            )
            continue

        # Handle pre-existing translations
        if entry.translation.strip() and not retranslate_all:
            summary.skipped_rows += 1
            resumed_count += 1
            statuses.append(
                StatusEntry(
                    sheet_name=sheet_name,
                    row_index=index + 2,
                    key=entry.key,
                    label=entry.label,
                    status="Pre-existing (unchanged)",
                )
            )
            new_entries.append(entry)
            _emit(progress, index + 1, total_rows, sheet_name, entry.key, "Pre-existing")
            continue

        # Skip blank labels
        if not entry.label.strip():
            summary.skipped_rows += 1
            skipped_count += 1
            statuses.append(
                StatusEntry(
                    sheet_name=sheet_name,
                    row_index=index + 2,
                    key=entry.key,
                    label=entry.label,
                    status="Skipped (blank label)",
                )
            )
            new_entries.append(entry)
            _emit(progress, index + 1, total_rows, sheet_name, entry.key, "Skipped")
            continue

        # Attempt translation via API
        try:
            translated = translator.translate(entry.label, source_lang, target_lang)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Translation failed for %s: %s", entry.key, exc)
            translated = entry.label
            status = f"Failed: {exc}"
            failed_count += 1
        else:
            if not translated or translated.strip() == "":
                translated = entry.label
                status = "Failed: empty result"
                failed_count += 1
            else:
                status = "Via Translation API"
                summary.translated_rows += 1
                translated_count += 1
                api_count += 1

        new_entries.append(Entry(key=entry.key, label=entry.label, translation=translated))
        statuses.append(
            StatusEntry(
                sheet_name=sheet_name,
                row_index=index + 2,
                key=entry.key,
                label=entry.label,
                status=status,
            )
        )
        _emit(progress, index + 1, total_rows, sheet_name, entry.key, status)

    doc.entries = new_entries

    return TranslationResult(
        document=doc,
        summaries=list(summaries.values()),
        statuses=statuses,
        translated_count=translated_count,
        skipped_count=skipped_count,
        api_count=api_count,
        cached_count=cached_count,
        deduped_count=deduped_count,
        fuzzy_accepted_count=fuzzy_accepted_count,
        imported_reuse_count=imported_reuse_count,
        infile_reuse_count=infile_reuse_count,
        resumed_count=resumed_count,
        failed_count=failed_count,
    )


def _emit(
    callback: Optional[ProgressCallback],
    completed: int,
    total: int,
    sheet: str,
    key: str,
    status: str,
) -> None:
    if callback is None:
        return
    try:
        callback(TranslationProgress(completed=completed, total=total, sheet=sheet, key=key, status=status))
    except Exception:  # noqa: BLE001
        LOGGER.debug("Progress callback raised; ignoring", exc_info=True)


# Re-export for convenience.
__all__ = [
    "translate_document",
    "TranslationProgress",
    "TranslationResult",
    "SheetSummary",
    "StatusEntry",
    "asdict",
]
