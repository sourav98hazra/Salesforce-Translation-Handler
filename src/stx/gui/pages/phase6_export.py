"""Phase 6 -- Export STF.

v1.2 redesign: the export phase now has its own **Load Excel** button so
users who bypassed earlier phases (e.g. they translated externally and
just want to convert to STF) can load their workbook directly here and
export without touching Phases 1-5.

Flow for users who went through the full pipeline:
    The document is already in memory from Phase 4/5 -- they just pick
    language, output dir, and click Export.

Flow for "direct convert" users:
    They click "Load translated Excel...", pick language/code, and Export.
    If they haven't validated, that's on them (documented in the subtitle).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...languages import LANGUAGE_NAME_TO_CODE, code_for_language, supported_language_names
from ...validate import validate_document
from ..state import AppState, PhaseStatus
from ..workers import ImportExcelWorker, WriteStfWorker
from .base import PhasePage, make_action_row, primary


class Phase6ExportPage(PhasePage):
    """Export the three STF files for Salesforce import.

    Supports two entry paths:
    1. Document already loaded from earlier phases.
    2. User loads a translated Excel directly here ("direct convert").
    """

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 6 \u2014 Export STF",
            subtitle=(
                "Emit the three STF files Salesforce expects (full / "
                "translated-only / untranslated-only).  If you have a "
                "translated Excel from an external source, you can load "
                "it directly here and convert -- the app trusts that you "
                "have validated it yourself."
            ),
            parent=parent,
        )
        self._build()

    def _build(self) -> None:
        # ---------- Load Excel (direct convert path)
        load_box = QGroupBox("Load translated Excel (direct convert)")
        load_layout = QHBoxLayout(load_box)
        self._load_btn = QPushButton("Load translated Excel (.xlsx)...")
        self._load_btn.setToolTip(
            "Load any organised/translated Excel and convert it to STF "
            "without going through earlier phases.  Validation is not "
            "run automatically -- if you want to check, go back to Phase 5."
        )
        self._load_btn.clicked.connect(self._on_load_excel)
        load_layout.addWidget(self._load_btn)
        self._load_status = QLabel("Or use the document already loaded from previous phases.")
        self._load_status.setStyleSheet("color: #4a5568;")
        load_layout.addWidget(self._load_status, stretch=1)
        self.add_widget(load_box)

        # ---------- Language config (compact row, no group box)
        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        lang_row.addWidget(QLabel("Target:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(supported_language_names())
        self._lang_combo.currentTextChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self._lang_combo)
        lang_row.addSpacing(12)
        lang_row.addWidget(QLabel("Code:"))
        self._code_field = QLineEdit()
        self._code_field.setMaximumWidth(120)
        lang_row.addWidget(self._code_field)
        lang_row.addStretch(1)
        self.add_layout(lang_row)

        # ---------- Quick validation summary (optional, not blocking)
        validate_box = QGroupBox("Quick validation check (optional)")
        v_layout = QHBoxLayout(validate_box)
        self._validate_btn = QPushButton("Run validation")
        self._validate_btn.clicked.connect(self._on_validate)
        v_layout.addWidget(self._validate_btn)
        self._validation_summary = QLabel("Not run.  Click to check before exporting.")
        self._validation_summary.setStyleSheet("color: #4a5568;")
        v_layout.addWidget(self._validation_summary, stretch=1)
        self.add_widget(validate_box)

        # ---------- Export button
        self._export_btn = primary(QPushButton("Export 3 STF files"))
        self._export_btn.clicked.connect(self._on_export)
        self.add_layout(make_action_row(self._export_btn))

        # ---------- Result table (no group box wrapper, pop-out inline)
        result_header_row = QHBoxLayout()
        result_header_row.addWidget(QLabel("Export results"))
        result_header_row.addStretch(1)

        self._popout_results_btn = QPushButton("\u2197")
        self._popout_results_btn.setFixedSize(20, 20)
        self._popout_results_btn.setToolTip("Pop out into a separate window")
        self._popout_results_btn.setStyleSheet("font-size: 12px; padding: 0; border: none; background: transparent; color: #64748b;")
        self._popout_results_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._popout_results_btn.clicked.connect(self._on_popout_results)
        result_header_row.addWidget(self._popout_results_btn)
        self.add_layout(result_header_row)

        self._result_table = QTableWidget(0, 2)
        self._result_table.setHorizontalHeaderLabels(["File", "Size"])
        self._result_table.horizontalHeader().setStretchLastSection(True)
        self._result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.add_widget(self._result_table)

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.target_language_name in LANGUAGE_NAME_TO_CODE:
            self._lang_combo.setCurrentText(self._state.target_language_name)
        if self._state.target_language_code:
            self._code_field.setText(self._state.target_language_code)

        has_doc = self._state.document is not None
        self._export_btn.setEnabled(has_doc and not self.is_busy)
        self._validate_btn.setEnabled(has_doc and not self.is_busy)

        if has_doc:
            stats = self._state.document.stats()
            self._load_status.setText(
                f"Document loaded: {stats['total']:,} rows "
                f"({stats['translated']:,} translated).  Ready to export."
            )
        else:
            self._load_status.setText(
                "No document loaded.  Use 'Load translated Excel' or complete earlier phases."
            )

    # ------------------------------------------------------------------ load Excel (direct convert)

    def _on_load_excel(self) -> None:
        if self.is_busy:
            return
        path = self.pick_open_file(
            "Load translated Excel for direct STF export",
            "Excel files (*.xlsx);;All files (*)",
        )
        if not path:
            return
        self.set_busy(True)
        self.status_message.emit(f"Loading {path.name} for direct export ...")
        worker = ImportExcelWorker(
            path,
            language=self._lang_combo.currentText(),
            language_code=self._code_field.text().strip() or None,
            parent=self,
        )
        worker.finished_ok.connect(lambda doc: self._on_excel_loaded(doc, path))
        worker.failed.connect(lambda msg: self._on_load_failed(msg))
        worker.start()

    def _on_excel_loaded(self, doc, path: Path) -> None:
        self._state.document = doc
        self._state.reviewed_xlsx_path = path
        self._state.output_dir = path.parent
        self.set_busy(False)
        self.on_enter()
        self.status_message.emit(
            f"Loaded {len(doc.entries):,} rows from {path.name}.  "
            f"Ready for direct STF export."
        )
        try:
            from .. import settings as gui_settings
            gui_settings.add_recent_file(path)
        except Exception:  # noqa: BLE001
            pass

    def _on_load_failed(self, msg: str) -> None:
        self.set_busy(False)
        self.error(msg, "Load failed")

    # ------------------------------------------------------------------ language

    def _on_lang_changed(self, name: str) -> None:
        code = code_for_language(name)
        if code:
            self._code_field.setText(code)
            self._state.target_language_name = name
            self._state.target_language_code = code

    # ------------------------------------------------------------------ validate (optional)

    def _on_validate(self) -> None:
        if self._state.document is None:
            return
        report = validate_document(self._state.document)
        if not report.issues:
            self._validation_summary.setText(
                "\u2713  No issues.  Safe to export."
            )
            self._validation_summary.setStyleSheet("color: #166534; font-weight: 600;")
        else:
            self._validation_summary.setText(
                f"\u26a0  {len(report.errors)} error(s), {len(report.warnings)} warning(s).  "
                f"Export will proceed anyway (Salesforce may reject some rows on import)."
            )
            style = "color: #92400e; font-weight: 600;"
            if report.has_errors:
                style = "color: #991b1b; font-weight: 600;"
            self._validation_summary.setStyleSheet(style)

    # ------------------------------------------------------------------ export

    def _on_export(self) -> None:
        if self._state.document is None or self.is_busy:
            return
        # Open directory picker on each export click
        out_dir = self.pick_directory("Choose output directory for STF files")
        if not out_dir:
            return

        lang_name = self._lang_combo.currentText()
        lang_code = self._code_field.text().strip() or code_for_language(lang_name) or "xx"

        self.set_busy(True)
        self._state.set_phase(5, PhaseStatus.RUNNING)
        self.status_message.emit(f"Writing STF files to {out_dir} ...")
        worker = WriteStfWorker(self._state.document, out_dir, lang_name, lang_code, self)
        worker.finished_ok.connect(self._on_exported)
        worker.failed.connect(lambda msg: self._on_export_failed(msg))
        worker.start()

    def _on_exported(self, res) -> None:
        files = res.as_list()
        self._result_table.setRowCount(len(files))
        for r, path in enumerate(files):
            self._result_table.setItem(r, 0, QTableWidgetItem(str(path)))
            self._result_table.setItem(r, 1, QTableWidgetItem(f"{path.stat().st_size:,} B"))
        self._result_table.resizeColumnsToContents()
        self._state.output_dir = res.full.parent
        self._state.set_phase(5, PhaseStatus.DONE)
        self.set_busy(False)
        self.status_message.emit(f"STF files written to {res.full.parent}")
        self.info(
            f"STF export complete:\n"
            f"  \u2022 {res.full.name}\n"
            f"  \u2022 {res.translated_only.name}\n"
            f"  \u2022 {res.untranslated_only.name}",
            "Export complete",
        )
        try:
            from .. import settings as gui_settings
            gui_settings.remember_output_dir(res.full.parent)
            gui_settings.add_recent_file(res.full)
        except Exception:  # noqa: BLE001
            pass

    def _on_export_failed(self, message: str) -> None:
        self.set_busy(False)
        self._state.set_phase(5, PhaseStatus.ERROR)
        self.error(message, "Export failed")

    # ------------------------------------------------------------------ pop-out results

    def _on_popout_results(self) -> None:
        if hasattr(self, '_results_dialog') and self._results_dialog is not None:
            self._results_dialog.raise_()
            return
        self._results_dialog = QDialog(self)
        self._results_dialog.setWindowTitle("Export Results")
        self._results_dialog.resize(700, 300)
        self._results_dialog.setWindowFlags(
            self._results_dialog.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        layout = QVBoxLayout(self._results_dialog)
        self._result_table.setParent(self._results_dialog)
        layout.addWidget(self._result_table)
        self._results_dialog.finished.connect(self._on_results_dialog_closed)
        self._results_dialog.show()
        self._popout_results_btn.setText("\u2199")
        self._popout_results_btn.setToolTip("Dock back into the page")
        self._popout_results_btn.clicked.disconnect()
        self._popout_results_btn.clicked.connect(self._on_dock_results_back)

    def _on_dock_results_back(self) -> None:
        if hasattr(self, '_results_dialog') and self._results_dialog is not None:
            self._results_dialog.close()

    def _on_results_dialog_closed(self) -> None:
        self._result_table.setParent(self)
        # Re-add to main layout (after the header row)
        self.layout().addWidget(self._result_table)
        self._results_dialog = None
        self._popout_results_btn.setText("\u2197")
        self._popout_results_btn.setToolTip("Pop out into a separate window")
        self._popout_results_btn.clicked.disconnect()
        self._popout_results_btn.clicked.connect(self._on_popout_results)
