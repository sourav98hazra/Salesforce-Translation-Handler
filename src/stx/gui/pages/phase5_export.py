"""Phase 5 -- Export the three STF files for Salesforce import."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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
from ..state import AppState
from ..workers import WriteStfWorker
from .base import PhasePage, make_action_row


class Phase5ExportPage(PhasePage):
    """Validate and emit the three STF files."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 5 \u2014 Export STF",
            subtitle=(
                "Run pre-import validation and emit the three Salesforce STF "
                "files (full / translated-only / untranslated-only). The "
                "files are UTF-8 with LF line endings, byte-compatible with "
                "the legacy ExcelToSTFV2 script."
            ),
            parent=parent,
        )
        self._build()

    def _build(self) -> None:
        # ---------- Language config (re-confirms target before export)
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

        # ---------- Output dir
        path_box = QGroupBox("Output directory")
        path_layout = QHBoxLayout(path_box)
        self._dir_field = QLineEdit()
        self._dir_field.setPlaceholderText("Where to write the three .stf files ...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._on_browse_dir)
        path_layout.addWidget(self._dir_field, stretch=1)
        path_layout.addWidget(browse)
        self.add_widget(path_box)

        # ---------- Validation panel
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
        self.add_widget(self._issues_table, stretch=1)

        # ---------- Action buttons
        self._export_btn = QPushButton("Export 3 STF files")
        self._export_btn.setStyleSheet("QPushButton { background:#2563eb; color:white; padding:6px 16px; border-radius:6px; }")
        self._export_btn.clicked.connect(self._on_export)
        self.add_layout(make_action_row(self._export_btn))

        # ---------- Result
        self._result_table = QTableWidget(0, 2)
        self._result_table.setHorizontalHeaderLabels(["File", "Size"])
        self._result_table.horizontalHeader().setStretchLastSection(True)
        self._result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.add_widget(self._result_table)

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        # Pre-fill language from prior phases.
        if self._state.target_language_name in LANGUAGE_NAME_TO_CODE:
            self._lang_combo.setCurrentText(self._state.target_language_name)
        if self._state.target_language_code:
            self._code_field.setText(self._state.target_language_code)
        if not self._dir_field.text() and self._state.output_dir:
            self._dir_field.setText(str(self._state.output_dir))
        self._export_btn.setEnabled(self._state.document is not None)
        self._validate_btn.setEnabled(self._state.document is not None)

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
        for r, issue in enumerate(report.issues):
            sev_item = QTableWidgetItem(issue.severity.upper())
            colors = {"error": "#dc2626", "warning": "#d97706", "info": "#2563eb"}
            sev_item.setForeground(Qt.GlobalColor.white)
            from PySide6.QtGui import QBrush, QColor
            sev_item.setBackground(QBrush(QColor(colors.get(issue.severity, "#4a5568"))))
            self._issues_table.setItem(r, 0, sev_item)
            self._issues_table.setItem(r, 1, QTableWidgetItem(issue.category))
            self._issues_table.setItem(r, 2, QTableWidgetItem(issue.key))
            self._issues_table.setItem(r, 3, QTableWidgetItem(issue.message))
        self._issues_table.resizeColumnsToContents()
        self._validation_summary.setText(
            f"{len(report.errors)} error(s), {len(report.warnings)} warning(s) "
            f"across {len(report.issues)} issue(s)."
        )

    def _on_export(self) -> None:
        if self._state.document is None:
            return
        dir_text = self._dir_field.text().strip()
        if not dir_text:
            self.warn("Choose an output directory first.")
            return
        out_dir = Path(dir_text)

        lang_name = self._lang_combo.currentText()
        lang_code = self._code_field.text().strip() or code_for_language(lang_name) or "xx"

        self.status_message.emit(f"Writing STF files to {out_dir} ...")
        worker = WriteStfWorker(self._state.document, out_dir, lang_name, lang_code, self)
        worker.finished_ok.connect(self._on_exported)
        worker.failed.connect(lambda msg: self.error(msg, "Export failed"))
        worker.start()

    def _on_exported(self, res) -> None:
        files = res.as_list()
        self._result_table.setRowCount(len(files))
        for r, path in enumerate(files):
            self._result_table.setItem(r, 0, QTableWidgetItem(str(path)))
            self._result_table.setItem(r, 1, QTableWidgetItem(f"{path.stat().st_size:,} B"))
        self._result_table.resizeColumnsToContents()
        self._state.output_dir = res.full.parent
        self.status_message.emit(f"STF files written to {res.full.parent}")
        self.info(
            f"STF export complete:\n  - {res.full.name}\n  - {res.translated_only.name}\n  - {res.untranslated_only.name}",
            "Export complete",
        )
