"""Phase 1 -- Import the source STF file."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...stf import write_stf_files
from ..state import AppState
from ..workers import ParseStfWorker, WriteStfWorker
from .base import PhasePage, make_action_row

_PREVIEW_ROWS = 100


class Phase1ImportPage(PhasePage):
    """File picker + parsed-STF preview + per-phase save buttons."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 1 \u2014 Import STF",
            subtitle=(
                "Select the source ``.stf`` file exported from Salesforce "
                "Translation Workbench. The file is parsed locally; nothing "
                "is sent over the network in this phase."
            ),
            parent=parent,
        )
        self._build()

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        # ---------- File picker row
        picker_row = make_action_row(
            self._make_button("Browse STF...", self._on_browse),
            self._make_button("Re-parse", self._on_reparse, enabled=False, primary=False, key="reparse_btn"),
        )
        self._path_label = QLabel("No file selected.")
        self._path_label.setStyleSheet("color: #4a5568;")
        self._path_label.setWordWrap(True)

        path_box = QGroupBox("Source file")
        path_layout = QFormLayout(path_box)
        path_layout.addRow(self._path_label)
        path_layout.addRow(picker_row)
        self.add_widget(path_box)

        # ---------- Parsed metadata
        self._language_field = QLineEdit()
        self._language_code_field = QLineEdit()
        self._stf_type_field = QLineEdit(); self._stf_type_field.setReadOnly(True)
        self._total_field = QLineEdit(); self._total_field.setReadOnly(True)
        self._translated_field = QLineEdit(); self._translated_field.setReadOnly(True)
        self._untranslated_field = QLineEdit(); self._untranslated_field.setReadOnly(True)
        self._components_field = QLineEdit(); self._components_field.setReadOnly(True)

        meta_box = QGroupBox("Parsed metadata")
        meta_form = QFormLayout(meta_box)
        meta_form.addRow("Language", self._language_field)
        meta_form.addRow("Language code", self._language_code_field)
        meta_form.addRow("STF type", self._stf_type_field)
        meta_form.addRow("Total rows", self._total_field)
        meta_form.addRow("Translated", self._translated_field)
        meta_form.addRow("Untranslated", self._untranslated_field)
        meta_form.addRow("Component types", self._components_field)
        self.add_widget(meta_box)

        # ---------- Preview table
        preview_box = QGroupBox(f"Preview (first {_PREVIEW_ROWS} rows)")
        preview_layout = QFormLayout(preview_box)
        self._preview = QTableWidget(0, 3)
        self._preview.setHorizontalHeaderLabels(["Key", "Label", "Translation"])
        self._preview.horizontalHeader().setStretchLastSection(True)
        self._preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._preview.setAlternatingRowColors(True)
        preview_layout.addRow(self._preview)
        self.add_widget(preview_box, stretch=1)

        # ---------- Actions
        self._save_stf_btn = self._make_button("Save copy as STF...", self._on_save_stf, enabled=False)
        self._reset_btn = self.create_reset_button(1)
        self._next_btn = self._make_button("Continue to Phase 2 \u2192", self._on_next, enabled=False, primary=True)
        actions = make_action_row(self._save_stf_btn, self._reset_btn, self._next_btn)
        self.add_layout(actions)

    def _make_button(self, label: str, handler, *, enabled: bool = True, primary: bool = False, key: str | None = None) -> QPushButton:
        btn = QPushButton(label)
        btn.setEnabled(enabled)
        btn.clicked.connect(handler)
        if primary:
            btn.setStyleSheet("QPushButton { background:#2563eb; color:white; padding:6px 16px; border-radius:6px; }")
        if key:
            setattr(self, key, btn)
        return btn

    # ------------------------------------------------------------------ slots

    def _on_browse(self) -> None:
        path = self.pick_open_file(
            "Select Salesforce STF file",
            "STF files (*.stf);;All files (*)",
        )
        if not path:
            return
        self._parse(path)

    def _on_reparse(self) -> None:
        if self._state.source_stf_path:
            self._parse(self._state.source_stf_path)

    def _parse(self, path: Path) -> None:
        self._state.source_stf_path = path
        self._path_label.setText(str(path))
        self.status_message.emit(f"Parsing {path.name} ...")

        worker = ParseStfWorker(path, self)
        worker.finished_ok.connect(self._on_parsed)
        worker.failed.connect(lambda msg: self.error(msg, "Parse failed"))
        worker.start()
        self.reparse_btn.setEnabled(True)

    def _on_parsed(self, doc) -> None:
        self._state.document = doc
        if doc.language:
            self._state.target_language_name = doc.language
        if doc.language_code:
            self._state.target_language_code = doc.language_code

        stats = doc.stats()
        self._language_field.setText(doc.language)
        self._language_code_field.setText(doc.language_code)
        self._stf_type_field.setText(doc.stf_type)
        self._total_field.setText(f"{stats['total']:,}")
        self._translated_field.setText(f"{stats['translated']:,}")
        self._untranslated_field.setText(f"{stats['untranslated']:,}")
        self._components_field.setText(str(stats["components"]))

        self._populate_preview(doc)
        self._save_stf_btn.setEnabled(True)
        self._next_btn.setEnabled(True)

        self.status_message.emit(
            f"Parsed {stats['total']:,} rows ({stats['untranslated']:,} untranslated) "
            f"across {stats['components']} component types."
        )

    def _populate_preview(self, doc) -> None:
        rows = doc.entries[:_PREVIEW_ROWS]
        self._preview.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            self._preview.setItem(r, 0, QTableWidgetItem(entry.key))
            self._preview.setItem(r, 1, QTableWidgetItem(entry.label))
            self._preview.setItem(r, 2, QTableWidgetItem(entry.translation))
        self._preview.resizeColumnsToContents()
        # Cap initial widths so the row doesn't get pushed off-screen
        for c in range(2):
            if self._preview.columnWidth(c) > 320:
                self._preview.setColumnWidth(c, 320)

    def _on_save_stf(self) -> None:
        if not self._state.document:
            return
        path = self.pick_directory("Choose output folder for STF files")
        if not path:
            return
        # Pull current language values from the fields so the user can correct
        # missing metadata before saving.
        lang = self._language_field.text().strip() or self._state.target_language_name
        code = self._language_code_field.text().strip() or self._state.target_language_code

        self.status_message.emit(f"Writing STF files to {path} ...")
        worker = WriteStfWorker(self._state.document, path, lang, code, self)
        worker.finished_ok.connect(lambda res: self._on_stf_saved(res))
        worker.failed.connect(lambda msg: self.error(msg, "STF write failed"))
        worker.start()

    def _on_stf_saved(self, res) -> None:
        self._state.output_dir = res.full.parent
        files = "\n  ".join(str(p) for p in res.as_list())
        self.info(f"STF files written:\n  {files}", "Saved")
        self.status_message.emit(f"STF files written to {res.full.parent}")

    def _on_next(self) -> None:
        # Sync any user-edited language fields back into shared state.
        if self._language_field.text().strip():
            self._state.target_language_name = self._language_field.text().strip()
        if self._language_code_field.text().strip():
            self._state.target_language_code = self._language_code_field.text().strip()
        self.request_navigate.emit(1)

    def on_reset(self) -> None:
        """Reset Phase 1 UI to initial state."""
        self._path_label.setText("No file selected.")
        self._language_field.clear()
        self._language_code_field.clear()
        self._stf_type_field.clear()
        self._total_field.clear()
        self._translated_field.clear()
        self._untranslated_field.clear()
        self._components_field.clear()
        
        # Clear preview table
        self._preview.setRowCount(0)
        
        # Reset button states
        self.reparse_btn.setEnabled(False)
        self._save_stf_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
