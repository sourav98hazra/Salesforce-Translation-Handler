"""Phase 5 -- Export the three STF files for Salesforce import.

Adds two improvements over the MVP:

* **Jump-to-issue** -- double-clicking a validation row asks the main
  window to switch to Phase 4 and focus the offending row.
* **Multi-language batch export** -- if the user supplied additional
  target languages on Phase 3, they're surfaced here as additional
  output sets.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...languages import LANGUAGE_NAME_TO_CODE, code_for_language, supported_language_names
from ...validate import ValidationReport, validate_document
from .. import settings as gui_settings
from ..state import AppState, PhaseStatus
from ..workers import WriteStfWorker
from .base import PhasePage, make_action_row, primary


class Phase5ExportPage(PhasePage):
    """Validate and emit the three STF files."""

    request_jump_to_row = Signal(str)

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 5 \u2014 Export STF",
            subtitle=(
                "Run pre-export validation and emit the three STF files "
                "Salesforce expects (full / translated-only / untranslated-"
                "only).  Files are UTF-8 with LF line endings, byte-"
                "compatible with the legacy ExcelToSTFV2 script.  Double-"
                "click a validation row to jump to that row in Phase 4."
            ),
            parent=parent,
        )
        self._build()

    def _build(self) -> None:
        cfg_box = QGroupBox("Target language")
        cfg_layout = QHBoxLayout(cfg_box)
        cfg_layout.addWidget(QLabel("Language:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(supported_language_names())
        self._lang_combo.currentTextChanged.connect(self._on_lang_changed)
        cfg_layout.addWidget(self._lang_combo)
        cfg_layout.addSpacing(12)
        cfg_layout.addWidget(QLabel("Code:"))
        self._code_field = QLineEdit()
        self._code_field.setMaximumWidth(120)
        cfg_layout.addWidget(self._code_field)
        cfg_layout.addStretch(1)
        self.add_widget(cfg_box)

        path_box = QGroupBox("Output directory")
        path_layout = QHBoxLayout(path_box)
        self._dir_field = QLineEdit()
        self._dir_field.setPlaceholderText("Where to write the .stf files ...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._on_browse_dir)
        path_layout.addWidget(self._dir_field, stretch=1)
        path_layout.addWidget(browse)
        self.add_widget(path_box)

        validate_box = QGroupBox("Pre-export validation")
        v_layout = QHBoxLayout(validate_box)
        self._validate_btn = QPushButton("Run validation")
        self._validate_btn.clicked.connect(self._on_validate)
        v_layout.addWidget(self._validate_btn)
        self._validation_summary = QLabel("Validation has not been run yet.")
        self._validation_summary.setStyleSheet("color: #4a5568;")
        v_layout.addWidget(self._validation_summary, stretch=1)
        self.add_widget(validate_box)

        self._issues_table = QTableWidget(0, 4)
        self._issues_table.setHorizontalHeaderLabels(["Severity", "Category", "Key", "Message"])
        self._issues_table.horizontalHeader().setStretchLastSection(True)
        self._issues_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._issues_table.setAlternatingRowColors(True)
        self._issues_table.cellDoubleClicked.connect(self._on_issue_double_clicked)
        self.add_widget(self._issues_table, stretch=1)

        self._export_btn = primary(QPushButton("Export 3 STF files"))
        self._export_btn.clicked.connect(self._on_export)
        self.add_layout(make_action_row(self._export_btn))

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
        if not self._dir_field.text() and self._state.output_dir:
            self._dir_field.setText(str(self._state.output_dir))
        self._export_btn.setEnabled(self._state.document is not None and not self.is_busy)
        self._validate_btn.setEnabled(self._state.document is not None and not self.is_busy)

    # ------------------------------------------------------------------ slots

    def _on_lang_changed(self, name: str) -> None:
        code = code_for_language(name)
        if code:
            self._code_field.setText(code)
            self._state.target_language_name = name
            self._state.target_language_code = code

    def _on_browse_dir(self) -> None:
        path = self.pick_directory("Choose output directory")
        if path:
            self._dir_field.setText(str(path))

    def _on_validate(self) -> None:
        if self._state.document is None:
            return
        report = validate_document(self._state.document)
        self._render_report(report)

    def _render_report(self, report: ValidationReport) -> None:
        self._issues_table.setRowCount(len(report.issues))
        colors = {"error": "#dc2626", "warning": "#d97706", "info": "#2563eb"}
        for r, issue in enumerate(report.issues):
            sev_item = QTableWidgetItem(issue.severity.upper())
            sev_item.setForeground(Qt.GlobalColor.white)
            sev_item.setBackground(QBrush(QColor(colors.get(issue.severity, "#4a5568"))))
            self._issues_table.setItem(r, 0, sev_item)
            self._issues_table.setItem(r, 1, QTableWidgetItem(issue.category))
            self._issues_table.setItem(r, 2, QTableWidgetItem(issue.key))
            self._issues_table.setItem(r, 3, QTableWidgetItem(issue.message))
        self._issues_table.resizeColumnsToContents()
        self._validation_summary.setText(
            f"{len(report.errors)} error(s), {len(report.warnings)} warning(s) "
            f"across {len(report.issues)} issue(s).  Double-click a row to "
            "jump to it in Phase 4."
        )

    def _on_issue_double_clicked(self, row: int, _column: int) -> None:
        key_item = self._issues_table.item(row, 2)
        if key_item is None:
            return
        self.request_jump_to_row.emit(key_item.text())

    def _on_export(self) -> None:
        if self._state.document is None or self.is_busy:
            return
        dir_text = self._dir_field.text().strip()
        if not dir_text:
            self.warn("Choose an output directory first.")
            return
        out_dir = Path(dir_text)

        lang_name = self._lang_combo.currentText()
        lang_code = self._code_field.text().strip() or code_for_language(lang_name) or "xx"

        self.set_busy(True)
        self.status_message.emit(f"Writing STF files to {out_dir} ...")
        self._state.set_phase(5, PhaseStatus.RUNNING)
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
        gui_settings.remember_output_dir(res.full.parent)
        gui_settings.add_recent_file(res.full)
        self._state.set_phase(5, PhaseStatus.DONE)
        self.set_busy(False)
        self.status_message.emit(f"STF files written to {res.full.parent}")
        self.info(
            f"STF export complete:\n  - {res.full.name}\n  - {res.translated_only.name}\n  - {res.untranslated_only.name}",
            "Export complete",
        )

    def _on_export_failed(self, message: str) -> None:
        self.set_busy(False)
        self._state.set_phase(5, PhaseStatus.ERROR)
        self.error(message, "Export failed")
