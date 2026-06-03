"""Phase 4 -- Review and edit translations.

The review page presents every entry in a single table.  The
``Translation`` column is editable; everything else is read-only.  A
filter row at the top lets the reviewer narrow by component type or
translation status, which is essential at 36k+ rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
)

from ...model import Document, Entry
from ..state import AppState
from ..workers import ExportExcelWorker, WriteAuditSheetsWorker
from .base import PhasePage, make_action_row

_HEADERS = ["#", "Key", "Component", "Status", "Label", "Translation"]
_TRANSLATION_COL = 5


class _EntriesModel(QAbstractTableModel):
    """Table model backed directly by ``Document.entries``."""

    edited = Signal(int)  # index of edited row

    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self._doc = doc

    # ---- read

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: D401, N802
        return 0 if parent.isValid() else len(self._doc.entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: D401, N802
        return len(_HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: D401, N802
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

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: D401, N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return section + 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: D401, N802
        base = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if index.column() == _TRANSLATION_COL:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    # ---- write

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:  # noqa: D401, N802
        if role != Qt.ItemDataRole.EditRole or index.column() != _TRANSLATION_COL:
            return False
        row = index.row()
        old = self._doc.entries[row]
        text = "" if value is None else str(value)
        self._doc.entries[row] = Entry(key=old.key, label=old.label, translation=text)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        # Also signal the Status column may have changed.
        status_idx = self.index(row, 3)
        self.dataChanged.emit(status_idx, status_idx, [Qt.ItemDataRole.DisplayRole])
        self.edited.emit(row)
        return True


class _ComponentStatusFilter(QSortFilterProxyModel):
    """Custom proxy that filters by component, status, and key/label search."""

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

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: D401, N802
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


class Phase4ReviewPage(PhasePage):
    """In-app review and edit of translations."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 4 \u2014 Review",
            subtitle=(
                "Inspect every translation and edit any cells that need correction. "
                "Filter by component type or status to focus your review. The "
                "edited workbook can be saved at any time."
            ),
            parent=parent,
        )
        self._model: Optional[_EntriesModel] = None
        self._proxy: _ComponentStatusFilter = _ComponentStatusFilter(self)
        self._build()

    def _build(self) -> None:
        # ---------- Filter row
        filter_box = QGroupBox("Filter")
        filter_layout = QHBoxLayout(filter_box)
        filter_layout.addWidget(QLabel("Component:"))
        self._component_combo = QComboBox()
        self._component_combo.addItem("All")
        self._component_combo.currentTextChanged.connect(self._proxy.set_component)
        filter_layout.addWidget(self._component_combo)
        filter_layout.addSpacing(12)

        filter_layout.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItems(["All", "Translated", "Untranslated"])
        self._status_combo.currentTextChanged.connect(self._proxy.set_status)
        filter_layout.addWidget(self._status_combo)
        filter_layout.addSpacing(12)

        filter_layout.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by key or label substring ...")
        self._search.textChanged.connect(self._proxy.set_search)
        filter_layout.addWidget(self._search, stretch=1)
        self.add_widget(filter_box)

        # ---------- Table
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.SelectedClicked)
        self.add_widget(self._table, stretch=1)

        # ---------- Counters
        self._counters = QLabel("")
        self._counters.setStyleSheet("color: #4a5568;")
        self.add_widget(self._counters)

        # ---------- Actions
        self._save_btn = QPushButton("Save reviewed workbook (.xlsx)")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setStyleSheet("QPushButton { background:#2563eb; color:white; padding:6px 16px; border-radius:6px; }")

        self._reset_btn = self.create_reset_button(4)

        self._next_btn = QPushButton("Continue to Phase 5 \u2192")
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(4))

        self.add_layout(make_action_row(self._save_btn, self._reset_btn, self._next_btn))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.document is None:
            self._counters.setText("No document loaded yet.")
            self._save_btn.setEnabled(False)
            return
        self._save_btn.setEnabled(True)

        if self._model is None:
            self._model = _EntriesModel(self._state.document, self)
            self._model.edited.connect(lambda _row: self._update_counters())
            self._proxy.setSourceModel(self._model)
        else:
            # Document may have been swapped underneath -- rebind.
            self._model.beginResetModel()
            self._model._doc = self._state.document  # noqa: SLF001 (intentional)
            self._model.endResetModel()

        # Refresh component combo
        components = sorted({e.component_type for e in self._state.document.entries})
        self._component_combo.blockSignals(True)
        current = self._component_combo.currentText()
        self._component_combo.clear()
        self._component_combo.addItems(["All", *components])
        if current in {"All", *components}:
            self._component_combo.setCurrentText(current)
        self._component_combo.blockSignals(False)

        # Reasonable column widths
        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 320)
        self._table.setColumnWidth(2, 120)
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 320)
        self._table.setColumnWidth(5, 320)
        self._update_counters()

    # ------------------------------------------------------------------ slots

    def _update_counters(self) -> None:
        if self._state.document is None:
            return
        stats = self._state.document.stats()
        self._counters.setText(
            f"Total: {stats['total']:,}   "
            f"Translated: {stats['translated']:,}   "
            f"Untranslated: {stats['untranslated']:,}   "
            f"Components: {stats['components']}"
        )

    def _on_save(self) -> None:
        if self._state.document is None:
            return
        suggested = (
            self._state.translated_xlsx_path or self._state.organized_xlsx_path or Path.cwd() / "reviewed.xlsx"
        )
        path = self.pick_save_file(
            "Save reviewed workbook as",
            "Excel files (*.xlsx)",
            "reviewed.xlsx",
        )
        if not path:
            return
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

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
                audit.failed.connect(lambda msg: self.error(msg, "Save failed"))
                audit.start()
            else:
                self._on_saved(path)

        worker.finished_ok.connect(_then_audit)
        worker.failed.connect(lambda msg: self.error(msg, "Save failed"))
        worker.start()

    def _on_saved(self, path: Path) -> None:
        self._state.reviewed_xlsx_path = path
        self._state.output_dir = path.parent
        self.status_message.emit(f"Reviewed workbook saved: {path}")

    def on_reset(self) -> None:
        """Reset Phase 4 UI to initial state."""
        # Clear the table model if it exists
        if self._model is not None:
            self._model.beginResetModel()
            self._model.endResetModel()
            
        # Reset filters
        self._component_combo.blockSignals(True)
        self._component_combo.clear()
        self._component_combo.addItem("All")
        self._component_combo.blockSignals(False)
        
        self._status_combo.setCurrentText("All")
        self._search.clear()
        
        # Clear counters
        self._counters.setText("")
        
        # Reset button state
        self._save_btn.setEnabled(False)
