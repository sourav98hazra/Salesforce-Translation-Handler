"""Phase 3 (index 2) -- Translate.

v1.4 layout: compact form at top, progress bar, then the live feed
taking all remaining space.  Counter boxes replaced by inline counts
in the feed.  Component selection moved to a dialog behind a button.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...glossary import Glossary
from ...languages import (
    LANGUAGE_NAME_TO_CODE,
    code_for_language,
    supported_language_names,
)
from ...memory import TranslationMemory, default_tm_path
from ...scope import Scope, StatusFilter
from .. import settings as gui_settings
from ..state import AppState, PhaseStatus
from ..workers import ExportExcelWorker, TranslationWorker, WriteAuditSheetsWorker
from .base import PhasePage, make_action_row, primary


# ---------------------------------------------------------------------------
# Component filter dialog
# ---------------------------------------------------------------------------

class _ComponentFilterDialog(QDialog):
    """Modal dialog for selecting which component types to translate."""

    def __init__(self, document, previously_selected: Optional[set[str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filter Components")
        self.setMinimumWidth(400)
        self.setMinimumHeight(350)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Actions row
        actions = QHBoxLayout()
        select_all_btn = QPushButton("Select all")
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        select_none_btn = QPushButton("Select none")
        select_none_btn.clicked.connect(lambda: self._set_all(False))
        invert_btn = QPushButton("Invert")
        invert_btn.clicked.connect(self._invert)
        actions.addWidget(select_all_btn)
        actions.addWidget(select_none_btn)
        actions.addWidget(invert_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        # Component list
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self._list, stretch=1)

        # Populate
        components = sorted({e.component_type for e in document.entries})
        counts: dict[str, int] = {}
        for e in document.entries:
            if not e.translation.strip():
                counts[e.component_type] = counts.get(e.component_type, 0) + 1

        for comp in components:
            count = counts.get(comp, 0)
            item = QListWidgetItem(f"{comp}  \u2014  {count} untranslated")
            item.setData(Qt.ItemDataRole.UserRole, comp)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            should_check = previously_selected is None or comp in previously_selected
            item.setCheckState(Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked)
            self._list.addItem(item)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _set_all(self, checked: bool) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )

    def _invert(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setCheckState(
                Qt.CheckState.Unchecked
                if item.checkState() == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )

    def selected_components(self) -> set[str]:
        selected = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.add(item.data(Qt.ItemDataRole.UserRole))
        return selected


# ---------------------------------------------------------------------------
# Phase 3 page
# ---------------------------------------------------------------------------

class Phase3TranslatePage(PhasePage):
    """Configure and run automatic translation -- compact version."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 3 \u2014 Translate",
            subtitle=(
                "Pick a target language, choose which component types to "
                "include, and start.  Advanced options (backend, glossary, "
                "translation memory, performance) live under "
                "Edit \u2192 Settings."
            ),
            parent=parent,
        )
        self._worker: Optional[TranslationWorker] = None
        self._selected_components: Optional[set[str]] = None
        # Live counters
        self._translated_count = 0
        self._cached_count = 0
        self._deduped_count = 0
        self._skipped_count = 0
        self._total_rows = 0
        self._current_row = 0
        self._start_time: Optional[float] = None
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # ----- Setup section: compact form
        setup_box = QGroupBox("Setup")
        setup_grid = QHBoxLayout()
        setup_grid.setSpacing(16)

        # Left: source + target side by side
        lang_form = QFormLayout()
        lang_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lang_form.setHorizontalSpacing(8)
        lang_form.setVerticalSpacing(4)

        self._source_combo = QComboBox()
        self._source_combo.addItems(supported_language_names())
        self._source_combo.setCurrentText("English")
        lang_form.addRow("Source:", self._source_combo)

        self._target_combo = QComboBox()
        self._target_combo.addItems(supported_language_names())
        self._target_combo.setCurrentText("Japanese")
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        lang_form.addRow("Target:", self._target_combo)

        setup_grid.addLayout(lang_form)

        # Right: output file
        path_form = QFormLayout()
        path_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        path_form.setHorizontalSpacing(8)
        path_form.setVerticalSpacing(4)

        self._path_field = QLineEdit()
        self._path_field.setPlaceholderText("Choose where to save the translated .xlsx")
        path_browse = QPushButton("Browse...")
        path_browse.clicked.connect(self._on_browse_save)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path_field, stretch=1)
        path_row.addWidget(path_browse)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        path_widget.layout().setContentsMargins(0, 0, 0, 0)
        path_form.addRow("Output:", path_widget)

        # Filter Components button + estimate
        filter_row = QHBoxLayout()
        self._filter_btn = QPushButton("Filter Components...")
        self._filter_btn.clicked.connect(self._on_filter_components)
        filter_row.addWidget(self._filter_btn)
        self._estimate_label = QLabel("Rows to translate: --")
        self._estimate_label.setStyleSheet("font-weight: 600;")
        filter_row.addWidget(self._estimate_label)
        filter_row.addStretch(1)
        path_form.addRow("", filter_row)

        setup_grid.addLayout(path_form, stretch=1)

        setup_layout = QVBoxLayout(setup_box)
        setup_layout.setContentsMargins(8, 6, 8, 6)
        setup_layout.addLayout(setup_grid)

        # Settings hint
        self._settings_summary = QLabel("")
        self._settings_summary.setWordWrap(True)
        self._settings_summary.setStyleSheet("color: #64748b; font-size: 11px;")
        setup_layout.addWidget(self._settings_summary)

        self.add_widget(setup_box)

        # ----- Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMaximumHeight(18)
        self.add_widget(self._progress)

        self._eta_label = QLabel("Idle.")
        self._eta_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self.add_widget(self._eta_label)

        # ----- Live feed log (takes all remaining space)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(800)
        self._log.setPlaceholderText("Live feed -- each translated row appears here with inline counters")
        self.add_widget(self._log, stretch=1)

        # ----- Action buttons
        self._start_btn = primary(QPushButton("Start translation"))
        self._start_btn.clicked.connect(self._on_start)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._load_btn = QPushButton("Load .xlsx ...")
        self._load_btn.setToolTip(
            "Load any Excel (organised or translated) directly into this phase.\n"
            "Use this when you want to work independently without going through earlier phases."
        )
        self._load_btn.clicked.connect(self._on_load_existing)
        self._next_btn = QPushButton("Continue to Phase 4 \u2192")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(3))

        self.add_layout(make_action_row(self._start_btn, self._cancel_btn, self._load_btn, self._next_btn))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        # Restore remembered target language.
        remembered = gui_settings.remembered_target_language()
        if remembered in LANGUAGE_NAME_TO_CODE:
            self._target_combo.setCurrentText(remembered)
        if self._state.target_language_name in LANGUAGE_NAME_TO_CODE:
            self._target_combo.setCurrentText(self._state.target_language_name)

        # Default output path.
        if not self._path_field.text():
            base = self._state.organized_xlsx_path or self._state.source_stf_path
            if base is not None:
                self._path_field.setText(str(Path(base).with_suffix("")) + "_translated.xlsx")

        # Restore previously selected components from state
        if self._state.scope is not None and self._state.scope.components is not None:
            self._selected_components = set(self._state.scope.components)
        elif self._state.document is not None:
            self._selected_components = {e.component_type for e in self._state.document.entries}

        self._update_estimate()
        self._refresh_settings_summary()
        self._start_btn.setEnabled(self._state.document is not None and not self.is_busy)

    def _refresh_settings_summary(self) -> None:
        backend = gui_settings.get_str(gui_settings.KEYS.backend, "google")
        workers = gui_settings.get_int(gui_settings.KEYS.workers, 4)
        glossary = gui_settings.get_str(gui_settings.KEYS.glossary_path, "")
        memory = gui_settings.get_str(gui_settings.KEYS.memory_path, "") or str(default_tm_path())
        bits = [f"backend = <b>{backend}</b>", f"workers = <b>{workers}</b>"]
        if glossary:
            bits.append("glossary attached")
        if memory:
            bits.append("TM enabled")
        bits.append("(change via <i>Edit \u2192 Settings...</i>)")
        self._settings_summary.setText("  \u00b7  ".join(bits))

    # ------------------------------------------------------------------ component filter dialog

    def _on_filter_components(self) -> None:
        if self._state.document is None:
            self.warn(
                "No document loaded yet.\n\n"
                "Either:\n"
                "  - Complete Phase 1 (Import STF) first, or\n"
                "  - Click 'Load .xlsx ...' below to load an Excel directly into this phase."
            )
            return
        dlg = _ComponentFilterDialog(
            self._state.document,
            self._selected_components,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._selected_components = dlg.selected_components()
            self._update_estimate()

    def _build_scope(self) -> Optional[Scope]:
        if self._state.document is None:
            return None
        all_components = {e.component_type for e in self._state.document.entries}
        components = self._selected_components if self._selected_components else all_components
        return Scope(
            components=components if components != all_components else None,
            status=StatusFilter.UNTRANSLATED,
            name="GUI scope",
        )

    def _update_estimate(self) -> None:
        if self._state.document is None:
            self._estimate_label.setText("Rows to translate: \u2014 (load a document first)")
            return
        scope = self._build_scope()
        if scope is None:
            return
        count = scope.estimate_count(self._state.document)
        self._total_rows = count
        self._estimate_label.setText(f"Rows to translate: <b>{count:,}</b>")
        self._estimate_label.setTextFormat(Qt.TextFormat.RichText)

    # ------------------------------------------------------------------ output path

    def _on_browse_save(self) -> None:
        path = self.pick_save_file(
            "Save translated workbook as", "Excel files (*.xlsx)", "translated.xlsx"
        )
        if path:
            self._path_field.setText(str(path))

    def _on_target_changed(self, name: str) -> None:
        code = code_for_language(name)
        if code:
            self._state.target_language_name = name
            self._state.target_language_code = code
            gui_settings.remember_target_language(name, code)

    # ------------------------------------------------------------------ translation slot

    def _on_start(self) -> None:
        if self.is_busy:
            self.status_message.emit("Translation already running -- ignoring duplicate click.")
            return

        if self._state.document is None:
            self.warn(
                "No document loaded yet.\n\n"
                "Click 'Load .xlsx ...' to load an Excel directly into this phase,\n"
                "or complete Phase 1 (Import STF) first."
            )
            return

        scope = self._build_scope()
        if scope is None or scope.estimate_count(self._state.document) == 0:
            if not self.confirm(
                "The current scope matches no rows.  Continue anyway?  "
                "(The translator will simply finish immediately.)"
            ):
                return

        self._state.scope = scope
        self._state.target_language_code = code_for_language(self._target_combo.currentText()) or "ja"
        self._state.target_language_name = self._target_combo.currentText()
        gui_settings.remember_target_language(self._state.target_language_name, self._state.target_language_code)

        # ---- Read advanced options from the Settings dialog values.
        workers = gui_settings.get_int(gui_settings.KEYS.workers, 4)
        rate_str = gui_settings.get_str("translation/rate_limit", "8.0")
        try:
            rate_value = float(rate_str)
        except (TypeError, ValueError):
            rate_value = 8.0
        rate_limit = rate_value if rate_value > 0 else None
        prevent_sleep = gui_settings.get_str("translation/prevent_sleep", "1") in {"1", "true", "True"}

        # Glossary
        glossary = None
        glossary_path = gui_settings.get_str(gui_settings.KEYS.glossary_path, "").strip()
        if glossary_path:
            try:
                glossary = Glossary.load_csv(glossary_path)
                self._state.glossary = glossary
                self._state.glossary_path = Path(glossary_path)
            except Exception as exc:  # noqa: BLE001
                self.error(f"Failed to load glossary: {exc}", "Glossary error")
                return

        # Translation memory (defaults to the per-user path if unset)
        memory_path = gui_settings.get_str(gui_settings.KEYS.memory_path, "").strip() or str(default_tm_path())
        try:
            memory = TranslationMemory(path=Path(memory_path))
            self._state.memory = memory
            self._state.memory_path = Path(memory_path)
        except Exception as exc:  # noqa: BLE001
            self.error(f"Failed to open TM at {memory_path}: {exc}", "TM error")
            return

        # ---- Reset live counters
        self._translated_count = 0
        self._cached_count = 0
        self._deduped_count = 0
        self._skipped_count = 0
        self._current_row = 0
        self._total_rows = scope.estimate_count(self._state.document)
        self._start_time = time.time()
        self._log.clear()

        # ---- Live feed header showing language pair
        src_code = code_for_language(self._source_combo.currentText()) or "en"
        self._log.appendPlainText(
            f"\u2500\u2500  {src_code.upper()} \u2192 {self._state.target_language_code.upper()}  "
            f"\u2500\u2500  scope: {self._total_rows:,} rows  "
            f"workers: {workers}\n"
        )

        self._progress.setValue(0)
        self._eta_label.setText("Starting...")
        self._set_running(True)
        self._state.set_phase(2, PhaseStatus.RUNNING)

        self.status_message.emit(
            f"Translating: {self._target_combo.currentText()}, "
            f"workers={workers}, scope={self._total_rows} rows"
        )

        self._worker = TranslationWorker(
            self._state.document,
            source_code=src_code,
            target_code=self._state.target_language_code,
            scope=scope,
            memory=memory,
            glossary=glossary,
            workers=workers,
            rate_limit_per_second=rate_limit,
            prevent_system_sleep=prevent_sleep,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.row_translated.connect(self._on_row_translated)
        self._worker.finished_ok.connect(self._on_translation_done)
        self._worker.failed.connect(self._on_translation_failed)
        self._worker.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self._progress.setValue(percent)

    def _on_row_translated(self, source: str, translation: str, status: str) -> None:
        self._current_row += 1

        # Update running counters from status keywords.
        if status.startswith("Translated"):
            self._translated_count += 1
            if "TM hit" in status:
                self._cached_count += 1
            elif "dedup" in status:
                self._deduped_count += 1
        elif status.startswith("Skipped") or status.startswith("Cancelled") or "Fallback" in status:
            self._skipped_count += 1

        # Inline counters in the feed line
        src_code = (code_for_language(self._source_combo.currentText()) or "en").upper()
        tgt_code = (self._state.target_language_code or "ja").upper()
        prefix = (
            f"[{self._current_row}/{self._total_rows} | "
            f"T:{self._translated_count} TM:{self._cached_count} D:{self._deduped_count}]"
        )

        if translation:
            self._log.appendPlainText(f"{prefix} {src_code}: {source} -> {tgt_code}: {translation}")
        else:
            self._log.appendPlainText(f"{prefix} [{status}] {source}")

        # Intermittent summary every 50 rows
        if self._current_row % 50 == 0 and self._start_time is not None:
            elapsed = time.time() - self._start_time
            rate = self._current_row / elapsed if elapsed > 0 else 0
            remaining = self._total_rows - self._current_row
            eta = remaining / rate if rate > 0 else 0
            self._log.appendPlainText(
                f"  --- {self._current_row}/{self._total_rows} "
                f"({self._current_row * 100 // self._total_rows}%) | "
                f"{rate:.1f} rows/s | ETA: {eta:.0f}s ---"
            )

    def _on_translation_done(self, done) -> None:
        self._state.translation_summaries = done.summaries
        self._state.translation_statuses = done.statuses
        elapsed = done.elapsed_seconds

        # Append summary line to the feed
        rate = done.translated_count / elapsed if elapsed > 0 else 0
        self._log.appendPlainText("")
        self._log.appendPlainText("\u2501\u2501\u2501 DONE \u2501\u2501\u2501")
        self._log.appendPlainText(
            f"Translated: {done.translated_count} | TM hits: {done.cached_count} | "
            f"Deduped: {done.deduped_count} | Skipped: {done.skipped_count}"
        )
        self._log.appendPlainText(f"Elapsed: {elapsed:.1f}s | Rate: {rate:.1f} rows/s")

        msg = (
            f"Done.  Translated {done.translated_count:,} "
            f"(TM hits {done.cached_count:,}, dedup {done.deduped_count:,}, "
            f"skipped {done.skipped_count:,})  -  elapsed {elapsed:.1f}s."
        )
        self._eta_label.setText(msg)
        self.status_message.emit(msg)
        self._save_translated()

    def _on_translation_failed(self, message: str) -> None:
        self._set_running(False)
        self._state.set_phase(2, PhaseStatus.ERROR)
        self.error(message, "Translation failed")

    def _save_translated(self) -> None:
        if self._state.document is None:
            self._set_running(False)
            return
        path_text = self._path_field.text().strip()
        if not path_text:
            self._set_running(False)
            self.warn("Choose an output path so the translated workbook can be saved.")
            return
        path = Path(path_text)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        self.status_message.emit(f"Saving translated workbook -> {path} ...")
        worker = ExportExcelWorker(self._state.document, path, self)
        worker.finished_ok.connect(lambda res: self._save_audit_sheets(res.path))
        worker.failed.connect(lambda msg: self._on_save_failed(msg))
        worker.start()

    def _save_audit_sheets(self, path: Path) -> None:
        worker = WriteAuditSheetsWorker(
            path,
            self._state.translation_summaries,
            self._state.translation_statuses,
            parent=self,
        )
        worker.finished_ok.connect(lambda _: self._on_save_done(path))
        worker.failed.connect(lambda msg: self._on_save_failed(msg))
        worker.start()

    def _on_save_done(self, path: Path) -> None:
        self._state.translated_xlsx_path = path
        self._state.output_dir = path.parent
        gui_settings.remember_output_dir(path.parent)
        gui_settings.add_recent_file(path)
        self._set_running(False)
        self._next_btn.setEnabled(True)
        self._state.set_phase(2, PhaseStatus.DONE)
        self.status_message.emit(f"Translated workbook saved: {path}")

    def _on_save_failed(self, message: str) -> None:
        self._set_running(False)
        self._state.set_phase(2, PhaseStatus.ERROR)
        self.error(message, "Save failed")

    def _on_cancel(self) -> None:
        if self._worker is not None and not self._worker.is_cancelled:
            self._worker.cancel()
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Cancelling...")
            self.status_message.emit("Cancellation requested -- finishing in-flight rows...")
        elif self._worker is not None and self._worker.is_cancelled:
            self.status_message.emit("Already cancelling -- please wait.")

    def _on_load_existing(self) -> None:
        """Load any Excel into this phase -- makes Phase 3 fully independent.

        The loaded document becomes the active document for translation.
        Component filter and estimate update automatically after loading.
        """
        if self.is_busy:
            return
        from ..workers import ImportExcelWorker

        path = self.pick_open_file(
            "Load Excel for translation (organised or translated)",
            "Excel files (*.xlsx);;All files (*)",
        )
        if not path:
            return
        self.status_message.emit(f"Loading {path.name} ...")
        worker = ImportExcelWorker(
            path,
            language=self._state.target_language_name,
            language_code=self._state.target_language_code,
            parent=self,
        )

        def _loaded(doc):
            self._state.document = doc
            self._state.organized_xlsx_path = path
            self._state.output_dir = path.parent
            gui_settings.add_recent_file(path)
            # Reset component selection so Filter Components picks up the new doc.
            self._selected_components = {e.component_type for e in doc.entries}
            # Suggest output path based on loaded file.
            if not self._path_field.text() or "translated" not in self._path_field.text().lower():
                self._path_field.setText(str(Path(path).with_suffix("")) + "_translated.xlsx")
            self._next_btn.setEnabled(True)
            self.on_enter()
            self.status_message.emit(
                f"Loaded {len(doc.entries):,} rows from {path.name}.  "
                f"Click 'Filter Components...' to select which to translate, then Start."
            )

        worker.finished_ok.connect(_loaded)
        worker.failed.connect(lambda msg: self.error(msg, "Load failed"))
        worker.start()

    # ------------------------------------------------------------------ helpers

    def _set_running(self, running: bool) -> None:
        self.set_busy(running)
        self._start_btn.setEnabled(not running and self._state.document is not None)
        self._cancel_btn.setEnabled(running)
        self._cancel_btn.setText("Cancel")
        self._load_btn.setEnabled(not running)
        self._target_combo.setEnabled(not running)
        self._source_combo.setEnabled(not running)
        self._filter_btn.setEnabled(not running)
