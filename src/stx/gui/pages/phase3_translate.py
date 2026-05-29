"""Phase 3 (index 2) -- Translate.

v1.3 simplification: this page now asks only what a translator needs
to answer:

* **Target language** (and optional source language).
* **Which components** to translate (default: all).
* **Where to save** the translated workbook.

Everything else -- backend, API key, worker count, rate limit,
wake-lock, glossary path, translation memory path, batch targets --
lives in the Settings dialog (``Edit -> Settings...``).  We read those
values when the user clicks Start.

The live feed in the lower half shows the actual ``EN -> JA`` pair
plus running counters (translated / TM hits / dedup / skipped) so the
user can confirm at a glance that the translator is working.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    QSplitter,
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

try:
    from PySide6.QtWidgets import QComboBox  # noqa: F401  -- kept for type completeness
except ImportError:  # pragma: no cover
    QComboBox = None  # type: ignore[assignment]


class Phase3TranslatePage(PhasePage):
    """Configure and run automatic translation -- minimal version."""

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
        # Live counters that the run updates.
        self._translated_count = 0
        self._cached_count = 0
        self._deduped_count = 0
        self._skipped_count = 0
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # Top split: Setup (left) | Components (right)
        top = QSplitter(Qt.Orientation.Horizontal)

        # ----- Setup card (left)
        setup_box = QGroupBox("Setup")
        setup_form = QFormLayout(setup_box)
        setup_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        setup_form.setHorizontalSpacing(12)

        from PySide6.QtWidgets import QComboBox as _Combo  # local alias for clarity

        self._source_combo = _Combo()
        self._source_combo.addItems(supported_language_names())
        self._source_combo.setCurrentText("English")
        setup_form.addRow("Source language:", self._source_combo)

        self._target_combo = _Combo()
        self._target_combo.addItems(supported_language_names())
        self._target_combo.setCurrentText("Japanese")
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        setup_form.addRow("Target language:", self._target_combo)

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
        setup_form.addRow("Output file:", path_widget)

        # Settings hint (read-only summary of advanced options)
        self._settings_summary = QLabel("")
        self._settings_summary.setWordWrap(True)
        self._settings_summary.setStyleSheet("color: #64748b; font-size: 11px;")
        setup_form.addRow("Advanced:", self._settings_summary)

        top.addWidget(setup_box)

        # ----- Components card (right)
        comp_box = QGroupBox("Components to translate")
        comp_layout = QVBoxLayout(comp_box)
        comp_layout.setContentsMargins(8, 6, 8, 6)

        comp_actions = QHBoxLayout()
        self._select_all_btn = QPushButton("Select all")
        self._select_all_btn.clicked.connect(lambda: self._set_all_components(True))
        self._select_none_btn = QPushButton("Select none")
        self._select_none_btn.clicked.connect(lambda: self._set_all_components(False))
        self._invert_btn = QPushButton("Invert")
        self._invert_btn.clicked.connect(self._invert_components)
        comp_actions.addWidget(self._select_all_btn)
        comp_actions.addWidget(self._select_none_btn)
        comp_actions.addWidget(self._invert_btn)
        comp_actions.addStretch(1)
        comp_layout.addLayout(comp_actions)

        self._component_list = QListWidget()
        self._component_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._component_list.itemChanged.connect(self._update_estimate)
        comp_layout.addWidget(self._component_list, stretch=1)

        self._estimate_label = QLabel("Rows to translate: --")
        self._estimate_label.setStyleSheet("font-weight: 600;")
        comp_layout.addWidget(self._estimate_label)

        top.addWidget(comp_box)
        top.setStretchFactor(0, 1)
        top.setStretchFactor(1, 1)
        self.add_widget(top)

        # ----- Progress + Live feed
        run_box = QGroupBox("Run")
        run_layout = QVBoxLayout(run_box)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        run_layout.addWidget(self._progress)

        self._eta_label = QLabel("Idle.")
        self._eta_label.setStyleSheet("color: #64748b;")
        run_layout.addWidget(self._eta_label)

        # Counters strip
        counters = QHBoxLayout()
        counters.setSpacing(20)
        self._counter_translated = self._make_counter("Translated", "0", "#16a34a")
        self._counter_tm = self._make_counter("From TM", "0", "#0284c7")
        self._counter_dedup = self._make_counter("Deduped", "0", "#7c3aed")
        self._counter_skipped = self._make_counter("Skipped", "0", "#64748b")
        counters.addWidget(self._counter_translated["frame"])
        counters.addWidget(self._counter_tm["frame"])
        counters.addWidget(self._counter_dedup["frame"])
        counters.addWidget(self._counter_skipped["frame"])
        counters.addStretch(1)
        run_layout.addLayout(counters)

        # Live feed log
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(800)
        self._log.setPlaceholderText("Live feed -- each translated row appears here as 'EN: ...' / 'JA: ...'")
        run_layout.addWidget(self._log)

        self.add_widget(run_box, stretch=1)

        # ----- Action buttons
        self._start_btn = primary(QPushButton("Start translation"))
        self._start_btn.clicked.connect(self._on_start)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._load_btn = QPushButton("Load translated .xlsx ...")
        self._load_btn.clicked.connect(self._on_load_existing)
        self._next_btn = QPushButton("Continue to Phase 4 \u2192")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(3))

        self.add_layout(make_action_row(self._start_btn, self._cancel_btn, self._load_btn, self._next_btn))

    def _make_counter(self, label: str, initial: str, accent: str) -> dict:
        from PySide6.QtWidgets import QFrame
        frame = QFrame()
        frame.setProperty("role", "card")
        frame.setStyleSheet(
            f"QFrame {{ background: palette(base); border: 1px solid palette(mid); "
            f"border-left: 3px solid {accent}; border-radius: 6px; padding: 6px 12px; }}"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(0)
        title = QLabel(label.upper())
        title.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600; letter-spacing: 0.6px;")
        v.addWidget(title)
        value = QLabel(initial)
        value.setStyleSheet(f"color: {accent}; font-size: 18px; font-weight: 700;")
        v.addWidget(value)
        return {"frame": frame, "value": value}

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

        self._populate_components()
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

    # ------------------------------------------------------------------ component panel

    def _populate_components(self) -> None:
        self._component_list.blockSignals(True)
        self._component_list.clear()
        if self._state.document is None:
            self._component_list.blockSignals(False)
            return
        components = sorted({e.component_type for e in self._state.document.entries})
        counts: dict[str, int] = {}
        for e in self._state.document.entries:
            if not e.translation.strip():
                counts[e.component_type] = counts.get(e.component_type, 0) + 1

        previously_selected: Optional[set[str]] = None
        if self._state.scope is not None and self._state.scope.components is not None:
            previously_selected = set(self._state.scope.components)

        for comp in components:
            count = counts.get(comp, 0)
            item = QListWidgetItem(f"{comp}  \u2014  {count} untranslated")
            item.setData(Qt.ItemDataRole.UserRole, comp)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            should_check = previously_selected is None or comp in previously_selected
            item.setCheckState(Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked)
            self._component_list.addItem(item)
        self._component_list.blockSignals(False)

    def _set_all_components(self, checked: bool) -> None:
        self._component_list.blockSignals(True)
        for i in range(self._component_list.count()):
            self._component_list.item(i).setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
        self._component_list.blockSignals(False)
        self._update_estimate()

    def _invert_components(self) -> None:
        self._component_list.blockSignals(True)
        for i in range(self._component_list.count()):
            item = self._component_list.item(i)
            item.setCheckState(
                Qt.CheckState.Unchecked
                if item.checkState() == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
        self._component_list.blockSignals(False)
        self._update_estimate()

    def _selected_components(self) -> set[str]:
        selected = set()
        for i in range(self._component_list.count()):
            item = self._component_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.add(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def _build_scope(self) -> Optional[Scope]:
        if self._state.document is None:
            return None
        components = self._selected_components()
        all_components = {e.component_type for e in self._state.document.entries}
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
            self.warn("Load a document first (Phase 1 or load an organised .xlsx).")
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
        self._update_counter_widgets()
        self._log.clear()

        # ---- Live feed header showing language pair
        src_code = code_for_language(self._source_combo.currentText()) or "en"
        self._log.appendPlainText(
            f"\u2500\u2500  {src_code.upper()} \u2192 {self._state.target_language_code.upper()}  "
            f"\u2500\u2500  scope: {scope.estimate_count(self._state.document):,} rows  "
            f"workers: {workers}\n"
        )

        self._progress.setValue(0)
        self._eta_label.setText("Starting...")
        self._set_running(True)
        self._state.set_phase(2, PhaseStatus.RUNNING)

        self.status_message.emit(
            f"Translating: {self._target_combo.currentText()}, "
            f"workers={workers}, scope={scope.estimate_count(self._state.document)} rows"
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
        # Update running counters from status keywords.
        if status.startswith("Translated"):
            self._translated_count += 1
            if "TM hit" in status:
                self._cached_count += 1
            elif "dedup" in status:
                self._deduped_count += 1
        elif status.startswith("Skipped") or status.startswith("Cancelled") or "Fallback" in status:
            self._skipped_count += 1
        self._update_counter_widgets()

        # Live feed entry showing source -> target.
        if translation:
            self._log.appendPlainText(f"[{status}]")
            self._log.appendPlainText(f"  {self._state.source_language_code.upper() if False else 'EN'}: {source}")
            self._log.appendPlainText(
                f"  {self._state.target_language_code.upper()}: {translation}"
            )
        else:
            self._log.appendPlainText(f"[{status}] {source}")

    def _update_counter_widgets(self) -> None:
        self._counter_translated["value"].setText(f"{self._translated_count:,}")
        self._counter_tm["value"].setText(f"{self._cached_count:,}")
        self._counter_dedup["value"].setText(f"{self._deduped_count:,}")
        self._counter_skipped["value"].setText(f"{self._skipped_count:,}")

    def _on_translation_done(self, done) -> None:
        self._state.translation_summaries = done.summaries
        self._state.translation_statuses = done.statuses
        elapsed = done.elapsed_seconds
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
        if self.is_busy:
            return
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
            gui_settings.add_recent_file(path)
            self._path_field.setText(str(path))
            self._next_btn.setEnabled(True)
            self.on_enter()
            self.status_message.emit(f"Loaded {len(doc.entries):,} rows from {path.name}")

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
        self._select_all_btn.setEnabled(not running)
        self._select_none_btn.setEnabled(not running)
        self._invert_btn.setEnabled(not running)
        self._component_list.setEnabled(not running)
