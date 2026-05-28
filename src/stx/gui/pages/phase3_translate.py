"""Phase 3 -- Auto-translate every untranslated row.

This page is the heart of the application.  It exposes:

* **Backend selection** -- Google free / DeepL / Azure / OpenAI.
* **Component scope** -- checkboxes per component type (default: all
  selected).  Implements the "select which components to ultimately
  translate" requirement.
* **Key list** -- save / load / auto-discover JSON files containing
  include / exclude key rules.  Implements the "store a list of keys
  somewhere which should be translated" requirement.
* **Glossary** picker (CSV).
* **Translation memory** path with hit-rate stats.
* **Worker count + rate limit** controls.
* **Live status feed** showing the actual EN -> JA pair as each row
  finishes, with ETA / rows-per-second.
* **Multi-language batch** -- translate to additional target languages
  in the same run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...glossary import Glossary
from ...languages import LANGUAGE_NAME_TO_CODE, code_for_language, supported_language_names
from ...memory import TranslationMemory, default_tm_path
from ...scope import Scope, StatusFilter
from ...translate import list_backends
from .. import settings as gui_settings
from ..state import AppState, PhaseStatus
from ..workers import ExportExcelWorker, TranslationWorker, WriteAuditSheetsWorker
from .base import PhasePage, make_action_row, primary


class Phase3TranslatePage(PhasePage):
    """Configure and run automatic translation."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Phase 3 \u2014 Translate",
            subtitle=(
                "Auto-translate every untranslated row.  Salesforce IDs, "
                "placeholders, URLs, emails, ALL-CAPS acronyms, and HTML "
                "rich text are protected from modification.  Use the panels "
                "below to limit what gets translated and to plug in a "
                "glossary or translation memory for higher quality and "
                "speed."
            ),
            parent=parent,
        )
        self._worker: Optional[TranslationWorker] = None
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # ---------- Backend + language config
        cfg = QGroupBox("Configuration")
        cfg_layout = QFormLayout(cfg)

        self._backend_combo = QComboBox()
        for info in list_backends():
            self._backend_combo.addItem(info.label, info.key)
        cfg_layout.addRow("Backend:", self._backend_combo)

        self._api_key_field = QLineEdit()
        self._api_key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_field.setPlaceholderText("Optional -- leave blank to use environment variable")
        cfg_layout.addRow("API key:", self._api_key_field)

        self._source_combo = QComboBox()
        self._source_combo.addItems(supported_language_names())
        self._source_combo.setCurrentText("English")
        cfg_layout.addRow("Source language:", self._source_combo)

        self._target_combo = QComboBox()
        self._target_combo.addItems(supported_language_names())
        self._target_combo.setCurrentText("Japanese")
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        cfg_layout.addRow("Target language:", self._target_combo)

        self._batch_targets_field = QLineEdit()
        self._batch_targets_field.setPlaceholderText(
            "Optional -- additional language codes, comma separated (e.g. fr, de, es)"
        )
        cfg_layout.addRow("Batch targets:", self._batch_targets_field)

        perf_row = QHBoxLayout()
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 32)
        self._workers_spin.setValue(4)
        perf_row.addWidget(QLabel("Workers:"))
        perf_row.addWidget(self._workers_spin)
        perf_row.addSpacing(12)
        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0.0, 100.0)
        self._rate_spin.setValue(8.0)
        self._rate_spin.setSuffix(" req/s")
        self._rate_spin.setSpecialValueText("unlimited")
        perf_row.addWidget(QLabel("Rate:"))
        perf_row.addWidget(self._rate_spin)
        perf_row.addSpacing(12)
        self._wakelock_check = QCheckBox("Prevent system sleep")
        self._wakelock_check.setChecked(True)
        perf_row.addWidget(self._wakelock_check)
        perf_row.addStretch(1)
        cfg_layout.addRow("Performance:", perf_row)

        self.add_widget(cfg)

        # ---------- Splitter: scope (left) / key list + glossary + TM (right)
        scope_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ----- Component scope panel (left)
        scope_box = QGroupBox("Components to translate")
        scope_layout = QVBoxLayout(scope_box)

        scope_actions = QHBoxLayout()
        self._select_all_btn = QPushButton("Select all")
        self._select_all_btn.clicked.connect(lambda: self._set_all_components(True))
        self._select_none_btn = QPushButton("Select none")
        self._select_none_btn.clicked.connect(lambda: self._set_all_components(False))
        self._invert_btn = QPushButton("Invert")
        self._invert_btn.clicked.connect(self._invert_components)
        scope_actions.addWidget(self._select_all_btn)
        scope_actions.addWidget(self._select_none_btn)
        scope_actions.addWidget(self._invert_btn)
        scope_actions.addStretch(1)
        scope_layout.addLayout(scope_actions)

        self._component_list = QListWidget()
        self._component_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._component_list.itemChanged.connect(self._update_estimate)
        scope_layout.addWidget(self._component_list, stretch=1)

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status filter:"))
        self._status_combo = QComboBox()
        self._status_combo.addItem("Untranslated only", StatusFilter.UNTRANSLATED)
        self._status_combo.addItem("All entries", StatusFilter.ALL)
        self._status_combo.addItem("Translated only", StatusFilter.TRANSLATED)
        self._status_combo.currentIndexChanged.connect(self._update_estimate)
        status_row.addWidget(self._status_combo)
        status_row.addStretch(1)
        scope_layout.addLayout(status_row)

        self._estimate_label = QLabel("Estimated rows to translate: --")
        self._estimate_label.setStyleSheet("font-weight: 600;")
        scope_layout.addWidget(self._estimate_label)

        scope_splitter.addWidget(scope_box)

        # ----- Right panel: key list + glossary + TM
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Key list
        keys_box = QGroupBox("Key list (allow / deny)")
        keys_form = QFormLayout(keys_box)
        self._scope_path_field = QLineEdit()
        self._scope_path_field.setPlaceholderText("Optional -- path to .stxscope.json")
        keys_form.addRow("Saved scope:", self._scope_path_field)

        keys_actions = QHBoxLayout()
        load_scope_btn = QPushButton("Load...")
        load_scope_btn.clicked.connect(self._on_load_scope)
        save_scope_btn = QPushButton("Save current...")
        save_scope_btn.clicked.connect(self._on_save_scope)
        keys_actions.addWidget(load_scope_btn)
        keys_actions.addWidget(save_scope_btn)
        keys_actions.addStretch(1)
        keys_form.addRow(keys_actions)

        self._include_keys_field = QPlainTextEdit()
        self._include_keys_field.setPlaceholderText(
            "Allowlist -- one key or glob per line (e.g. CustomLabel.* or CustomApp.Foo)"
        )
        self._include_keys_field.setMaximumHeight(80)
        keys_form.addRow("Include:", self._include_keys_field)

        self._exclude_keys_field = QPlainTextEdit()
        self._exclude_keys_field.setPlaceholderText(
            "Denylist -- one key or glob per line"
        )
        self._exclude_keys_field.setMaximumHeight(80)
        keys_form.addRow("Exclude:", self._exclude_keys_field)

        self._include_keys_field.textChanged.connect(self._update_estimate)
        self._exclude_keys_field.textChanged.connect(self._update_estimate)

        right_layout.addWidget(keys_box)

        # Glossary
        gloss_box = QGroupBox("Glossary (.csv)")
        gloss_layout = QHBoxLayout(gloss_box)
        self._glossary_field = QLineEdit()
        self._glossary_field.setPlaceholderText("Optional -- CSV with source,target,do_not_translate")
        gloss_browse = QPushButton("Browse...")
        gloss_browse.clicked.connect(self._on_browse_glossary)
        gloss_layout.addWidget(self._glossary_field, stretch=1)
        gloss_layout.addWidget(gloss_browse)
        right_layout.addWidget(gloss_box)

        # Translation memory
        tm_box = QGroupBox("Translation memory (SQLite)")
        tm_form = QFormLayout(tm_box)
        self._memory_field = QLineEdit(str(default_tm_path()))
        tm_browse = QPushButton("Browse...")
        tm_browse.clicked.connect(self._on_browse_memory)
        tm_clear = QPushButton("Clear cache")
        tm_clear.clicked.connect(self._on_clear_memory)
        tm_row = QHBoxLayout()
        tm_row.addWidget(self._memory_field, stretch=1)
        tm_row.addWidget(tm_browse)
        tm_row.addWidget(tm_clear)
        tm_form.addRow("Path:", tm_row)
        self._memory_stats_label = QLabel("Cache: --")
        tm_form.addRow("Stats:", self._memory_stats_label)
        right_layout.addWidget(tm_box)

        right_layout.addStretch(1)
        scope_splitter.addWidget(right_panel)
        scope_splitter.setStretchFactor(0, 1)
        scope_splitter.setStretchFactor(1, 1)
        self.add_widget(scope_splitter, stretch=1)

        # ---------- Output path
        out_box = QGroupBox("Translated workbook output")
        out_layout = QHBoxLayout(out_box)
        self._path_field = QLineEdit()
        self._path_field.setPlaceholderText("Where to save the translated .xlsx ...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._on_browse_save)
        out_layout.addWidget(self._path_field, stretch=1)
        out_layout.addWidget(browse)
        self.add_widget(out_box)

        # ---------- Progress + ETA + live feed
        progress_box = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_box)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        progress_layout.addWidget(self._progress)
        self._eta_label = QLabel("Idle.")
        self._eta_label.setStyleSheet("color: #64748b;")
        progress_layout.addWidget(self._eta_label)
        self.add_widget(progress_box)

        feed_box = QGroupBox("Live feed (last 200 events) -- shows source and translation")
        feed_layout = QVBoxLayout(feed_box)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(200 * 4)  # ~4 lines per event
        feed_layout.addWidget(self._log)
        self.add_widget(feed_box, stretch=1)

        # ---------- Actions
        self._start_btn = primary(QPushButton("Start translation"))
        self._start_btn.clicked.connect(self._on_start)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._load_btn = QPushButton("Load translated .xlsx ...")
        self._load_btn.clicked.connect(self._on_load_existing)
        self._next_btn = QPushButton("Continue to Phase 4 \u2192")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(lambda: self.request_navigate.emit(4))

        self.add_layout(make_action_row(self._start_btn, self._cancel_btn, self._load_btn, self._next_btn))

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        # Restore remembered settings
        remembered_target = gui_settings.remembered_target_language()
        if remembered_target in LANGUAGE_NAME_TO_CODE:
            self._target_combo.setCurrentText(remembered_target)
        backend = gui_settings.get_str(gui_settings.KEYS.backend, "google")
        for i in range(self._backend_combo.count()):
            if self._backend_combo.itemData(i) == backend:
                self._backend_combo.setCurrentIndex(i)
                break

        if self._state.target_language_name in LANGUAGE_NAME_TO_CODE:
            self._target_combo.setCurrentText(self._state.target_language_name)

        # Default output path
        if not self._path_field.text():
            base = self._state.organized_xlsx_path or self._state.source_stf_path
            if base is not None:
                self._path_field.setText(str(Path(base).with_suffix("")) + "_translated.xlsx")

        # Refresh component checkboxes from the loaded document.
        self._populate_components()
        self._refresh_memory_stats()
        self._update_estimate()
        self._start_btn.setEnabled(self._state.document is not None and not self.is_busy)

    # ------------------------------------------------------------------ component panel

    def _populate_components(self) -> None:
        self._component_list.blockSignals(True)
        self._component_list.clear()
        if self._state.document is None:
            self._component_list.blockSignals(False)
            return
        components = sorted({e.component_type for e in self._state.document.entries})

        # Counts per component (untranslated only) for display.
        counts: dict[str, int] = {}
        for e in self._state.document.entries:
            if not e.translation.strip():
                counts[e.component_type] = counts.get(e.component_type, 0) + 1

        previously_selected: Optional[set[str]] = None
        if self._state.scope is not None and self._state.scope.components is not None:
            previously_selected = set(self._state.scope.components)

        for comp in components:
            count = counts.get(comp, 0)
            item = QListWidgetItem(f"{comp}  ({count} untranslated)")
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
        scope = Scope(
            components=components if components != all_components else None,
            status=self._status_combo.currentData(),
            include_keys=[
                line.strip()
                for line in self._include_keys_field.toPlainText().splitlines()
                if line.strip() and "*" not in line and "?" not in line
            ],
            include_patterns=[
                line.strip()
                for line in self._include_keys_field.toPlainText().splitlines()
                if line.strip() and ("*" in line or "?" in line)
            ],
            exclude_keys=[
                line.strip()
                for line in self._exclude_keys_field.toPlainText().splitlines()
                if line.strip() and "*" not in line and "?" not in line
            ],
            exclude_patterns=[
                line.strip()
                for line in self._exclude_keys_field.toPlainText().splitlines()
                if line.strip() and ("*" in line or "?" in line)
            ],
            name="GUI scope",
        )
        return scope

    def _update_estimate(self) -> None:
        if self._state.document is None:
            self._estimate_label.setText("Estimated rows to translate: -- (load a document first)")
            return
        scope = self._build_scope()
        if scope is None:
            return
        count = scope.estimate_count(self._state.document)
        self._estimate_label.setText(f"Estimated rows to translate: {count:,}")

    # ------------------------------------------------------------------ scope file actions

    def _on_load_scope(self) -> None:
        path = self.pick_open_file(
            "Load scope file", "Scope files (*.json *.stxscope.json);;All files (*)"
        )
        if not path:
            return
        try:
            scope = Scope.load(path)
        except Exception as exc:  # noqa: BLE001
            self.error(f"Failed to load scope: {exc}", "Load failed")
            return
        self._scope_path_field.setText(str(path))
        self._state.scope_path = path
        self._state.scope = scope
        self._apply_scope_to_widgets(scope)

    def _apply_scope_to_widgets(self, scope: Scope) -> None:
        if scope.components is not None:
            self._component_list.blockSignals(True)
            for i in range(self._component_list.count()):
                item = self._component_list.item(i)
                comp = item.data(Qt.ItemDataRole.UserRole)
                item.setCheckState(
                    Qt.CheckState.Checked if comp in scope.components else Qt.CheckState.Unchecked
                )
            self._component_list.blockSignals(False)
        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == scope.status:
                self._status_combo.setCurrentIndex(i)
                break
        self._include_keys_field.setPlainText(
            "\n".join([*scope.include_keys, *scope.include_patterns])
        )
        self._exclude_keys_field.setPlainText(
            "\n".join([*scope.exclude_keys, *scope.exclude_patterns])
        )
        self._update_estimate()

    def _on_save_scope(self) -> None:
        scope = self._build_scope()
        if scope is None:
            return
        path = self.pick_save_file(
            "Save scope as",
            "Scope files (*.stxscope.json);;JSON (*.json)",
            "scope.stxscope.json",
        )
        if not path:
            return
        if not path.suffix:
            path = path.with_suffix(".stxscope.json")
        try:
            scope.save(path)
        except Exception as exc:  # noqa: BLE001
            self.error(f"Failed to save scope: {exc}", "Save failed")
            return
        self._scope_path_field.setText(str(path))
        self._state.scope_path = path
        self.status_message.emit(f"Saved scope to {path}")

    # ------------------------------------------------------------------ glossary / TM

    def _on_browse_glossary(self) -> None:
        path = self.pick_open_file("Select glossary CSV", "CSV files (*.csv)")
        if path:
            self._glossary_field.setText(str(path))

    def _on_browse_memory(self) -> None:
        path = self.pick_save_file(
            "Translation memory database",
            "SQLite (*.sqlite *.db);;All files (*)",
            "tm.sqlite",
        )
        if path:
            self._memory_field.setText(str(path))
            self._refresh_memory_stats()

    def _on_clear_memory(self) -> None:
        path_text = self._memory_field.text().strip()
        if not path_text:
            return
        if not self.confirm("Clear every entry from the translation memory cache?"):
            return
        try:
            tm = TranslationMemory(path=Path(path_text))
            tm.clear()
            self.status_message.emit("Translation memory cleared.")
            self._refresh_memory_stats()
        except Exception as exc:  # noqa: BLE001
            self.error(f"Failed to clear cache: {exc}", "Clear failed")

    def _refresh_memory_stats(self) -> None:
        path_text = self._memory_field.text().strip()
        if not path_text:
            self._memory_stats_label.setText("Cache: not configured")
            return
        path = Path(path_text)
        if not path.exists():
            self._memory_stats_label.setText("Cache: empty (will be created on first run)")
            return
        try:
            tm = TranslationMemory(path=path)
            stats = tm.stats()
            self._memory_stats_label.setText(
                f"Cache: {stats['entries']:,} entries / {stats['hits']:,} hits / "
                f"{stats['size_bytes'] // 1024:,} KB"
            )
        except Exception as exc:  # noqa: BLE001
            self._memory_stats_label.setText(f"Cache: unreadable ({exc})")

    def _on_browse_save(self) -> None:
        path = self.pick_save_file("Save translated workbook as", "Excel files (*.xlsx)", "translated.xlsx")
        if path:
            self._path_field.setText(str(path))

    # ------------------------------------------------------------------ translation slot

    def _on_target_changed(self, name: str) -> None:
        code = code_for_language(name)
        if code:
            self._state.target_language_name = name
            self._state.target_language_code = code
            gui_settings.remember_target_language(name, code)

    def _on_start(self) -> None:
        # Multi-click guard: ignore if already translating.
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

        # Backend
        backend_key = self._backend_combo.currentData()
        gui_settings.set_str(gui_settings.KEYS.backend, backend_key)

        # Glossary
        glossary_path_text = self._glossary_field.text().strip()
        glossary = None
        if glossary_path_text:
            try:
                glossary = Glossary.load_csv(glossary_path_text)
                self._state.glossary = glossary
                self._state.glossary_path = Path(glossary_path_text)
            except Exception as exc:  # noqa: BLE001
                self.error(f"Failed to load glossary: {exc}", "Glossary error")
                return

        # Translation memory
        memory = None
        memory_path_text = self._memory_field.text().strip()
        if memory_path_text:
            try:
                memory = TranslationMemory(path=Path(memory_path_text))
                self._state.memory = memory
                self._state.memory_path = Path(memory_path_text)
            except Exception as exc:  # noqa: BLE001
                self.error(f"Failed to open TM: {exc}", "TM error")
                return

        # Performance
        workers = self._workers_spin.value()
        rate = self._rate_spin.value() if self._rate_spin.value() > 0 else None
        prevent_sleep = self._wakelock_check.isChecked()
        self._state.workers = workers
        if rate is not None:
            self._state.rate_limit_per_second = rate

        self._log.clear()
        self._progress.setValue(0)
        self._eta_label.setText("Starting...")
        self._set_running(True)
        self._state.set_phase(3, PhaseStatus.RUNNING)

        self.status_message.emit(
            f"Translating: {self._target_combo.currentText()}, "
            f"workers={workers}, scope={scope.estimate_count(self._state.document)} rows"
        )

        self._worker = TranslationWorker(
            self._state.document,
            source_code=code_for_language(self._source_combo.currentText()) or "en",
            target_code=self._state.target_language_code,
            scope=scope,
            memory=memory,
            glossary=glossary,
            workers=workers,
            rate_limit_per_second=rate,
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
        # Multi-line entry: status header + EN line + JA line
        sep = "  " if not source.startswith("<") else " "
        if translation:
            self._log.appendPlainText(f"[{status}]")
            self._log.appendPlainText(f"  EN: {source}")
            self._log.appendPlainText(f"  {self._state.target_language_code.upper()}: {translation}")
        else:
            self._log.appendPlainText(f"[{status}] {source}")

        # Update the ETA label too.
        eta_text = self._eta_label.text().split(" | ")[0]
        if "%" in eta_text:
            self._eta_label.setText(eta_text)

    def _on_translation_done(self, done) -> None:
        self._state.translation_summaries = done.summaries
        self._state.translation_statuses = done.statuses
        elapsed = done.elapsed_seconds
        cache_ratio = (
            (done.cached_count / done.translated_count * 100)
            if done.translated_count > 0
            else 0
        )
        dedup_ratio = (
            (done.deduped_count / done.translated_count * 100)
            if done.translated_count > 0
            else 0
        )
        msg = (
            f"Translated {done.translated_count:,} (TM hits {done.cached_count:,} = "
            f"{cache_ratio:.0f}%, dedup hits {done.deduped_count:,} = {dedup_ratio:.0f}%); "
            f"skipped {done.skipped_count:,}; elapsed {elapsed:.1f}s."
        )
        self._eta_label.setText(msg)
        self.status_message.emit(msg)
        self._save_translated()

    def _on_translation_failed(self, message: str) -> None:
        self._set_running(False)
        self._state.set_phase(3, PhaseStatus.ERROR)
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
        self._refresh_memory_stats()
        self._state.set_phase(3, PhaseStatus.DONE)
        self.status_message.emit(f"Translated workbook saved: {path}")

    def _on_save_failed(self, message: str) -> None:
        self._set_running(False)
        self._state.set_phase(3, PhaseStatus.ERROR)
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
        self._backend_combo.setEnabled(not running)
        self._workers_spin.setEnabled(not running)
        self._rate_spin.setEnabled(not running)
        self._select_all_btn.setEnabled(not running)
        self._select_none_btn.setEnabled(not running)
        self._invert_btn.setEnabled(not running)
        self._component_list.setEnabled(not running)
