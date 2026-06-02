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
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...autofix import auto_fix_document, auto_fix_entry
from ...model import Entry
from ...validate import ValidationIssue, ValidationReport, validate_document
from ..state import AppState, PhaseStatus
from ..workers import ExportExcelWorker, WriteAuditSheetsWorker
from .base import PhasePage, add_popout_to_groupbox, make_action_row, primary


class Phase5ValidatePage(PhasePage):
    """Dedicated validation and auto-fix phase."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 5 \u2014 Validate & Fix",
            subtitle="Only rows with issues. Auto-fix all, edit inline, or double-click a row to jump to Phase 4.",
            parent=parent,
        )
        self._issues: List[ValidationIssue] = []
        self._report: Optional[ValidationReport] = None
        self._applied_fixes: List[dict] = []
        self._build()

    def _build(self) -> None:
        # ---------- Summary banner
        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            "padding: 10px; border-radius: 6px; font-weight: 600;"
        )
        self.add_widget(self._banner)

        # ---------- Action buttons — split into two rows to avoid overflow on small screens
        # Row 1: primary workflow actions
        self._load_btn = QPushButton("Load Excel...")
        self._load_btn.setToolTip(
            "Load any organised / translated / reviewed Excel directly into "
            "this phase.  Validation runs automatically after the load."
        )
        self._load_btn.clicked.connect(self._on_load_excel)
        self._validate_btn = QPushButton("Re-validate")
        self._validate_btn.setToolTip(
            "Re-run validation on the current document. Use this after editing "
            "or auto-fixing to confirm issues are resolved."
        )
        self._validate_btn.clicked.connect(self._on_validate)
        self._fix_all_btn = primary(QPushButton("Auto-fix all"))
        self._fix_all_btn.setToolTip(
            "Automatically fix common issues like length overflow and lost "
            "placeholders. Use 'Fix Selected' for finer control."
        )
        self._fix_all_btn.clicked.connect(self._on_fix_all)
        self._fix_selected_btn = QPushButton("Fix Selected")
        self._fix_selected_btn.setToolTip(
            "Auto-fix only the rows currently selected in the issues table."
        )
        self._fix_selected_btn.setEnabled(False)
        self._fix_selected_btn.clicked.connect(self._on_fix_selected)
        self._save_btn = QPushButton("Save Workbook")
        self._save_btn.setToolTip(
            "Save the current (fixed) document as an .xlsx file."
        )
        self._save_btn.clicked.connect(self._on_save)
        self._download_report_btn = QPushButton("Export Report")
        self._download_report_btn.setToolTip(
            "Export the validation report as CSV, JSON, or HTML."
        )
        self._download_report_btn.clicked.connect(self._on_download_report)

        # Primary workflow actions row — load, validate, fix (before the table)
        self.add_layout(make_action_row(
            self._load_btn, self._validate_btn,
            self._fix_all_btn, self._fix_selected_btn,
        ))

        # ---------- Splitter: issues table (top) + inline editor (bottom)
        # Wrapped in a single QGroupBox so the pop-out icon lives on the
        # group box border (Q1 + Q2: one consolidated pop-out for Phase 5).
        issues_box = QGroupBox("Validation issues")
        self._issues_box = issues_box
        issues_layout = QVBoxLayout(issues_box)
        issues_layout.setContentsMargins(4, 4, 4, 4)
        issues_layout.setSpacing(2)
        self._issues_layout = issues_layout

        splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter = splitter
        splitter.setHandleWidth(4)              # matches the global QSS height
        splitter.setChildrenCollapsible(False)  # prevent accidental collapse
        splitter.setOpaqueResize(True)          # ensure live drag feedback
        # Handle styling comes from the global theme stylesheet -- do NOT set
        # a per-splitter ::handle:vertical rule here.  See phase4_review.py
        # for why (Qt QSS sub-control cascading is unreliable).

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
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
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

        fields_row = QSplitter(Qt.Orientation.Horizontal)
        fields_row.setChildrenCollapsible(False)

        src_widget = QWidget()
        src_col = QVBoxLayout(src_widget)
        # Inset the whole column (label + text area) so it sits with
        # breathing room from the outer group-box border on the left
        # and from the splitter handle on the right.
        src_col.setContentsMargins(6, 4, 6, 4)
        src_col.setSpacing(2)
        src_label = QLabel("Source label (read-only)")
        src_label.setStyleSheet(
            "padding-left: 2px; padding-bottom: 1px; "
            "color: #475569; font-weight: 500; font-size: 11px;"
        )
        src_col.addWidget(src_label)
        self._src_field = QPlainTextEdit()
        self._src_field.setReadOnly(True)
        self._src_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._src_field.setMinimumHeight(40)
        src_col.addWidget(self._src_field)
        fields_row.addWidget(src_widget)

        tgt_widget = QWidget()
        tgt_col = QVBoxLayout(tgt_widget)
        tgt_col.setContentsMargins(6, 4, 6, 4)
        tgt_col.setSpacing(2)
        tgt_label = QLabel("Translation (editable)")
        tgt_label.setStyleSheet(
            "padding-left: 2px; padding-bottom: 1px; "
            "color: #475569; font-weight: 500; font-size: 11px;"
        )
        tgt_col.addWidget(tgt_label)
        self._tgt_field = QPlainTextEdit()
        self._tgt_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tgt_field.setMinimumHeight(40)
        tgt_col.addWidget(self._tgt_field)
        fields_row.addWidget(tgt_widget)

        fields_row.setSizes([400, 400])  # equal halves horizontally

        # stretch=1 so that any extra vertical space in the editor pane
        # (when the user drags the outer vertical splitter) flows directly
        # into the source/translation text areas instead of into padding.
        editor_layout.addWidget(fields_row, stretch=1)

        edit_actions = QHBoxLayout()
        self._apply_btn = primary(QPushButton("Apply"))
        self._apply_btn.setToolTip(
            "Apply your manual edit from the translation field above to this row."
        )
        self._apply_btn.clicked.connect(self._on_apply_edit)
        self._fix_row_btn = QPushButton("Auto-fix this row")
        self._fix_row_btn.setToolTip(
            "Run the safe fixers on just the currently selected row "
            "(placeholder restoration, length trimming, etc.)."
        )
        self._fix_row_btn.clicked.connect(self._on_fix_current_row)
        self._jump_btn = QPushButton("Jump to Phase 4 for context")
        self._jump_btn.setToolTip(
            "Open Phase 4 (Browse & Review) focused on this row so you can see "
            "it in the full table context with its neighbours."
        )
        self._jump_btn.clicked.connect(self._on_jump_to_review)
        edit_actions.addWidget(self._apply_btn)
        edit_actions.addWidget(self._fix_row_btn)
        edit_actions.addWidget(self._jump_btn)
        edit_actions.addStretch(1)
        editor_layout.addLayout(edit_actions)

        splitter.addWidget(editor_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([450, 150])           # table bigger, editor compact by default

        issues_layout.addWidget(splitter)
        self.add_widget(issues_box, stretch=1)

        # ONE pop-out icon glued to the group box border, popping the
        # whole splitter (issues table + editor) into a modeless QDialog.
        add_popout_to_groupbox(issues_box, self._on_popout_issues)

        # ---------- Bottom: save/export + next phase on same row
        self._next_btn = QPushButton("Continue to Phase 6 (Export STF) \u2192")
        self._next_btn.setToolTip("Move to the next phase (Export STF).")
        self._next_btn.clicked.connect(self._on_continue_to_phase6)
        self.add_layout(make_action_row(
            self._save_btn, self._download_report_btn, self._next_btn,
        ))

    # ------------------------------------------------------------------ continue to Phase 6

    def _on_continue_to_phase6(self) -> None:
        self._state.set_phase(4, PhaseStatus.DONE)
        self.request_navigate.emit(5)

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.document is None:
            self._banner.setText("No document loaded.  Complete earlier phases first.")
            self._banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 700; "
                "background-color: #f1f5f9; color: #475569;"
            )
            self._banner.setVisible(True)
            self._fix_all_btn.setEnabled(False)
            self._save_btn.setEnabled(False)
            return
        self._fix_all_btn.setEnabled(True)
        self._save_btn.setEnabled(True)

        # Show "data loaded" state before running validation
        stats = self._state.document.stats()
        self._banner.setText(
            f"Document loaded: {stats['total']:,} rows "
            f"({stats['translated']:,} translated, {stats['untranslated']:,} untranslated). "
            f"Running validation..."
        )
        self._banner.setStyleSheet(
            "padding: 10px; border-radius: 6px; font-weight: 600; "
            "background-color: #e0e7ff; color: #3730a3;"
        )
        self._banner.setVisible(True)
        QApplication.processEvents()

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
        if not self.check_workflow_override(path):
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
            # Set active workflow context so subsequent loads trigger override dialog.
            self._state.set_active_workflow_context(
                document=doc,
                original_source_path=path,
                current_working_path=path,
                current_working_artifact_type="reviewed_excel",
                start_phase=4,
                current_phase=4,
                override_existing=False,
                reset_downstream=False,
            )
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
        errors = self._report.errors
        warnings = self._report.warnings
        if not errors and not warnings:
            self._banner.setText(
                "\u2713  All clear \u2014 no validation issues.  "
                "You can proceed to export."
            )
            self._banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #dcfce7; color: #166534; border: 1px solid #86efac;"
            )
        elif errors:
            self._banner.setText(
                f"\u26a0  {len(errors)} error(s) must be fixed "
                f"before Salesforce import.  {len(warnings)} warning(s) "
                f"are advisory.  Use 'Auto-fix all' or edit rows below."
            )
            self._banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;"
            )
        else:
            self._banner.setText(
                f"\u26a0  {len(warnings)} warning(s) found (advisory).  "
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

    # ------------------------------------------------------------------ selection

    def _on_selection_changed(self) -> None:
        """Enable/disable Fix Selected button based on table selection."""
        has_selection = bool(self._table.selectedIndexes())
        self._fix_selected_btn.setEnabled(has_selection)

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
        # Capture before-state for fix tracking
        before_translations: dict[str, tuple[str, str]] = {}
        for entry in self._state.document.entries:
            before_translations[entry.key] = (entry.label, entry.translation)

        report = auto_fix_document(self._state.document)
        self.status_message.emit(
            f"Auto-fix complete: {report.fixed_count} fix(es) applied."
        )

        # Record applied fixes with before/after details
        if report.fixed_count > 0:
            for key, description in report.details:
                old_label, old_translation = before_translations.get(key, ("", ""))
                # Find current (fixed) translation
                new_translation = old_translation
                for entry in self._state.document.entries:
                    if entry.key == key:
                        new_translation = entry.translation
                        break
                # Determine issue category from description
                issue_category = self._categorize_fix(description)
                self._applied_fixes.append({
                    "key": key,
                    "label": old_label,
                    "previous_translation": old_translation,
                    "fixed_translation": new_translation,
                    "issue_category": issue_category,
                    "fix_description": description,
                })

            self.info(
                f"Applied {report.fixed_count} fix(es).\n\n"
                + "\n".join(f"  \u2022 {key}: {desc}" for key, desc in report.details[:20])
                + ("\n  ..." if len(report.details) > 20 else ""),
                "Auto-fix results",
            )
            self.action_recorded.emit(f"Auto-fix all ({report.fixed_count} fixes)")
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
            old_translation = entry.translation
            fixed_entry, descriptions = auto_fix_entry(entry)
            if descriptions:
                self._replace_entry(issue.key, fixed_entry)
                fixed_count += 1
                # Record fix details
                self._applied_fixes.append({
                    "key": entry.key,
                    "label": entry.label,
                    "previous_translation": old_translation,
                    "fixed_translation": fixed_entry.translation,
                    "issue_category": issue.category,
                    "fix_description": "; ".join(descriptions),
                })
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
        old_translation = entry.translation
        fixed_entry, descriptions = auto_fix_entry(entry)
        if descriptions:
            self._replace_entry(issue.key, fixed_entry)
            self._tgt_field.setPlainText(fixed_entry.translation)
            self.status_message.emit(f"Fixed: {'; '.join(descriptions)}")
            # Record fix details
            self._applied_fixes.append({
                "key": entry.key,
                "label": entry.label,
                "previous_translation": old_translation,
                "fixed_translation": fixed_entry.translation,
                "issue_category": issue.category,
                "fix_description": "; ".join(descriptions),
            })
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
                    key=e.key, label=e.label, translation=new_translation,
                    approved=e.approved,
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
        path = self.pick_save_file("Save fixed workbook as", "Excel files (*.xlsx)", self.default_save_name("validated"))
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
        self.info(
            f"Workbook saved successfully.\n\n{path.name}\n\nLocation: {path.parent}",
            "Save Complete",
        )
        try:
            from .. import settings as gui_settings
            gui_settings.add_recent_file(path)
        except Exception:  # noqa: BLE001
            pass

    def _on_save_failed(self, message: str) -> None:
        self.set_busy(False)
        self._state.set_phase(4, PhaseStatus.ERROR)
        self.error(message, "Save failed")

    # ------------------------------------------------------------------ download report

    def _on_download_report(self) -> None:
        """Export the current validation report to CSV, JSON, or HTML."""
        if self._report is None:
            self.status_message.emit("No validation report available. Run validation first.")
            return
        path = self.pick_save_file(
            "Save validation report",
            "CSV (*.csv);;JSON (*.json);;HTML (*.html)",
            "validation_report.csv",
        )
        if not path:
            return

        from ...report import export_csv, export_html, export_json

        fixes = self._applied_fixes if self._applied_fixes else None
        ext = path.suffix.lower()
        if ext == ".csv":
            export_csv(self._report, path, fixes_applied=fixes)
        elif ext == ".json":
            export_json(self._report, path, fixes_applied=fixes)
        elif ext == ".html":
            export_html(self._report, path, fixes_applied=fixes)
        else:
            self.status_message.emit(
                f"Unsupported format '{ext}'. Use .csv, .json, or .html."
            )
            return
        self.status_message.emit(f"Report exported to {path}")

    # ------------------------------------------------------------------ pop-out (entire splitter: issues table + editor)

    def _categorize_fix(self, description: str) -> str:
        """Derive issue category from a fix description string."""
        desc_lower = description.lower()
        if "placeholder" in desc_lower:
            return "missing_placeholder"
        if "messageformat" in desc_lower or "token" in desc_lower:
            return "missing_message_format"
        if "trim" in desc_lower or "length" in desc_lower:
            return "length_exceeded"
        if "whitespace" in desc_lower:
            return "whitespace_only"
        if "html" in desc_lower or "tag" in desc_lower:
            return "missing_html_tag"
        if "duplicate" in desc_lower:
            return "duplicate_key"
        return "other"

    def reset_page(self) -> None:
        """Called by Reset Session to clear all displayed widgets back to defaults."""
        self._table.setRowCount(0)
        self._issues = []
        self._report = None
        self._applied_fixes = []
        self._banner.setText("No document loaded.  Complete earlier phases first.")
        self._banner.setStyleSheet(
            "padding: 10px; border-radius: 6px; font-weight: 700; "
            "background-color: #f1f5f9; color: #475569;"
        )
        self._fix_all_btn.setEnabled(False)
        self._fix_selected_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._key_label.clear()
        self._issue_label.setText("")
        self._src_field.clear()
        self._tgt_field.clear()

    def _on_popout_issues(self) -> None:
        if hasattr(self, '_issues_dialog') and self._issues_dialog is not None:
            self._issues_dialog.raise_()
            self._issues_dialog.activateWindow()
            return
        self._issues_dialog = QDialog(self)
        self._issues_dialog.setWindowTitle("Phase 5 \u2014 Validate & Fix")
        from .base import clamp_to_screen
        clamp_to_screen(self._issues_dialog, 1100, 700)
        self._issues_dialog.setWindowFlags(
            self._issues_dialog.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        layout = QVBoxLayout(self._issues_dialog)
        self._splitter.setParent(self._issues_dialog)
        layout.addWidget(self._splitter)
        self._issues_dialog.finished.connect(self._on_issues_dialog_closed)
        self._issues_dialog.show()

    def _on_issues_dialog_closed(self) -> None:
        self._splitter.setParent(self._issues_box)
        self._issues_layout.addWidget(self._splitter)
        self._issues_dialog = None
