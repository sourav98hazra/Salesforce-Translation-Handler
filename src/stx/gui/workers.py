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
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._doc = doc
        self._source = to_google_code(source_code)
        self._target = to_google_code(target_code)
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
