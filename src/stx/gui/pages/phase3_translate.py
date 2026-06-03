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
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ...glossary import Glossary
from ...languages import (
    LANGUAGE_NAME_TO_CODE,
    code_for_language,
    supported_language_names,
)
from ...memory import TranslationMemory, default_tm_path
from ...checkpoint import CheckpointStore
from ...scope import Scope, StatusFilter
from .. import settings as gui_settings
from .. import secrets as gui_secrets
from ..state import AppState, PhaseStatus
from ..workers import ExportExcelWorker, TranslationWorker, WriteAuditSheetsWorker
from .base import PhasePage, add_popout_to_groupbox, compact_btn, primary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_eta(seconds: float) -> str:
    """Format seconds as HH:MM:SS (or MM:SS if under one hour)."""
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


# ---------------------------------------------------------------------------
# Component filter dialog
# ---------------------------------------------------------------------------

class _ComponentFilterDialog(QDialog):
    """Modal dialog for selecting which component types to translate.

    Features:
    - Search field to filter components by name
    - Status filter combo (all / untranslated only / translated only / both)
    - Select all / Select none / Invert buttons
    - Per-component row counts
    - Summary label showing selected count and estimated rows
    """

    def __init__(self, document, previously_selected: Optional[set[str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filter Components")
        self.setMinimumWidth(480)
        self.setMinimumHeight(450)

        self._document = document

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Search field
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search_field = QLineEdit()
        self._search_field.setPlaceholderText("Type to filter components by name...")
        self._search_field.textChanged.connect(self._apply_filters)
        search_row.addWidget(self._search_field, stretch=1)
        layout.addLayout(search_row)

        # Status filter combo
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItems([
            "Show all components",
            "Only components with untranslated rows",
            "Only components with translated rows (for retranslation)",
            "Only components with both translated and untranslated",
        ])
        self._status_combo.currentIndexChanged.connect(self._apply_filters)
        status_row.addWidget(self._status_combo, stretch=1)
        layout.addLayout(status_row)

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

        # Populate -- compute per-component counts
        components = sorted({e.component_type for e in document.entries})
        self._untranslated_counts: dict[str, int] = {}
        self._translated_counts: dict[str, int] = {}
        for e in document.entries:
            if not e.translation.strip():
                self._untranslated_counts[e.component_type] = (
                    self._untranslated_counts.get(e.component_type, 0) + 1
                )
            else:
                self._translated_counts[e.component_type] = (
                    self._translated_counts.get(e.component_type, 0) + 1
                )

        for comp in components:
            untrans = self._untranslated_counts.get(comp, 0)
            trans = self._translated_counts.get(comp, 0)
            label = f"{comp}  \u2014  {untrans} untranslated"
            if trans:
                label += f", {trans} translated"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, comp)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            should_check = previously_selected is None or comp in previously_selected
            item.setCheckState(Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked)
            self._list.addItem(item)

        # Connect itemChanged for live summary updates
        self._list.itemChanged.connect(self._update_summary)

        # Summary label
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("font-weight: 600; color: #475569; padding: 4px 0;")
        layout.addWidget(self._summary_label)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        btn_box.button(QDialogButtonBox.StandardButton.Apply).setText("Apply")
        btn_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._update_summary()

    def _apply_filters(self) -> None:
        """Hide items that don't match the search text or status filter."""
        search_text = self._search_field.text().strip().lower()
        status_index = self._status_combo.currentIndex()

        for i in range(self._list.count()):
            item = self._list.item(i)
            comp = item.data(Qt.ItemDataRole.UserRole)

            # Search filter
            matches_search = not search_text or search_text in comp.lower()

            # Status filter
            has_untranslated = self._untranslated_counts.get(comp, 0) > 0
            has_translated = self._translated_counts.get(comp, 0) > 0

            if status_index == 0:
                matches_status = True
            elif status_index == 1:
                matches_status = has_untranslated
            elif status_index == 2:
                matches_status = has_translated
            elif status_index == 3:
                matches_status = has_untranslated and has_translated
            else:
                matches_status = True

            item.setHidden(not (matches_search and matches_status))

        self._update_summary()

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._list.count()):
            item = self._list.item(i)
            if not item.isHidden():
                item.setCheckState(state)
        self._update_summary()

    def _invert(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if not item.isHidden():
                item.setCheckState(
                    Qt.CheckState.Unchecked
                    if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
        self._update_summary()

    def _update_summary(self) -> None:
        """Update the summary label with selection count and estimated rows."""
        total_components = self._list.count()
        selected = self.selected_components()
        selected_count = len(selected)

        # Count rows that will be translated (untranslated rows in selected components)
        rows = 0
        for e in self._document.entries:
            if e.component_type in selected and not e.translation.strip():
                rows += 1

        self._summary_label.setText(
            f"{selected_count} of {total_components} selected  \u00b7  "
            f"{rows:,} rows will be translated"
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
        self._use_fuzzy_this_run = False
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # ----- Setup section: compact form
        setup_box = QGroupBox("Setup")

        # Source + Target on the SAME ROW (saves a vertical line vs. the
        # old QFormLayout that stacked them).  Output field already
        # removed in v1.4 -- the translated document stays in memory
        # until the user clicks "Save copy to..." in the action row.
        self._source_combo = QComboBox()
        self._source_combo.addItems(supported_language_names())
        self._source_combo.setCurrentText("English")
        self._source_combo.setToolTip("Source language of your STF file.")

        self._target_combo = QComboBox()
        self._target_combo.addItems(supported_language_names())
        self._target_combo.setCurrentText("Japanese")
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        self._target_combo.setToolTip("Language to translate into.")

        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        src_label = QLabel("Source:")
        src_label.setStyleSheet("font-weight: 600;")
        lang_row.addWidget(src_label)
        lang_row.addWidget(self._source_combo, stretch=1)
        lang_row.addSpacing(20)
        tgt_label = QLabel("Target:")
        tgt_label.setStyleSheet("font-weight: 600;")
        lang_row.addWidget(tgt_label)
        lang_row.addWidget(self._target_combo, stretch=1)

        setup_layout = QVBoxLayout(setup_box)
        setup_layout.setContentsMargins(6, 4, 6, 4)
        setup_layout.addLayout(lang_row)

        # ----- Filter row 1: action buttons + checkboxes
        self._filter_btn = QPushButton("Filter Components...")
        self._filter_btn.setStyleSheet("padding: 4px 12px; font-weight: 600;")
        self._filter_btn.setToolTip(
            "Choose which component types to translate. By default all "
            "components are selected."
        )
        self._filter_btn.clicked.connect(self._on_filter_components)

        self._import_trans_btn = QPushButton("Import existing translations...")
        self._import_trans_btn.setStyleSheet("padding: 4px 12px;")
        self._import_trans_btn.setToolTip(
            "Load translations from a previously translated Excel file. "
            "Imported translations are applied with highest priority."
        )
        self._import_trans_btn.clicked.connect(self._on_import_translations)

        self._import_trans_check = QCheckBox("Use imports")
        self._import_trans_check.setToolTip(
            "Enable or disable the imported translations.\n"
            "Only available after a translation file has been imported."
        )
        self._import_trans_check.setChecked(False)
        self._import_trans_check.setEnabled(False)   # disabled until a file is imported
        self._import_trans_check.toggled.connect(self._on_import_trans_toggled)



        # Single row: Filter Components | Import translations | Use imports | Retranslate | stretch | import status | Rows to translate
        self._import_trans_label = QLabel("")
        self._import_trans_label.setStyleSheet("color: #16a34a; font-size: 11px;")

        self._estimate_label = QLabel("Rows to translate: --")
        self._estimate_label.setStyleSheet("font-weight: 700; color: #94a3b8;")

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 8, 0, 0)
        btn_row.setSpacing(10)
        btn_row.addWidget(self._filter_btn)
        btn_row.addWidget(self._import_trans_btn)
        btn_row.addWidget(self._import_trans_check)
        btn_row.addStretch(1)
        btn_row.addWidget(self._import_trans_label)
        btn_row.addWidget(self._estimate_label)

        setup_layout.addLayout(btn_row)

        # Settings hint
        self._settings_summary = QLabel("")
        self._settings_summary.setWordWrap(True)
        self._settings_summary.setStyleSheet("color: #64748b; font-size: 11px;")
        setup_layout.addWidget(self._settings_summary)

        self.add_widget(setup_box)

        # ----- Progress bar + status label on same row (no wasted line)
        progress_row = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMaximumHeight(20)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")
        progress_row.addWidget(self._progress, stretch=1)

        self._eta_label = QLabel("")   # blank until translation starts
        self._eta_label.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; margin-left: 8px;")
        self._eta_label.setMinimumWidth(120)
        progress_row.addWidget(self._eta_label)
        progress_layout = QVBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.addLayout(progress_row)
        self.add_layout(progress_layout)

        # ----- Live feed log (takes all remaining space)
        feed_box = QGroupBox("Live feed")
        self._feed_box = feed_box
        self._feed_layout = QVBoxLayout(feed_box)
        self._feed_layout.setContentsMargins(4, 4, 4, 4)
        self._feed_layout.setSpacing(2)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(800)
        self._log.setPlaceholderText("Live feed -- each translated row appears here with inline counters")
        self._feed_layout.addWidget(self._log)
        self.add_widget(feed_box, stretch=1)

        # Pop-out icon glued to the top-right of the group box border
        add_popout_to_groupbox(feed_box, self._on_popout_feed)

        # ----- Action buttons
        self._start_btn = primary(QPushButton("Start translation"))
        self._start_btn.setToolTip(
            "Start translating untranslated rows in the selected components. "
            "Progress and live source/translation pairs appear in the feed below."
        )
        self._start_btn.clicked.connect(self._on_start)
        self._reset_checkpoint_btn = QPushButton("Clear progress")
        self._reset_checkpoint_btn.setToolTip(
            "Clear any saved resume point. Use this if you want to start translation\n"
            "from scratch instead of continuing where it last stopped.\n"
            "(The progress is only saved when translation is interrupted mid-run.)"
        )
        self._reset_checkpoint_btn.clicked.connect(self._on_reset_checkpoint)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setToolTip(
            "Cancel a running translation. In-flight rows finish, then the "
            "translated portion is still saved."
        )
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._save_copy_btn = QPushButton("Save a Copy...")
        self._save_copy_btn.setEnabled(False)
        self._save_copy_btn.setToolTip(
            "Save the translated document to a file of your choice. "
            "Default filename will be suggested based on the source file."
        )
        self._save_copy_btn.clicked.connect(self._on_save_copy_to)
        self._load_btn = QPushButton("Load Excel...")
        self._load_btn.setToolTip(
            "Load any Excel (organised or translated) directly into this phase.\n"
            "Use this when you want to work independently without going through earlier phases."
        )
        self._load_btn.clicked.connect(self._on_load_existing)
        self._next_btn = QPushButton("Continue to Phase 4 \u2192")
        self._next_btn.setEnabled(False)
        self._next_btn.setToolTip("Move to the next phase (Browse & Review).")
        self._next_btn.clicked.connect(self._on_continue_to_phase4)

        # Custom action row: left group (primary actions) | stretch | right group (secondary)
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        # Left group: Start (primary) + Cancel
        for btn in (self._start_btn, self._cancel_btn):
            btn.setMinimumHeight(28)
            action_row.addWidget(btn)
        action_row.addStretch(1)
        # Right group: Clear progress, Save a Copy, Load Excel, Continue
        for btn in (
            compact_btn(self._reset_checkpoint_btn),
            compact_btn(self._save_copy_btn),
            compact_btn(self._load_btn),
            self._next_btn,
        ):
            btn.setMinimumHeight(28)
            action_row.addWidget(btn)
        self.add_layout(action_row)

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        # Sync source language combo from state.
        src_name = getattr(self._state, "source_language_name", "English") or "English"
        if src_name in LANGUAGE_NAME_TO_CODE:
            self._source_combo.setCurrentText(src_name)

        # Restore remembered target language.
        remembered = gui_settings.remembered_target_language()
        if remembered in LANGUAGE_NAME_TO_CODE:
            self._target_combo.setCurrentText(remembered)
        if self._state.target_language_name in LANGUAGE_NAME_TO_CODE:
            self._target_combo.setCurrentText(self._state.target_language_name)

        # Auto-generate a professional default suggested output path so Save a Copy...
        # has a sensible filename ready when the user clicks it.
        if self._state.translated_xlsx_path is None:
            base = self._state.organized_xlsx_path or self._state.source_stf_path
            if base is not None:
                parent = Path(base).parent
                self._state.translated_xlsx_path = parent / self.default_save_name("translated")

        # Restore previously selected components from state
        if self._state.scope is not None and self._state.scope.components is not None:
            self._selected_components = set(self._state.scope.components)
        elif self._state.document is not None:
            self._selected_components = {e.component_type for e in self._state.document.entries}

        # Restore imported translations from settings if not already loaded
        if self._state.imported_translations is None:
            import_path = gui_settings.get_str(
                gui_settings.KEYS.import_translations_path, ""
            ).strip()
            import_enabled = gui_settings.get_str(
                gui_settings.KEYS.import_translations_enabled, "0"
            ) in {"1", "true"}
            if import_path and import_enabled and Path(import_path).exists():
                from ...import_translations import parse_translation_file

                try:
                    result = parse_translation_file(Path(import_path))
                    if result.count:
                        self._state.imported_translations = result.translations
                        self._state.imported_translations_path = Path(import_path)
                        self._state.imported_translations_enabled = True
                        self._import_trans_label.setText(
                            f"Loaded {result.count:,} translations from imported file"
                        )
                except Exception:  # noqa: BLE001
                    import logging as _logging

                    _logging.getLogger(__name__).warning(
                        "Could not read import file: %s", import_path, exc_info=True
                    )
                    self._import_trans_label.setText(
                        "\u26a0 Could not read import file"
                    )
                    self._import_trans_label.setStyleSheet(
                        "color: #dc2626; font-size: 11px;"
                    )

        # Show label if already loaded
        if self._state.imported_translations and self._state.imported_translations_enabled:
            count = len(self._state.imported_translations)
            self._import_trans_label.setText(
                f"Loaded {count:,} translations from imported file"
            )

        # Sync import translations checkbox state — only enable if translations are loaded
        has_imports = bool(self._state.imported_translations)
        self._import_trans_check.setEnabled(has_imports)
        self._import_trans_check.setChecked(
            has_imports and self._state.imported_translations_enabled
        )
        if has_imports:
            count = len(self._state.imported_translations)
            self._import_trans_label.setText(f"\u2713 {count:,} translations imported")
            self._import_trans_label.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 600;")
        else:
            self._import_trans_label.setText("")
        self._update_estimate()
        self._refresh_settings_summary()
        self._start_btn.setEnabled(self._state.document is not None and not self.is_busy)

        # Show retranslation checkbox only if document has any translated entries
        if self._state.document is not None:
            pass  # retranslate is controlled via Translation menu only

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

    # ------------------------------------------------------------------ import translations

    def _on_import_translations(self) -> None:
        """Open a file dialog, parse the selected Excel, and store imported translations."""
        from PySide6.QtWidgets import QFileDialog
        from ...import_translations import parse_translation_file

        path, _ = QFileDialog.getOpenFileName(
            self, "Import existing translations",
            str(Path.home()),
            "Excel files (*.xlsx);;All files (*)",
        )
        if not path:
            return
        try:
            result = parse_translation_file(Path(path))
        except Exception as exc:  # noqa: BLE001
            self.error(f"Failed to parse import file: {exc}", "Import error")
            return

        if result.count == 0:
            self.warn(
                "No translations found in the selected file.\n\n"
                "The file should have columns like Label/Translation, "
                "Source/Translation, or Source/Target."
            )
            return

        self._state.imported_translations = result.translations
        self._state.imported_translations_path = Path(path)
        self._state.imported_translations_enabled = True
        self._import_trans_check.setEnabled(True)
        self._import_trans_check.setChecked(True)
        self._import_trans_label.setText(
            f"\u2713 {result.count:,} translations imported"
        )
        self._import_trans_label.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 600;")
        # Persist path + enabled state so Settings dialog stays in sync
        gui_settings.set_str(gui_settings.KEYS.import_translations_path, path)
        gui_settings.set_str(gui_settings.KEYS.import_translations_enabled, "1")
        self.status_message.emit(
            f"Imported {result.count:,} translations from {Path(path).name}"
        )

    def _on_import_trans_toggled(self, checked: bool) -> None:
        """Toggle whether imported translations are used during translation.

        Writes back to gui_settings so the Settings dialog stays in sync,
        and updates the Translation menu toggle as well.
        """
        self._state.imported_translations_enabled = checked
        # Keep Settings dialog in sync
        gui_settings.set_str(gui_settings.KEYS.import_translations_enabled, "1" if checked else "0")
        # Keep Translation menu action in sync (use_imported_translations key)
        gui_settings.set_use_imported_translations(checked)
        # Update the menu action widget without triggering infinite loop
        main_win = self.window()
        if hasattr(main_win, '_act_use_imported'):
            main_win._act_use_imported.blockSignals(True)
            main_win._act_use_imported.setChecked(checked)
            main_win._act_use_imported.blockSignals(False)

    # ------------------------------------------------------------------ output path

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
                "Click 'Load Excel...' to load an Excel directly into this phase,\n"
                "or complete Phase 1 (Import STF) first."
            )
            return

        # Pre-flight: check backend availability.
        from ...translate.factory import check_backend_available

        backend_key = gui_settings.get_str(gui_settings.KEYS.backend, "google")
        api_key = gui_secrets.retrieve_api_key(backend_key) or None
        available, reason = check_backend_available(backend_key, api_key)
        if not available:
            self.error(
                f"Backend '{backend_key}' is not ready:\n\n{reason}\n\n"
                "Fix the issue in Edit \u2192 Settings, then try again.",
                "Backend not available",
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

        # --- Read translation option toggles from Translation menu (persistent settings)
        use_infile = gui_settings.get_use_infile_translations()
        use_tm = gui_settings.get_use_tm_cache()
        use_fuzzy = gui_settings.get_use_fuzzy_matching() and use_tm
        retranslate = gui_settings.get_retranslate_existing()
        self._state.retranslate_existing = retranslate
        self._use_fuzzy_this_run = use_fuzzy

        # Imported translations: respect both the menu toggle and state
        use_imported_menu = gui_settings.get_use_imported_translations()
        imported_translations = None
        imported_count = 0
        if use_imported_menu and self._state.imported_translations_enabled and self._state.imported_translations:
            imported_translations = self._state.imported_translations
            imported_count = len(imported_translations)

        # --- In-file translations: build seed dict from already-translated rows
        infile_seed: dict[str, str] | None = None
        infile_reuse_count = [0]
        if use_infile and not retranslate:
            seed: dict[str, str] = {}
            for entry in self._state.document.entries:
                label = entry.label.strip()
                translation = entry.translation.strip()
                if label and translation and label not in seed:
                    seed[label] = translation
            if seed:
                infile_seed = seed
                self.status_message.emit(
                    f"In-file translations: {len(seed):,} unique labels with existing translations "
                    f"will be reused without API calls."
                )

        gui_settings.remember_target_language(self._state.target_language_name, self._state.target_language_code)

        # ---- Show pre-flight confirmation dialog (unless user disabled it)
        if not gui_settings.get_preflight_skip():
            from ..preflight_dialog import PreflightDialog
            checkpoint = self._build_checkpoint()
            dlg = PreflightDialog(
                source_lang=self._source_combo.currentText() or "English",
                target_lang=self._state.target_language_name,
                rows_to_translate=scope.estimate_count(self._state.document) if scope else len(self._state.document.entries),
                total_rows=len(self._state.document.entries),
                backend=backend_key,
                workers=gui_settings.get_int(gui_settings.KEYS.workers, 4),
                use_infile=use_infile,
                use_tm=use_tm,
                use_fuzzy=use_fuzzy,
                use_imported=use_imported_menu,
                imported_count=imported_count,
                retranslate=retranslate,
                has_checkpoint=checkpoint.exists() if checkpoint else False,
                parent=self,
            )
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            if dlg.dont_show_again():
                gui_settings.set_preflight_skip(True)

        # ---- Read advanced options from Settings.
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

        # Translation memory (disabled if use_tm toggle is off)
        memory = None
        if use_tm:
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
        self._total_rows = len(self._state.document.entries)
        self._start_time = time.time()
        self._log.clear()

        # ---- Live feed header showing language pair
        src_code = code_for_language(self._source_combo.currentText()) or "en"
        self._log.appendPlainText(
            f"\u2500\u2500  {src_code.upper()} \u2192 {self._state.target_language_code.upper()}  "
            f"\u2500\u2500  scope: {self._total_rows:,} rows  |  workers: {workers}"
        )
        self._log.appendPlainText(
            "  Legend: Translated = via API  |  Memory = via Translation Memory  "
            "|  Dedup = via deduplication (same label in run)"
        )
        self._log.appendPlainText("")

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
            checkpoint=self._build_checkpoint(),
            workers=workers,
            rate_limit_per_second=rate_limit,
            prevent_system_sleep=prevent_sleep,
            backend_name=gui_settings.get_str(gui_settings.KEYS.backend, "google"),
            api_key=gui_secrets.retrieve_api_key(
                gui_settings.get_str(gui_settings.KEYS.backend, "google")
            ) or None,
            fuzzy_threshold=self._get_fuzzy_threshold() if use_fuzzy else None,
            fuzzy_max_results=gui_settings.get_int(gui_settings.KEYS.fuzzy_max_results, 5),
            fuzzy_auto_accept_threshold=self._get_fuzzy_auto_accept(),
            imported_translations=imported_translations,
            infile_translations=infile_seed,
            retranslate_existing=self._state.retranslate_existing,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.row_translated.connect(self._on_row_translated)
        self._worker.finished_ok.connect(self._on_translation_done)
        self._worker.failed.connect(self._on_translation_failed)
        self._worker.start()

    def _on_progress(self, percent: int, message: str) -> None:
        if self._worker is None:
            return  # Ignore queued signals after force stop
        self._progress.setValue(percent)
        if self._start_time is not None and self._current_row > 0:
            elapsed = time.time() - self._start_time
            rate = self._current_row / elapsed if elapsed > 0 else 0
            remaining = self._total_rows - self._current_row
            eta_sec = remaining / rate if rate > 0 else 0
            self._eta_label.setText(
                f"Translating... {percent}% | {rate:.1f} rows/s | ETA: {_format_eta(eta_sec)}"
            )
        elif percent > 0:
            self._eta_label.setText(f"Translating... {percent}%")

    def _on_row_translated(self, source: str, translation: str, status: str, from_fuzzy: bool) -> None:
        if self._worker is None:
            return  # Ignore queued signals after force stop
        self._current_row += 1

        # Update running counters from status keywords.
        if status.startswith("Translated") or status.startswith("Reused") or status.startswith("Resumed"):
            self._translated_count += 1
            if "TM hit" in status:
                self._cached_count += 1
            elif "dedup" in status:
                self._deduped_count += 1
        elif status.startswith("Skipped") or status.startswith("Cancelled"):
            self._skipped_count += 1

        # Inline counters in the feed line — readable labels
        src_code = (code_for_language(self._source_combo.currentText()) or "en").upper()
        tgt_code = (self._state.target_language_code or "ja").upper()
        prefix = (
            f"[{self._current_row}/{self._total_rows} | "
            f"Translated:{self._translated_count} Memory:{self._cached_count} "
            f"Dedup:{self._deduped_count}]"
        )

        # Show [FUZZY] prefix for fuzzy TM matches using structured flag
        fuzzy_prefix = ""
        if from_fuzzy:
            fuzzy_prefix = "[FUZZY] "

        if translation:
            self._log.appendPlainText(
                f"{prefix} {fuzzy_prefix}{src_code}: {source} -> {tgt_code}: {translation}"
            )
        else:
            self._log.appendPlainText(f"{prefix} {fuzzy_prefix}[{status}] {source}")

        # Intermittent summary every 50 rows
        if self._current_row % 50 == 0 and self._start_time is not None:
            elapsed = time.time() - self._start_time
            rate = self._current_row / elapsed if elapsed > 0 else 0
            remaining = self._total_rows - self._current_row
            eta = remaining / rate if rate > 0 else 0
            pct = (self._current_row * 100 // self._total_rows) if self._total_rows > 0 else 100
            self._log.appendPlainText(
                f"  --- {self._current_row}/{self._total_rows} "
                f"({pct}%) | "
                f"{rate:.1f} rows/s | ETA: {_format_eta(eta)} ---"
            )

    def _on_translation_done(self, done) -> None:
        self._state.translation_summaries = done.summaries
        self._state.translation_statuses = done.statuses
        elapsed = done.elapsed_seconds

        # Set progress bar to 100% on completion
        self._progress.setValue(100)

        # Detect if this completion was from a cancellation
        was_cancelled = self._worker is not None and self._worker.is_cancelled

        # Compute summary numbers
        # "Rows processed successfully" = all rows that ended up with a valid
        # translation (regardless of method).  translated_count already includes
        # TM hits, dedup reuse, imported file reuse, in-file reuse, and fuzzy
        # matches as subsets.  skipped_count covers rows kept as-is (blank
        # labels, already translated when not retranslating, out of scope).
        rows_successful = done.translated_count + done.skipped_count
        rows_failed = done.failed_count
        elapsed_str = _format_eta(elapsed)
        rate = rows_successful / elapsed if elapsed > 0 else 0

        # Breakdown of how rows were translated.  translated_count is the
        # TOTAL of all methods, so compute the pure-API portion by subtracting
        # all sub-categories that are already tracked separately.
        api_count = (
            done.translated_count - done.cached_count - done.deduped_count
            - done.fuzzy_accepted_count - done.imported_reuse_count
            - done.infile_reuse_count - done.resumed_count
        )

        sep = "\u2550" * 43
        retranslate_on = self._state.retranslate_existing
        fuzzy_enabled = getattr(self, "_use_fuzzy_this_run", False)

        self._log.appendPlainText("")
        if was_cancelled:
            self._log.appendPlainText(sep)
            self._log.appendPlainText("  TRANSLATION CANCELLED")
            self._log.appendPlainText(sep)
        else:
            self._log.appendPlainText(sep)
            self._log.appendPlainText("  TRANSLATION COMPLETE")
            self._log.appendPlainText(sep)

        self._log.appendPlainText(f"  Rows processed successfully: {rows_successful:>5,}")
        self._log.appendPlainText(f"  Rows Process Failed:         {rows_failed:>5,}")
        self._log.appendPlainText("")
        self._log.appendPlainText(
            f"  Successfully Translated:     {rows_successful:>5,}"
        )
        self._log.appendPlainText(
            f"  \u251c\u2500 Via Translation API:      {api_count:>7,}"
        )
        self._log.appendPlainText(
            f"  \u251c\u2500 Via Translation Memory:   {done.cached_count:>7,}"
        )
        if fuzzy_enabled:
            self._log.appendPlainText(
                f"  \u2502    (via fuzzy match:      {done.fuzzy_accepted_count:>7,})"
            )
        self._log.appendPlainText(
            f"  \u251c\u2500 Via deduplication:        {done.deduped_count:>7,}"
        )
        # In-file label match: always show, annotate when retranslate is ON
        infile_ann = "   (disabled when retranslate=ON)" if retranslate_on else ""
        self._log.appendPlainText(
            f"  \u251c\u2500 Via in-file label match: {done.infile_reuse_count:>7,}{infile_ann}"
        )
        # Imported reference: always show
        self._log.appendPlainText(
            f"  \u251c\u2500 Via imported reference:   {done.imported_reuse_count:>7,}"
        )
        # Resumed from checkpoint: only show if count > 0
        if done.resumed_count:
            self._log.appendPlainText(
                f"  \u251c\u2500 Resumed from checkpoint: {done.resumed_count:>7,}"
            )
        # Pre-existing (unchanged): always show, annotate when retranslate is ON
        preexist_ann = "   (nothing skipped when retranslate=ON)" if retranslate_on else ""
        self._log.appendPlainText(
            f"  \u2514\u2500 Pre-existing (unchanged):{done.skipped_count:>7,}{preexist_ann}"
        )
        self._log.appendPlainText("")
        self._log.appendPlainText(f"  Failed Translations:         {rows_failed:>5,}")
        self._log.appendPlainText("")
        self._log.appendPlainText(f"  Elapsed time:            {elapsed_str:>9}")
        if rate > 0:
            self._log.appendPlainText(f"  Rate:                    {rate:>5.1f} rows/s")
        self._log.appendPlainText(sep)

        if was_cancelled:
            msg = (
                f"Cancelled - translated {done.translated_count:,} rows before stopping.  "
                f"Click 'Start translation' to resume from checkpoint."
            )
        else:
            # The translated document is held in memory (self._state.document).
            # Don't auto-save: surface the "Save copy to..." button instead so
            # the user picks where to save.
            failed_note = f", {rows_failed:,} failed" if rows_failed else ""
            infile_note = f" | InFile: {done.infile_reuse_count:,}" if done.infile_reuse_count else ""
            msg = (
                f"Translation complete - {rows_successful:,} rows processed successfully"
                f"{failed_note}.  "
                f"Click 'Save a Copy...' to save.  "
                f"[API: {api_count:,} | TM: {done.cached_count:,} | "
                f"Dedup: {done.deduped_count:,}{infile_note} | "
                f"Kept: {done.skipped_count:,}] "
                f"in {elapsed_str}."
            )

        self._eta_label.setText(msg)
        self.status_message.emit(msg)

        # Mark the phase done so users can navigate forward; the Save
        # a Copy... button is now available for explicit file save.
        self._set_running(False)
        self._save_copy_btn.setEnabled(True)
        self._next_btn.setEnabled(True)
        self._state.set_phase(2, PhaseStatus.DONE)
        self._state.has_unsaved_changes = True
        # Update workflow artifact type to reflect that we now have a
        # translated in-memory document (even if not saved to disk yet).
        self._state.current_working_artifact_type = "translated_excel"
        self.action_recorded.emit(
            f"Translate completed ({done.translated_count} rows, "
            f"{self._state.target_language_code.upper()})"
        )

    def _on_translation_failed(self, message: str) -> None:
        self._set_running(False)
        self._state.set_phase(2, PhaseStatus.ERROR)
        safe_msg = gui_secrets.sanitize_error_message(message)

        # Append the error to the live feed so it's visible even if the dialog is dismissed.
        self._log.appendPlainText(f"\n[ERROR] Translation failed: {safe_msg}")
        self._eta_label.setText(f"Error: {safe_msg[:120]}")

        # Provide actionable help based on common error types.
        help_text = ""
        lower = message.lower()
        if "connectionerror" in lower or "network" in lower or "timeout" in lower or "connect" in lower:
            help_text = (
                "\n\nThis looks like a network issue.\n"
                "• Check that you have internet access.\n"
                "• If you're behind a corporate proxy, translation may be blocked.\n"
                "• Try again -- Google's free tier sometimes rate-limits briefly."
            )
        elif "429" in message or "too many requests" in lower or "rate" in lower:
            help_text = (
                "\n\nGoogle's free tier rate-limited the request.\n"
                "• Wait a minute and try again.\n"
                "• Reduce Workers in Edit → Settings (try 1 worker).\n"
                "• Switch to a paid backend (DeepL/Azure) in Edit → Settings."
            )
        elif "importerror" in lower or "no module" in lower:
            help_text = (
                "\n\nA required library is missing.\n"
                "• Run: pip install -e \".[gui]\" in the project folder.\n"
                "• Re-launch the app."
            )
        elif "invalid" in lower and ("lang" in lower or "code" in lower):
            help_text = (
                "\n\nThe source or target language code is not recognised by Google.\n"
                "• Check that the Source language combo in Phase 3 shows 'English'.\n"
                "• Check that the Target language is set correctly."
            )

        self.error(safe_msg + help_text, "Translation failed")

    def _on_save_copy_to(self) -> None:
        """Open a save dialog and persist the in-memory translated document.

        Suggests ``<source_stem>_translated.xlsx`` in the same folder as
        the source/organised file by default.  The audit sheets (summary
        and per-row status log) are still appended to the saved workbook.
        """
        if self._state.document is None:
            self.warn("No translated document to save -- run translation first.")
            return
        if self.is_busy:
            return

        # Suggest a professional, dated default filename based on the source.
        suggested_name = self.default_save_name("translated")

        path = self.pick_save_file(
            "Save translated workbook as",
            "Excel files (*.xlsx)",
            suggested_name,
        )
        if not path:
            return
        self._save_translated(path)

    def _save_translated(self, path: Path) -> None:
        """Persist the in-memory document to ``path`` as .xlsx with audit sheets."""
        if self._state.document is None:
            return
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        self.set_busy(True)
        self._save_copy_btn.setEnabled(False)
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
        self.set_busy(False)
        self._save_copy_btn.setEnabled(True)
        self._next_btn.setEnabled(True)
        self._state.set_phase(2, PhaseStatus.DONE)
        self.status_message.emit(f"Translated workbook saved: {path}")

    def _on_save_failed(self, message: str) -> None:
        self.set_busy(False)
        self._save_copy_btn.setEnabled(self._state.document is not None)
        self.error(message, "Save failed")

    def _on_cancel(self) -> None:
        if self._worker is None:
            return
        if self._worker.is_cancelled:
            self.status_message.emit("Already cancelling -- please wait.")
            return

        # Show cancellation type dialog
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Cancel Translation")
        dlg.setText("Translation is running. How would you like to cancel?")
        dlg.setIcon(QMessageBox.Icon.Question)

        graceful_btn = dlg.addButton(
            "Finish in-flight rows", QMessageBox.ButtonRole.AcceptRole
        )
        graceful_btn.setToolTip(
            "Wait for currently running rows to complete, then stop.\n"
            "Progress is saved and resumable."
        )
        force_btn = dlg.addButton(
            "Stop immediately", QMessageBox.ButtonRole.DestructiveRole
        )
        force_btn.setToolTip(
            "Kill all workers immediately without waiting.\n"
            "Progress up to the last completed row is saved."
        )
        dlg.addButton(QMessageBox.StandardButton.Cancel)

        dlg.exec()
        clicked = dlg.clickedButton()

        if clicked == graceful_btn:
            # Cooperative cancellation: let in-flight rows finish
            self._worker.cancel()
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Cancelling (graceful)...")
            self.status_message.emit(
                "Graceful cancellation requested -- finishing in-flight rows..."
            )
        elif clicked == force_btn:
            # Force-terminate the worker thread immediately
            self._worker.cancel()  # set the flag first
            self._worker.terminate()
            self._worker.wait(3000)  # wait up to 3s for cleanup
            # Disconnect progress signals so queued events don't update UI
            try:
                self._worker.progress.disconnect(self._on_progress)
                self._worker.row_translated.disconnect(self._on_row_translated)
            except (RuntimeError, TypeError):
                pass  # already disconnected
            self._worker = None
            self._set_running(False)
            self._cancel_btn.setText("Cancel")
            # Freeze progress bar at current value and show cancelled state
            self._eta_label.setText(
                f"Cancelled (force stopped) — {self._current_row:,} rows completed"
            )
            self._log.appendPlainText(
                "\n[CANCELLED] Force stopped -- in-flight rows discarded."
            )
            self._state.set_phase(2, PhaseStatus.ERROR)
            self.status_message.emit(
                "Translation force-stopped. Progress up to last completed row is saved."
            )
        # else: user clicked Cancel (dismiss) -- translation continues

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
        if not self.check_workflow_override(path):
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
            # Set active workflow context so subsequent loads trigger override dialog.
            self._state.set_active_workflow_context(
                document=doc,
                original_source_path=path,
                current_working_path=path,
                current_working_artifact_type="organized_excel",
                start_phase=2,
                current_phase=2,
                override_existing=False,
                reset_downstream=False,
            )
            # Reset component selection so Filter Components picks up the new doc.
            self._selected_components = {e.component_type for e in doc.entries}
            # Suggest a professional default translated output path for Save a Copy...
            self._state.translated_xlsx_path = path.parent / self.default_save_name("translated")
            self._next_btn.setEnabled(True)
            self.on_enter()
            self.status_message.emit(
                f"Loaded {len(doc.entries):,} rows from {path.name}.  "
                f"Click 'Filter Components...' to select which to translate, then Start."
            )

        worker.finished_ok.connect(_loaded)
        worker.failed.connect(lambda msg: self.error(msg, "Load failed"))
        worker.start()

    # ------------------------------------------------------------------ continue to Phase 4

    def _on_continue_to_phase4(self) -> None:
        self._state.set_phase(2, PhaseStatus.DONE)
        self.request_navigate.emit(3)

    # ------------------------------------------------------------------ helpers

    def _build_checkpoint(self) -> Optional[CheckpointStore]:
        """Create a CheckpointStore for the current document and target language."""
        source_path = self._state.organized_xlsx_path or self._state.source_stf_path
        if source_path is None:
            return None
        target_code = self._state.target_language_code or "ja"
        return CheckpointStore(
            source_file=str(Path(source_path).resolve()),
            target_lang=target_code,
        )

    def _on_reset_checkpoint(self) -> None:
        """Clear checkpoint if one exists, otherwise offer to reset Phase 3 entirely."""
        cp = self._build_checkpoint()
        if cp is not None and cp.exists():
            # Checkpoint exists: confirm clearing it
            reply = QMessageBox.question(
                self,
                "Clear Checkpoint",
                "Clear the saved checkpoint?\n"
                "Translation will start from the beginning next time.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                cp.clear()
                self.status_message.emit("Checkpoint cleared -- next run will start fresh.")
        else:
            # No checkpoint: offer to reset Phase 3 to initial state
            reply = QMessageBox.question(
                self,
                "Reset Phase 3",
                "No checkpoint found.\n\n"
                "Reset Phase 3 to initial state? This will clear the live feed "
                "and translation results.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.reset_page()
                self.status_message.emit("Phase 3 reset to initial state.")

    def _get_fuzzy_threshold(self) -> Optional[float]:
        """Read fuzzy threshold from settings; returns None if disabled (0)."""
        raw = gui_settings.get_str(gui_settings.KEYS.fuzzy_threshold, "75.0")
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = 75.0
        return val if val > 0 else None

    def _get_fuzzy_auto_accept(self) -> float:
        """Read fuzzy auto-accept threshold from settings."""
        raw = gui_settings.get_str(gui_settings.KEYS.fuzzy_auto_accept, "90.0")
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 90.0

    def _set_running(self, running: bool) -> None:
        self.set_busy(running)
        self._start_btn.setEnabled(not running and self._state.document is not None)
        self._cancel_btn.setEnabled(running)
        self._cancel_btn.setText("Cancel")
        self._load_btn.setEnabled(not running)
        self._target_combo.setEnabled(not running)
        self._source_combo.setEnabled(not running)
        self._filter_btn.setEnabled(not running)
        # Disable Save copy to... while translating; re-enable it once a
        # translation has completed (handled in _on_translation_done /
        # _on_save_done).
        if running:
            self._save_copy_btn.setEnabled(False)

    # ------------------------------------------------------------------ pop-out feed

    def reset_page(self) -> None:
        """Called by Reset Session to clear all displayed widgets back to defaults."""
        self._log.clear()
        self._progress.setValue(0)
        self._eta_label.setText("")
        self._save_copy_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        self._start_btn.setEnabled(False)
        self._source_combo.setCurrentText("English")
        self._target_combo.setCurrentText("Japanese")
        self._selected_components = None
        self._estimate_label.setText("Rows to translate: --")
        self._import_trans_label.setText("")
        self._import_trans_check.setChecked(False)
        self._import_trans_check.setEnabled(False)
        self._translated_count = 0
        self._cached_count = 0
        self._deduped_count = 0
        self._skipped_count = 0
        self._total_rows = 0
        self._current_row = 0
        self._start_time = None
        self._import_trans_label.setText("")
        self._import_trans_check.setChecked(False)

    def _on_popout_feed(self) -> None:
        if hasattr(self, '_feed_dialog') and self._feed_dialog is not None:
            self._feed_dialog.raise_()
            self._feed_dialog.activateWindow()
            return
        self._feed_dialog = QDialog(self)
        self._feed_dialog.setWindowTitle("Live Translation Feed")
        from .base import clamp_to_screen
        clamp_to_screen(self._feed_dialog, 800, 500)
        self._feed_dialog.setWindowFlags(
            self._feed_dialog.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        layout = QVBoxLayout(self._feed_dialog)
        self._log.setParent(self._feed_dialog)
        layout.addWidget(self._log)
        self._feed_dialog.finished.connect(self._on_feed_dialog_closed)
        self._feed_dialog.show()

    def _on_feed_dialog_closed(self) -> None:
        self._log.setParent(self._feed_box)
        self._feed_layout.addWidget(self._log)
        self._feed_dialog = None
