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
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...model import Document, Entry
from ...validate import validate_document
from ..state import AppState, PhaseStatus
from ..workers import ExportExcelWorker, ImportExcelWorker, WriteAuditSheetsWorker
from .base import PhasePage, make_action_row, primary

_HEADERS = ["#", "Key", "Component", "Status", "Label", "Translation"]
_TRANSLATION_COL = 5


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class _EntriesModel(QAbstractTableModel):
    edited = Signal(int)

    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self._doc = doc

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._doc.entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(_HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        entry = self._doc.entries[index.row()]
        col = index.column()
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
        if role == Qt.ItemDataRole.ToolTipRole and col in (4, 5):
            return entry.label if col == 4 else entry.translation
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return section + 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        base = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if index.column() == _TRANSLATION_COL:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if role != Qt.ItemDataRole.EditRole or index.column() != _TRANSLATION_COL:
            return False
        row = index.row()
        old = self._doc.entries[row]
        text = "" if value is None else str(value)
        self._doc.entries[row] = Entry(key=old.key, label=old.label, translation=text)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        status_idx = self.index(row, 3)
        self.dataChanged.emit(status_idx, status_idx, [Qt.ItemDataRole.DisplayRole])
        self.edited.emit(row)
        return True


class _ComponentStatusFilter(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._component = "All"
        self._status = "All"
        self._needle = ""

    def set_component(self, component: str) -> None:
        self._component = component
        self.invalidateFilter()

    def set_status(self, status: str) -> None:
        self._status = status
        self.invalidateFilter()

    def set_search(self, needle: str) -> None:
        self._needle = needle.strip().lower()
        self.invalidateFilter()

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
        # ---------- Compact toolbar (status pill + counters + actions)
        toolbar = QFrame()
        toolbar.setProperty("role", "card")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 10, 12, 10)
        tb_layout.setSpacing(14)

        self._status_pill = QLabel("\u2022  No document loaded")
        self._status_pill.setStyleSheet(
            "padding: 4px 10px; border-radius: 12px; "
            "background: #f1f5f9; color: #475569; font-weight: 600;"
        )
        tb_layout.addWidget(self._status_pill)

        self._stat_translated = self._make_inline_stat("Translated", "0", "#16a34a")
        self._stat_untranslated = self._make_inline_stat("Untranslated", "0", "#d97706")
        self._stat_issues = self._make_inline_stat("Issues", "0", "#dc2626")
        tb_layout.addWidget(self._stat_translated["frame"])
        tb_layout.addWidget(self._stat_untranslated["frame"])
        tb_layout.addWidget(self._stat_issues["frame"])

        tb_layout.addStretch(1)

        self._load_btn = QPushButton("Load reviewed Excel...")
        self._load_btn.setToolTip(
            "Replace the current document with an externally edited workbook.  "
            "It becomes the latest version used by all subsequent phases."
        )
        self._load_btn.clicked.connect(self._on_load_excel)
        tb_layout.addWidget(self._load_btn)
        self.add_widget(toolbar)

        # ---------- Filter row (slim)
        filter_row = QFrame()
        fr_layout = QHBoxLayout(filter_row)
        fr_layout.setContentsMargins(2, 0, 2, 0)
        fr_layout.setSpacing(8)

        fr_layout.addWidget(QLabel("Component:"))
        self._component_combo = QComboBox()
        self._component_combo.addItem("All")
        self._component_combo.currentTextChanged.connect(self._proxy.set_component)
        fr_layout.addWidget(self._component_combo)

        fr_layout.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItems(["All", "Translated", "Untranslated"])
        self._status_combo.currentTextChanged.connect(self._proxy.set_status)
        fr_layout.addWidget(self._status_combo)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by key or label...")
        self._search.textChanged.connect(self._proxy.set_search)
        fr_layout.addWidget(self._search, stretch=1)
        self.add_widget(filter_row)

        # ---------- Splitter: table on top, slim inline editor below
        splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.SelectedClicked
        )
        splitter.addWidget(self._table)

        # Slim editor pane (smaller than v1.2's giant box)
        editor = QFrame()
        editor.setProperty("role", "card")
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
        self._apply_btn = primary(QPushButton("Apply"))
        self._apply_btn.clicked.connect(self._apply_editor_to_row)
        self._reset_btn = QPushButton("Reset to source")
        self._reset_btn.clicked.connect(self._reset_row)
        meta.addWidget(self._apply_btn)
        meta.addWidget(self._reset_btn)

        # Pop-out button inline at far right of key row
        self._popout_editor_btn = QPushButton("\u2197")
        self._popout_editor_btn.setFixedSize(20, 20)
        self._popout_editor_btn.setToolTip("Pop out into a separate window")
        self._popout_editor_btn.setStyleSheet("font-size: 12px; padding: 0; border: none; background: transparent; color: #64748b;")
        self._popout_editor_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._popout_editor_btn.clicked.connect(self._on_popout_editor)
        meta.addWidget(self._popout_editor_btn)

        self._editor_layout.addLayout(meta)

        side_by_side = QHBoxLayout()
        side_by_side.setSpacing(8)
        src_col = QVBoxLayout()
        src_col.setSpacing(2)
        src_col.addWidget(QLabel("Source"))
        self._source_field = QPlainTextEdit()
        self._source_field.setReadOnly(True)
        self._source_field.setMaximumHeight(110)
        src_col.addWidget(self._source_field)
        tgt_col = QVBoxLayout()
        tgt_col.setSpacing(2)
        tgt_col.addWidget(QLabel("Translation (editable)"))
        self._translation_field = QPlainTextEdit()
        self._translation_field.setMaximumHeight(110)
        tgt_col.addWidget(self._translation_field)
        side_by_side.addLayout(src_col, stretch=1)
        side_by_side.addLayout(tgt_col, stretch=1)
        self._editor_layout.addLayout(side_by_side)

        splitter.addWidget(editor)
        self._editor_widget = editor
        self._splitter = splitter
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        self.add_widget(splitter, stretch=1)

        # ---------- Bottom action buttons
        self._save_btn = primary(QPushButton("Save reviewed workbook (.xlsx)"))
        self._save_btn.clicked.connect(self._on_save)
        self._next_btn = QPushButton("Continue to Phase 5 (Validate & Fix) \u2192")
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

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.document is None:
            self._status_pill.setText("\u2022  No document loaded")
            self._status_pill.setStyleSheet(
                "padding: 4px 10px; border-radius: 12px; "
                "background: #f1f5f9; color: #475569; font-weight: 600;"
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
            self._model = _EntriesModel(self._state.document, self)
            self._model.edited.connect(lambda _row: self._update_counters())
            self._proxy.setSourceModel(self._model)
            self._table.selectionModel().currentChanged.connect(self._on_selection_changed)
        else:
            self._model.beginResetModel()
            self._model._doc = self._state.document  # noqa: SLF001
            self._model.endResetModel()

        components = sorted({e.component_type for e in self._state.document.entries})
        self._component_combo.blockSignals(True)
        current = self._component_combo.currentText()
        self._component_combo.clear()
        self._component_combo.addItems(["All", *components])
        if current in {"All", *components}:
            self._component_combo.setCurrentText(current)
        self._component_combo.blockSignals(False)

        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 320)
        self._table.setColumnWidth(2, 120)
        self._table.setColumnWidth(3, 110)
        self._table.setColumnWidth(4, 320)
        self._table.setColumnWidth(5, 320)
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

    # ------------------------------------------------------------------ save

    def _on_save(self) -> None:
        if self._state.document is None or self.is_busy:
            return
        path = self.pick_save_file(
            "Save reviewed workbook as", "Excel files (*.xlsx)", "reviewed.xlsx"
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
        self.request_navigate.emit(4)

    # ------------------------------------------------------------------ pop-out editor

    def _on_popout_editor(self) -> None:
        if hasattr(self, '_editor_dialog') and self._editor_dialog is not None:
            self._editor_dialog.raise_()
            return
        self._editor_dialog = QDialog(self)
        self._editor_dialog.setWindowTitle("Editor - Key / Source / Translation")
        self._editor_dialog.resize(800, 400)
        self._editor_dialog.setWindowFlags(
            self._editor_dialog.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        layout = QVBoxLayout(self._editor_dialog)
        self._editor_widget.setParent(self._editor_dialog)
        layout.addWidget(self._editor_widget)
        self._editor_dialog.finished.connect(self._on_editor_dialog_closed)
        self._editor_dialog.show()
        self._popout_editor_btn.setText("\u2199")
        self._popout_editor_btn.setToolTip("Dock back into the page")
        self._popout_editor_btn.clicked.disconnect()
        self._popout_editor_btn.clicked.connect(self._on_dock_editor_back)

    def _on_dock_editor_back(self) -> None:
        if hasattr(self, '_editor_dialog') and self._editor_dialog is not None:
            self._editor_dialog.close()

    def _on_editor_dialog_closed(self) -> None:
        self._editor_widget.setParent(self)
        self._splitter.addWidget(self._editor_widget)
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 1)
        self._editor_dialog = None
        self._popout_editor_btn.setText("\u2197")
        self._popout_editor_btn.setToolTip("Pop out into a separate window")
        self._popout_editor_btn.clicked.disconnect()
        self._popout_editor_btn.clicked.connect(self._on_popout_editor)
