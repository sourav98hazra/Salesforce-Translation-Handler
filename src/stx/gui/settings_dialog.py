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
from ..translate.factory import check_backend_available
from . import secrets as gui_secrets
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
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        from .pages.base import clamp_to_screen
        clamp_to_screen(self, 600, 700)

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
            1, "Translation memory, glossary, imported translations, session"
        )
        self._tabs.setTabToolTip(
            2, "Application theme and credential storage"
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

        # --- Translator Backend group ---
        backend_box = QGroupBox("Translator Backend")
        form = QFormLayout(backend_box)
        self._backend_combo = QComboBox()
        for info in list_backends():
            self._backend_combo.addItem(info.label, info.key)
        self._backend_combo.currentIndexChanged.connect(self._update_backend_help)
        form.addRow("Translator:", self._backend_combo)

        self._api_key_field = QLineEdit()
        self._api_key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_field.setPlaceholderText("Leave blank to use environment variable")
        self._api_key_field.textChanged.connect(self._update_backend_status)
        form.addRow("API key:", self._api_key_field)

        self._backend_help = QLabel("")
        self._backend_help.setWordWrap(True)
        self._backend_help.setStyleSheet("color: #64748b; font-size: 11px;")
        form.addRow("", self._backend_help)

        self._backend_status = QLabel("")
        self._backend_status.setWordWrap(True)
        self._backend_status.setStyleSheet("font-size: 11px; font-weight: 600;")
        form.addRow("", self._backend_status)
        outer.addWidget(backend_box)

        # --- Performance group ---
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

        # --- Batch group ---
        batch_box = QGroupBox("Batch")
        batch_form = QFormLayout(batch_box)
        self._batch_field = QLineEdit()
        self._batch_field.setPlaceholderText("Comma separated extra target codes (e.g. fr, de, es)")
        self._batch_field.setToolTip(
            "Translate to multiple languages in one run. Comma-separated codes "
            "(e.g. fr, de, es). Each language gets its own output subfolder."
        )
        batch_form.addRow("Extra targets:", self._batch_field)
        outer.addWidget(batch_box)

        outer.addStretch(1)
        return widget

    def _build_resources_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        # --- Translation Memory group ---
        tm_box = QGroupBox("Translation Memory")
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

        # Fuzzy matching controls within TM group
        fuzzy_form = QFormLayout()
        fuzzy_help = QLabel(
            "When an exact TM match is not found, fuzzy matching searches for "
            "similar source strings.  Matches above the auto-accept threshold "
            "are used automatically; others are logged as suggestions."
        )
        fuzzy_help.setWordWrap(True)
        fuzzy_help.setStyleSheet("color: #64748b; font-size: 11px;")
        fuzzy_form.addRow(fuzzy_help)

        self._fuzzy_threshold_spin = QDoubleSpinBox()
        self._fuzzy_threshold_spin.setRange(0.0, 100.0)
        self._fuzzy_threshold_spin.setSingleStep(5.0)
        self._fuzzy_threshold_spin.setValue(75.0)
        self._fuzzy_threshold_spin.setSuffix("%")
        self._fuzzy_threshold_spin.setSpecialValueText("disabled")
        self._fuzzy_threshold_spin.setToolTip(
            "Minimum similarity score (0-100) for a fuzzy match.  0 = disabled."
        )
        fuzzy_form.addRow("Fuzzy threshold:", self._fuzzy_threshold_spin)

        self._fuzzy_max_results_spin = QSpinBox()
        self._fuzzy_max_results_spin.setRange(1, 20)
        self._fuzzy_max_results_spin.setValue(5)
        self._fuzzy_max_results_spin.setToolTip("Maximum number of fuzzy matches to consider.")
        fuzzy_form.addRow("Fuzzy max results:", self._fuzzy_max_results_spin)

        self._fuzzy_auto_accept_spin = QDoubleSpinBox()
        self._fuzzy_auto_accept_spin.setRange(0.0, 100.0)
        self._fuzzy_auto_accept_spin.setSingleStep(5.0)
        self._fuzzy_auto_accept_spin.setValue(90.0)
        self._fuzzy_auto_accept_spin.setSuffix("%")
        self._fuzzy_auto_accept_spin.setToolTip(
            "Fuzzy matches scoring above this threshold are auto-accepted "
            "without calling the translator backend."
        )
        fuzzy_form.addRow("Fuzzy auto-accept:", self._fuzzy_auto_accept_spin)

        tm_layout.addLayout(fuzzy_form)
        outer.addWidget(tm_box)

        # --- Glossary group ---
        gloss_box = QGroupBox("Glossary")
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

        # --- Import Translations group ---
        import_box = QGroupBox("Import Translations")
        import_layout = QVBoxLayout(import_box)
        import_help = QLabel(
            "Reuse translations from a previously translated Excel file.  "
            "Imported translations have the highest priority -- they are used "
            "before the TM or network translator."
        )
        import_help.setWordWrap(True)
        import_help.setStyleSheet("color: #64748b; font-size: 11px;")
        import_layout.addWidget(import_help)
        row = QHBoxLayout()
        self._import_trans_field = QLineEdit()
        self._import_trans_field.setPlaceholderText("Path to translated .xlsx file")
        import_browse = QPushButton("Browse...")
        import_browse.clicked.connect(self._on_browse_import_translations)
        row.addWidget(self._import_trans_field, stretch=1)
        row.addWidget(import_browse)
        import_layout.addLayout(row)
        self._import_trans_check = QCheckBox("Use imported translations")
        self._import_trans_check.setToolTip(
            "When checked, translations from the imported file are applied "
            "with highest priority during translation runs."
        )
        import_layout.addWidget(self._import_trans_check)
        outer.addWidget(import_box)

        # --- Session group ---
        session_box = QGroupBox("Session")
        session_form = QFormLayout(session_box)
        self._session_check = QCheckBox("Enable session persistence")
        self._session_check.setToolTip(
            "When enabled, the application automatically saves your session on exit "
            "and restores it when you re-open the same source file."
        )
        session_form.addRow(self._session_check)
        session_note = QLabel(
            "Auto-saves project state (document, translation progress, phase status) "
            "on close and restores it on next launch."
        )
        session_note.setWordWrap(True)
        session_note.setStyleSheet("color: #64748b; font-size: 11px;")
        session_form.addRow(session_note)
        outer.addWidget(session_box)

        outer.addStretch(1)
        return widget

    def _build_appearance_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        # --- Theme group ---
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

        # --- Credentials group ---
        cred_box = QGroupBox("Credentials")
        cred_form = QFormLayout(cred_box)

        self._remember_key_check = QCheckBox("Remember API key (secure storage)")
        self._remember_key_check.setToolTip(
            "Store the key in your OS credential manager (Keychain / Credential Manager / SecretService)."
        )
        cred_form.addRow(self._remember_key_check)

        self._keyring_status_label = QLabel(gui_secrets.keyring_status())
        self._keyring_status_label.setWordWrap(True)
        self._keyring_status_label.setStyleSheet("color: #64748b; font-size: 10px;")
        cred_form.addRow(self._keyring_status_label)

        cred_note = QLabel(
            "When enabled, your API key is stored in the operating system's "
            "secure credential manager (macOS Keychain, Windows Credential "
            "Manager, or Linux SecretService/kwallet)."
        )
        cred_note.setWordWrap(True)
        cred_note.setStyleSheet("color: #64748b; font-size: 11px;")
        cred_form.addRow(cred_note)
        outer.addWidget(cred_box)

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

        # Load API key from secure storage, not QSettings
        backend = self._backend_combo.currentData() or "google"
        remember = gui_settings.get_str(f"translation/remember_api_key_{backend}", "0") == "1"
        self._remember_key_check.setChecked(remember)
        if remember:
            stored_key = gui_secrets.retrieve_api_key(backend) or ""
            self._api_key_field.setText(stored_key)
        else:
            self._api_key_field.setText("")

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

        # Fuzzy matching
        fuzzy_thresh = gui_settings.get_str(gui_settings.KEYS.fuzzy_threshold, "75.0")
        try:
            self._fuzzy_threshold_spin.setValue(float(fuzzy_thresh))
        except (TypeError, ValueError):
            self._fuzzy_threshold_spin.setValue(75.0)
        self._fuzzy_max_results_spin.setValue(
            gui_settings.get_int(gui_settings.KEYS.fuzzy_max_results, 5)
        )
        fuzzy_auto = gui_settings.get_str(gui_settings.KEYS.fuzzy_auto_accept, "90.0")
        try:
            self._fuzzy_auto_accept_spin.setValue(float(fuzzy_auto))
        except (TypeError, ValueError):
            self._fuzzy_auto_accept_spin.setValue(90.0)

        # Appearance
        theme = gui_settings.get_theme()
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == theme:
                self._theme_combo.setCurrentIndex(i)
                break

        # Import existing translations
        self._import_trans_field.setText(
            gui_settings.get_str(gui_settings.KEYS.import_translations_path, "")
        )
        import_enabled = gui_settings.get_str(
            gui_settings.KEYS.import_translations_enabled, "0"
        )
        self._import_trans_check.setChecked(import_enabled in {"1", "true"})

        # Session persistence
        self._session_check.setChecked(gui_settings.get_session_enabled())

    def _save_values(self) -> None:
        gui_settings.set_str(gui_settings.KEYS.backend, self._backend_combo.currentData())

        # Handle API key via secure storage, never in QSettings
        backend = self._backend_combo.currentData() or "google"
        api_key = self._api_key_field.text().strip()
        if self._remember_key_check.isChecked() and api_key:
            stored = gui_secrets.store_api_key(backend, api_key)
            if stored:
                gui_settings.set_str(f"translation/remember_api_key_{backend}", "1")
            else:
                # Storage failed -- don't set the remember flag so next launch
                # doesn't expect to find a key in keyring.
                gui_settings.set_str(f"translation/remember_api_key_{backend}", "0")
                self._remember_key_check.setChecked(False)
        else:
            gui_secrets.delete_api_key(backend)
            gui_settings.set_str(f"translation/remember_api_key_{backend}", "0")

        gui_settings.set_int(gui_settings.KEYS.workers, self._workers_spin.value())
        gui_settings.set_str("translation/rate_limit", str(self._rate_spin.value()))
        gui_settings.set_str(
            "translation/prevent_sleep",
            "1" if self._wakelock_check.isChecked() else "0",
        )
        gui_settings.set_str("translation/batch_targets", self._batch_field.text().strip())
        gui_settings.set_str(gui_settings.KEYS.glossary_path, self._glossary_field.text().strip())
        gui_settings.set_str(gui_settings.KEYS.memory_path, self._memory_field.text().strip())
        gui_settings.set_str(
            gui_settings.KEYS.fuzzy_threshold, str(self._fuzzy_threshold_spin.value())
        )
        gui_settings.set_int(
            gui_settings.KEYS.fuzzy_max_results, self._fuzzy_max_results_spin.value()
        )
        gui_settings.set_str(
            gui_settings.KEYS.fuzzy_auto_accept, str(self._fuzzy_auto_accept_spin.value())
        )
        gui_settings.set_str(
            gui_settings.KEYS.import_translations_path,
            self._import_trans_field.text().strip(),
        )
        gui_settings.set_str(
            gui_settings.KEYS.import_translations_enabled,
            "1" if self._import_trans_check.isChecked() else "0",
        )
        gui_settings.set_theme(self._theme_combo.currentData())
        gui_settings.set_session_enabled(self._session_check.isChecked())

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
        self._fuzzy_threshold_spin.setValue(75.0)
        self._fuzzy_max_results_spin.setValue(5)
        self._fuzzy_auto_accept_spin.setValue(90.0)
        self._import_trans_field.clear()
        self._import_trans_check.setChecked(False)
        self._theme_combo.setCurrentIndex(0)
        self._session_check.setChecked(False)

    # ------------------------------------------------------------------ helpers

    def _update_backend_help(self) -> None:
        key = self._backend_combo.currentData()
        for info in list_backends():
            if info.key == key:
                env_hint = f"  Env var: {info.env_var}" if info.env_var else ""
                requires = "API key required" if info.requires_api_key else "No API key needed"
                self._backend_help.setText(f"{info.description}  ({requires}.{env_hint})")
                break
        self._update_backend_status()

    def _update_backend_status(self) -> None:
        """Check availability of the currently selected backend and show status."""
        key = self._backend_combo.currentData()
        if key is None:
            return
        # If the user has typed an API key in the field, that counts as available
        # even if it is not yet in the environment variable.
        has_local_key = bool(self._api_key_field.text().strip())
        info = None
        for bi in list_backends():
            if bi.key == key:
                info = bi
                break
        if info is not None and info.requires_api_key and has_local_key:
            self._backend_status.setText("\u2705 Ready (API key provided in field above)")
            self._backend_status.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 600;")
            return
        # Also check keyring for a stored key so the status is accurate
        # on dialog open before the user types anything.
        stored_key = gui_secrets.retrieve_api_key(key) if (info and info.requires_api_key) else None
        available, reason = check_backend_available(key, api_key=stored_key)
        if available:
            self._backend_status.setText("\u2705 Ready")
            self._backend_status.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 600;")
        else:
            self._backend_status.setText(f"\u274c {reason}")
            self._backend_status.setStyleSheet("color: #dc2626; font-size: 11px; font-weight: 600;")

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

    def _on_browse_import_translations(self) -> None:
        start = self._import_trans_field.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose translated Excel file", start,
            "Excel files (*.xlsx);;All files (*)"
        )
        if path:
            self._import_trans_field.setText(path)
            self._import_trans_check.setChecked(True)


def open_settings(parent: Optional[QWidget] = None) -> bool:
    """Open the dialog modally.  Returns True if the user clicked OK."""
    dialog = SettingsDialog(parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
