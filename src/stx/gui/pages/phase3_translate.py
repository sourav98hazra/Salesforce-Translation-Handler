"""Phase 3 -- Auto-translate every untranslated row."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
)

from ...languages import LANGUAGE_NAME_TO_CODE, code_for_language, language_for_code, supported_language_names
from ..state import AppState
from ..workers import ExportExcelWorker, TranslationWorker, WriteAuditSheetsWorker
from .base import PhasePage, make_action_row


class Phase3TranslatePage(PhasePage):
    """Configure and run automatic translation."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 3 \u2014 Translate",
            subtitle=(
                "Auto-translate every untranslated row using Google Translate "
                "(free tier). Salesforce IDs, placeholders, URLs, emails and "
                "ALL-CAPS acronyms are protected from modification, and rich "
                "text (HTML) is translated tag-by-tag without altering "
                "structure or attributes."
            ),
            parent=parent,
        )
        self._worker: TranslationWorker | None = None
        self._start_time: float | None = None
        self._timer: QTimer | None = None
        self._build()

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        # ---------- Language config
        cfg = QGroupBox("Translation configuration")
        cfg_layout = QHBoxLayout(cfg)

        cfg_layout.addWidget(QLabel("Source:"))
        self._source_combo = QComboBox()
        self._source_combo.addItems(supported_language_names())
        self._source_combo.setCurrentText("English")
        cfg_layout.addWidget(self._source_combo)

        cfg_layout.addSpacing(16)

        cfg_layout.addWidget(QLabel("Target:"))
        self._target_combo = QComboBox()
        self._target_combo.addItems(supported_language_names())
        self._target_combo.setCurrentText("Japanese")
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        cfg_layout.addWidget(self._target_combo)

        cfg_layout.addSpacing(16)
        cfg_layout.addWidget(QLabel("Backend:"))
        self._backend_combo = QComboBox()
        self._backend_combo.addItem("Google Translate (free)")
        self._backend_combo.setEnabled(False)
        cfg_layout.addWidget(self._backend_combo)

        cfg_layout.addStretch(1)
        self.add_widget(cfg)

        # ---------- Output path
        path_box = QGroupBox("Translated workbook output")
        path_layout = QHBoxLayout(path_box)
        self._path_field = QLineEdit()
        self._path_field.setPlaceholderText("Where to save the translated .xlsx ...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._on_browse_save)
        path_layout.addWidget(self._path_field, stretch=1)
        path_layout.addWidget(browse)
        self.add_widget(path_box)

        # ---------- Progress + log
        progress_box = QGroupBox("Progress")
        progress_layout = QHBoxLayout(progress_box)
        
        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        progress_layout.addWidget(self._progress)
        
        # ETA and timing display
        self._eta_label = QLabel("ETA: --:--")
        self._eta_label.setMinimumWidth(80)
        self._elapsed_label = QLabel("Elapsed: 00:00")
        self._elapsed_label.setMinimumWidth(80)
        
        progress_layout.addWidget(self._elapsed_label)
        progress_layout.addWidget(self._eta_label)
        
        self.add_widget(progress_box)

        log_box = QGroupBox("Live status (last 200 events)")
        log_layout = QHBoxLayout(log_box)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(200)
        self._log.setStyleSheet("font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace; font-size: 11px;")
        log_layout.addWidget(self._log)
        self.add_widget(log_box, stretch=1)

        # ---------- Actions
        self._start_btn = QPushButton("Start translation")
        self._start_btn.setStyleSheet("QPushButton { background:#2563eb; color:white; padding:6px 16px; border-radius:6px; }")
        self._start_btn.clicked.connect(self._on_start)

        self._retranslate_btn = QPushButton("Retranslate all rows")
        self._retranslate_btn.setStyleSheet("QPushButton { background:#dc2626; color:white; padding:6px 16px; border-radius:6px; }")
        self._retranslate_btn.clicked.connect(self._on_retranslate)
        self._retranslate_btn.setVisible(False)  # Hidden by default

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._load_btn = QPushButton("Load translated .xlsx ...")
        self._load_btn.clicked.connect(self._on_load_existing)

        self._reset_btn = self.create_reset_button(3)

        self._next_btn = QPushButton("Continue to Phase 4 \u2192")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(3))

        self.add_layout(make_action_row(self._start_btn, self._retranslate_btn, self._cancel_btn, self._load_btn, self._reset_btn, self._next_btn))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        if self._state.target_language_name in LANGUAGE_NAME_TO_CODE:
            self._target_combo.setCurrentText(self._state.target_language_name)

        if not self._path_field.text():
            base = self._state.organized_xlsx_path or self._state.source_stf_path
            if base is not None:
                self._path_field.setText(str(base.with_suffix("")) + "_translated.xlsx")

        self._start_btn.setEnabled(self._state.document is not None)
        self._update_button_visibility()

    # ------------------------------------------------------------------ slots

    def _on_target_changed(self, name: str) -> None:
        code = code_for_language(name)
        if code:
            self._state.target_language_name = name
            self._state.target_language_code = code

    def _on_browse_save(self) -> None:
        path = self.pick_save_file("Save translated workbook as", "Excel files (*.xlsx)", "translated.xlsx")
        if path:
            self._path_field.setText(str(path))

    def _on_retranslate(self) -> None:
        """Start retranslation of all rows, including existing translations."""
        if self._state.document is None:
            self.warn("Load a document first (Phase 1 or load an organised .xlsx).")
            return

        target_name = self._target_combo.currentText()
        target_code = code_for_language(target_name) or "ja"
        source_name = self._source_combo.currentText()
        source_code = code_for_language(source_name) or "en"

        self._state.source_language_code = source_code
        self._state.target_language_code = target_code
        self._state.target_language_name = target_name

        self._log.clear()
        self._progress.setValue(0)
        
        # Initialize timing
        self._start_time = time.time()
        self._eta_label.setText("ETA: calculating...")
        self._elapsed_label.setText("Elapsed: 00:00")
        
        # Setup timer to update elapsed time
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_elapsed_time)
        self._timer.start(1000)  # Update every second
        
        self._set_running(True)
        self.status_message.emit(
            f"Retranslating ALL {len(self._state.document.entries):,} rows: "
            f"{source_name} -> {target_name}"
        )

        # Use retranslate_all=True for this worker
        self._worker = TranslationWorker(
            self._state.document,
            source_code=source_code,
            target_code=target_code,
            retranslate_all=True,  # This is the key difference
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_translation_done)
        self._worker.failed.connect(self._on_translation_failed)
        self._worker.start()

    def _update_button_visibility(self) -> None:
        """Show/hide the retranslate button based on document state."""
        if self._state.document is None:
            self._retranslate_btn.setVisible(False)
            return
            
        stats = self._state.document.stats()
        has_translated = stats['translated'] > 0
        has_untranslated = stats['untranslated'] > 0
        
        # Show retranslate button when there are translated rows but also some untranslated
        # or when we want to retranslate existing translations
        should_show = has_translated and (has_untranslated or stats['translated'] > 0)
        self._retranslate_btn.setVisible(should_show)
        
        # Update button text based on state
        if has_translated and has_untranslated:
            self._retranslate_btn.setText("Retranslate all rows")
        elif has_translated:
            self._retranslate_btn.setText("Retranslate all rows")

    def _on_start(self) -> None:
        if self._state.document is None:
            self.warn("Load a document first (Phase 1 or load an organised .xlsx).")
            return

        target_name = self._target_combo.currentText()
        target_code = code_for_language(target_name) or "ja"
        source_name = self._source_combo.currentText()
        source_code = code_for_language(source_name) or "en"

        self._state.source_language_code = source_code
        self._state.target_language_code = target_code
        self._state.target_language_name = target_name

        self._log.clear()
        self._progress.setValue(0)
        
        # Initialize timing
        self._start_time = time.time()
        self._eta_label.setText("ETA: calculating...")
        self._elapsed_label.setText("Elapsed: 00:00")
        
        # Setup timer to update elapsed time
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_elapsed_time)
        self._timer.start(1000)  # Update every second
        
        self._set_running(True)
        self.status_message.emit(
            f"Translating {len(self._state.document.entries):,} rows: "
            f"{source_name} -> {target_name}"
        )

        self._worker = TranslationWorker(
            self._state.document,
            source_code=source_code,
            target_code=target_code,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_translation_done)
        self._worker.failed.connect(self._on_translation_failed)
        self._worker.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self._progress.setValue(percent)
        self._log.appendPlainText(message)
        
        # Calculate and update ETA
        if self._start_time is not None and percent > 0:
            elapsed = time.time() - self._start_time
            if percent < 100:
                total_estimated = elapsed * (100 / percent)
                eta_seconds = total_estimated - elapsed
                eta_text = self._format_duration(eta_seconds)
                self._eta_label.setText(f"ETA: {eta_text}")
            else:
                self._eta_label.setText("ETA: complete")

    def _update_elapsed_time(self) -> None:
        """Update the elapsed time display."""
        if self._start_time is not None:
            elapsed = time.time() - self._start_time
            elapsed_text = self._format_duration(elapsed)
            self._elapsed_label.setText(f"Elapsed: {elapsed_text}")

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS format."""
        if seconds < 0:
            return "--:--"
        
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def _on_translation_done(self, done) -> None:
        # Stop the timer
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        
        # Final elapsed time update
        if self._start_time is not None:
            elapsed = time.time() - self._start_time
            elapsed_text = self._format_duration(elapsed)
            self._elapsed_label.setText(f"Completed in: {elapsed_text}")
        self._eta_label.setText("ETA: complete")
        
        self._state.translation_summaries = done.summaries
        self._state.translation_statuses = done.statuses
        
        # Display the improved summary format
        summary_text = done.format_summary()
        self._log.appendPlainText("\n" + "="*50)
        self._log.appendPlainText("TRANSLATION COMPLETE - SUMMARY")
        self._log.appendPlainText("="*50)
        self._log.appendPlainText(summary_text)
        self._log.appendPlainText("="*50)
        
        self.status_message.emit(
            f"Translation complete: {done.translated_count} translated, "
            f"{done.resumed_count} pre-existing, {done.failed_count} failed."
        )
        self._save_translated()

    def _on_translation_failed(self, message: str) -> None:
        # Stop the timer
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        
        self._eta_label.setText("ETA: failed")
        self._set_running(False)
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
        self._set_running(False)
        self._next_btn.setEnabled(True)
        self.status_message.emit(f"Translated workbook saved: {path}")

    def _on_save_failed(self, message: str) -> None:
        self._set_running(False)
        self.error(message, "Save failed")

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.status_message.emit("Cancellation requested...")
        
        # Stop the timer
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        
        self._eta_label.setText("ETA: cancelled")

    def _on_load_existing(self) -> None:
        from ..workers import ImportExcelWorker

        path = self.pick_open_file("Select translated workbook", "Excel files (*.xlsx)")
        if not path:
            return
        worker = ImportExcelWorker(
            path,
            language=self._state.target_language_name,
            language_code=self._state.target_language_code,
            parent=self,
        )

        def _loaded(doc):
            self._state.document = doc
            self._state.translated_xlsx_path = path
            self._state.output_dir = path.parent
            self._path_field.setText(str(path))
            self._next_btn.setEnabled(True)
            self.status_message.emit(f"Loaded {len(doc.entries):,} rows from {path.name}")

        worker.finished_ok.connect(_loaded)
        worker.failed.connect(lambda msg: self.error(msg, "Load failed"))
        worker.start()

    # ------------------------------------------------------------------ helpers

    def _set_running(self, running: bool) -> None:
        self._start_btn.setEnabled(not running)
        self._retranslate_btn.setEnabled(not running)
        self._cancel_btn.setEnabled(running)
        self._load_btn.setEnabled(not running)
        self._target_combo.setEnabled(not running)
        self._source_combo.setEnabled(not running)

    def on_reset(self) -> None:
        """Reset Phase 3 UI to initial state."""
        self._path_field.clear()
        self._log.clear()
        self._progress.setValue(0)
        self._eta_label.setText("ETA: --:--")
        self._elapsed_label.setText("Elapsed: 00:00")
        
        # Stop any running timer
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        
        # Reset button states
        self._start_btn.setEnabled(self._state.document is not None)
        self._retranslate_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._load_btn.setEnabled(True)
        self._next_btn.setEnabled(False)
        
        # Update button visibility
        self._update_button_visibility()
