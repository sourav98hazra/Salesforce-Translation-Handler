"""Phase 5 -- Validate & Fix.

This is a **dedicated validation phase** that shows *only* the rows with
issues.  The user can:

* See all errors/warnings in one focused table (no noise from clean rows).
* Click **"Auto-fix all"** to let the deterministic fixers resolve what
  they can (placeholder restoration, length trimming, dedup, etc.).
* Click **"Auto-fix selected"** to fix only the highlighted rows.
* **Inline-edit** the Translation column directly in the issues table.
* Click **"Re-validate"** after fixes to confirm issues are resolved.
* Double-click a row to **jump back to Phase 4** for full context editing.
* **Save** the fixed workbook at any time.

Once there are zero errors the user can proceed to Phase 6 (Export STF).
Warnings are surfaced but don't block export.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...autofix import auto_fix_document, auto_fix_entry
from ...model import Entry
from ...validate import ValidationIssue, ValidationReport, validate_document
from ..state import AppState, PhaseStatus
from ..workers import ExportExcelWorker, WriteAuditSheetsWorker
from .base import PhasePage, make_action_row, primary


class Phase5ValidatePage(PhasePage):
    """Dedicated validation and auto-fix phase."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 5 \u2014 Validate & Fix",
            subtitle=(
                "Only rows with validation issues are shown below.  Use "
                "'Auto-fix all' to let the app repair what it can "
                "(placeholder restoration, length trimming, deduplication), "
                "then re-validate to confirm.  You can also inline-edit any "
                "row or double-click to jump back to Phase 4 for full context."
            ),
            parent=parent,
        )
        self._issues: List[ValidationIssue] = []
        self._report: Optional[ValidationReport] = None
        self._build()

    def _build(self) -> None:
        # ---------- Summary banner
        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            "padding: 10px; border-radius: 6px; font-weight: 600;"
        )
        self.add_widget(self._banner)

        # ---------- Action buttons row (kept compact: 4 buttons max)
        self._load_btn = QPushButton("Load Excel...")
        self._load_btn.setToolTip(
            "Load any organised / translated / reviewed Excel directly into "
            "this phase.  Validation runs automatically after the load."
        )
        self._load_btn.clicked.connect(self._on_load_excel)
        self._validate_btn = QPushButton("Re-validate")
        self._validate_btn.clicked.connect(self._on_validate)
        self._fix_all_btn = primary(QPushButton("Auto-fix all"))
        self._fix_all_btn.setToolTip(
            "Apply every safe fixer to every issue.  Use 'Auto-fix this row' "
            "in the editor below for finer control."
        )
        self._fix_all_btn.clicked.connect(self._on_fix_all)
        self._save_btn = QPushButton("Save (.xlsx)")
        self._save_btn.clicked.connect(self._on_save)

        actions = make_action_row(
            self._load_btn,
            self._validate_btn,
            self._fix_all_btn,
            self._save_btn,
        )
        self.add_layout(actions)

        # ---------- Splitter: issues table (top) + inline editor (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Issues table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels([
            "Severity", "Category", "Key", "Label", "Translation", "Message",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self._table.currentCellChanged.connect(self._on_current_row_changed)
        splitter.addWidget(self._table)

        # Inline editor for the selected issue row
        editor_box = QGroupBox("Edit selected row")
        editor_layout = QVBoxLayout(editor_box)

        meta_row = QHBoxLayout()
        self._key_label = QLineEdit()
        self._key_label.setReadOnly(True)
        self._key_label.setStyleSheet("font-family: monospace;")
        meta_row.addWidget(QLabel("Key:"))
        meta_row.addWidget(self._key_label, stretch=1)
        self._issue_label = QLabel("")
        self._issue_label.setStyleSheet("color: #991b1b; font-weight: 600;")
        meta_row.addWidget(self._issue_label, stretch=2)
        editor_layout.addLayout(meta_row)

        fields_row = QHBoxLayout()
        src_col = QVBoxLayout()
        src_col.addWidget(QLabel("Source label (read-only)"))
        self._src_field = QPlainTextEdit()
        self._src_field.setReadOnly(True)
        src_col.addWidget(self._src_field)
        fields_row.addLayout(src_col, stretch=1)

        tgt_col = QVBoxLayout()
        tgt_col.addWidget(QLabel("Translation (editable)"))
        self._tgt_field = QPlainTextEdit()
        tgt_col.addWidget(self._tgt_field)
        fields_row.addLayout(tgt_col, stretch=1)

        editor_layout.addLayout(fields_row)

        edit_actions = QHBoxLayout()
        self._apply_btn = primary(QPushButton("Apply edit"))
        self._apply_btn.clicked.connect(self._on_apply_edit)
        self._fix_row_btn = QPushButton("Auto-fix this row")
        self._fix_row_btn.clicked.connect(self._on_fix_current_row)
        self._jump_btn = QPushButton("Jump to Phase 4 for context")
        self._jump_btn.clicked.connect(self._on_jump_to_review)
        edit_actions.addWidget(self._apply_btn)
        edit_actions.addWidget(self._fix_row_btn)
        edit_actions.addWidget(self._jump_btn)
        edit_actions.addStretch(1)
        editor_layout.addLayout(edit_actions)

        splitter.addWidget(editor_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.add_widget(splitter, stretch=1)

        # ---------- Bottom: next phase
        self._next_btn = QPushButton("Continue to Phase 6 (Export STF) \u2192")
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(5))
        self.add_layout(make_action_row(self._next_btn))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.document is None:
            self._banner.setText("No document loaded.  Complete earlier phases first.")
            self._banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #f1f5f9; color: #475569;"
            )
            self._banner.setVisible(True)
            self._fix_all_btn.setEnabled(False)
            self._fix_selected_btn.setEnabled(False)
            self._save_btn.setEnabled(False)
            return
        self._fix_all_btn.setEnabled(True)
        self._fix_selected_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        # Auto-validate on entry.
        self._on_validate()

    # ------------------------------------------------------------------ validate

    def _on_load_excel(self) -> None:
        """Load any Excel for validation -- makes Phase 5 self-contained.

        The user can land here from the sidebar without going through
        earlier phases (e.g. they just want to validate a hand-edited
        workbook from a colleague).  Validation runs automatically after
        the load.
        """
        if self.is_busy:
            return
        path = self.pick_open_file(
            "Load Excel for validation",
            "Excel files (*.xlsx);;All files (*)",
        )
        if not path:
            return
        from ..workers import ImportExcelWorker

        self.set_busy(True)
        self.status_message.emit(f"Loading {path.name} for validation ...")
        worker = ImportExcelWorker(
            path,
            language=self._state.target_language_name,
            language_code=self._state.target_language_code,
            parent=self,
        )

        def _loaded(doc):
            self._state.document = doc
            self._state.reviewed_xlsx_path = path
            self._state.output_dir = path.parent
            self.set_busy(False)
            self.on_enter()
            self.status_message.emit(
                f"Loaded {len(doc.entries):,} rows from {path.name}; running validation."
            )
            try:
                from .. import settings as gui_settings
                gui_settings.add_recent_file(path)
            except Exception:  # noqa: BLE001
                pass

        worker.finished_ok.connect(_loaded)
        worker.failed.connect(lambda msg: (self.set_busy(False), self.error(msg, "Load failed")))
        worker.start()

    def _on_validate(self) -> None:
        if self._state.document is None:
            return
        self._report = validate_document(self._state.document)
        self._issues = list(self._report.issues)
        self._render_issues()
        self._update_banner()
        self.status_message.emit(
            f"Validation: {len(self._report.errors)} error(s), "
            f"{len(self._report.warnings)} warning(s)."
        )

    def _update_banner(self) -> None:
        if self._report is None:
            return
        if not self._report.issues:
            self._banner.setText(
                "\u2713  All clear \u2014 no validation issues.  "
                "You can proceed to export."
            )
            self._banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #dcfce7; color: #166534; border: 1px solid #86efac;"
            )
        elif self._report.has_errors:
            self._banner.setText(
                f"\u26a0  {len(self._report.errors)} error(s) must be fixed "
                f"before Salesforce import.  {len(self._report.warnings)} warning(s) "
                f"are advisory.  Use 'Auto-fix all' or edit rows below."
            )
            self._banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;"
            )
        else:
            self._banner.setText(
                f"\u26a0  {len(self._report.warnings)} warning(s) found (advisory).  "
                f"No errors.  Safe to export."
            )
            self._banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #fef3c7; color: #92400e; border: 1px solid #fbbf24;"
            )
        self._banner.setVisible(True)

    def _render_issues(self) -> None:
        sev_colors = {
            "error": ("#dc2626", "#ffffff"),
            "warning": ("#d97706", "#ffffff"),
            "info": ("#2563eb", "#ffffff"),
        }
        self._table.setRowCount(len(self._issues))
        for r, issue in enumerate(self._issues):
            # Severity (colored)
            sev_item = QTableWidgetItem(issue.severity.upper())
            bg, fg = sev_colors.get(issue.severity, ("#4a5568", "#ffffff"))
            sev_item.setBackground(QBrush(QColor(bg)))
            sev_item.setForeground(QBrush(QColor(fg)))
            sev_item.setFlags(sev_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 0, sev_item)

            # Category
            cat_item = QTableWidgetItem(issue.category)
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 1, cat_item)

            # Key
            key_item = QTableWidgetItem(issue.key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 2, key_item)

            # Label + Translation (from document)
            entry = self._find_entry(issue.key)
            label_item = QTableWidgetItem(entry.label if entry else "")
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 3, label_item)

            trans_item = QTableWidgetItem(entry.translation if entry else "")
            trans_item.setFlags(trans_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 4, trans_item)

            # Message
            msg_item = QTableWidgetItem(issue.message)
            msg_item.setFlags(msg_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 5, msg_item)

        self._table.resizeColumnsToContents()
        # Cap key and message columns to reasonable widths.
        if self._table.columnWidth(2) > 300:
            self._table.setColumnWidth(2, 300)
        if self._table.columnWidth(5) > 500:
            self._table.setColumnWidth(5, 500)

    def _find_entry(self, key: str) -> Optional[Entry]:
        if self._state.document is None:
            return None
        for e in self._state.document.entries:
            if e.key == key:
                return e
        return None

    # ------------------------------------------------------------------ auto-fix

    def _on_fix_all(self) -> None:
        if self._state.document is None:
            return
        if not self.confirm(
            "Auto-fix will attempt to:\n"
            "  \u2022 Restore missing placeholders / MessageFormat tokens\n"
            "  \u2022 Trim translations exceeding length limits\n"
            "  \u2022 Remove duplicate keys (keeps last occurrence)\n"
            "  \u2022 Clear whitespace-only translations\n"
            "  \u2022 Restore missing HTML tags\n\n"
            "Proceed?"
        ):
            return
        report = auto_fix_document(self._state.document)
        self.status_message.emit(
            f"Auto-fix complete: {report.fixed_count} fix(es) applied."
        )
        if report.fixed_count > 0:
            self.info(
                f"Applied {report.fixed_count} fix(es).\n\n"
                + "\n".join(f"  \u2022 {key}: {desc}" for key, desc in report.details[:20])
                + ("\n  ..." if len(report.details) > 20 else ""),
                "Auto-fix results",
            )
        # Re-validate to update the table.
        self._on_validate()

    def _on_fix_selected(self) -> None:
        if self._state.document is None:
            return
        selected_rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        if not selected_rows:
            self.warn("Select one or more rows to fix.")
            return
        fixed_count = 0
        for row_idx in selected_rows:
            if row_idx >= len(self._issues):
                continue
            issue = self._issues[row_idx]
            entry = self._find_entry(issue.key)
            if entry is None:
                continue
            fixed_entry, descriptions = auto_fix_entry(entry)
            if descriptions:
                self._replace_entry(issue.key, fixed_entry)
                fixed_count += 1
        self.status_message.emit(f"Fixed {fixed_count} of {len(selected_rows)} selected row(s).")
        self._on_validate()

    def _on_fix_current_row(self) -> None:
        """Fix the single row currently shown in the inline editor."""
        current = self._table.currentRow()
        if current < 0 or current >= len(self._issues):
            return
        issue = self._issues[current]
        entry = self._find_entry(issue.key)
        if entry is None:
            return
        fixed_entry, descriptions = auto_fix_entry(entry)
        if descriptions:
            self._replace_entry(issue.key, fixed_entry)
            self._tgt_field.setPlainText(fixed_entry.translation)
            self.status_message.emit(f"Fixed: {'; '.join(descriptions)}")
            self._on_validate()
        else:
            self.status_message.emit("Auto-fix could not resolve this issue.  Please fix manually.")

    def _replace_entry(self, key: str, new_entry: Entry) -> None:
        """Replace the first entry matching ``key`` in the document."""
        if self._state.document is None:
            return
        for i, e in enumerate(self._state.document.entries):
            if e.key == key:
                self._state.document.entries[i] = new_entry
                return

    # ------------------------------------------------------------------ inline editor

    def _on_current_row_changed(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if row < 0 or row >= len(self._issues):
            return
        issue = self._issues[row]
        entry = self._find_entry(issue.key)
        self._key_label.setText(issue.key)
        self._issue_label.setText(f"[{issue.severity.upper()}] {issue.message}")
        if entry:
            self._src_field.setPlainText(entry.label)
            self._tgt_field.setPlainText(entry.translation)
        else:
            self._src_field.clear()
            self._tgt_field.clear()

    def _on_apply_edit(self) -> None:
        """Apply the user's manual edit from the inline editor back to the document."""
        current = self._table.currentRow()
        if current < 0 or current >= len(self._issues):
            return
        issue = self._issues[current]
        new_translation = self._tgt_field.toPlainText()
        if self._state.document is None:
            return
        for i, e in enumerate(self._state.document.entries):
            if e.key == issue.key:
                self._state.document.entries[i] = Entry(
                    key=e.key, label=e.label, translation=new_translation
                )
                break
        # Update the table cell visually.
        trans_item = self._table.item(current, 4)
        if trans_item:
            trans_item.setText(new_translation)
        self.status_message.emit(f"Applied manual edit for {issue.key}.")

    # ------------------------------------------------------------------ jump

    def _on_jump_to_review(self) -> None:
        """Jump to Phase 4 (Review) focused on the currently selected issue's key."""
        current = self._table.currentRow()
        if current < 0 or current >= len(self._issues):
            return
        key = self._issues[current].key
        self.request_jump_to_row.emit(key)

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        """Double-click jumps back to Phase 4 (Review) focused on this key."""
        if row < 0 or row >= len(self._issues):
            return
        key = self._issues[row].key
        self.request_jump_to_row.emit(key)

    # ------------------------------------------------------------------ save

    def _on_save(self) -> None:
        if self._state.document is None or self.is_busy:
            return
        path = self.pick_save_file("Save fixed workbook as", "Excel files (*.xlsx)", "fixed.xlsx")
        if not path:
            return
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        self.set_busy(True)
        self.status_message.emit(f"Saving fixed workbook -> {path}")
        worker = ExportExcelWorker(self._state.document, path, self)

        def _then_audit(_result):
            if self._state.translation_summaries or self._state.translation_statuses:
                audit = WriteAuditSheetsWorker(
                    path,
                    self._state.translation_summaries,
                    self._state.translation_statuses,
                    parent=self,
                )
                audit.finished_ok.connect(lambda _: self._on_saved(path))
                audit.failed.connect(lambda msg: self._on_save_failed(msg))
                audit.start()
            else:
                self._on_saved(path)

        worker.finished_ok.connect(_then_audit)
        worker.failed.connect(lambda msg: self._on_save_failed(msg))
        worker.start()

    def _on_saved(self, path: Path) -> None:
        self._state.reviewed_xlsx_path = path
        self._state.output_dir = path.parent
        self._state.set_phase(4, PhaseStatus.DONE)
        self.set_busy(False)
        self.status_message.emit(f"Fixed workbook saved: {path}")
        try:
            from .. import settings as gui_settings
            gui_settings.add_recent_file(path)
        except Exception:  # noqa: BLE001
            pass

    def _on_save_failed(self, message: str) -> None:
        self.set_busy(False)
        self._state.set_phase(4, PhaseStatus.ERROR)
        self.error(message, "Save failed")
