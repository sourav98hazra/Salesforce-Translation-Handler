"""Settings dialog -- one place for every advanced option.

Phase 3 used to expose backend, API key, worker count, rate limit,
wake-lock, glossary path, TM path, and batch targets directly on the
page.  That made the page feel cluttered.  v1.3 moves all of that into
this dialog (``Edit -> Settings...`` or ``Ctrl+,``) so Phase 3 only
has to ask the questions a translator actually needs to answer
(target language, which components, where to save).

Values persist via :mod:`stx.gui.settings` (QSettings under the hood).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..memory import default_tm_path
from ..translate import list_backends
from . import settings as gui_settings


class SettingsDialog(QDialog):
    """Single dialog grouping every advanced option.

    Tabs:

    * **Translation** -- backend / API key / workers / rate / wake-lock /
      batch targets.
    * **Resources** -- glossary CSV, translation memory database.
    * **Appearance** -- theme.

    OK saves and emits :pyattr:`accepted`; Cancel discards changes.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "Advanced options.  Most users can leave these alone -- defaults "
            "are sensible for the free Google Translate tier."
        )
        intro.setStyleSheet("color: #64748b;")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_translation_tab(), "Translation")
        self._tabs.addTab(self._build_resources_tab(), "Resources")
        self._tabs.addTab(self._build_appearance_tab(), "Appearance")
        self._tabs.setTabToolTip(
            0, "Translator backend, API key, performance, multi-language batch"
        )
        self._tabs.setTabToolTip(
            1, "Glossary CSV and translation memory database paths"
        )
        self._tabs.setTabToolTip(
            2, "Application theme and visual preferences"
        )
        layout.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._on_restore_defaults)
        layout.addWidget(buttons)

        self._load_values()

    # ------------------------------------------------------------------ tabs

    def _build_translation_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        # Backend group
        backend_box = QGroupBox("Backend")
        form = QFormLayout(backend_box)
        self._backend_combo = QComboBox()
        for info in list_backends():
            self._backend_combo.addItem(info.label, info.key)
        self._backend_combo.currentIndexChanged.connect(self._update_backend_help)
        form.addRow("Translator:", self._backend_combo)

        self._api_key_field = QLineEdit()
        self._api_key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_field.setPlaceholderText("Leave blank to use environment variable")
        form.addRow("API key:", self._api_key_field)

        self._backend_help = QLabel("")
        self._backend_help.setWordWrap(True)
        self._backend_help.setStyleSheet("color: #64748b; font-size: 11px;")
        form.addRow("", self._backend_help)
        outer.addWidget(backend_box)

        # Performance group
        perf_box = QGroupBox("Performance")
        perf_form = QFormLayout(perf_box)

        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 32)
        self._workers_spin.setValue(4)
        self._workers_spin.setToolTip("Concurrent translation workers (4 is a safe default)")
        perf_form.addRow("Workers:", self._workers_spin)

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0.0, 100.0)
        self._rate_spin.setSingleStep(0.5)
        self._rate_spin.setValue(8.0)
        self._rate_spin.setSuffix(" req/s")
        self._rate_spin.setSpecialValueText("unlimited")
        self._rate_spin.setToolTip("0 = unlimited (recommended for paid backends only)")
        perf_form.addRow("Rate limit:", self._rate_spin)

        self._wakelock_check = QCheckBox("Prevent system sleep during translation")
        self._wakelock_check.setChecked(True)
        perf_form.addRow("", self._wakelock_check)
        outer.addWidget(perf_box)

        # Multi-language batch group
        batch_box = QGroupBox("Multi-language batch (optional)")
        batch_form = QFormLayout(batch_box)
        self._batch_field = QLineEdit()
        self._batch_field.setPlaceholderText("Comma separated extra target codes (e.g. fr, de, es)")
        batch_form.addRow("Extra targets:", self._batch_field)
        outer.addWidget(batch_box)

        outer.addStretch(1)
        return widget

    def _build_resources_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        # Glossary
        gloss_box = QGroupBox("Glossary (optional)")
        gloss_layout = QVBoxLayout(gloss_box)
        gloss_help = QLabel(
            "CSV with three columns: source, target, do_not_translate.  "
            "Brand or product names you mark as do_not_translate are protected "
            "from modification."
        )
        gloss_help.setWordWrap(True)
        gloss_help.setStyleSheet("color: #64748b; font-size: 11px;")
        gloss_layout.addWidget(gloss_help)
        row = QHBoxLayout()
        self._glossary_field = QLineEdit()
        self._glossary_field.setPlaceholderText("Path to glossary.csv")
        gloss_browse = QPushButton("Browse...")
        gloss_browse.clicked.connect(self._on_browse_glossary)
        row.addWidget(self._glossary_field, stretch=1)
        row.addWidget(gloss_browse)
        gloss_layout.addLayout(row)
        outer.addWidget(gloss_box)

        # Translation memory
        tm_box = QGroupBox("Translation memory")
        tm_layout = QVBoxLayout(tm_box)
        tm_help = QLabel(
            "SQLite database that caches every translation.  Subsequent runs "
            "with the same source text reuse the cached translation -- much "
            "faster, and no API quota consumed."
        )
        tm_help.setWordWrap(True)
        tm_help.setStyleSheet("color: #64748b; font-size: 11px;")
        tm_layout.addWidget(tm_help)
        row = QHBoxLayout()
        self._memory_field = QLineEdit()
        self._memory_field.setPlaceholderText(str(default_tm_path()))
        tm_browse = QPushButton("Browse...")
        tm_browse.clicked.connect(self._on_browse_memory)
        row.addWidget(self._memory_field, stretch=1)
        row.addWidget(tm_browse)
        tm_layout.addLayout(row)
        outer.addWidget(tm_box)

        outer.addStretch(1)
        return widget

    def _build_appearance_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        theme_box = QGroupBox("Theme")
        theme_form = QFormLayout(theme_box)
        self._theme_combo = QComboBox()
        self._theme_combo.addItem("Light", "light")
        self._theme_combo.addItem("Dark", "dark")
        self._theme_combo.addItem("Ocean (blue/teal)", "ocean")
        self._theme_combo.addItem("Forest (green)", "forest")
        self._theme_combo.addItem("Sunset (warm amber)", "sunset")
        self._theme_combo.addItem("Auto (follow system)", "auto")
        theme_form.addRow("Application theme:", self._theme_combo)

        note = QLabel("Theme changes apply immediately when you click OK.")
        note.setStyleSheet("color: #64748b; font-size: 11px;")
        theme_form.addRow("", note)
        outer.addWidget(theme_box)

        outer.addStretch(1)
        return widget

    # ------------------------------------------------------------------ load / save

    def _load_values(self) -> None:
        # Backend
        backend = gui_settings.get_str(gui_settings.KEYS.backend, "google")
        for i in range(self._backend_combo.count()):
            if self._backend_combo.itemData(i) == backend:
                self._backend_combo.setCurrentIndex(i)
                break
        self._update_backend_help()
        self._api_key_field.setText(gui_settings.get_str("translation/api_key", ""))

        # Performance
        self._workers_spin.setValue(gui_settings.get_int(gui_settings.KEYS.workers, 4))
        rate = gui_settings.get_str("translation/rate_limit", "8.0")
        try:
            self._rate_spin.setValue(float(rate))
        except (TypeError, ValueError):
            self._rate_spin.setValue(8.0)
        wake = gui_settings.get_str("translation/prevent_sleep", "1")
        self._wakelock_check.setChecked(wake in {"1", "true", "True"})

        # Batch
        self._batch_field.setText(gui_settings.get_str("translation/batch_targets", ""))

        # Resources
        self._glossary_field.setText(gui_settings.get_str(gui_settings.KEYS.glossary_path, ""))
        self._memory_field.setText(gui_settings.get_str(gui_settings.KEYS.memory_path, ""))

        # Appearance
        theme = gui_settings.get_theme()
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == theme:
                self._theme_combo.setCurrentIndex(i)
                break

    def _save_values(self) -> None:
        gui_settings.set_str(gui_settings.KEYS.backend, self._backend_combo.currentData())
        gui_settings.set_str("translation/api_key", self._api_key_field.text().strip())
        gui_settings.set_int(gui_settings.KEYS.workers, self._workers_spin.value())
        gui_settings.set_str("translation/rate_limit", str(self._rate_spin.value()))
        gui_settings.set_str(
            "translation/prevent_sleep",
            "1" if self._wakelock_check.isChecked() else "0",
        )
        gui_settings.set_str("translation/batch_targets", self._batch_field.text().strip())
        gui_settings.set_str(gui_settings.KEYS.glossary_path, self._glossary_field.text().strip())
        gui_settings.set_str(gui_settings.KEYS.memory_path, self._memory_field.text().strip())
        gui_settings.set_theme(self._theme_combo.currentData())

    def _on_accept(self) -> None:
        self._save_values()
        # Apply theme change immediately.
        try:
            from . import theme as theme_module
            theme_module.apply_theme(self._theme_combo.currentData())
        except Exception:  # noqa: BLE001
            pass
        self.accept()

    def _on_restore_defaults(self) -> None:
        self._backend_combo.setCurrentIndex(0)
        self._api_key_field.clear()
        self._workers_spin.setValue(4)
        self._rate_spin.setValue(8.0)
        self._wakelock_check.setChecked(True)
        self._batch_field.clear()
        self._glossary_field.clear()
        self._memory_field.clear()
        self._theme_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------ helpers

    def _update_backend_help(self) -> None:
        key = self._backend_combo.currentData()
        for info in list_backends():
            if info.key == key:
                env_hint = f"  Env var: {info.env_var}" if info.env_var else ""
                requires = "API key required" if info.requires_api_key else "No API key needed"
                self._backend_help.setText(f"{info.description}  ({requires}.{env_hint})")
                return

    def _on_browse_glossary(self) -> None:
        start = self._glossary_field.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose glossary CSV", start, "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._glossary_field.setText(path)

    def _on_browse_memory(self) -> None:
        start = self._memory_field.text() or str(default_tm_path())
        path, _ = QFileDialog.getSaveFileName(
            self, "Translation memory database", start, "SQLite (*.sqlite *.db);;All files (*)"
        )
        if path:
            self._memory_field.setText(path)


def open_settings(parent: Optional[QWidget] = None) -> bool:
    """Open the dialog modally.  Returns True if the user clicked OK."""
    dialog = SettingsDialog(parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
