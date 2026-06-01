"""Phase 4 (index 3) -- Review.

v1.3 simplification: this page now reads as a translation browser
rather than an editor.  Layout (top to bottom):

* **Compact toolbar**: validation status pill, big counters
  (translated / untranslated / issues), Load Excel button, filter
  fields.
* **Big table** showing every row.
* **Slim inline editor** at the bottom for the selected row.
* **Save** + **Continue** action buttons.

Auto-validation still runs on entry; the result colours the status
pill.  Re-uploading an externally edited Excel keeps the convenience
of editing outside the app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...model import Document, Entry
from ...validate import validate_document
from ..find_replace_dialog import FindReplaceDialog
from ..state import AppState, PhaseStatus
from ..undo import UndoCommand, UndoStack
from ..workers import ExportExcelWorker, ImportExcelWorker, WriteAuditSheetsWorker
from .base import PhasePage, add_popout_to_groupbox, make_action_row, primary

_HEADERS = ["#", "Key", "Component", "Status", "Label", "Translation", "Approved"]
_TRANSLATION_COL = 5
_APPROVED_COL = 6


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class _EntriesModel(QAbstractTableModel):
    edited = Signal(int)

    def __init__(self, doc: Document, parent=None, undo_stack: "UndoStack | None" = None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._undo_stack: UndoStack | None = undo_stack
        self._applying_undo = False  # guard to avoid pushing during undo/redo

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._doc.entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(_HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        entry = self._doc.entries[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and col == _APPROVED_COL:
            return Qt.CheckState.Checked if entry.approved else Qt.CheckState.Unchecked
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if col == 0:
                return index.row() + 1
            if col == 1:
                return entry.key
            if col == 2:
                return entry.component_type
            if col == 3:
                return entry.status
            if col == 4:
                return entry.label
            if col == 5:
                return entry.translation
            if col == _APPROVED_COL:
                return "\u2713" if entry.approved else ""
        if role == Qt.ItemDataRole.ToolTipRole and col in (4, 5):
            return entry.label if col == 4 else entry.translation
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            if section == _APPROVED_COL:
                return (
                    "Mark translations as reviewed and accepted.\n"
                    "Approved rows are skipped during validation in Phase 5."
                )
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return section + 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        base = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if index.column() == _TRANSLATION_COL:
            return base | Qt.ItemFlag.ItemIsEditable
        if index.column() == _APPROVED_COL:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if index.column() == _APPROVED_COL and role == Qt.ItemDataRole.CheckStateRole:
            row = index.row()
            old = self._doc.entries[row]
            new_approved = (
                value == Qt.CheckState.Checked.value
                if isinstance(value, int)
                else value == Qt.CheckState.Checked
            )
            # Push undo command (unless we are replaying an undo/redo)
            if not self._applying_undo and self._undo_stack is not None:
                self._undo_stack.push(
                    UndoCommand(
                        row=row,
                        column=_APPROVED_COL,
                        old_value=old.approved,
                        new_value=new_approved,
                    )
                )
            self._doc.entries[row] = Entry(
                key=old.key,
                label=old.label,
                translation=old.translation,
                approved=new_approved,
            )
            self.dataChanged.emit(
                index, index, [Qt.ItemDataRole.CheckStateRole, Qt.ItemDataRole.DisplayRole]
            )
            status_idx = self.index(row, 3)
            self.dataChanged.emit(status_idx, status_idx, [Qt.ItemDataRole.DisplayRole])
            self.edited.emit(row)
            return True
        if role != Qt.ItemDataRole.EditRole or index.column() != _TRANSLATION_COL:
            return False
        row = index.row()
        old = self._doc.entries[row]
        text = "" if value is None else str(value)
        # Push undo command (unless we are replaying an undo/redo)
        if not self._applying_undo and self._undo_stack is not None:
            self._undo_stack.push(
                UndoCommand(
                    row=row,
                    column=_TRANSLATION_COL,
                    old_value=old.translation,
                    new_value=text,
                )
            )
        self._doc.entries[row] = Entry(
            key=old.key, label=old.label, translation=text, approved=old.approved
        )
        self.dataChanged.emit(
            index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]
        )
        status_idx = self.index(row, 3)
        self.dataChanged.emit(status_idx, status_idx, [Qt.ItemDataRole.DisplayRole])
        self.edited.emit(row)
        return True

    # ------------------------------------------------------------------ undo / redo

    def undo(self) -> None:
        """Undo the last edit by restoring old_value."""
        if self._undo_stack is None:
            return
        cmd = self._undo_stack.undo()
        if cmd is None:
            return
        self._apply_command_value(cmd.row, cmd.column, cmd.old_value)

    def redo(self) -> None:
        """Redo a previously undone edit by re-applying new_value."""
        if self._undo_stack is None:
            return
        cmd = self._undo_stack.redo()
        if cmd is None:
            return
        self._apply_command_value(cmd.row, cmd.column, cmd.new_value)

    def _apply_command_value(self, row: int, column: int, value) -> None:
        """Apply a value from an undo/redo command without pushing to stack."""
        self._applying_undo = True
        try:
            idx = self.index(row, column)
            if column == _APPROVED_COL:
                check = (
                    Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
                )
                self.setData(idx, check, Qt.ItemDataRole.CheckStateRole)
            else:
                self.setData(idx, value, Qt.ItemDataRole.EditRole)
        finally:
            self._applying_undo = False


class _ComponentStatusFilter(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._component = "All"
        self._status = "All"
        self._needle = ""
        self._column_filters: dict[int, set[str]] = {}  # col -> allowed values

    def set_component(self, component: str) -> None:
        self._component = component
        self.invalidateFilter()

    def set_status(self, status: str) -> None:
        self._status = status
        self.invalidateFilter()

    def set_search(self, needle: str) -> None:
        self._needle = needle.strip().lower()
        self.invalidateFilter()

    def set_column_filter(self, col: int, values: "Optional[set[str]]") -> None:
        """Set allowed values for a column, or clear if *values* is None."""
        if values is None:
            self._column_filters.pop(col, None)
        else:
            self._column_filters[col] = values
        self.invalidateFilter()

    def clear_column_filter(self, col: int) -> None:
        """Remove the column filter for *col*."""
        self._column_filters.pop(col, None)
        self.invalidateFilter()

    def column_filter(self, col: int) -> "Optional[set[str]]":
        """Return the active allowed-value set for *col*, or None if unfiltered."""
        return self._column_filters.get(col)

    def has_column_filter(self, col: int) -> bool:
        """True when a per-value filter is currently active on *col*."""
        return col in self._column_filters

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return True
        comp = model.index(source_row, 2, source_parent).data(Qt.ItemDataRole.DisplayRole) or ""
        status = model.index(source_row, 3, source_parent).data(Qt.ItemDataRole.DisplayRole) or ""
        key = (model.index(source_row, 1, source_parent).data(Qt.ItemDataRole.DisplayRole) or "").lower()
        label = (model.index(source_row, 4, source_parent).data(Qt.ItemDataRole.DisplayRole) or "").lower()
        if self._component != "All" and comp != self._component:
            return False
        if self._status != "All" and status != self._status:
            return False
        if self._needle and self._needle not in key and self._needle not in label:
            return False
        # Per-column value filters
        for col, allowed in self._column_filters.items():
            val = str(
                model.index(source_row, col, source_parent).data(Qt.ItemDataRole.DisplayRole) or ""
            )
            if val not in allowed:
                return False
        return True


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class Phase4ReviewPage(PhasePage):
    """In-app translation browser with on-demand editing."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 4 \u2014 Review",
            subtitle=(
                "Browse the translations, filter to focus on what matters, "
                "edit on demand, and re-upload an externally edited Excel "
                "if you prefer to review there.  Validation runs on entry "
                "so you can spot issues at a glance."
            ),
            parent=parent,
        )
        self._model: Optional[_EntriesModel] = None
        self._proxy = _ComponentStatusFilter(self)
        self._current_row: Optional[int] = None
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # ---------- Undo stack (shared with model + menu)
        self._undo_stack = UndoStack(self)

        # ---------- Compact toolbar (status pill + counters + actions)
        toolbar = QFrame()
        toolbar.setProperty("role", "card")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 10, 12, 10)
        tb_layout.setSpacing(14)

        self._status_pill = QLabel("\u2022  No document loaded")
        self._status_pill.setStyleSheet(
            "padding: 4px 10px; border-radius: 12px; "
            "background: #f1f5f9; color: #475569; font-weight: 700;"
        )
        tb_layout.addWidget(self._status_pill)

        self._stat_translated = self._make_inline_stat("Translated", "0", "#16a34a")
        self._stat_untranslated = self._make_inline_stat("Untranslated", "0", "#d97706")
        self._stat_issues = self._make_inline_stat("Issues", "0", "#dc2626")
        tb_layout.addWidget(self._stat_translated["frame"])
        tb_layout.addWidget(self._stat_untranslated["frame"])
        tb_layout.addWidget(self._stat_issues["frame"])

        tb_layout.addStretch(1)

        # Undo / Redo toolbar buttons
        self._undo_btn = QPushButton("Undo")
        self._undo_btn.setToolTip("Undo last translation edit (Ctrl+Z)")
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self._on_undo)
        tb_layout.addWidget(self._undo_btn)

        self._redo_btn = QPushButton("Redo")
        self._redo_btn.setToolTip("Redo last undone edit (Ctrl+Y)")
        self._redo_btn.setEnabled(False)
        self._redo_btn.clicked.connect(self._on_redo)
        tb_layout.addWidget(self._redo_btn)

        self._undo_stack.stack_changed.connect(self._refresh_undo_buttons)

        self._load_btn = QPushButton("Load reviewed Excel...")
        self._load_btn.setToolTip(
            "Replace the current document with an externally edited workbook.  "
            "It becomes the latest version used by all subsequent phases."
        )
        self._load_btn.clicked.connect(self._on_load_excel)
        tb_layout.addWidget(self._load_btn)

        self._find_replace_btn = QPushButton("Global Replace...")
        self._find_replace_btn.setToolTip(
            "Open Find & Replace dialog to perform bulk text replacements "
            "across translations (Ctrl+H)."
        )
        self._find_replace_btn.clicked.connect(self._on_find_replace)
        tb_layout.addWidget(self._find_replace_btn)

        self.add_widget(toolbar)

        # ---------- Filter row (slim)
        filter_row = QFrame()
        fr_layout = QHBoxLayout(filter_row)
        fr_layout.setContentsMargins(2, 0, 2, 0)
        fr_layout.setSpacing(8)

        fr_layout.addWidget(QLabel("Component:"))
        self._component_combo = QComboBox()
        self._component_combo.addItem("All")
        self._component_combo.setToolTip(
            "Filter the table to show rows from a single component type "
            "(e.g. CustomLabel). 'All' shows everything."
        )
        self._component_combo.currentTextChanged.connect(self._proxy.set_component)
        fr_layout.addWidget(self._component_combo)

        fr_layout.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItems(["All", "Translated", "Untranslated", "Approved"])
        self._status_combo.setToolTip(
            "Filter the table by translation status. Use 'Untranslated' to "
            "focus on rows that still need work."
        )
        self._status_combo.currentTextChanged.connect(self._proxy.set_status)
        fr_layout.addWidget(self._status_combo)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by key or label...")
        self._search.setToolTip(
            "Filter rows whose key or source label contains this text. "
            "Case-insensitive substring match."
        )
        self._search.textChanged.connect(self._proxy.set_search)
        fr_layout.addWidget(self._search, stretch=1)
        self.add_widget(filter_row)

        # ---------- Splitter: table on top, slim inline editor below
        # Wrapped in a single QGroupBox so the pop-out icon lives on the
        # group box border (Q1 + Q2: one consolidated pop-out for Phase 4).
        review_box = QGroupBox("Translations")
        self._review_box = review_box
        review_layout = QVBoxLayout(review_box)
        review_layout.setContentsMargins(4, 4, 4, 4)
        review_layout.setSpacing(2)
        self._review_layout = review_layout

        splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter = splitter
        splitter.setHandleWidth(4)              # matches the global QSS height
        splitter.setChildrenCollapsible(False)  # prevent accidental collapse
        splitter.setOpaqueResize(True)          # ensure live drag feedback
        # Handle styling comes from the global theme stylesheet -- do NOT set
        # a per-splitter ::handle:vertical rule here.  Per-widget QSS for QSS
        # sub-controls is unreliable when a global rule with the same selector
        # is already in scope, and that's what was making the handle un-draggable.

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.SelectedClicked
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        splitter.addWidget(self._table)

        # Slim editor pane (no "card" role -- a card-styled QFrame inside an
        # already-bordered QGroupBox creates a visible double border (the
        # "dark hue" reported by the user).  Plain QWidget = no extra frame.
        editor = QWidget()
        self._editor_layout = QVBoxLayout(editor)
        self._editor_layout.setContentsMargins(12, 10, 12, 10)
        self._editor_layout.setSpacing(6)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(QLabel("Key:"))
        self._key_field = QLineEdit()
        self._key_field.setReadOnly(True)
        self._key_field.setStyleSheet("font-family: monospace;")
        meta.addWidget(self._key_field, stretch=1)
        self._apply_all_check = QCheckBox("Apply to all rows")
        self._apply_all_check.setToolTip(
            "When checked, clicking Apply will find the old translation of "
            "this row across ALL rows and replace matches with the new text."
        )
        meta.addWidget(self._apply_all_check)
        self._apply_btn = primary(QPushButton("Apply"))
        self._apply_btn.setToolTip("Apply your edits to the translation in the table above.")
        self._apply_btn.clicked.connect(self._apply_editor_to_row)
        self._reset_btn = QPushButton("Reset to source")
        self._reset_btn.setToolTip(
            "Clear the translation back to the source label. Use this to "
            "discard a bad translation and start fresh."
        )
        self._reset_btn.clicked.connect(self._reset_row)
        meta.addWidget(self._apply_btn)
        meta.addWidget(self._reset_btn)
        self._editor_layout.addLayout(meta)

        side_by_side = QSplitter(Qt.Orientation.Horizontal)
        side_by_side.setChildrenCollapsible(False)

        src_widget = QWidget()
        src_col = QVBoxLayout(src_widget)
        # Inset the whole column (label + text area) so it sits with
        # breathing room from the outer group-box border on the left
        # and from the splitter handle on the right.
        src_col.setContentsMargins(10, 6, 10, 6)
        src_col.setSpacing(3)
        src_label = QLabel("Source")
        src_label.setStyleSheet(
            "padding-left: 4px; padding-bottom: 2px; "
            "color: #475569; font-weight: 500;"
        )
        src_col.addWidget(src_label)
        self._source_field = QPlainTextEdit()
        self._source_field.setReadOnly(True)
        self._source_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._source_field.setMinimumHeight(60)
        src_col.addWidget(self._source_field)
        side_by_side.addWidget(src_widget)

        tgt_widget = QWidget()
        tgt_col = QVBoxLayout(tgt_widget)
        tgt_col.setContentsMargins(10, 6, 10, 6)
        tgt_col.setSpacing(3)
        tgt_label = QLabel("Translation (editable)")
        tgt_label.setStyleSheet(
            "padding-left: 4px; padding-bottom: 2px; "
            "color: #475569; font-weight: 500;"
        )
        tgt_col.addWidget(tgt_label)
        self._translation_field = QPlainTextEdit()
        self._translation_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._translation_field.setMinimumHeight(60)
        tgt_col.addWidget(self._translation_field)
        side_by_side.addWidget(tgt_widget)

        side_by_side.setSizes([400, 400])  # equal halves horizontally
        # stretch=1 so that any extra vertical space in the editor pane
        # (when the user drags the outer vertical splitter) flows directly
        # into the source/translation text areas instead of into padding.
        self._editor_layout.addWidget(side_by_side, stretch=1)

        splitter.addWidget(editor)
        self._editor_widget = editor
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 200])           # explicit initial sizes (table top, editor bottom)

        review_layout.addWidget(splitter)
        self.add_widget(review_box, stretch=1)

        # ONE pop-out icon glued to the group box border, popping the
        # whole splitter (table + editor) into a modeless QDialog.
        add_popout_to_groupbox(review_box, self._on_popout_review)

        # ---------- Bottom action buttons
        self._save_btn = primary(QPushButton("Save Workbook"))
        self._save_btn.setToolTip(
            "Save the current document (with all edits applied) as an .xlsx file. "
            "This becomes the canonical reviewed workbook used by Phase 5/6."
        )
        self._save_btn.clicked.connect(self._on_save)
        self._next_btn = QPushButton("Continue to Phase 5 (Validate & Fix) \u2192")
        self._next_btn.setToolTip("Move to the next phase (Validate & Fix).")
        self._next_btn.clicked.connect(self._on_continue_to_phase5)
        self.add_layout(make_action_row(self._save_btn, self._next_btn))

    def _make_inline_stat(self, label: str, value: str, accent: str) -> dict:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel(label.upper())
        title.setStyleSheet(
            "color: #64748b; font-size: 10px; font-weight: 600; letter-spacing: 0.6px;"
        )
        val = QLabel(value)
        val.setStyleSheet(f"color: {accent}; font-size: 16px; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(val)
        return {"frame": frame, "value": val}

    # ------------------------------------------------------------------ undo / redo UI

    def _refresh_undo_buttons(self) -> None:
        """Enable/disable undo and redo buttons based on stack state."""
        self._undo_btn.setEnabled(self._undo_stack.can_undo)
        self._redo_btn.setEnabled(self._undo_stack.can_redo)

    def _on_undo(self) -> None:
        if self._model is not None:
            self._model.undo()
            self._update_counters()
            self._run_auto_validation()

    def _on_redo(self) -> None:
        if self._model is not None:
            self._model.redo()
            self._update_counters()
            self._run_auto_validation()

    # ------------------------------------------------------------------ find & replace

    def _on_find_replace(self) -> None:
        """Open Find & Replace dialog and apply replacements via undo stack."""
        if self._state.document is None or self._model is None:
            return
        dialog = FindReplaceDialog(self._state.document, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        replacements = dialog.replacements
        if not replacements:
            self.status_message.emit("No replacements to apply.")
            return
        # Apply each replacement through the model (pushes undo commands)
        count = 0
        for rep in replacements:
            if rep.field == "translation":
                idx = self._model.index(rep.row, _TRANSLATION_COL)
                self._model.setData(idx, rep.new_value, Qt.ItemDataRole.EditRole)
                count += 1
        self._update_counters()
        self._run_auto_validation()
        self.status_message.emit(f"Replaced {count} occurrence(s).")

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.document is None:
            self._status_pill.setText("\u2022  No document loaded")
            self._status_pill.setStyleSheet(
                "padding: 4px 10px; border-radius: 12px; "
                "background: #f1f5f9; color: #475569; font-weight: 700;"
            )
            self._save_btn.setEnabled(False)
            return
        self._save_btn.setEnabled(True)

        # Show loading indicator for large documents
        if len(self._state.document.entries) > 1000:
            self._status_pill.setText("\u23f3  Loading...")
            self._status_pill.setStyleSheet(
                "padding: 4px 10px; border-radius: 12px; "
                "background: #e0e7ff; color: #3730a3; font-weight: 600;"
            )
            QApplication.processEvents()

        if self._model is None:
            self._model = _EntriesModel(
                self._state.document, self, undo_stack=self._undo_stack
            )
            self._model.edited.connect(lambda _row: self._update_counters())
            self._model.edited.connect(lambda _row: self._mark_unsaved())
            self._proxy.setSourceModel(self._model)
            self._table.selectionModel().currentChanged.connect(self._on_selection_changed)
        else:
            self._model.beginResetModel()
            self._model._doc = self._state.document  # noqa: SLF001
            self._model.endResetModel()
            # Clear undo history when document is reloaded
            self._undo_stack.clear()

        components = sorted({e.component_type for e in self._state.document.entries})
        self._component_combo.blockSignals(True)
        current = self._component_combo.currentText()
        self._component_combo.clear()
        self._component_combo.addItems(["All", *components])
        if current in {"All", *components}:
            self._component_combo.setCurrentText(current)
        self._component_combo.blockSignals(False)

        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 280)
        self._table.setColumnWidth(2, 120)
        self._table.setColumnWidth(3, 110)
        self._table.setColumnWidth(4, 280)
        self._table.setColumnWidth(5, 280)
        self._table.setColumnWidth(6, 80)
        self._update_counters()
        self._run_auto_validation()

    def _update_counters(self) -> None:
        if self._state.document is None:
            return
        stats = self._state.document.stats()
        self._stat_translated["value"].setText(f"{stats['translated']:,}")
        self._stat_untranslated["value"].setText(f"{stats['untranslated']:,}")

    def _run_auto_validation(self) -> None:
        if self._state.document is None:
            return
        report = validate_document(self._state.document)
        issue_count = len(report.issues)
        self._stat_issues["value"].setText(f"{issue_count:,}")
        if issue_count == 0:
            self._stat_issues["value"].setStyleSheet(
                "color: #16a34a; font-size: 16px; font-weight: 700;"
            )
            self._status_pill.setText("\u2713  All clear")
            self._status_pill.setStyleSheet(
                "padding: 4px 10px; border-radius: 12px; "
                "background: #dcfce7; color: #166534; font-weight: 600;"
            )
        elif report.has_errors:
            self._stat_issues["value"].setStyleSheet(
                "color: #dc2626; font-size: 16px; font-weight: 700;"
            )
            self._status_pill.setText(
                f"\u26a0  {len(report.errors)} error(s)  \u2192  Phase 5 to fix"
            )
            self._status_pill.setStyleSheet(
                "padding: 4px 10px; border-radius: 12px; "
                "background: #fee2e2; color: #991b1b; font-weight: 600;"
            )
        else:
            self._stat_issues["value"].setStyleSheet(
                "color: #d97706; font-size: 16px; font-weight: 700;"
            )
            self._status_pill.setText(f"\u26a0  {len(report.warnings)} warning(s)")
            self._status_pill.setStyleSheet(
                "padding: 4px 10px; border-radius: 12px; "
                "background: #fef3c7; color: #92400e; font-weight: 600;"
            )
        self.status_message.emit(
            f"Validation: {len(report.errors)} error(s), {len(report.warnings)} warning(s)."
        )

    # ------------------------------------------------------------------ selection

    def _on_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        source_row = self._proxy.mapToSource(current).row()
        self._current_row = source_row
        if self._model is None or self._state.document is None:
            return
        entry = self._state.document.entries[source_row]
        self._key_field.setText(entry.key)
        self._source_field.setPlainText(entry.label)
        self._translation_field.setPlainText(entry.translation)

    def _apply_editor_to_row(self) -> None:
        if self._current_row is None or self._model is None:
            return
        new_text = self._translation_field.toPlainText()

        # "Apply to all rows" mode: exact full-field replacement across all rows
        if self._apply_all_check.isChecked() and self._state.document is not None:
            old_text = self._state.document.entries[self._current_row].translation
            if old_text and old_text != new_text:
                count = 0
                for row, entry in enumerate(self._state.document.entries):
                    if entry.translation == old_text:
                        idx = self._model.index(row, _TRANSLATION_COL)
                        self._model.setData(idx, new_text, Qt.ItemDataRole.EditRole)
                        count += 1
                self._update_counters()
                self._run_auto_validation()
                self.status_message.emit(f"Replaced {count} occurrence(s) across all rows.")
                return

        idx = self._model.index(self._current_row, _TRANSLATION_COL)
        self._model.setData(idx, new_text, Qt.ItemDataRole.EditRole)
        self.status_message.emit(f"Updated translation for row {self._current_row + 1}.")

    def _reset_row(self) -> None:
        if self._current_row is None or self._model is None:
            return
        if not self.confirm("Reset this row's translation to the source label?"):
            return
        entry = self._state.document.entries[self._current_row]
        idx = self._model.index(self._current_row, _TRANSLATION_COL)
        self._model.setData(idx, entry.label, Qt.ItemDataRole.EditRole)
        self._translation_field.setPlainText(entry.label)

    # ------------------------------------------------------------------ clear for retranslation (context menu)

    def _on_clear_for_retranslation(self) -> None:
        """Clear the selected row's translation so it becomes untranslated.

        On the next translation run (with or without retranslate_existing),
        this row will be retranslated because its translation is empty.
        """
        if self._current_row is None or self._model is None:
            return
        idx = self._model.index(self._current_row, _TRANSLATION_COL)
        self._model.setData(idx, "", Qt.ItemDataRole.EditRole)
        self._translation_field.setPlainText("")
        self._update_counters()
        self.status_message.emit(
            f"Cleared translation for row {self._current_row + 1} "
            "(will be retranslated on next run)."
        )

    def _on_table_context_menu(self, pos) -> None:
        """Show a context menu with a 'Clear for retranslation' action."""
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        source_index = self._proxy.mapToSource(index)
        row = source_index.row()
        self._current_row = row
        if self._state.document is None:
            return
        entry = self._state.document.entries[row]

        menu = QMenu(self._table)
        if entry.translation.strip():
            clear_action = menu.addAction("Clear for retranslation")
            clear_action.triggered.connect(self._on_clear_for_retranslation)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ column-wise filtering (Excel-like header menu)

    def _on_header_context_menu(self, pos) -> None:
        """Excel-like column filter / sort menu shown on header right-click.

        Right-clicking a column header opens a menu offering:

        * **Sort Ascending / Sort Descending** for that column.
        * **Filter by value** -- a submenu of every distinct value in the
          column (built from the *source* model), each a checkable action.
          Unchecking values hides the matching rows via the proxy's
          ``set_column_filter`` / ``clear_column_filter`` hooks.
        * **Clear filter** -- removes any active per-value filter on the
          column.
        """
        if self._model is None:
            return
        header = self._table.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col < 0:
            return

        menu = QMenu(self._table)
        menu.setTitle(_HEADERS[col] if 0 <= col < len(_HEADERS) else "")

        # ---- Sort actions
        sort_asc = menu.addAction("Sort Ascending")
        sort_asc.triggered.connect(
            lambda _checked=False, c=col: self._table.sortByColumn(
                c, Qt.SortOrder.AscendingOrder
            )
        )
        sort_desc = menu.addAction("Sort Descending")
        sort_desc.triggered.connect(
            lambda _checked=False, c=col: self._table.sortByColumn(
                c, Qt.SortOrder.DescendingOrder
            )
        )
        menu.addSeparator()

        # ---- Clear filter
        clear_action = menu.addAction("Clear filter")
        clear_action.setEnabled(self._proxy.has_column_filter(col))
        clear_action.triggered.connect(
            lambda _checked=False, c=col: self._proxy.clear_column_filter(c)
        )

        # ---- Distinct values submenu (checkable)
        distinct = sorted(
            {
                str(self._model.index(r, col).data(Qt.ItemDataRole.DisplayRole) or "")
                for r in range(self._model.rowCount())
            }
        )
        allowed = self._proxy.column_filter(col)

        values_menu = menu.addMenu("Filter by value")
        # Quick (de)select helpers at the top of the submenu.
        select_all = values_menu.addAction("Select all")
        select_none = values_menu.addAction("Select none")
        values_menu.addSeparator()

        value_actions: dict[str, object] = {}
        for val in distinct:
            act = values_menu.addAction(val if val else "(empty)")
            act.setCheckable(True)
            act.setChecked(allowed is None or val in allowed)
            value_actions[val] = act

        def _apply_value_filter() -> None:
            chosen = {v for v, a in value_actions.items() if a.isChecked()}
            # All (or nothing) selected behaves as "no filter" so the user
            # always sees rows again instead of an empty table.
            if not chosen or chosen == set(distinct):
                self._proxy.clear_column_filter(col)
            else:
                self._proxy.set_column_filter(col, chosen)

        def _select_all() -> None:
            self._proxy.clear_column_filter(col)

        def _select_none() -> None:
            # Empty allowed set -> hide everything in this column.
            self._proxy.set_column_filter(col, set())

        select_all.triggered.connect(lambda _checked=False: _select_all())
        select_none.triggered.connect(lambda _checked=False: _select_none())
        for act in value_actions.values():
            act.triggered.connect(lambda _checked=False: _apply_value_filter())

        menu.exec(header.mapToGlobal(pos))

    # ------------------------------------------------------------------ load Excel

    def _on_load_excel(self) -> None:
        if self.is_busy:
            return
        path = self.pick_open_file(
            "Load reviewed / edited Excel",
            "Excel files (*.xlsx);;All files (*)",
        )
        if not path:
            return
        if not self.check_workflow_override(path):
            return
        self.set_busy(True)
        self.status_message.emit(f"Loading {path.name} as the latest version ...")
        worker = ImportExcelWorker(
            path,
            language=self._state.target_language_name,
            language_code=self._state.target_language_code,
            parent=self,
        )
        worker.finished_ok.connect(lambda doc: self._on_excel_loaded(doc, path))
        worker.failed.connect(lambda msg: self._on_load_failed(msg))
        worker.start()

    def _on_excel_loaded(self, doc: Document, path: Path) -> None:
        self._state.document = doc
        self._state.reviewed_xlsx_path = path
        self._state.output_dir = path.parent
        self.set_busy(False)
        self.on_enter()
        self.status_message.emit(
            f"Loaded {len(doc.entries):,} rows from {path.name}.  "
            "This is now the latest version."
        )
        try:
            from .. import settings as gui_settings
            gui_settings.add_recent_file(path)
        except Exception:  # noqa: BLE001
            pass

    def _on_load_failed(self, msg: str) -> None:
        self.set_busy(False)
        self.error(msg, "Load failed")

    # ------------------------------------------------------------------ jump-to-issue (Phase 5 -> Phase 4)

    def focus_key(self, key: str) -> None:
        if self._state.document is None or self._model is None:
            return
        for index, entry in enumerate(self._state.document.entries):
            if entry.key == key:
                self._component_combo.setCurrentText("All")
                self._status_combo.setCurrentText("All")
                self._search.clear()
                src_index = self._model.index(index, 1)
                proxy_index = self._proxy.mapFromSource(src_index)
                if proxy_index.isValid():
                    self._table.scrollTo(proxy_index, QTableView.ScrollHint.PositionAtCenter)
                    self._table.setCurrentIndex(proxy_index)
                self._on_selection_changed(proxy_index, QModelIndex())
                return

    # ------------------------------------------------------------------ unsaved changes tracking

    def _mark_unsaved(self) -> None:
        """Mark the state as having unsaved changes after an edit."""
        self._state.has_unsaved_changes = True

    # ------------------------------------------------------------------ save

    def _on_save(self) -> None:
        if self._state.document is None or self.is_busy:
            return
        path = self.pick_save_file(
            "Save reviewed workbook as", "Excel files (*.xlsx)", self.default_save_name("reviewed")
        )
        if not path:
            return
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        self.set_busy(True)
        self.status_message.emit(f"Saving reviewed workbook -> {path}")
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
        self._state.set_phase(3, PhaseStatus.DONE)
        self._state.has_unsaved_changes = False
        self.set_busy(False)
        self.status_message.emit(f"Reviewed workbook saved: {path}")

    def _on_save_failed(self, message: str) -> None:
        self.set_busy(False)
        self._state.set_phase(3, PhaseStatus.ERROR)
        self.error(message, "Save failed")

    # ------------------------------------------------------------------ continue to Phase 5

    def _on_continue_to_phase5(self) -> None:
        if self._state.document is not None:
            stats = self._state.document.stats()
            self.status_message.emit(
                f"Document carried forward to Phase 5 "
                f"({stats['total']:,} rows, {stats['translated']:,} translated)."
            )
        self._state.set_phase(3, PhaseStatus.DONE)
        self.request_navigate.emit(4)

    # ------------------------------------------------------------------ pop-out (entire splitter: table + editor)

    def reset_page(self) -> None:
        """Called by Reset Session to clear all displayed widgets back to defaults."""
        if self._model is not None:
            self._model.beginResetModel()
            self._model.endResetModel()
        self._model = None
        self._proxy.setSourceModel(None)
        self._current_row = None
        self._key_field.clear()
        self._source_field.clear()
        self._translation_field.clear()
        self._undo_stack.clear()
        self._component_combo.blockSignals(True)
        self._component_combo.clear()
        self._component_combo.addItem("All")
        self._component_combo.blockSignals(False)
        self._status_combo.setCurrentText("All")
        self._search.clear()
        self._stat_translated["value"].setText("0")
        self._stat_untranslated["value"].setText("0")
        self._stat_issues["value"].setText("0")
        self._status_pill.setText("\u2022  No document loaded")
        self._status_pill.setStyleSheet(
            "padding: 4px 10px; border-radius: 12px; "
            "background: #f1f5f9; color: #475569; font-weight: 700;"
        )
        self._save_btn.setEnabled(False)

    def _on_popout_review(self) -> None:
        if hasattr(self, '_review_dialog') and self._review_dialog is not None:
            self._review_dialog.raise_()
            self._review_dialog.activateWindow()
            return
        self._review_dialog = QDialog(self)
        self._review_dialog.setWindowTitle("Phase 4 \u2014 Browse & Review")
        from .base import clamp_to_screen
        clamp_to_screen(self._review_dialog, 1100, 700)
        self._review_dialog.setWindowFlags(
            self._review_dialog.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        layout = QVBoxLayout(self._review_dialog)
        self._splitter.setParent(self._review_dialog)
        layout.addWidget(self._splitter)
        self._review_dialog.finished.connect(self._on_review_dialog_closed)
        self._review_dialog.show()

    def _on_review_dialog_closed(self) -> None:
        self._splitter.setParent(self._review_box)
        self._review_layout.addWidget(self._splitter)
        self._review_dialog = None
