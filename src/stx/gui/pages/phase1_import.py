"""Phase 1 -- Import the source STF file."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...stf import write_stf_files
from ..state import AppState, PhaseStatus
from ..workers import ParseStfWorker, WriteStfWorker
from .base import PhasePage, add_popout_to_groupbox, make_action_row

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
        # ---------- File picker row (label + buttons on ONE line)
        self._path_label = QLabel("No file selected.")
        self._path_label.setStyleSheet("font-weight: 700; color: #cbd5e1;")
        self._path_label.setWordWrap(False)

        path_box = QGroupBox("Source file")
        path_row = QHBoxLayout(path_box)
        path_row.setContentsMargins(8, 4, 8, 4)
        path_row.setSpacing(8)
        path_row.addWidget(self._path_label, stretch=1)
        browse_btn = self._make_button("Browse STF...", self._on_browse)
        browse_btn.setToolTip(
            "Select a .stf file exported from Salesforce Translation Workbench. "
            "The file is parsed locally; nothing is sent over the network here."
        )
        path_row.addWidget(browse_btn)
        reparse_btn = self._make_button("Re-parse", self._on_reparse, enabled=False, primary=False, key="reparse_btn")
        reparse_btn.setToolTip(
            "Re-read the same .stf file from disk. "
            "Useful if the file changed externally since you last loaded it."
        )
        path_row.addWidget(reparse_btn)
        self.add_widget(path_box)

        # ---------- Parsed metadata (2-column grid)
        self._language_field = QLineEdit()
        self._language_field.setToolTip(
            "Human-readable target language name (e.g. Japanese). "
            "Auto-filled from the STF header; edit if it's missing or wrong."
        )
        self._language_code_field = QLineEdit()
        self._language_code_field.setToolTip(
            "Salesforce language code (e.g. ja, fr, de). "
            "Auto-filled from the STF header; edit if it's missing or wrong."
        )
        self._stf_type_field = QLineEdit(); self._stf_type_field.setReadOnly(True)
        self._total_field = QLineEdit(); self._total_field.setReadOnly(True)
        self._translated_field = QLineEdit(); self._translated_field.setReadOnly(True)
        self._untranslated_field = QLineEdit(); self._untranslated_field.setReadOnly(True)
        self._components_field = QLineEdit(); self._components_field.setReadOnly(True)

        meta_box = QGroupBox("Parsed metadata")
        meta_grid = QGridLayout(meta_box)
        meta_grid.setContentsMargins(8, 4, 8, 4)
        meta_grid.setHorizontalSpacing(16)
        meta_grid.setVerticalSpacing(4)

        # Row 0
        meta_grid.addWidget(QLabel("Language:"), 0, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._language_field, 0, 1)
        meta_grid.addWidget(QLabel("Language code:"), 0, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._language_code_field, 0, 3)
        # Row 1 - Source language (auto-detected)
        self._source_language_field = QLineEdit()
        self._source_language_field.setToolTip(
            "Auto-detected source language. Edit if incorrect."
        )
        self._source_language_code_field = QLineEdit()
        self._source_language_code_field.setToolTip(
            "Salesforce code for the detected source language."
        )
        self._source_detect_label = QLabel("")
        self._source_detect_label.setStyleSheet(
            "color: #2563eb; font-size: 12px; font-weight: 700;"
        )
        meta_grid.addWidget(QLabel("Source language:"), 1, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._source_language_field, 1, 1)
        meta_grid.addWidget(QLabel("Source code:"), 1, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._source_language_code_field, 1, 3)
        # Row 2
        meta_grid.addWidget(QLabel("STF type:"), 2, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._stf_type_field, 2, 1)
        meta_grid.addWidget(QLabel("Total rows:"), 2, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._total_field, 2, 3)
        # Row 3
        meta_grid.addWidget(QLabel("Translated:"), 3, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._translated_field, 3, 1)
        meta_grid.addWidget(QLabel("Untranslated:"), 3, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._untranslated_field, 3, 3)
        # Row 4
        meta_grid.addWidget(QLabel("Component types:"), 4, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._components_field, 4, 1, 1, 3)
        # Row 5 - Detection info label
        meta_grid.addWidget(self._source_detect_label, 5, 1, 1, 3)

        meta_grid.setColumnStretch(1, 1)
        meta_grid.setColumnStretch(3, 1)
        self.add_widget(meta_box)

        # ---------- Preview table
        preview_box = QGroupBox(f"Preview (first {_PREVIEW_ROWS} rows)")
        self._preview_box = preview_box
        self._preview_layout = QVBoxLayout(preview_box)
        self._preview_layout.setContentsMargins(4, 4, 4, 4)
        self._preview_layout.setSpacing(2)

        self._preview = QTableWidget(0, 3)
        self._preview.setHorizontalHeaderLabels(["Key", "Label", "Translation"])
        self._preview.horizontalHeader().setStretchLastSection(True)
        self._preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._preview.setAlternatingRowColors(True)
        self._preview.setToolTip(
            "Read-only preview of the first {} rows of the parsed STF. "
            "Use the pop-out icon (top-right) to view it in a larger window.".format(_PREVIEW_ROWS)
        )
        self._preview_layout.addWidget(self._preview)
        self.add_widget(preview_box, stretch=1)

        # Pop-out icon glued to the top-right of the group box border
        add_popout_to_groupbox(preview_box, self._on_popout_preview)

        # ---------- Actions
        self._save_stf_btn = self._make_button("Save copy as STF...", self._on_save_stf, enabled=False)
        self._save_stf_btn.setToolTip(
            "Write the parsed document back out as the three Salesforce STF files "
            "(full / translated-only / untranslated-only) into a folder you choose."
        )
        self._next_btn = self._make_button("Continue to Phase 2 \u2192", self._on_next, enabled=False, primary=True)
        self._next_btn.setToolTip("Move to the next phase (STF \u2192 Excel).")
        actions = make_action_row(self._save_stf_btn, self._next_btn)
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

    @staticmethod
    def _set_field(field: QLineEdit, value: str) -> None:
        """Set field text and tooltip so long values can be seen on hover."""
        field.setText(value)
        field.setToolTip(value)

    # ------------------------------------------------------------------ slots

    def _on_browse(self) -> None:
        path = self.pick_open_file(
            "Select Salesforce STF file",
            "STF files (*.stf);;All files (*)",
        )
        if not path:
            return
        # If another workflow is already active, ask the user before overriding.
        if not self.check_workflow_override(path):
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
        self._set_field(self._language_field, doc.language)
        self._set_field(self._language_code_field, doc.language_code)
        self._set_field(self._stf_type_field, doc.stf_type)
        self._set_field(self._total_field, f"{stats['total']:,}")
        self._set_field(self._translated_field, f"{stats['translated']:,}")
        self._set_field(self._untranslated_field, f"{stats['untranslated']:,}")
        self._set_field(self._components_field, str(stats["components"]))

        # Auto-detect source language
        self._detect_source_language(doc)

        self._populate_preview(doc)
        self._save_stf_btn.setEnabled(True)
        self._next_btn.setEnabled(True)

        # Set the active workflow context so every subsequent load-in-any-phase
        # will trigger the override confirmation dialog.
        if self._state.source_stf_path:
            self._state.set_active_workflow_context(
                document=doc,
                original_source_path=self._state.source_stf_path,
                current_working_path=self._state.source_stf_path,
                current_working_artifact_type="stf",
                start_phase=0,
                current_phase=0,
                override_existing=False,
                reset_downstream=False,
            )

        # Persist this file in the recent files list and mark phase 1 done.
        try:
            from .. import settings as gui_settings
            from ..state import PhaseStatus

            if self._state.source_stf_path:
                gui_settings.add_recent_file(self._state.source_stf_path)
            self._state.set_phase(0, PhaseStatus.DONE)
        except Exception:  # noqa: BLE001
            pass

        self.status_message.emit(
            f"Parsed {stats['total']:,} rows ({stats['untranslated']:,} untranslated) "
            f"across {stats['components']} component types."
        )
        if self._state.source_stf_path is not None:
            self.action_recorded.emit(f"Load STF ({self._state.source_stf_path.name})")

    def _detect_source_language(self, doc) -> None:
        """Run language detection on labels and populate source language fields."""
        try:
            from ...lang_detect import (
                CONFIDENCE_THRESHOLD,
                detect_source_language,
                map_detected_to_salesforce,
            )
            from ...languages import language_for_code
        except ImportError:
            return

        labels = [e.label for e in doc.entries if e.label]
        detected = detect_source_language(labels)
        if not detected:
            self._source_detect_label.setText("")
            return

        iso_code, confidence = detected[0]
        if confidence < CONFIDENCE_THRESHOLD:
            self._source_detect_label.setText(
                f"Low confidence detection: {iso_code} ({confidence * 100:.0f}%) "
                "-- using default"
            )
            return

        sf_code = map_detected_to_salesforce(iso_code)
        if sf_code:
            lang_name = language_for_code(sf_code) or iso_code
            self._set_field(self._source_language_field, lang_name)
            self._set_field(self._source_language_code_field, sf_code)
            self._state.source_language_code = sf_code
            self._state.source_language_name = lang_name
            self._source_detect_label.setText(
                f"Auto-detected: {lang_name} ({confidence * 100:.0f}%)"
            )
        else:
            self._set_field(self._source_language_field, iso_code)
            self._set_field(self._source_language_code_field, iso_code)
            self._source_detect_label.setText(
                f"Auto-detected: {iso_code} ({confidence * 100:.0f}%)"
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
        self._state.set_phase(0, PhaseStatus.DONE)
        self.request_navigate.emit(1)

    # ------------------------------------------------------------------ pop-out preview

    def reset_page(self) -> None:
        """Called by Reset Session to clear all displayed widgets back to defaults."""
        self._path_label.setText("No file selected.")
        self._language_field.clear()
        self._language_code_field.clear()
        self._source_language_field.clear()
        self._source_language_code_field.clear()
        self._source_detect_label.setText("")
        self._stf_type_field.clear()
        self._total_field.clear()
        self._translated_field.clear()
        self._untranslated_field.clear()
        self._components_field.clear()
        self._preview.setRowCount(0)
        self._save_stf_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        if hasattr(self, 'reparse_btn') and self.reparse_btn is not None:
            self.reparse_btn.setEnabled(False)

    def _on_popout_preview(self) -> None:
        if hasattr(self, '_preview_dialog') and self._preview_dialog is not None:
            self._preview_dialog.raise_()
            self._preview_dialog.activateWindow()
            return
        self._preview_dialog = QDialog(self)
        self._preview_dialog.setWindowTitle("Preview (first 100 rows)")
        from .base import clamp_to_screen
        clamp_to_screen(self._preview_dialog, 800, 500)
        self._preview_dialog.setWindowFlags(
            self._preview_dialog.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        layout = QVBoxLayout(self._preview_dialog)
        self._preview.setParent(self._preview_dialog)
        layout.addWidget(self._preview)
        self._preview_dialog.finished.connect(self._on_preview_dialog_closed)
        self._preview_dialog.show()

    def _on_preview_dialog_closed(self) -> None:
        self._preview.setParent(self._preview_box)
        self._preview_layout.addWidget(self._preview)
        self._preview_dialog = None
