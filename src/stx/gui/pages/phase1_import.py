"""Phase 1 -- Import the source STF file."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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

from ...languages import LANGUAGE_NAME_TO_CODE, code_for_language, supported_language_names
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
        # ---- Row 0: Translation Language (= the STF target language, read from header)
        # This is the language the STF is translating INTO (e.g. Japanese).
        # It is auto-filled from the STF header but the user can override via dropdown.
        self._stf_lang_combo = QComboBox()
        self._stf_lang_combo.addItems(supported_language_names())
        self._stf_lang_combo.setCurrentIndex(-1)   # blank until a file is loaded
        self._stf_lang_combo.setToolTip(
            "The language this STF file translates INTO — read from the STF header.\n"
            "Change here if the header is missing or incorrect.\n"
            "This value is carried forward to Phase 3 as the translation target."
        )
        self._stf_lang_combo.currentTextChanged.connect(self._on_stf_lang_changed)

        self._stf_lang_code_field = QLineEdit()
        self._stf_lang_code_field.setReadOnly(True)
        self._stf_lang_code_field.setToolTip(
            "Salesforce language code for the translation language (auto-filled from the dropdown)."
        )

        # ---- Row 1: Source Language (= language the labels are written in, e.g. English)
        # Auto-detected from label text via langdetect; user can override.
        # Starts BLANK — populated after the STF is parsed (detection or fallback).
        self._source_language_combo = QComboBox()
        self._source_language_combo.addItems(supported_language_names())
        self._source_language_combo.setCurrentIndex(-1)   # blank until file is loaded
        self._source_language_combo.setToolTip(
            "The language the STF labels are written in — usually English.\n"
            "Auto-detected from label text after parsing; change if incorrect.\n"
            "This is used as the 'source' language in Phase 3 translation."
        )
        self._source_language_combo.currentTextChanged.connect(self._on_source_language_changed)

        self._source_language_code_field = QLineEdit()
        self._source_language_code_field.setReadOnly(True)
        self._source_language_code_field.setToolTip(
            "Salesforce code for the label language (auto-filled from the dropdown)."
        )

        self._source_detect_label = QLabel("")
        self._source_detect_label.setStyleSheet(
            "color: #2563eb; font-size: 11px; font-weight: 700;"
        )

        # ---- Other stat fields
        self._stf_type_field = QLineEdit(); self._stf_type_field.setReadOnly(True)
        self._total_field = QLineEdit(); self._total_field.setReadOnly(True)
        self._translated_field = QLineEdit(); self._translated_field.setReadOnly(True)
        self._untranslated_field = QLineEdit(); self._untranslated_field.setReadOnly(True)
        self._components_field = QLineEdit(); self._components_field.setReadOnly(True)

        meta_box = QGroupBox("Parsed metadata")
        meta_grid = QGridLayout(meta_box)
        meta_grid.setContentsMargins(8, 6, 8, 6)
        meta_grid.setHorizontalSpacing(16)
        meta_grid.setVerticalSpacing(6)

        # Row 0 — Translation language (STF target)
        lbl0a = QLabel("Translation language:")
        lbl0a.setToolTip("The language this STF translates into (from STF header).")
        meta_grid.addWidget(lbl0a, 0, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._stf_lang_combo, 0, 1)
        lbl0b = QLabel("Language code:")
        lbl0b.setToolTip("Salesforce code for the translation language.")
        meta_grid.addWidget(lbl0b, 0, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._stf_lang_code_field, 0, 3)

        # Row 1 — Source / label language
        lbl1a = QLabel("Label language:")
        lbl1a.setToolTip("Language the labels are written in (usually English). Auto-detected.")
        meta_grid.addWidget(lbl1a, 1, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._source_language_combo, 1, 1)
        lbl1b = QLabel("Label code:")
        lbl1b.setToolTip("Salesforce code for the label language.")
        meta_grid.addWidget(lbl1b, 1, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._source_language_code_field, 1, 3)

        # Row 2 — detection info
        meta_grid.addWidget(self._source_detect_label, 2, 1, 1, 3)

        # Row 3 — STF type + total rows
        meta_grid.addWidget(QLabel("STF type:"), 3, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._stf_type_field, 3, 1)
        meta_grid.addWidget(QLabel("Total rows:"), 3, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._total_field, 3, 3)

        # Row 4 — translated + untranslated
        meta_grid.addWidget(QLabel("Translated:"), 4, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._translated_field, 4, 1)
        meta_grid.addWidget(QLabel("Untranslated:"), 4, 2, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._untranslated_field, 4, 3)

        # Row 5 — component types
        meta_grid.addWidget(QLabel("Component types:"), 5, 0, Qt.AlignmentFlag.AlignRight)
        meta_grid.addWidget(self._components_field, 5, 1, 1, 3)

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

    def _on_stf_lang_changed(self, name: str) -> None:
        """Sync translation language code field and state when the dropdown changes."""
        if not name:
            self._stf_lang_code_field.clear()
            return
        code = code_for_language(name) or ""
        self._stf_lang_code_field.setText(code)
        self._state.target_language_name = name
        self._state.target_language_code = code

    def _on_source_language_changed(self, name: str) -> None:
        """Sync source language code field and state when the dropdown changes."""
        code = code_for_language(name) or ""
        self._source_language_code_field.setText(code)
        self._state.source_language_code = code
        self._state.source_language_name = name

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

        # Populate the Translation Language dropdown from the STF header.
        # Block signals so _on_stf_lang_changed doesn't fire redundantly.
        from ...languages import language_for_code as _lang_for_code
        stf_lang_name = _lang_for_code(doc.language_code) or doc.language or ""
        if stf_lang_name:
            self._stf_lang_combo.blockSignals(True)
            # Try to match in the combo; fall back to plain text set
            idx = self._stf_lang_combo.findText(stf_lang_name)
            if idx >= 0:
                self._stf_lang_combo.setCurrentIndex(idx)
            else:
                # Language from header not in our list — show it as-is
                self._stf_lang_combo.setCurrentIndex(-1)
                self._stf_lang_combo.setEditText(stf_lang_name) if hasattr(self._stf_lang_combo, 'setEditText') else None
            self._stf_lang_combo.blockSignals(False)
        self._stf_lang_code_field.setText(doc.language_code or "")

        self._set_field(self._stf_type_field, doc.stf_type)
        self._set_field(self._total_field, f"{stats['total']:,}")
        self._set_field(self._translated_field, f"{stats['translated']:,}")
        self._set_field(self._untranslated_field, f"{stats['untranslated']:,}")
        self._set_field(self._components_field, str(stats["components"]))

        # Auto-detect label language (source language)
        self._detect_source_language(doc)

        self._populate_preview(doc)
        self._save_stf_btn.setEnabled(True)
        self._next_btn.setEnabled(True)

        # Set the active workflow context.
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
        """Run language detection on labels and populate the source language dropdown."""
        try:
            from ...lang_detect import (
                CONFIDENCE_THRESHOLD,
                detect_source_language,
                map_detected_to_salesforce,
            )
            from ...languages import language_for_code
        except ImportError:
            # langdetect not installed — default to English and inform user
            self._source_language_combo.blockSignals(True)
            self._source_language_combo.setCurrentText("English")
            self._source_language_combo.blockSignals(False)
            self._source_language_code_field.setText(code_for_language("English") or "en_US")
            self._state.source_language_code = code_for_language("English") or "en_US"
            self._state.source_language_name = "English"
            self._source_detect_label.setText(
                "Auto-detect unavailable — defaulted to English. Change if incorrect."
            )
            return

        labels = [e.label for e in doc.entries if e.label]
        if not labels:
            self._source_detect_label.setText("(no labels to detect from)")
            return

        detected = detect_source_language(labels)
        if not detected:
            # Can't detect — default to English
            self._source_language_combo.blockSignals(True)
            self._source_language_combo.setCurrentText("English")
            self._source_language_combo.blockSignals(False)
            self._source_language_code_field.setText(code_for_language("English") or "en_US")
            self._state.source_language_code = code_for_language("English") or "en_US"
            self._state.source_language_name = "English"
            self._source_detect_label.setText(
                "Could not detect — defaulted to English. Change if incorrect."
            )
            return

        iso_code, confidence = detected[0]
        if confidence < CONFIDENCE_THRESHOLD:
            # Low confidence — default to English as the safe fallback
            self._source_language_combo.blockSignals(True)
            self._source_language_combo.setCurrentText("English")
            self._source_language_combo.blockSignals(False)
            self._source_language_code_field.setText(code_for_language("English") or "en_US")
            self._state.source_language_code = code_for_language("English") or "en_US"
            self._state.source_language_name = "English"
            self._source_detect_label.setText(
                f"Low confidence ({iso_code}, {confidence * 100:.0f}%) — defaulted to English. "
                "Change if incorrect."
            )
            return

        # Map ISO code to Salesforce code and set the dropdown
        sf_code = map_detected_to_salesforce(iso_code)
        lang_name = language_for_code(sf_code) if sf_code else None

        if lang_name and lang_name in LANGUAGE_NAME_TO_CODE:
            # Block signals so _on_source_language_changed fires only once
            self._source_language_combo.blockSignals(True)
            self._source_language_combo.setCurrentText(lang_name)
            self._source_language_combo.blockSignals(False)
            # Update code field and state manually
            self._source_language_code_field.setText(sf_code or "")
            self._state.source_language_code = sf_code or ""
            self._state.source_language_name = lang_name
            self._source_detect_label.setText(
                f"\u2713 Auto-detected: {lang_name} ({confidence * 100:.0f}% confidence)"
            )
        else:
            # Detection succeeded but language not in our list — show info
            fallback_name = lang_name or iso_code
            self._source_detect_label.setText(
                f"Detected: {fallback_name} ({confidence * 100:.0f}%) — "
                "not in dropdown list, please select manually."
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
        # Use the translation language dropdown values
        lang = self._stf_lang_combo.currentText().strip() or self._state.target_language_name
        code = self._stf_lang_code_field.text().strip() or self._state.target_language_code

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
        # Sync translation language (STF target) into state
        stf_lang = self._stf_lang_combo.currentText().strip()
        stf_code = self._stf_lang_code_field.text().strip()
        if stf_lang:
            self._state.target_language_name = stf_lang
        if stf_code:
            self._state.target_language_code = stf_code
        # Sync label language (source) into state
        src_name = self._source_language_combo.currentText()
        src_code = code_for_language(src_name) or self._source_language_code_field.text().strip()
        if src_name:
            self._state.source_language_name = src_name
        if src_code:
            self._state.source_language_code = src_code
        self._state.set_phase(0, PhaseStatus.DONE)
        self.request_navigate.emit(1)

    # ------------------------------------------------------------------ pop-out preview

    def reset_page(self) -> None:
        """Called by Reset Session to clear all displayed widgets back to defaults."""
        self._path_label.setText("No file selected.")
        self._stf_lang_combo.setCurrentIndex(-1)
        self._stf_lang_code_field.clear()
        self._source_language_combo.setCurrentIndex(-1)
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
