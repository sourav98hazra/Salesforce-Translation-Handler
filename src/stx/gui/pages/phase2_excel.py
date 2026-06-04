"""Phase 2 -- Convert the parsed STF into an organised Excel workbook."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..state import AppState, PhaseSnapshot, PhaseStatus
from ..workers import ExportExcelWorker, ImportExcelWorker
from .base import PhasePage, add_popout_to_groupbox, make_action_row, primary


class Phase2ExcelPage(PhasePage):
    """Convert the in-memory document into an organised workbook on disk."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 2 \u2014 STF to Organised Excel",
            subtitle=(
                "Group rows by component type and translation status into a "
                "structured ``.xlsx`` workbook. The workbook can be reviewed "
                "outside this app and re-loaded at any later phase."
            ),
            parent=parent,
        )
        self._build()

    def _build(self) -> None:
        # Status / summary
        self._summary_label = QLabel("No document loaded yet \u2014 complete Phase 1 first.")
        self._summary_label.setStyleSheet("color: #4a5568; font-weight: 700;")
        self.add_widget(self._summary_label)

        # Content Details preview
        details_box = QGroupBox("Content Details (post-export preview)")
        self._details_box = details_box
        self._details_layout = QVBoxLayout(details_box)
        self._details_layout.setContentsMargins(4, 4, 4, 4)
        self._details_layout.setSpacing(2)

        self._details = QTableWidget(0, 5)
        self._details.setHorizontalHeaderLabels([
            "SheetName", "SavedAs", "ComponentType", "TranslationStatus", "TotalRecords",
        ])
        header = self._details.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # Last column (TotalRecords) stretches to fill remaining space so
        # all the previous columns stay fully visible without truncation.
        header.setSectionResizeMode(self._details.columnCount() - 1, QHeaderView.ResizeMode.Stretch)
        self._details.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._details.setAlternatingRowColors(True)
        self._details_layout.addWidget(self._details)
        self.add_widget(details_box, stretch=1)

        # Pop-out icon glued to the top-right of the group box border
        add_popout_to_groupbox(details_box, self._on_popout_details)

        # Actions
        self._convert_btn = primary(QPushButton("Convert"))
        self._convert_btn.clicked.connect(self._on_convert)
        self._convert_btn.setToolTip(
            "Convert the parsed STF into an organised Excel workbook.\n"
            "The file is auto-named and saved — use 'Save a Copy...' if you want a different location."
        )

        self._save_copy_btn = QPushButton("Save a Copy...")
        self._save_copy_btn.clicked.connect(self._on_save_copy)
        self._save_copy_btn.setEnabled(False)
        self._save_copy_btn.setToolTip(
            "Write an additional copy of the organised workbook to a "
            "different location (handy for backups or sharing)."
        )

        self._load_btn = QPushButton("Load existing .xlsx...")
        self._load_btn.setToolTip(
            "Open a previously generated organised workbook so you can resume from "
            "Phase 3 (Translate) without re-parsing the STF."
        )
        self._load_btn.clicked.connect(self._on_load_existing)

        self._next_btn = QPushButton("Continue to Phase 3 \u2192")
        self._next_btn.setEnabled(False)
        self._next_btn.setToolTip("Move to the next phase (Translate).")
        self._next_btn.clicked.connect(self._on_continue_to_phase3)
        primary(self._next_btn)

        self.add_layout(make_action_row(
            self._convert_btn, self._save_copy_btn, self._load_btn, self._next_btn
        ))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        # If this phase was reset (IDLE) and upstream hasn't sent us here
        # via "Continue" (upstream not DONE), show empty state.
        phase_idx = 1  # Phase 2 = index 1
        upstream_done = (
            phase_idx > 0
            and self._state.phase_status[phase_idx - 1] == PhaseStatus.DONE
        )
        if self._state.document is None or (
            self._state.phase_status[phase_idx] == PhaseStatus.IDLE and not upstream_done
        ):
            self._summary_label.setText(
                "No document loaded \u2014 complete Phase 1 first, "
                "or use 'Load existing organised .xlsx...' to jump straight to Phase 3."
            )
            self._convert_btn.setEnabled(False)
            return
        stats = self._state.document.stats()
        self._summary_label.setText(
            f"Document ready: {stats['total']:,} rows, "
            f"{stats['untranslated']:,} untranslated, {stats['components']} component types."
        )
        self._convert_btn.setEnabled(True)

        # If conversion was already performed, re-enable downstream buttons
        if self._state.organized_xlsx_path is not None:
            self._next_btn.setEnabled(True)
            self._save_copy_btn.setEnabled(True)
        else:
            # Auto-convert when arriving from Phase 1 with a document loaded.
            # This avoids requiring the user to manually click Convert before
            # they can proceed to Phase 3.
            self._on_convert()

        # Auto-populate Content Details when arriving from Phase 1 (or any
        # navigation) if a document exists but the table is still empty.
        if self._details.rowCount() == 0:
            self._populate_details_from_doc(self._state.document)

    # ------------------------------------------------------------------ slots

    def _on_convert(self) -> None:
        if self._state.document is None:
            self.warn("Load an STF file in Phase 1 first.")
            return
        # Auto-generate output path: professional dated name in the source folder.
        name = self.default_save_name("organized")
        if self._state.source_stf_path is not None:
            path = self._state.source_stf_path.parent / name
        elif self._state.output_dir:
            path = Path(self._state.output_dir) / name
        else:
            path = Path(name)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        self.status_message.emit(f"Exporting {len(self._state.document.entries):,} rows -> {path} ...")
        worker = ExportExcelWorker(self._state.document, path, self)
        worker.finished_ok.connect(self._on_exported)
        worker.failed.connect(lambda msg: self.error(msg, "Export failed"))
        worker.start()

    def _on_exported(self, result) -> None:
        # Guard: if the document was cleared (e.g. by Reset Phase) while the
        # export worker was running, discard this stale callback.
        if self._state.document is None:
            return
        self._state.organized_xlsx_path = result.path
        self._state.output_dir = result.path.parent
        self._populate_details(result)
        try:
            from .. import settings as gui_settings
            from ..state import PhaseStatus

            gui_settings.add_recent_file(result.path)
            gui_settings.remember_output_dir(result.path.parent)
            self._state.set_phase(1, PhaseStatus.DONE)
            # Set workflow context so override dialog works for subsequent loads
            self._state.set_active_workflow_context(
                document=self._state.document,
                original_source_path=self._state.source_stf_path or result.path,
                current_working_path=result.path,
                current_working_artifact_type="organized_excel",
                start_phase=0,
                current_phase=1,
                override_existing=False,
                reset_downstream=False,
            )
        except Exception:  # noqa: BLE001
            pass

        # Take Phase 2 snapshot
        if self._state.document is not None:
            self._state.phase_snapshots[1] = PhaseSnapshot(
                source_path=result.path,
                artifact_type="organized_excel",
                row_count=len(self._state.document.entries),
                target_language_code=self._state.target_language_code,
                target_language_name=self._state.target_language_name,
                timestamp=time.time(),
            )
        total_sheets = len(result.sheets_written)
        # If there is a Content Details sheet, separate the count
        has_content_details = any(
            "content" in s.lower() and "detail" in s.lower()
            for s in result.sheets_written
        )
        if has_content_details and total_sheets > 1:
            component_count = total_sheets - 1
            msg = (
                f"{component_count} component sheets + 1 Content Details sheet "
                f"created ({result.path.name})"
            )
        else:
            msg = f"{total_sheets} sheets created ({result.path.name})"
        self.status_message.emit(msg)
        self._next_btn.setEnabled(True)
        self._save_copy_btn.setEnabled(True)

    def _on_save_copy(self) -> None:
        """Write an additional copy of the organised workbook elsewhere.

        Useful for keeping a backup or sharing without disturbing the
        ``organized_xlsx_path`` that subsequent phases rely on.
        """
        if self._state.document is None:
            self.warn("Convert the document first before saving a copy.")
            return
        suggested_name = self.default_save_name("organized")
        path = self.pick_save_file(
            "Save additional copy as", "Excel files (*.xlsx)", suggested_name
        )
        if not path:
            return
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        self.status_message.emit(f"Saving copy to {path} ...")
        worker = ExportExcelWorker(self._state.document, path, self)
        worker.finished_ok.connect(
            lambda _result: self.status_message.emit(f"Copy saved: {path}")
        )
        worker.failed.connect(lambda msg: self.error(msg, "Save copy failed"))
        worker.start()

    def _populate_details(self, result) -> None:
        # Re-derive Content Details from the in-memory document so we don't
        # have to re-open the file we just wrote.
        doc = self._state.document
        if doc is None:
            return
        groups: dict[str, int] = {}
        for entry in doc.entries:
            groups[entry.logical_sheet_name] = groups.get(entry.logical_sheet_name, 0) + 1

        self._details.setRowCount(len(groups))
        for r, (logical, count) in enumerate(groups.items()):
            saved_as = result.sheet_name_map.get(logical, logical)
            comp, _, status = logical.partition("_")
            self._details.setItem(r, 0, QTableWidgetItem(logical))
            self._details.setItem(r, 1, QTableWidgetItem(saved_as))
            self._details.setItem(r, 2, QTableWidgetItem(comp))
            self._details.setItem(r, 3, QTableWidgetItem(status))
            self._details.setItem(r, 4, QTableWidgetItem(f"{count:,}"))
        self._details.resizeColumnsToContents()

    def _populate_details_from_doc(self, doc) -> None:
        """Populate Content Details table from a loaded document (no export result needed)."""
        if doc is None:
            return
        groups: dict[str, int] = {}
        translated_groups: dict[str, int] = {}
        for entry in doc.entries:
            sheet = entry.logical_sheet_name
            groups[sheet] = groups.get(sheet, 0) + 1
            if entry.translation.strip():
                translated_groups[sheet] = translated_groups.get(sheet, 0) + 1

        self._details.setRowCount(len(groups))
        for r, (logical, count) in enumerate(groups.items()):
            comp, _, status = logical.partition("_")
            translated = translated_groups.get(logical, 0)
            trans_status = "Translated" if translated == count else (
                "Untranslated" if translated == 0 else "Mixed"
            )
            self._details.setItem(r, 0, QTableWidgetItem(logical))
            self._details.setItem(r, 1, QTableWidgetItem(logical))
            self._details.setItem(r, 2, QTableWidgetItem(comp))
            self._details.setItem(r, 3, QTableWidgetItem(trans_status))
            self._details.setItem(r, 4, QTableWidgetItem(f"{count:,}"))
        self._details.resizeColumnsToContents()

    def _on_load_existing(self) -> None:
        path = self.pick_open_file("Select organised workbook", "Excel files (*.xlsx)")
        if not path:
            return
        if not self.check_workflow_override(path):
            return
        self.status_message.emit(f"Loading {path.name} ...")
        worker = ImportExcelWorker(
            path,
            language=self._state.target_language_name,
            language_code=self._state.target_language_code,
            parent=self,
        )
        worker.finished_ok.connect(lambda doc: self._on_loaded(doc, path))
        worker.failed.connect(lambda msg: self.error(msg, "Load failed"))
        worker.start()

    def _on_loaded(self, doc, path: Path) -> None:
        self._state.document = doc
        self._state.organized_xlsx_path = path
        self._state.output_dir = path.parent
        # Clear source_stf_path: the document no longer comes from Phase 1's STF.
        # This signals that an override occurred (used by Reset Current Phase).
        self._state.source_stf_path = None

        # Set active workflow context so subsequent loads trigger override dialog.
        self._state.set_active_workflow_context(
            document=doc,
            original_source_path=path,
            current_working_path=path,
            current_working_artifact_type="organized_excel",
            start_phase=1,
            current_phase=1,
            override_existing=False,
            reset_downstream=False,
        )

        # Clear downstream snapshots and take Phase 2 snapshot
        for i in range(1, 6):
            self._state.phase_snapshots[i] = None
        self._state.phase_snapshots[1] = PhaseSnapshot(
            source_path=path,
            artifact_type="organized_excel",
            row_count=len(doc.entries),
            target_language_code=self._state.target_language_code,
            target_language_name=self._state.target_language_name,
            timestamp=time.time(),
        )

        # Auto-detect source language from labels
        self._detect_source_language(doc)

        self.on_enter()

        # Populate Content Details table from the loaded document
        self._populate_details_from_doc(doc)

        self.status_message.emit(f"Loaded {len(doc.entries):,} rows from {path.name}")
        self._next_btn.setEnabled(True)
        self.action_recorded.emit(f"Load Excel ({path.name})")

    def _detect_source_language(self, doc) -> None:
        """Run language detection on labels and update state with suggestion."""
        try:
            from ...lang_detect import (
                CONFIDENCE_THRESHOLD,
                detect_source_language,
                map_detected_to_salesforce,
            )
            from ...languages import language_for_code
        except ImportError:
            return

        labels = [e.label for e in doc.entries if e.label]
        detected = detect_source_language(labels)
        if not detected:
            return

        iso_code, confidence = detected[0]
        if confidence < CONFIDENCE_THRESHOLD:
            return

        sf_code = map_detected_to_salesforce(iso_code)
        if sf_code:
            lang_name = language_for_code(sf_code) or iso_code
            self._state.source_language_code = sf_code
            self._state.source_language_name = lang_name
            self._summary_label.setText(
                self._summary_label.text()
                + f" | Source: {lang_name} ({confidence * 100:.0f}%)"
            )

    # ------------------------------------------------------------------ continue to Phase 3

    def _on_continue_to_phase3(self) -> None:
        self._state.set_phase(1, PhaseStatus.DONE)
        self.request_navigate.emit(2)

    # ------------------------------------------------------------------ pop-out details

    def reset_page(self) -> None:
        """Called by Reset Session to clear all displayed widgets back to defaults."""
        self._summary_label.setText("No document loaded yet \u2014 complete Phase 1 first.")
        self._details.setRowCount(0)
        self._save_copy_btn.setEnabled(False)
        self._next_btn.setEnabled(False)

    def _on_popout_details(self) -> None:
        if hasattr(self, '_details_dialog') and self._details_dialog is not None:
            self._details_dialog.raise_()
            self._details_dialog.activateWindow()
            return
        self._details_dialog = QDialog(self)
        self._details_dialog.setWindowTitle("Content Details")
        from .base import clamp_to_screen
        clamp_to_screen(self._details_dialog, 800, 500)
        self._details_dialog.setWindowFlags(
            self._details_dialog.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        layout = QVBoxLayout(self._details_dialog)
        self._details.setParent(self._details_dialog)
        layout.addWidget(self._details)
        self._details_dialog.finished.connect(self._on_details_dialog_closed)
        self._details_dialog.show()

    def _on_details_dialog_closed(self) -> None:
        self._details.setParent(self._details_box)
        self._details_layout.addWidget(self._details)
        self._details_dialog = None
