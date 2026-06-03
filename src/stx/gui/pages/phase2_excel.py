"""Phase 2 -- Convert the parsed STF into an organised Excel workbook."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ..state import AppState
from ..workers import ExportExcelWorker, ImportExcelWorker
from .base import PhasePage, make_action_row


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
        # Output path row
        path_box = QGroupBox("Output workbook")
        path_layout = QHBoxLayout(path_box)
        self._path_field = QLineEdit()
        self._path_field.setPlaceholderText("Choose where to write the organised .xlsx ...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_save)
        path_layout.addWidget(self._path_field, stretch=1)
        path_layout.addWidget(browse_btn)
        self.add_widget(path_box)

        # Status / summary
        self._summary_label = QLabel("No document loaded yet \u2014 complete Phase 1 first.")
        self._summary_label.setStyleSheet("color: #4a5568;")
        self.add_widget(self._summary_label)

        # Content Details preview
        details_box = QGroupBox("Content Details (post-export preview)")
        details_layout = QHBoxLayout(details_box)
        self._details = QTableWidget(0, 5)
        self._details.setHorizontalHeaderLabels([
            "SheetName", "SavedAs", "ComponentType", "TranslationStatus", "TotalRecords",
        ])
        self._details.horizontalHeader().setStretchLastSection(True)
        self._details.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._details.setAlternatingRowColors(True)
        details_layout.addWidget(self._details)
        self.add_widget(details_box, stretch=1)

        # Actions
        self._convert_btn = QPushButton("Convert and save .xlsx")
        self._convert_btn.clicked.connect(self._on_convert)
        self._convert_btn.setStyleSheet("QPushButton { background:#2563eb; color:white; padding:6px 16px; border-radius:6px; }")

        self._load_btn = QPushButton("Load existing organised .xlsx ...")
        self._load_btn.clicked.connect(self._on_load_existing)

        self._reset_btn = self.create_reset_button(2)

        self._next_btn = QPushButton("Continue to Phase 3 \u2192")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(2))

        self.add_layout(make_action_row(self._convert_btn, self._load_btn, self._reset_btn, self._next_btn))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.document is None:
            self._summary_label.setText("No document loaded \u2014 complete Phase 1 or load an existing workbook.")
            self._convert_btn.setEnabled(False)
            return
        stats = self._state.document.stats()
        self._summary_label.setText(
            f"Document ready: {stats['total']:,} rows, "
            f"{stats['untranslated']:,} untranslated, {stats['components']} component types."
        )
        self._convert_btn.setEnabled(True)
        # Suggest a default output path based on the source STF.
        if not self._path_field.text():
            src = self._state.source_stf_path
            if src is not None:
                self._path_field.setText(str(src.with_suffix("")) + "_organized.xlsx")

    # ------------------------------------------------------------------ slots

    def _on_browse_save(self) -> None:
        path = self.pick_save_file(
            "Save organised workbook as",
            "Excel files (*.xlsx)",
            "organized.xlsx",
        )
        if path:
            self._path_field.setText(str(path))

    def _on_convert(self) -> None:
        if self._state.document is None:
            self.warn("Load an STF file in Phase 1 first.")
            return
        path_text = self._path_field.text().strip()
        if not path_text:
            self.warn("Choose an output path first.")
            return
        path = Path(path_text)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        self.status_message.emit(f"Exporting {len(self._state.document.entries):,} rows -> {path} ...")
        worker = ExportExcelWorker(self._state.document, path, self)
        worker.finished_ok.connect(self._on_exported)
        worker.failed.connect(lambda msg: self.error(msg, "Export failed"))
        worker.start()

    def _on_exported(self, result) -> None:
        self._state.organized_xlsx_path = result.path
        self._state.output_dir = result.path.parent
        self._populate_details(result)
        self.status_message.emit(
            f"Wrote {len(result.sheets_written)} sheets to {result.path}"
        )
        self._next_btn.setEnabled(True)

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

    def _on_load_existing(self) -> None:
        path = self.pick_open_file("Select organised workbook", "Excel files (*.xlsx)")
        if not path:
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
        self._path_field.setText(str(path))
        self.on_enter()
        self.status_message.emit(f"Loaded {len(doc.entries):,} rows from {path.name}")
        self._next_btn.setEnabled(True)

    def on_reset(self) -> None:
        """Reset Phase 2 UI to initial state."""
        self._path_field.clear()
        self._summary_label.setText("No document loaded yet \u2014 complete Phase 1 first.")
        self._details.setRowCount(0)
        self._convert_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
