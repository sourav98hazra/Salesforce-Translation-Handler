"""Background workers (QThread) so the UI thread is never blocked.

Long-running operations (parsing a 36k-row STF, exporting an Excel
workbook, calling the translator API) run inside :class:`QThread`
subclasses that emit Qt signals back to the main window.  This module
is the only place in the GUI where Qt threading primitives are used
directly -- pages just connect to signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

from ..excel import (
    export_document_to_excel,
    import_document_from_excel,
    write_translation_audit_sheets,
)
from ..languages import to_google_code
from ..model import Document
from ..stf import parse_stf, write_stf_files
from ..translate import GoogleFreeTranslator, TranslationProgress, translate_document


# ---------------------------------------------------------------------------
# Generic "run a callable in a thread" worker
# ---------------------------------------------------------------------------

class _CallableWorker(QThread):
    """Run an arbitrary callable inside a QThread.

    Emits :pyattr:`finished_ok` with the return value on success or
    :pyattr:`failed` with the exception on error.  We deliberately keep
    one worker per logical operation (rather than a generic pool) so
    that pages can connect/disconnect signals predictably.
    """

    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # noqa: D401 -- Qt API
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished_ok.emit(result)


# ---------------------------------------------------------------------------
# Specialised workers -- each is a thin wrapper over a single core call
# ---------------------------------------------------------------------------

class ParseStfWorker(_CallableWorker):
    """Parse an STF file off the UI thread."""

    def __init__(self, path: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(lambda: parse_stf(path), parent)


class ExportExcelWorker(_CallableWorker):
    """Export a :class:`Document` to ``.xlsx``."""

    def __init__(self, doc: Document, output_path: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(lambda: export_document_to_excel(doc, output_path), parent)


class ImportExcelWorker(_CallableWorker):
    """Import a :class:`Document` from a workbook on disk."""

    def __init__(
        self,
        path: Path,
        language: str | None = None,
        language_code: str | None = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(
            lambda: import_document_from_excel(
                path, language=language, language_code=language_code
            ),
            parent,
        )


class WriteStfWorker(_CallableWorker):
    """Write the three STF files to a directory."""

    def __init__(
        self,
        doc: Document,
        output_dir: Path,
        language_name: str,
        language_code: str,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(
            lambda: write_stf_files(
                doc,
                output_dir,
                language_name=language_name,
                language_code=language_code,
            ),
            parent,
        )


# ---------------------------------------------------------------------------
# Translation worker -- emits granular progress updates
# ---------------------------------------------------------------------------

@dataclass
class TranslationDone:
    """Bundle returned by :class:`TranslationWorker` on success."""

    summaries: list
    statuses: list
    translated_count: int
    skipped_count: int
    api_count: int = 0
    cached_count: int = 0
    deduped_count: int = 0
    fuzzy_accepted_count: int = 0
    imported_reuse_count: int = 0
    infile_reuse_count: int = 0
    resumed_count: int = 0
    failed_count: int = 0
    
    def format_summary(self) -> str:
        """Format the summary for display."""
        lines = []
        
        rows_attempted = self.translated_count + self.failed_count
        total_with_translation = self.translated_count + self.resumed_count
        total_rows_processed = self.translated_count + self.resumed_count + self.skipped_count + self.failed_count
        
        lines.append(f"Rows attempted:              {rows_attempted:,}")
        lines.append(f"Rows translated:             {self.translated_count:,}")
        lines.append(f"Rows failed:                 {self.failed_count:,}")
        lines.append("")
        
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
        
        lines.append(f"Pre-existing (kept as-is): {self.resumed_count:,}")
        lines.append(f"Failed Translations:       {self.failed_count:,}")
        lines.append(f"Total with translation:   {total_with_translation:,} / {total_rows_processed:,}")
        
        return "\n".join(lines)


class TranslationWorker(QThread):
    """Run :func:`translate_document` and report incremental progress.

    Emits
    -----
    progress(int percent, str message)
        Roughly once per row.  The message includes the current sheet
        plus the row's key.
    finished_ok(TranslationDone)
        On successful completion (even if some rows fell back to
        original text -- the audit sheets still capture that detail).
    failed(str)
        On unexpected error.
    """

    progress = Signal(int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        doc: Document,
        source_code: str,
        target_code: str,
        retranslate_all: bool = False,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._doc = doc
        self._source = to_google_code(source_code)
        self._target = to_google_code(target_code)
        self._retranslate_all = retranslate_all
        self._cancel = False

    def cancel(self) -> None:
        """Request a graceful early-stop after the current row."""
        self._cancel = True

    def run(self) -> None:  # noqa: D401
        translator = GoogleFreeTranslator()

        def on_progress(event: TranslationProgress) -> None:
            self.progress.emit(
                event.percent,
                f"[{event.completed}/{event.total}] {event.sheet} :: {event.key} -> {event.status}",
            )

        try:
            result = translate_document(
                self._doc,
                translator,
                source_lang=self._source,
                target_lang=self._target,
                retranslate_all=self._retranslate_all,
                progress=on_progress,
                cancel=lambda: self._cancel,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return

        self.finished_ok.emit(
            TranslationDone(
                summaries=result.summaries,
                statuses=result.statuses,
                translated_count=result.translated_count,
                skipped_count=result.skipped_count,
                api_count=result.api_count,
                cached_count=result.cached_count,
                deduped_count=result.deduped_count,
                fuzzy_accepted_count=result.fuzzy_accepted_count,
                imported_reuse_count=result.imported_reuse_count,
                infile_reuse_count=result.infile_reuse_count,
                resumed_count=result.resumed_count,
                failed_count=result.failed_count,
            )
        )


class WriteAuditSheetsWorker(_CallableWorker):
    """Append translation audit sheets to an existing workbook."""

    def __init__(
        self,
        workbook_path: Path,
        summaries: list,
        statuses: list,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(
            lambda: write_translation_audit_sheets(
                workbook_path,
                summary_rows=[s.as_audit_row() for s in summaries],
                status_rows=[s.as_audit_row() for s in statuses],
            ),
            parent,
        )
