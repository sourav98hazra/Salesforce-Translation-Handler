"""Top-level window: sidebar phase navigation + stacked phase pages.

The window hosts the six-phase pipeline (Import STF / STF -> Excel /
Translate / Browse & Review / Validate & Fix / Export STF) with:

* **Status badges** in the sidebar (idle / running / done / error)
  for every phase, so the entire pipeline state is visible at a glance.
* **Drag-and-drop** anywhere in the window auto-routes by extension
  (.stf -> Phase 1, .xlsx -> Phase 4 / 2 / 5 based on filename).
* **Keyboard shortcuts**: ``Ctrl+0..5`` jump straight to a phase,
  ``Ctrl+O`` opens a file, ``Ctrl+S`` saves the current phase artifact,
  ``Ctrl+L`` toggles the status log, ``Ctrl+,`` opens Settings,
  ``F1`` opens the user guide, ``Ctrl+Q`` quits.
* **File menu** with a Recent files submenu (auto-routes on click).
* **Edit menu** with a single Settings entry -- everything advanced
  (backend / API key / workers / rate limit / glossary / TM / batch
  targets / wake-lock) lives there.
* **View menu** with the five theme presets (light / dark / ocean /
  forest / sunset) plus auto, persisted across sessions.
* **Settings persistence** for window geometry, theme, last target
  language, recent files, and last-used backend.
* **Resizable sidebar** (220-280 px) and a sensible
  ``setMinimumSize(900, 600)`` floor; the initial window size is
  clamped to the available screen geometry so the app never opens
  wider than the user's display.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..session import SessionManager
from ..stf import parse_stf
from . import settings as gui_settings
from . import theme
from .pages.base import PhasePage
from .pages.phase1_import import Phase1ImportPage
from .pages.phase2_excel import Phase2ExcelPage
from .pages.phase3_translate import Phase3TranslatePage
from .pages.phase4_review import Phase4ReviewPage
from .pages.phase5_validate import Phase5ValidatePage
from .pages.phase6_export import Phase6ExportPage
from .state import AppState, PhaseSnapshot, PhaseStatus
from .app_history import AppHistory, capture_snapshot, restore_snapshot
from .workers import ImportExcelWorker, ParseStfWorker
from .dialogs.override_dialog import (
    OverrideConfirmationDialog,
    UnsavedChangesDialog,
    UnsavedChangesResult,
    PHASE_NAMES,
)

_PHASES = [
    ("1. Import STF", "Pick the source .stf file"),
    ("2. STF \u2192 Excel", "Convert to organised workbook"),
    ("3. Translate", "Auto-translate untranslated rows"),
    ("4. Browse & Review", "View translations, edit, re-upload"),
    ("5. Validate & Fix", "Find issues, auto-fix, re-validate"),
    ("6. Export STF", "Write final STF files"),
]

_PHASE_TOOLTIPS = [
    "Phase 1: select and parse the source .stf file from Salesforce Translation Workbench.",
    "Phase 2: convert the parsed STF into an organised Excel workbook (one sheet per component type).",
    "Phase 3: auto-translate untranslated rows using the configured backend.",
    "Phase 4: browse all translations, search, edit on demand, or re-upload an externally edited workbook.",
    "Phase 5: detect validation issues and apply deterministic auto-fixes.",
    "Phase 6: write the final three .stf files ready to upload back to Salesforce.",
]

_STATUS_ICONS = {
    PhaseStatus.IDLE: "  ",
    PhaseStatus.RUNNING: "\u25b6",  # play
    PhaseStatus.DONE: "\u2713",     # check
    PhaseStatus.ERROR: "\u26a0",    # warning
}


def _load_app_icon() -> QIcon:
    """Load the application icon with fallback: .ico -> .png -> .svg.

    Returns a QIcon (possibly null/empty if all paths fail).
    """
    _assets = Path(__file__).parent / "assets"
    _ico_path = _assets / "logo.ico"
    _png_path = _assets / "logo.png"
    _svg_path = _assets / "logo.svg"

    if _ico_path.is_file():
        return QIcon(str(_ico_path))
    if _png_path.is_file():
        return QIcon(str(_png_path))
    try:
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPixmap, QPainter
        from PySide6.QtCore import QSize

        if _svg_path.is_file():
            renderer = QSvgRenderer(str(_svg_path))
            pixmap = QPixmap(QSize(256, 256))
            pixmap.fill()
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)
    except ImportError:
        pass  # PySide6-Svg not available
    return QIcon()


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        # Run one-time settings migration (resets stale defaults from older versions)
        gui_settings.migrate_settings()
        self.setWindowTitle("Salesforce Translation Manager")
        self.setWindowIcon(_load_app_icon())
        # Reasonable minimum so users on small / windowed displays can
        # actually shrink the window.  Was being held hostage by a fixed
        # 260px sidebar plus large content minimums.
        self.setMinimumSize(900, 600)
        # Clamp the initial size to whatever fits on the user's screen
        # (avoids the window starting wider than the display).
        from .pages.base import clamp_to_screen
        clamp_to_screen(self, 1400, 900)
        self.setAcceptDrops(True)
        self._state = AppState()
        # App-wide action history (coarse undo/redo of major actions:
        # load file / translate / auto-fix / reset).  Distinct from the
        # Phase 4 per-translation undo stack.
        self._app_history = AppHistory(self)
        self._restoring_snapshot = False

        # ---- central layout
        central = QWidget(self)
        central.setAutoFillBackground(True)
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar(), stretch=0)
        layout.addWidget(self._build_separator(), stretch=0)
        layout.addWidget(self._build_pages(), stretch=1)

        # ---- bottom status log dock
        self._status_log = QPlainTextEdit()
        self._status_log.setReadOnly(True)
        self._status_log.setMaximumBlockCount(1000)
        self._status_log.setMinimumHeight(50)
        self._status_dock = QDockWidget("Status log", self)
        self._status_dock.setWidget(self._status_log)
        self._status_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._status_dock)
        self._status_dock.setMinimumHeight(70)

        # ---- status bar
        bar = QStatusBar()
        self.setStatusBar(bar)
        bar.showMessage(f"Ready  (stx {__version__})")

        # ---- menu + shortcuts
        self._build_menu()
        self._wire_shortcuts()

        # ---- sync Translation menu "Use imported translations" -> Phase 3 checkbox
        self._act_use_imported.toggled.connect(self._sync_import_to_phase3)

        # ---- wire phase signals
        for page in self._pages:
            page.status_message.connect(self._log)
            page.request_navigate.connect(self._goto)
            page.busy_changed.connect(lambda _busy: self._refresh_phase_badges())
            page.file_dropped.connect(self._handle_dropped_file)
            page.action_recorded.connect(self._record_app_action)
            page.action_recorded.connect(lambda _label: self._update_sidebar_footer())

        # Any page exposing request_jump_to_row jumps to the Review phase
        # (currently index 3) focused on the matching row.
        for page in self._pages:
            if hasattr(page, "request_jump_to_row"):
                try:
                    page.request_jump_to_row.connect(self._jump_to_row)
                except Exception:  # noqa: BLE001 -- defensive
                    pass

        # ---- restore window geometry / theme from settings
        self._apply_remembered_theme()
        self._restore_geometry()

        # ---- session persistence: attempt restore
        self._session_manager = SessionManager()
        self._try_restore_session()

        # ---- baseline snapshot for app-wide undo/redo
        self._app_history.record(capture_snapshot(self._state, "Initial state"))
        self._refresh_app_history_actions()

        self._goto(0)

    # ------------------------------------------------------------------ build

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        # Resizable instead of fixed, so the user can shrink the window
        # past the previous 260px floor.  Range keeps it readable.
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(280)
        sidebar.setObjectName("sidebar")
        # Force the dark sidebar background regardless of QSS inheritance
        # issues on some platforms (Windows native style ignores parent bg).
        sidebar.setAutoFillBackground(True)
        sidebar.setStyleSheet(
            "#sidebar { background-color: #1e293b; }"
        )
        v = QVBoxLayout(sidebar)
        v.setContentsMargins(16, 24, 16, 16)
        v.setSpacing(12)

        # Logo icon beside the title text
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Render the SVG logo as a 32x32 pixmap (Q3: bumped from 28x28)
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        try:
            from PySide6.QtSvg import QSvgRenderer
            from PySide6.QtGui import QPixmap, QPainter
            from PySide6.QtCore import QSize
            from pathlib import Path as _Path

            svg_path = _Path(__file__).parent / "assets" / "logo.svg"
            if svg_path.exists():
                renderer = QSvgRenderer(str(svg_path))
                pixmap = QPixmap(QSize(32, 32))
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                logo_label.setPixmap(pixmap)
            else:
                # Fallback: text-based hex indicator
                logo_label.setText("\u2b22")
                logo_label.setStyleSheet("font-size: 24px; color: #818cf8;")
        except ImportError:
            # PySide6-Svg not installed -- use unicode hex as fallback
            logo_label.setText("\u2b22")
            logo_label.setStyleSheet("font-size: 24px; color: #818cf8;")
        header_row.addWidget(logo_label)

        title = QLabel()
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setText(
            '<div style="font-size: 13px; font-weight: 700; color: #ffffff; letter-spacing: 0.3px;">'
            'Salesforce<br>Translation Manager'
            '</div>'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(title)
        header_row.addStretch(1)
        v.addLayout(header_row)

        version = QLabel(f"v{__version__}")
        version.setStyleSheet("color:#64748b; font-size:11px;")
        v.addWidget(version)

        v.addSpacing(16)

        self._phase_list = QListWidget()
        self._phase_list.setSpacing(0)
        self._phase_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for index, (label, hint) in enumerate(_PHASES):
            item = QListWidgetItem(self._format_phase_label(label, hint, PhaseStatus.IDLE))
            item.setData(Qt.ItemDataRole.UserRole, label)
            if index < len(_PHASE_TOOLTIPS):
                item.setToolTip(_PHASE_TOOLTIPS[index])
            self._phase_list.addItem(item)
        self._phase_list.currentRowChanged.connect(self._on_sidebar_row_changed)
        v.addWidget(self._phase_list)
        v.addStretch(1)

        # ---- sidebar footer: stats + progress
        self._footer_stats = QLabel("No file loaded")
        self._footer_stats.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        self._footer_stats.setWordWrap(True)
        v.addWidget(self._footer_stats)

        self._footer_lang = QLabel("")
        self._footer_lang.setStyleSheet("color: #64748b; font-size: 10px;")
        v.addWidget(self._footer_lang)

        self._footer_progress = QProgressBar()
        self._footer_progress.setFixedHeight(4)
        self._footer_progress.setTextVisible(False)
        self._footer_progress.setStyleSheet(
            "QProgressBar { background: #334155; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: #4338ca; border-radius: 2px; }"
        )
        self._footer_progress.setVisible(False)
        v.addWidget(self._footer_progress)

        return sidebar

    def _format_phase_label(self, label: str, hint: str, status: PhaseStatus) -> str:
        icon = _STATUS_ICONS.get(status, "  ")
        return f"{icon}  {label}\n      {hint}"

    def _refresh_phase_badges(self) -> None:
        for index in range(self._phase_list.count()):
            label, hint = _PHASES[index]
            status = self._state.phase_status[index] if index < len(self._state.phase_status) else PhaseStatus.IDLE
            item = self._phase_list.item(index)
            item.setText(self._format_phase_label(label, hint, status))

    def _update_sidebar_footer(self) -> None:
        """Refresh the sidebar footer stats and progress bar."""
        doc = self._state.document
        if doc is None:
            self._footer_stats.setText("No file loaded")
            self._footer_lang.setText("")
            self._footer_progress.setVisible(False)
            return

        # Count rows and unique components
        row_count = len(doc.entries)
        translated = len(doc.translated())
        untranslated = row_count - translated
        components = {e.component_type for e in doc.entries}
        stats_parts = [f"{row_count:,} rows", f"{len(components)} components"]
        if untranslated > 0:
            stats_parts.append(f"{untranslated:,} untranslated")
        self._footer_stats.setText(" \u00b7 ".join(stats_parts))

        # Second line: target language + import count if applicable
        lang_name = self._state.target_language_name or ""
        lang_code = self._state.target_language_code or ""
        lang_text = f"{lang_name} ({lang_code})" if lang_name and lang_code else lang_name

        # Show import translations count if loaded and enabled
        import_text = ""
        if (
            self._state.imported_translations
            and self._state.imported_translations_enabled
        ):
            import_text = f"\u2713 {len(self._state.imported_translations):,} imports active"

        if lang_text and import_text:
            self._footer_lang.setText(f"{lang_text}\n{import_text}")
        elif lang_text:
            self._footer_lang.setText(lang_text)
        elif import_text:
            self._footer_lang.setText(import_text)
        else:
            self._footer_lang.setText("")

        # Progress bar: only visible during Phase 3 (Translate) running
        phase3_running = (
            len(self._state.phase_status) > 2
            and self._state.phase_status[2] == PhaseStatus.RUNNING
        )
        self._footer_progress.setVisible(phase3_running)
        if phase3_running and row_count > 0:
            translated_count = len(doc.translated())
            self._footer_progress.setMaximum(row_count)
            self._footer_progress.setValue(translated_count)

    def _build_separator(self) -> QFrame:
        # 1px soft vertical line.  The default QFrame.VLine renders as a
        # bevelled native frame on Windows that looks bold/thick, so we
        # paint it explicitly with the soft theme border colour.
        line = QFrame()
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedWidth(1)
        line.setStyleSheet("background-color: rgba(148, 163, 184, 0.35);")
        return line

    def _build_pages(self) -> QWidget:
        self._stack = QStackedWidget()
        self._pages: List[PhasePage] = [
            Phase1ImportPage(self._state, self),       # 0  -- Import STF
            Phase2ExcelPage(self._state, self),        # 1  -- STF -> Excel
            Phase3TranslatePage(self._state, self),    # 2  -- Translate
            Phase4ReviewPage(self._state, self),       # 3  -- Review
            Phase5ValidatePage(self._state, self),     # 4  -- Validate & Fix
            Phase6ExportPage(self._state, self),       # 5  -- Export STF
        ]
        for page in self._pages:
            self._stack.addWidget(page)
        return self._stack

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        open_action = QAction("&Open file...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setToolTip("Open an .stf or .xlsx file")
        open_action.triggered.connect(self._action_open_file)
        file_menu.addAction(open_action)

        save_action = QAction("&Save current phase", self)
        save_action.setShortcut("Ctrl+S")
        save_action.setToolTip("Save the current phase's output")
        save_action.triggered.connect(self._action_save_current)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        self._recent_menu = QMenu("Recent files", self)
        file_menu.addMenu(self._recent_menu)
        self._refresh_recent_menu()

        file_menu.addSeparator()

        save_project_action = QAction("Save &project...", self)
        save_project_action.setToolTip("Save the full session state to a .stxproj file")
        save_project_action.triggered.connect(self._action_save_project)
        file_menu.addAction(save_project_action)

        open_project_action = QAction("Open p&roject...", self)
        open_project_action.setToolTip("Open a previously saved .stxproj project file")
        open_project_action.triggered.connect(self._action_open_project)
        file_menu.addAction(open_project_action)

        file_menu.addSeparator()

        reset_all_action = QAction("Reset &Session", self)
        reset_all_action.setToolTip("Clear all state and reset session to defaults")
        reset_all_action.triggered.connect(self._action_restart_session)
        file_menu.addAction(reset_all_action)

        reset_phase_action = QAction("Reset Current &Phase", self)
        reset_phase_action.setToolTip("Reset the current phase and all downstream phases")
        reset_phase_action.triggered.connect(self._action_reset_current_phase)
        file_menu.addAction(reset_phase_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu: Undo/Redo (delegated to Phase 4) then Settings.
        edit_menu = bar.addMenu("&Edit")

        self._undo_action = QAction("&Undo translation edit", self)
        self._undo_action.setShortcut("Ctrl+Z")
        self._undo_action.setEnabled(False)
        self._undo_action.setToolTip(
            "Undo the last individual translation cell edit in Phase 4.\n"
            "Only works while Phase 4 (Browse & Review) is open."
        )
        self._undo_action.triggered.connect(self._action_undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("&Redo translation edit", self)
        self._redo_action.setShortcut("Ctrl+Y")
        self._redo_action.setEnabled(False)
        self._redo_action.setToolTip(
            "Redo a previously undone translation cell edit in Phase 4."
        )
        self._redo_action.triggered.connect(self._action_redo)
        edit_menu.addAction(self._redo_action)

        edit_menu.addSeparator()

        # App-wide coarse undo/redo — reverses whole major actions, not single edits.
        self._app_undo_action = QAction("Undo last major action", self)
        self._app_undo_action.setShortcut("Ctrl+Shift+Z")
        self._app_undo_action.setEnabled(False)
        self._app_undo_action.setToolTip(
            "Reverse the last major step such as loading a file, running translation,\n"
            "applying auto-fix, or resetting.  Different from Ctrl+Z which only undoes\n"
            "single cell edits inside Phase 4."
        )
        self._app_undo_action.triggered.connect(self._app_undo)
        edit_menu.addAction(self._app_undo_action)

        self._app_redo_action = QAction("Redo last major action", self)
        self._app_redo_action.setShortcut("Ctrl+Shift+Y")
        self._app_redo_action.setEnabled(False)
        self._app_redo_action.setToolTip(
            "Re-apply the last major step that was reversed by 'Undo last major action'."
        )
        self._app_redo_action.triggered.connect(self._app_redo)
        edit_menu.addAction(self._app_redo_action)

        self._app_history.changed.connect(self._refresh_app_history_actions)

        edit_menu.addSeparator()

        self._find_replace_action = QAction("Find && Replace...", self)
        self._find_replace_action.setShortcut("Ctrl+H")
        self._find_replace_action.setEnabled(False)
        self._find_replace_action.triggered.connect(self._action_find_replace)
        edit_menu.addAction(self._find_replace_action)

        edit_menu.addSeparator()

        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._action_open_settings)
        edit_menu.addAction(settings_action)

        # Wire Phase 4 undo stack to the edit menu actions
        phase4: Phase4ReviewPage = self._pages[3]  # type: ignore[assignment]
        phase4._undo_stack.stack_changed.connect(self._refresh_undo_actions)

        # Refresh undo/redo menu state when navigating between pages
        self._stack.currentChanged.connect(lambda _idx: self._refresh_undo_actions())

        # ------------------------------------------------------------------ Translation menu
        self._build_translation_menu(bar)

        # ------------------------------------------------------------------ Validation menu
        self._build_validation_menu(bar)

        view_menu = bar.addMenu("&View")
        themes = [
            ("light", "&Light theme"),
            ("dark", "&Dark theme"),
            ("ocean", "&Ocean theme"),
            ("forest", "Fo&rest theme"),
            ("sunset", "&Sunset theme"),
            ("auto", "&Auto (system)"),
        ]
        for name, label in themes:
            act = QAction(label, self)
            act.triggered.connect(lambda _checked=False, n=name: self._switch_theme(n))
            view_menu.addAction(act)

        view_menu.addSeparator()
        self._toggle_log_action = QAction("Show &Status Log", self)
        self._toggle_log_action.setShortcut("Ctrl+L")
        self._toggle_log_action.setCheckable(True)
        self._toggle_log_action.setChecked(True)
        self._toggle_log_action.triggered.connect(self._on_toggle_status_log)
        view_menu.addAction(self._toggle_log_action)
        self._status_dock.visibilityChanged.connect(self._toggle_log_action.setChecked)

        view_menu.addSeparator()
        prev_phase_action = QAction("&Previous Phase", self)
        prev_phase_action.setShortcut("Ctrl+B")
        prev_phase_action.setToolTip("Navigate to the previous phase (app-wide back)")
        prev_phase_action.triggered.connect(self._action_previous_phase)
        view_menu.addAction(prev_phase_action)

        help_menu = bar.addMenu("&Help")
        guide_action = QAction("User Guide (F1)", self)
        guide_action.setShortcut("F1")
        guide_action.triggered.connect(self._show_user_guide)
        help_menu.addAction(guide_action)
        faq_action = QAction("FAQ && Troubleshooting", self)
        faq_action.setShortcut("Ctrl+F1")
        faq_action.setToolTip("Open the searchable FAQ")
        faq_action.triggered.connect(self._show_faq)
        help_menu.addAction(faq_action)
        about = QAction("&About", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)
        help_menu.addSeparator()
        updates_action = QAction("Check for &Updates", self)
        updates_action.triggered.connect(self._check_for_updates)
        help_menu.addAction(updates_action)

    def _build_translation_menu(self, bar) -> None:
        """Build the Translation menu with all translation option toggles."""
        trans_menu = bar.addMenu("&Translation")

        def _make_toggle(label: str, tooltip: str, get_fn, set_fn) -> QAction:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(get_fn())
            act.setToolTip(tooltip)
            def _toggled(checked: bool, _set=set_fn, _label=label) -> None:
                _set(checked)
                state_str = "ON" if checked else "OFF"
                self._log(f"Translation option changed: {_label} \u2192 {state_str}")
            act.toggled.connect(_toggled)
            return act

        self._act_use_infile = _make_toggle(
            "Use in-file translations",
            "Reuse translations already present in the same STF/Excel file.\n"
            "If label 'Save' is already translated as '保存' somewhere in the file,\n"
            "all other untranslated rows with label 'Save' will reuse '保存' — no API call.",
            gui_settings.get_use_infile_translations,
            gui_settings.set_use_infile_translations,
        )
        trans_menu.addAction(self._act_use_infile)

        self._act_use_tm = _make_toggle(
            "Use Translation Memory cache",
            "Reuse translations from the Translation Memory database (from previous runs).\n"
            "Speeds up repeated translations significantly.",
            gui_settings.get_use_tm_cache,
            gui_settings.set_use_tm_cache,
        )
        trans_menu.addAction(self._act_use_tm)

        self._act_use_fuzzy = _make_toggle(
            "Use Fuzzy matching",
            "Find approximate matches in the Translation Memory (e.g. 'Save record' matches 'Save Record').\n"
            "Configure threshold in Edit → Settings → Resources.",
            gui_settings.get_use_fuzzy_matching,
            gui_settings.set_use_fuzzy_matching,
        )
        trans_menu.addAction(self._act_use_fuzzy)

        self._act_use_imported = _make_toggle(
            "Use imported translations",
            "Apply translations imported from an external Excel file with highest priority.\n"
            "Import a file in Phase 3 → 'Import existing translations...'",
            gui_settings.get_use_imported_translations,
            gui_settings.set_use_imported_translations,
        )
        trans_menu.addSeparator()
        trans_menu.addAction(self._act_use_imported)

        trans_menu.addSeparator()

        self._act_retranslate = _make_toggle(
            "Retranslate all (overwrite existing)",
            "When checked, ALL rows (including already-translated ones) are sent for translation.\n"
            "When unchecked (default), only blank/untranslated rows are translated.",
            gui_settings.get_retranslate_existing,
            gui_settings.set_retranslate_existing,
        )
        trans_menu.addAction(self._act_retranslate)

        trans_menu.addSeparator()

        settings_shortcut = QAction("&Settings...", self)
        settings_shortcut.setShortcut("Ctrl+,")
        settings_shortcut.setToolTip("Open advanced translation settings (backend, TM path, fuzzy thresholds, etc.)")
        settings_shortcut.triggered.connect(self._action_open_settings)
        trans_menu.addAction(settings_shortcut)

        trans_menu.addSeparator()

        re_enable_preflight = QAction("Re-enable pre-flight confirmation", self)
        re_enable_preflight.setToolTip(
            "Show the 'Ready to translate?' summary dialog before each run again.\n"
            "(Shown by default, can be disabled with 'Don't show again' in the dialog.)"
        )
        re_enable_preflight.triggered.connect(
            lambda: (
                gui_settings.set_preflight_skip(False),
                self._log(  # type: ignore[attr-defined]
                    "Pre-flight dialog re-enabled — will show before the next translation run."
                ),
            )
        )
        trans_menu.addAction(re_enable_preflight)

        trans_menu.addSeparator()

        clear_tm_action = QAction("Clear Translation Memory...", self)
        clear_tm_action.setToolTip(
            "Delete the Translation Memory database. "
            "All cached translations from previous runs will be lost."
        )
        clear_tm_action.triggered.connect(self._action_clear_tm)
        trans_menu.addAction(clear_tm_action)

    def _build_validation_menu(self, bar) -> None:
        """Build the Validation menu with limit override actions."""
        from ..validate import clear_limit_overrides, get_limit_overrides

        validation_menu = bar.addMenu("V&alidation")

        limits_action = QAction("Custom Length Limits...", self)
        limits_action.setToolTip(
            "Override default Salesforce character limits for this session."
        )
        limits_action.triggered.connect(self._action_open_limits_dialog)
        validation_menu.addAction(limits_action)

        clear_action = QAction("Clear All Overrides", self)
        clear_action.setToolTip("Reset all character limits to Salesforce defaults.")
        clear_action.triggered.connect(self._action_clear_overrides)
        validation_menu.addAction(clear_action)

    def _action_open_limits_dialog(self) -> None:
        """Open the Custom Length Limits dialog."""
        from .dialogs.limits_override_dialog import LimitsOverrideDialog

        dlg = LimitsOverrideDialog(self)
        dlg.exec()
        self._update_override_indicator()

    def _action_clear_overrides(self) -> None:
        """Clear all custom limit overrides."""
        from ..validate import clear_limit_overrides

        clear_limit_overrides()
        self._log("All custom character limit overrides cleared.")
        self._update_override_indicator()

    def _update_override_indicator(self) -> None:
        """Show or hide the override indicator in the status bar."""
        from ..validate import get_limit_overrides

        overrides = get_limit_overrides()
        if overrides:
            count = len(overrides)
            self.statusBar().showMessage(
                f"Custom limits active ({count} override{'s' if count != 1 else ''})",
                0,
            )
        else:
            self.statusBar().showMessage(f"Ready  (stx {__version__})", 3000)

    def _wire_shortcuts(self) -> None:
        # Ctrl+0..6 to switch phases.
        for index in range(len(_PHASES)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda i=index: self._goto(i))

    def _on_sidebar_row_changed(self, index: int) -> None:
        """Called when the user clicks a phase in the sidebar list.

        If navigation is blocked (e.g. translation is running), the sidebar
        highlight is moved back to the currently active phase so it never
        shows the user on a phase they haven't actually navigated to.
        """
        if index < 0 or index >= len(self._pages):
            return

        # Block during active translation
        if (
            len(self._state.phase_status) > 2
            and self._state.phase_status[2] == PhaseStatus.RUNNING
            and index != 2
        ):
            # Snap the sidebar highlight back to the current page BEFORE
            # showing the warning, so the user sees the highlight stay put.
            current = self._stack.currentIndex()
            self._phase_list.blockSignals(True)
            self._phase_list.setCurrentRow(current)
            self._phase_list.blockSignals(False)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Translation Running",
                "Cannot switch phases while translation is in progress.\n"
                "Please wait for translation to complete or cancel it first.",
            )
            return

        # Proceed normally
        self._goto(index)

    # ------------------------------------------------------------------ navigation

    def _goto(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return
        # Block programmatic navigation during active translation
        # (sidebar clicks are already blocked by _on_sidebar_row_changed).
        if (
            len(self._state.phase_status) > 2
            and self._state.phase_status[2] == PhaseStatus.RUNNING
            and index != 2
            and index != self._stack.currentIndex()
        ):
            return  # silently ignore — the warning was already shown by the sidebar handler
        self._state.current_phase = index
        self._stack.setCurrentIndex(index)
        self._phase_list.blockSignals(True)
        self._phase_list.setCurrentRow(index)
        self._phase_list.blockSignals(False)
        self._pages[index].on_enter()
        self._refresh_phase_badges()
        self._update_sidebar_footer()
        # Refresh undo/redo menu state when switching pages
        if hasattr(self, "_undo_action"):
            self._refresh_undo_actions()

    def _jump_to_row(self, key: str) -> None:
        # Phase 4 (Review) is now at index 3 in the simplified flow.
        self._goto(3)
        review = self._pages[3]
        if hasattr(review, "focus_key"):
            review.focus_key(key)

    def _sync_import_to_phase3(self, checked: bool) -> None:
        """Sync the Translation menu 'Use imported translations' state to Phase 3 checkbox."""
        if checked and not self._state.imported_translations:
            # No import file loaded -- block the toggle and warn
            self._act_use_imported.blockSignals(True)
            self._act_use_imported.setChecked(False)
            self._act_use_imported.blockSignals(False)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "No Import File",
                "No translations have been imported yet.\n\n"
                "First import a file in Phase 3 using 'Import existing translations...' "
                "before enabling this option.",
            )
            return
        page = self._pages[2]  # Phase3TranslatePage
        page._import_trans_check.blockSignals(True)
        page._import_trans_check.setChecked(checked)
        page._import_trans_check.blockSignals(False)
        # Also keep the io/import_translations_enabled key in sync
        gui_settings.set_str(gui_settings.KEYS.import_translations_enabled, "1" if checked else "0")
        self._state.imported_translations_enabled = checked
        # Update the import label visibility to match checkbox state
        if checked and self._state.imported_translations:
            count = len(self._state.imported_translations)
            page._import_trans_label.setText(f"\u2713 {count:,} translations imported")
            page._import_trans_label.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 600;")
        else:
            page._import_trans_label.setText("")
        # Refresh sidebar footer to show/hide "imports active" text
        self._update_sidebar_footer()

    def _on_toggle_status_log(self, checked: bool) -> None:
        """Toggle the status log dock. When showing, re-dock it to the bottom."""
        if checked:
            # Always re-dock to bottom when showing (in case it was floating)
            self._status_dock.setFloating(False)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._status_dock)
            self._status_dock.setVisible(True)
        else:
            self._status_dock.setVisible(False)

    def _action_previous_phase(self) -> None:
        """Navigate to the previous phase (app-wide back)."""
        idx = max(0, self._stack.currentIndex() - 1)
        self._goto(idx)

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._status_log.appendPlainText(f"[{timestamp}] {message}")
        self.statusBar().showMessage(message, 6000)

    # ------------------------------------------------------------------ menu actions

    def _action_open_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open file",
            "",
            "All supported (*.stf *.xlsx);;STF (*.stf);;Excel (*.xlsx)",
        )
        if path_str:
            self._handle_dropped_file(path_str)

    def _action_save_current(self) -> None:
        # Each page exposes its own "Save" button.  Forward Ctrl+S by simulating
        # the conventional name -- if the page has a `_on_save` slot we invoke it.
        page = self._pages[self._stack.currentIndex()]
        for slot_name in ("_on_save", "_save_translated", "_on_export", "_action_save"):
            if hasattr(page, slot_name):
                getattr(page, slot_name)()
                return
        self._log("No save action on the current phase.")

    # ------------------------------------------------------------------ undo / redo delegation

    def _action_undo(self) -> None:
        """Delegate Ctrl+Z to Phase 4 when it is the active page."""
        if self._stack.currentIndex() == 3:
            phase4: Phase4ReviewPage = self._pages[3]  # type: ignore[assignment]
            phase4._on_undo()

    def _action_redo(self) -> None:
        """Delegate Ctrl+Y to Phase 4 when it is the active page."""
        if self._stack.currentIndex() == 3:
            phase4: Phase4ReviewPage = self._pages[3]  # type: ignore[assignment]
            phase4._on_redo()

    def _action_find_replace(self) -> None:
        """Delegate Ctrl+H to Phase 4 when it is the active page."""
        if self._stack.currentIndex() == 3:
            phase4: Phase4ReviewPage = self._pages[3]  # type: ignore[assignment]
            phase4._on_find_replace()

    def _refresh_undo_actions(self) -> None:
        """Enable/disable Edit menu undo/redo based on stack + active page."""
        is_phase4 = self._stack.currentIndex() == 3
        phase4: Phase4ReviewPage = self._pages[3]  # type: ignore[assignment]
        self._undo_action.setEnabled(is_phase4 and phase4._undo_stack.can_undo)
        self._redo_action.setEnabled(is_phase4 and phase4._undo_stack.can_redo)
        if hasattr(self, "_find_replace_action"):
            self._find_replace_action.setEnabled(is_phase4)

    # ------------------------------------------------------------------ app-wide history (major actions)

    def _record_app_action(self, label: str) -> None:
        """Record a snapshot of the app state after a major action.

        Connected to every page's ``action_recorded`` signal and called
        directly after file loads / resets.  Suppressed while restoring a
        snapshot so undo/redo never re-records itself.
        """
        if self._restoring_snapshot:
            return
        self._app_history.record(capture_snapshot(self._state, label))
        self._refresh_app_history_actions()

    def _app_undo(self) -> None:
        """Reverse the last major action (app-wide)."""
        if self._is_translation_running():
            self._warn_translation_running()
            return
        snapshot = self._app_history.undo()
        if snapshot is None:
            self._log("Nothing to undo.")
            return
        self._restore_app_snapshot(snapshot)
        self._log(f"Undid action -- restored to: {snapshot.label}.")

    def _app_redo(self) -> None:
        """Re-apply the last major action reversed by app-wide undo."""
        if self._is_translation_running():
            self._warn_translation_running()
            return
        snapshot = self._app_history.redo()
        if snapshot is None:
            self._log("Nothing to redo.")
            return
        self._restore_app_snapshot(snapshot)
        self._log(f"Redid action -- restored to: {snapshot.label}.")

    def _restore_app_snapshot(self, snapshot) -> None:
        """Apply a snapshot to the live state and refresh every page."""
        self._restoring_snapshot = True
        try:
            restore_snapshot(self._state, snapshot)
            # Clear the Phase 4 per-edit undo stack -- its commands point at a
            # document that no longer matches after a coarse restore.
            phase4: Phase4ReviewPage = self._pages[3]  # type: ignore[assignment]
            phase4._undo_stack.clear()
            self._refresh_phase_badges()
            self._update_sidebar_footer()
            # Navigate to the snapshot's recorded phase and refresh its widgets.
            target = self._state.current_phase
            if not (0 <= target < len(self._pages)):
                target = self._stack.currentIndex()
            self._goto(target)
        finally:
            self._restoring_snapshot = False
        self._refresh_app_history_actions()

    def _refresh_app_history_actions(self) -> None:
        """Update enabled state + dynamic labels for app-wide undo/redo."""
        if not hasattr(self, "_app_undo_action"):
            return
        can_undo = self._app_history.can_undo
        can_redo = self._app_history.can_redo
        self._app_undo_action.setEnabled(can_undo)
        self._app_redo_action.setEnabled(can_redo)
        undo_label = self._app_history.undo_label()
        redo_label = self._app_history.redo_label()
        self._app_undo_action.setText(
            f"Undo: {undo_label}" if can_undo and undo_label
            else "Undo last major action"
        )
        self._app_redo_action.setText(
            f"Redo: {redo_label}" if can_redo and redo_label
            else "Redo last major action"
        )

    def _is_translation_running(self) -> bool:
        return (
            len(self._state.phase_status) > 2
            and self._state.phase_status[2] == PhaseStatus.RUNNING
        )

    def _warn_translation_running(self) -> None:
        QMessageBox.warning(
            self,
            "Translation Running",
            "Cannot undo/redo app actions while translation is in progress.\n"
            "Please wait for translation to complete or cancel it first.",
        )

    # ------------------------------------------------------------------ recent files

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = gui_settings.get_recent_files()
        if not recent:
            empty = QAction("(No recent files)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for path in recent:
            act = QAction(Path(path).name, self)
            act.setToolTip(path)
            act.triggered.connect(lambda _checked=False, p=path: self._handle_dropped_file(p))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        clear = QAction("Clear recent files", self)
        clear.triggered.connect(self._clear_recent)
        self._recent_menu.addAction(clear)

    def _clear_recent(self) -> None:
        gui_settings.clear_recent_files()
        self._refresh_recent_menu()

    # ------------------------------------------------------------------ drag-and-drop

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self._handle_dropped_file(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    # ------------------------------------------------------------------ workflow override

    def _check_workflow_override(self, new_file_path: Path, target_phase: int) -> bool:
        """Check if loading a new file should override the active workflow.

        Returns True if the load should proceed, False if cancelled.
        """
        if not self._state.active_workflow:
            return True

        # Same file as current working path -- no override needed
        if (
            self._state.current_working_path is not None
            and new_file_path.resolve() == self._state.current_working_path.resolve()
        ):
            return True

        # Show unsaved changes dialog first if needed
        if self._state.has_unsaved_changes:
            unsaved_dlg = UnsavedChangesDialog(
                self._state.current_working_path,
                new_file_path,
                parent=self,
            )
            unsaved_dlg.exec()
            result = unsaved_dlg.result_action
            if result == UnsavedChangesResult.CANCEL:
                return False
            save_first = result == UnsavedChangesResult.SAVE_AND_OVERRIDE
            self._perform_workflow_override(save_first=save_first)
            return True

        # Show override confirmation dialog
        current_phase_name = PHASE_NAMES.get(
            self._state.current_phase, f"Phase {self._state.current_phase}"
        )
        dlg = OverrideConfirmationDialog(
            current_source=self._state.original_source_path,
            current_working=self._state.current_working_path,
            current_phase_name=current_phase_name,
            new_file_path=new_file_path,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._perform_workflow_override(save_first=False)
            return True
        return False

    def _perform_workflow_override(self, save_first: bool) -> None:
        """Perform the override: optionally save, then clear stale state."""
        if save_first:
            self._action_save_current()

        # Clear stale state via clear_workflow_context (resets all workflow fields)
        self._state.clear_workflow_context()

        # Reset downstream phase statuses
        current = self._state.current_phase
        for i in range(current, len(self._state.phase_status)):
            self._state.phase_status[i] = PhaseStatus.IDLE

        # Refresh UI
        self._refresh_phase_badges()
        self._update_sidebar_footer()

    # ------------------------------------------------------------------ file loading

    def _handle_dropped_file(self, path: str) -> None:
        path_obj = Path(path)
        if not path_obj.exists():
            QMessageBox.warning(self, "File not found", f"Could not find: {path_obj}")
            return

        suffix = path_obj.suffix.lower()

        # Determine target phase for override check
        target_phase = 0
        if suffix == ".stf":
            target_phase = 0
        elif suffix == ".xlsx":
            stem = path_obj.stem.lower()
            if "translated" in stem:
                target_phase = 3
            elif "organized" in stem or "organised" in stem:
                target_phase = 2
            elif "reviewed" in stem or "fixed" in stem:
                target_phase = 4
            else:
                target_phase = 3

        # Check workflow override before proceeding
        if not self._check_workflow_override(path_obj, target_phase):
            return

        gui_settings.add_recent_file(path_obj)
        self._refresh_recent_menu()

        if suffix == ".stf":
            self._load_stf(path_obj)
        elif suffix == ".xlsx":
            self._load_xlsx(path_obj)
        else:
            QMessageBox.warning(
                self,
                "Unsupported file type",
                f"Don't know how to open {suffix} files.  "
                "Supported: .stf, .xlsx",
            )

    def _load_stf(self, path: Path) -> None:
        self._log(f"Parsing {path.name} ...")
        worker = ParseStfWorker(path, self)
        worker.finished_ok.connect(lambda doc: self._after_stf_loaded(doc, path))
        worker.failed.connect(lambda msg: QMessageBox.critical(self, "Parse failed", msg))
        worker.start()

    def _after_stf_loaded(self, doc, path: Path) -> None:
        self._state.document = doc
        self._state.source_stf_path = path
        if doc.language:
            self._state.target_language_name = doc.language
        if doc.language_code:
            self._state.target_language_code = doc.language_code
        # Set workflow context
        self._state.set_active_workflow_context(
            document=doc,
            original_source_path=path,
            current_working_path=path,
            current_working_artifact_type="stf",
            start_phase=0,
            current_phase=0,
        )
        # Take Phase 1 snapshot
        self._state.phase_snapshots[0] = PhaseSnapshot(
            source_path=path,
            artifact_type="stf",
            row_count=len(doc.entries),
            target_language_code=self._state.target_language_code,
            target_language_name=self._state.target_language_name,
            timestamp=time.time(),
        )
        # Phase 0 (Import STF) is now complete -- jump to Phase 1 (STF -> Excel).
        self._state.set_phase(0, PhaseStatus.DONE)
        self._goto(1)
        self._log(f"Loaded {len(doc.entries):,} rows from {path.name}")
        self._record_app_action(f"Load STF ({path.name})")

    def _load_xlsx(self, path: Path) -> None:
        self._log(f"Loading {path.name} ...")
        worker = ImportExcelWorker(
            path,
            language=self._state.target_language_name,
            language_code=self._state.target_language_code,
            parent=self,
        )

        def _loaded(doc):
            self._state.document = doc
            # Heuristically route based on file name.  Indices reflect the
            # 6-phase layout: 0=Import, 1=Excel, 2=Translate, 3=Review,
            # 4=Validate, 5=Export.
            target_phase = 3  # default to Review
            artifact_type = "translated_excel"
            stem = path.stem.lower()
            if "translated" in stem:
                self._state.translated_xlsx_path = path
                target_phase = 3
                artifact_type = "translated_excel"
            elif "organized" in stem or "organised" in stem:
                self._state.organized_xlsx_path = path
                target_phase = 2
                artifact_type = "organized_excel"
            elif "reviewed" in stem or "fixed" in stem:
                self._state.reviewed_xlsx_path = path
                target_phase = 4
                artifact_type = "reviewed_excel" if "reviewed" in stem else "fixed_excel"
            # Set workflow context
            self._state.set_active_workflow_context(
                document=doc,
                original_source_path=path,
                current_working_path=path,
                current_working_artifact_type=artifact_type,
                start_phase=target_phase,
                current_phase=target_phase,
            )
            self._state.set_phase(target_phase, PhaseStatus.DONE)
            self._goto(target_phase)
            self._log(f"Loaded {len(doc.entries):,} rows from {path.name}")
            self._record_app_action(f"Load Excel ({path.name})")

        worker.finished_ok.connect(_loaded)
        worker.failed.connect(lambda msg: QMessageBox.critical(self, "Load failed", msg))
        worker.start()

    # ------------------------------------------------------------------ theme + geometry

    def _switch_theme(self, name: str) -> None:
        gui_settings.set_theme(name)
        theme.apply_theme(name)
        self._log(f"Theme switched to {name}.")

    def _action_open_settings(self) -> None:
        """Open the Settings dialog as a non-modal, movable window."""
        if (
            hasattr(self, "_settings_dialog")
            and self._settings_dialog is not None
            and self._settings_dialog.isVisible()
        ):
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        from .settings_dialog import SettingsDialog

        self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.accepted.connect(self._on_settings_accepted)
        self._settings_dialog.finished.connect(self._on_settings_dialog_closed)
        self._settings_dialog.show()

    def _on_settings_accepted(self) -> None:
        """Refresh UI after settings are saved."""
        self._log("Settings saved.")
        # Refresh the active phase so it picks up changed values
        current = self._stack.currentIndex()
        if 0 <= current < len(self._pages):
            self._pages[current].on_enter()

    def _on_settings_dialog_closed(self) -> None:
        """Clear settings dialog reference when closed/rejected."""
        if self._settings_dialog is not None:
            self._settings_dialog.deleteLater()
            self._settings_dialog = None

    def _snapshot_settings(self) -> dict:
        """Capture current key settings values for change detection."""
        return {
            "backend": gui_settings.get_str(gui_settings.KEYS.backend, "google"),
            "workers": gui_settings.get_int(gui_settings.KEYS.workers, 4),
            "theme": gui_settings.get_theme(),
            "session_persistence": gui_settings.get_session_enabled(),
            "glossary_path": gui_settings.get_str(gui_settings.KEYS.glossary_path, ""),
            "tm_path": gui_settings.get_str(gui_settings.KEYS.memory_path, ""),
            "fuzzy_threshold": gui_settings.get_int(gui_settings.KEYS.fuzzy_threshold, 80),
        }

    @staticmethod
    def _describe_settings_changes(before: dict, after: dict) -> str:
        """Return a human-readable string of what changed between two snapshots."""
        parts: list[str] = []
        labels = {
            "backend": "backend",
            "workers": "workers",
            "theme": "theme",
            "session_persistence": "session persistence",
            "glossary_path": "glossary path",
            "tm_path": "TM path",
            "fuzzy_threshold": "fuzzy threshold",
        }
        for key, label in labels.items():
            old_val = before.get(key)
            new_val = after.get(key)
            if old_val != new_val:
                parts.append(f"{label}={new_val}")
        return ", ".join(parts)

    def _show_user_guide(self) -> None:
        """Open the bundled user guide *inside the app*.

        The guide is the ``USER_GUIDE.md`` shipped alongside the source
        tree, rendered as Markdown in a modal :class:`UserGuideDialog`
        so users never get bounced out to an external editor or
        browser.
        """
        from .about_dialog import UserGuideDialog

        viewer = UserGuideDialog(self)
        viewer.exec()

    def _apply_remembered_theme(self) -> None:
        theme.apply_theme(gui_settings.get_theme())

    def _restore_geometry(self) -> None:
        s = gui_settings.settings()
        geo = s.value(gui_settings.KEYS.window_geometry)
        state = s.value(gui_settings.KEYS.window_state)
        if geo:
            self.restoreGeometry(geo)
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Auto-save session if persistence is enabled and a document is loaded
        if gui_settings.get_session_enabled() and self._state.document is not None:
            source = self._state.source_stf_path
            if source is not None:
                try:
                    save_path = self._session_manager.auto_save_path(source)
                    self._session_manager.save(self._state, save_path)
                except Exception:  # noqa: BLE001
                    pass  # best effort -- do not block window close

        s = gui_settings.settings()
        s.setValue(gui_settings.KEYS.window_geometry, self.saveGeometry())
        s.setValue(gui_settings.KEYS.window_state, self.saveState())
        super().closeEvent(event)

    def _show_faq(self) -> None:
        """Open the searchable FAQ dialog."""
        from .faq_dialog import FaqDialog
        dlg = FaqDialog(self)
        dlg.exec()

    def _show_about(self) -> None:
        from .about_dialog import AboutDialog

        dialog = AboutDialog(self)
        dialog.exec()

    def _check_for_updates(self) -> None:
        """Open the GitHub releases page in the default browser."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        releases_url = "https://github.com/sourav98hazra/Salesforce-Translation-Handler/releases"
        QDesktopServices.openUrl(QUrl(releases_url))

    # ------------------------------------------------------------------ session persistence

    def _try_restore_session(self) -> None:
        """Attempt to restore session state from auto-save on startup."""
        if not gui_settings.get_session_enabled():
            return

        # Check the most recent file to see if a session exists
        recent = gui_settings.get_recent_files()
        if not recent:
            return

        last_path = Path(recent[0])

        # If the source file no longer exists on disk, clear the stale
        # session and skip restoration to avoid broken state.
        if not last_path.is_file():
            self._session_manager.clear_session(last_path)
            return

        if not self._session_manager.has_session(last_path):
            return

        try:
            save_path = self._session_manager.auto_save_path(last_path)
            session_data = self._session_manager.load(save_path)
            self._apply_session_data(session_data)
        except Exception:  # noqa: BLE001
            pass  # silently skip restore on failure

    def _apply_session_data(self, data: dict) -> None:
        """Apply loaded session data to the current AppState."""
        if data.get("document") is not None:
            self._state.document = data["document"]

        source_path = data.get("source_file_path")
        if source_path:
            self._state.source_stf_path = Path(source_path)

        self._state.target_language_code = data.get("target_language_code", "ja")
        self._state.target_language_name = data.get("target_language_name", "Japanese")
        self._state.source_language_code = data.get("source_language_code", "en")
        self._state.backend_key = data.get("backend_key", "google")

        scope_path = data.get("scope_path")
        self._state.scope_path = Path(scope_path) if scope_path else None

        glossary_path = data.get("glossary_path")
        self._state.glossary_path = Path(glossary_path) if glossary_path else None

        memory_path = data.get("memory_path")
        self._state.memory_path = Path(memory_path) if memory_path else None

        self._state.translation_summaries = data.get("translation_summaries", [])
        self._state.translation_statuses = data.get("translation_statuses", [])

        phase_status = data.get("phase_status", [0] * 6)
        from .state import PhaseStatus as PS
        for i, val in enumerate(phase_status):
            if i < len(self._state.phase_status):
                self._state.phase_status[i] = PS(val)

    def _action_save_project(self) -> None:
        """Save the current session to a user-chosen .stxproj file."""
        from PySide6.QtWidgets import QFileDialog

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save project",
            "",
            "STX Project (*.stxproj);;All files (*)",
        )
        if path_str:
            try:
                self._session_manager.save(self._state, Path(path_str))
                self._log(f"Project saved to {Path(path_str).name}")
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Save failed", str(exc))

    def _action_open_project(self) -> None:
        """Open a .stxproj project file and restore its state."""
        from PySide6.QtWidgets import QFileDialog

        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open project",
            "",
            "STX Project (*.stxproj);;All files (*)",
        )
        if path_str:
            try:
                data = self._session_manager.load(Path(path_str))
                self._apply_session_data(data)
                self._refresh_phase_badges()
                self._update_sidebar_footer()
                self._goto(0)
                self._log(f"Project restored from {Path(path_str).name}")
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Load failed", str(exc))

    def _action_restart_session(self) -> None:
        """Clear the current session and reset to defaults (Reset All)."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Reset Session",
            "Reset the entire session to defaults?\n\n"
            "All progress will be lost. Translation Memory (API cache) will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Clear auto-save
        if self._state.source_stf_path is not None:
            self._session_manager.clear_session(self._state.source_stf_path)

        # Clear any checkpoint for the current document/target language
        from ..checkpoint import CheckpointStore
        source_path = self._state.organized_xlsx_path or self._state.source_stf_path
        if source_path is not None:
            target_code = self._state.target_language_code or "ja"
            try:
                cp = CheckpointStore(
                    source_file=str(Path(source_path).resolve()),
                    target_lang=target_code,
                )
                if cp.exists():
                    cp.clear()
            except Exception:  # noqa: BLE001
                pass  # best effort

        # Reset state
        self._state.document = None
        self._state.source_stf_path = None
        self._state.organized_xlsx_path = None
        self._state.translated_xlsx_path = None
        self._state.reviewed_xlsx_path = None
        self._state.output_dir = None
        self._state.translation_summaries = []
        self._state.translation_statuses = []
        self._state.source_language_code = "en"
        self._state.target_language_code = "ja"
        self._state.target_language_name = "Japanese"

        # Clear imported translations
        self._state.imported_translations = None
        self._state.imported_translations_path = None
        self._state.imported_translations_enabled = False

        # Clear translation scope tracking
        self._state.translation_failed_indices = set()
        self._state.translation_scope_indices = set()

        # Clear scope, glossary, memory references
        self._state.scope = None
        self._state.scope_path = None
        self._state.glossary = None
        self._state.glossary_path = None
        self._state.memory = None
        self._state.memory_path = None

        # Clear other settings
        self._state.retranslate_existing = False
        self._state.target_languages_batch = []
        self._state.backend_options = {}

        # Clear unsaved changes flag
        self._state.has_unsaved_changes = False

        from .state import PhaseStatus as PS
        self._state.phase_status = [PS.IDLE for _ in range(6)]

        # Clear workflow context
        self._state.clear_workflow_context()

        # Clear phase snapshots
        self._state.phase_snapshots = [None] * 6

        # Visually reset all phase pages
        for page in self._pages:
            page.reset_page()

        self._refresh_phase_badges()
        self._update_sidebar_footer()
        self._goto(0)
        self._log("Session reset to defaults.")
        self._app_history.clear()
        self._app_history.record(capture_snapshot(self._state, "Initial state"))
        self._refresh_app_history_actions()

    def _action_clear_tm(self) -> None:
        """Clear the Translation Memory database file after confirmation."""
        from PySide6.QtWidgets import QMessageBox

        from .. import settings as gui_settings

        # Determine TM path: use state reference first, then settings, then default
        tm_path = None
        if self._state.memory_path is not None and self._state.memory_path.exists():
            tm_path = self._state.memory_path
        else:
            memory_path_str = gui_settings.get_str(gui_settings.KEYS.memory_path, "").strip()
            if memory_path_str:
                tm_path = Path(memory_path_str)
            else:
                try:
                    from ..memory import default_tm_path
                    tm_path = default_tm_path()
                except (ImportError, AttributeError):
                    tm_path = Path.home() / ".cache" / "salesforce-translation-handler" / "tm.sqlite"

        if tm_path is None or not tm_path.exists():
            # Even if no file on disk, clear the in-memory reference
            self._state.memory = None
            self._state.memory_path = None
            self._log("Clear TM: no Translation Memory database found on disk.")
            QMessageBox.information(
                self, "Translation Memory",
                "No Translation Memory database found.\n"
                f"Expected at: {tm_path}"
            )
            return

        # Show file size for context
        size_kb = tm_path.stat().st_size / 1024
        reply = QMessageBox.warning(
            self,
            "Clear Translation Memory",
            f"Delete the Translation Memory database?\n\n"
            f"File: {tm_path.name} ({size_kb:.0f} KB)\n\n"
            f"All cached translations from previous runs will be permanently lost.\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._log("Clear TM: cancelled by user.")
            return

        try:
            tm_path.unlink()
            self._state.memory = None
            self._state.memory_path = None
            self._log(f"Translation Memory cleared: {tm_path.name} ({size_kb:.0f} KB deleted).")
            QMessageBox.information(
                self, "Translation Memory",
                "Translation Memory has been cleared successfully.\n"
                f"Deleted: {tm_path.name}"
            )
        except Exception as exc:
            self._log(f"Clear TM failed: {exc}")
            QMessageBox.critical(
                self, "Error",
                f"Could not delete Translation Memory:\n{exc}"
            )

    def _action_reset_current_phase(self) -> None:
        """Reset the current phase status and all downstream phases.

        Behaves like Reset Session but scoped to the current phase onwards:
        - Clears all state owned by the current phase and downstream phases
        - Clears the document if it was loaded/overridden in the current phase or later
        - Preserves upstream phase data and UI
        - TM database on disk is always kept
        """
        current = self._stack.currentIndex()
        from PySide6.QtWidgets import QMessageBox

        from .state import PhaseStatus as PS

        reply = QMessageBox.question(
            self,
            "Reset Phase",
            f"Reset Phase {current + 1} and all downstream phases?\n\n"
            "This will clear all progress from this phase onwards.\n"
            "Translation Memory (API cache) will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Release in-memory TM reference (TM database on disk is kept)
        self._state.memory = None
        self._state.memory_path = None

        # Reset current phase and downstream to IDLE; upstream stays as-is
        for i in range(current, len(self._state.phase_status)):
            self._state.phase_status[i] = PS.IDLE

        # Clear any checkpoint for the current document/target language
        # (must happen before paths are cleared below)
        from ..checkpoint import CheckpointStore
        source_path = self._state.organized_xlsx_path or self._state.source_stf_path
        if source_path is not None:
            target_code = self._state.target_language_code or "ja"
            try:
                cp = CheckpointStore(
                    source_file=str(Path(source_path).resolve()),
                    target_lang=target_code,
                )
                if cp.exists():
                    cp.clear()
            except Exception:  # noqa: BLE001
                pass  # best effort

        # --- Clear state from the current phase onwards ---
        # The document is preserved if it came from an upstream phase (normal flow).
        # It is cleared if the reset is from Phase 1, or if the document was loaded
        # via override in the current phase or downstream.
        # Detection: if source_stf_path is set AND current > 0, the document came
        # from Phase 1 and should be preserved for the "go back, click Continue" flow.

        # Try to restore document from upstream snapshot
        upstream_snapshot = None
        for i in range(current - 1, -1, -1):
            snap = self._state.phase_snapshots[i]
            if snap is not None:
                upstream_snapshot = snap
                break

        if upstream_snapshot is not None and upstream_snapshot.source_path.exists():
            self._restore_from_snapshot(upstream_snapshot)
        elif current <= 0 or self._state.source_stf_path is None:
            # Resetting Phase 1, or document came from an override (no Phase 1 import)
            self._state.document = None
            self._state.source_stf_path = None

        # Clear snapshots from current phase onwards
        for i in range(current, 6):
            self._state.phase_snapshots[i] = None

        if current <= 1:
            self._state.organized_xlsx_path = None

        self._state.translated_xlsx_path = None
        self._state.reviewed_xlsx_path = None
        self._state.output_dir = None

        self._state.translation_summaries = []
        self._state.translation_statuses = []
        self._state.translation_failed_indices = set()
        self._state.translation_scope_indices = set()

        self._state.scope = None
        self._state.scope_path = None
        self._state.glossary = None
        self._state.glossary_path = None

        self._state.imported_translations = None
        self._state.imported_translations_path = None
        self._state.imported_translations_enabled = False

        self._state.retranslate_existing = False
        self._state.last_validation_report = None

        # Clear flags and workflow context
        self._state.has_unsaved_changes = False
        upstream_snaps = self._state.phase_snapshots[:current]
        self._state.clear_workflow_context()
        self._state.phase_snapshots[:current] = upstream_snaps

        # Visually reset pages from current phase onwards.
        # Do NOT call on_enter() -- it would auto-convert/repopulate from
        # upstream data.  The user should manually navigate back to Phase N-1
        # and click "Continue" to re-forward data (like first time).
        for i in range(current, len(self._pages)):
            self._pages[i].reset_page()

        self._refresh_phase_badges()
        self._update_sidebar_footer()
        self._log(f"Reset Phase {current + 1} and all downstream phases.")

    def _restore_from_snapshot(self, snapshot: PhaseSnapshot) -> None:
        """Reload the document from an upstream phase snapshot."""
        from ..stf import parse_stf
        from ..excel import import_document_from_excel

        path = snapshot.source_path
        try:
            if snapshot.artifact_type == "stf":
                doc = parse_stf(path)
                self._state.document = doc
                self._state.source_stf_path = path
            else:
                doc = import_document_from_excel(
                    path,
                    language=snapshot.target_language_name,
                    language_code=snapshot.target_language_code,
                )
                self._state.document = doc
        except Exception:  # noqa: BLE001
            self._state.document = None
            self._state.source_stf_path = None
