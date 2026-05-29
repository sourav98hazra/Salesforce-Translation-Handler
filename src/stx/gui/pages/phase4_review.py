"""Phase 4 -- Review and edit translations.

v1.2 additions over v1.1:

* **Load reviewed Excel** -- primary-style button for re-uploading an
  externally edited Excel.  The uploaded document replaces the current
  one and becomes the "latest" version going forward.
* **Auto-validate on entry** -- when the user navigates to this phase,
  validation runs automatically and a banner displays the issue count
  (e.g. "3 errors, 2 warnings -- click Continue to fix").
* **Navigation** now points to Phase 5 (Validate & Fix) instead of
  directly to Export.
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
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
)

from ...model import Document, Entry
from ...validate import validate_document
from ..state import AppState, PhaseStatus
from ..workers import ExportExcelWorker, ImportExcelWorker, WriteAuditSheetsWorker
from .base import PhasePage, make_action_row, primary

_HEADERS = ["#", "Key", "Component", "Status", "Label", "Translation"]
_TRANSLATION_COL = 5


class _EntriesModel(QAbstractTableModel):
    """Table model backed directly by ``Document.entries``."""

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


class Phase4ReviewPage(PhasePage):
    """In-app review and edit of translations.

    v1.2: auto-validate on enter, prominent "Load Excel" for re-upload,
    validation banner, navigation to Phase 5 (Validate & Fix).
    """

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 4 \u2014 Review",
            subtitle=(
                "Review translations and edit any that need correction.  "
                "You can also re-upload an externally edited Excel here -- "
                "it will replace the current document and become the latest "
                "version.  Validation runs automatically on entry so you "
                "can see issues before moving to the next phase."
            ),
            parent=parent,
        )
        self._model: Optional[_EntriesModel] = None
        self._proxy = _ComponentStatusFilter(self)
        self._current_row: Optional[int] = None
        self._build()

    def _build(self) -> None:
        # ---------- Validation banner (auto-populated on_enter)
        self._validation_banner = QLabel("")
        self._validation_banner.setWordWrap(True)
        self._validation_banner.setStyleSheet(
            "padding: 10px; border-radius: 6px; font-weight: 600;"
        )
        self._validation_banner.setVisible(False)
        self.add_widget(self._validation_banner)

        # ---------- Load Excel row (prominent)
        load_box = QGroupBox("Load / re-upload reviewed Excel")
        load_layout = QHBoxLayout(load_box)
        self._load_btn = primary(QPushButton("Load reviewed Excel (.xlsx)..."))
        self._load_btn.setToolTip(
            "Replace the current document with an externally edited workbook.  "
            "This becomes the latest version used by all subsequent phases."
        )
        self._load_btn.clicked.connect(self._on_load_excel)
        load_layout.addWidget(self._load_btn)
        load_layout.addWidget(
            QLabel(
                "Upload an Excel you edited outside the app.  "
                "It replaces the current document and becomes the latest."
            )
        )
        load_layout.addStretch(1)
        self.add_widget(load_box)

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

        # ---------- Splitter: table + side-by-side editor
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

        # Side-by-side editor
        editor_box = QGroupBox("Selected row -- side-by-side editor")
        editor_layout = QVBoxLayout(editor_box)

        meta_row = QHBoxLayout()
        self._key_field = QLineEdit()
        self._key_field.setReadOnly(True)
        self._key_field.setStyleSheet("font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace;")
        meta_row.addWidget(QLabel("Key:"))
        meta_row.addWidget(self._key_field, stretch=1)
        editor_layout.addLayout(meta_row)

        side_by_side = QHBoxLayout()
        src_box = QVBoxLayout()
        src_box.addWidget(QLabel("Source label"))
        self._source_field = QPlainTextEdit()
        self._source_field.setReadOnly(True)
        src_box.addWidget(self._source_field)
        side_by_side.addLayout(src_box, stretch=1)

        tgt_box = QVBoxLayout()
        tgt_box.addWidget(QLabel("Translation (editable)"))
        self._translation_field = QPlainTextEdit()
        tgt_box.addWidget(self._translation_field)
        side_by_side.addLayout(tgt_box, stretch=1)

        editor_layout.addLayout(side_by_side)

        editor_actions = QHBoxLayout()
        self._save_row_btn = primary(QPushButton("Apply to row"))
        self._save_row_btn.clicked.connect(self._apply_editor_to_row)
        self._reset_row_btn = QPushButton("Reset row to source")
        self._reset_row_btn.clicked.connect(self._reset_row)
        editor_actions.addWidget(self._save_row_btn)
        editor_actions.addWidget(self._reset_row_btn)
        editor_actions.addStretch(1)
        editor_layout.addLayout(editor_actions)

        splitter.addWidget(editor_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.add_widget(splitter, stretch=1)

        # Counters
        self._counters = QLabel("")
        self._counters.setStyleSheet("color: #4a5568;")
        self.add_widget(self._counters)

        # Actions
        self._save_btn = primary(QPushButton("Save reviewed workbook (.xlsx)"))
        self._save_btn.clicked.connect(self._on_save)
        # Phase 5 is now "Validate & Fix" (index 5 in the new 7-phase layout)
        self._next_btn = QPushButton("Continue to Phase 5 (Validate & Fix) \u2192")
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(5))
        self.add_layout(make_action_row(self._save_btn, self._next_btn))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.document is None:
            self._counters.setText("No document loaded yet.")
            self._save_btn.setEnabled(False)
            self._validation_banner.setVisible(False)
            return
        self._save_btn.setEnabled(True)

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
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 320)
        self._table.setColumnWidth(5, 320)
        self._update_counters()

        # --- Auto-validate on entry ---
        self._run_auto_validation()

    def _run_auto_validation(self) -> None:
        """Run validation and show a summary banner."""
        if self._state.document is None:
            self._validation_banner.setVisible(False)
            return
        report = validate_document(self._state.document)
        if not report.issues:
            self._validation_banner.setText(
                "\u2713  No validation issues found.  You may proceed to export."
            )
            self._validation_banner.setStyleSheet(
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #dcfce7; color: #166534; border: 1px solid #86efac;"
            )
            self._validation_banner.setVisible(True)
        else:
            self._validation_banner.setText(
                f"\u26a0  {len(report.errors)} error(s), {len(report.warnings)} warning(s) detected.  "
                f"Click 'Continue to Phase 5 (Validate & Fix)' to review and auto-fix them, "
                f"or fix here by editing cells directly."
            )
            style = (
                "padding: 10px; border-radius: 6px; font-weight: 600; "
                "background-color: #fef3c7; color: #92400e; border: 1px solid #fbbf24;"
            )
            if report.has_errors:
                style = (
                    "padding: 10px; border-radius: 6px; font-weight: 600; "
                    "background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;"
                )
            self._validation_banner.setStyleSheet(style)
            self._validation_banner.setVisible(True)
        self.status_message.emit(
            f"Auto-validation: {len(report.errors)} error(s), {len(report.warnings)} warning(s)."
        )

    # ------------------------------------------------------------------ counters

    def _update_counters(self) -> None:
        if self._state.document is None:
            return
        stats = self._state.document.stats()
        self._counters.setText(
            f"Total: {stats['total']:,}   Translated: {stats['translated']:,}   "
            f"Untranslated: {stats['untranslated']:,}   Components: {stats['components']}"
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
        """Re-upload an externally edited Excel as the new latest document."""
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
        self.on_enter()  # refresh table + run auto-validate
        self.status_message.emit(
            f"Loaded {len(doc.entries):,} rows from {path.name}.  "
            f"This is now the latest version."
        )
        try:
            from .. import settings as gui_settings
            gui_settings.add_recent_file(path)
        except Exception:  # noqa: BLE001
            pass

    def _on_load_failed(self, msg: str) -> None:
        self.set_busy(False)
        self.error(msg, "Load failed")

    # ------------------------------------------------------------------ jump-to-issue

    def focus_key(self, key: str) -> None:
        """Find ``key`` in the table and select it (called by Phase 5/6)."""
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
        path = self.pick_save_file("Save reviewed workbook as", "Excel files (*.xlsx)", "reviewed.xlsx")
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
        self._state.set_phase(4, PhaseStatus.DONE)
        self.set_busy(False)
        self.status_message.emit(f"Reviewed workbook saved: {path}")

    def _on_save_failed(self, message: str) -> None:
        self.set_busy(False)
        self._state.set_phase(4, PhaseStatus.ERROR)
        self.error(message, "Save failed")
