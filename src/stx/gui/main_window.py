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

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
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
from .state import AppState, PhaseStatus
from .workers import ImportExcelWorker, ParseStfWorker

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


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Salesforce Translation Manager")
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
        self._status_log.setMinimumHeight(60)
        self._status_dock = QDockWidget("Status log", self)
        self._status_dock.setWidget(self._status_log)
        self._status_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._status_dock)
        # Give the dock enough initial height so it's clearly visible --
        # not clipped or hidden behind the status bar.
        self._status_dock.setMinimumHeight(80)

        # ---- status bar
        bar = QStatusBar()
        self.setStatusBar(bar)
        bar.showMessage(f"Ready  (stx {__version__})")

        # ---- menu + shortcuts
        self._build_menu()
        self._wire_shortcuts()

        # ---- wire phase signals
        for page in self._pages:
            page.status_message.connect(self._log)
            page.request_navigate.connect(self._goto)
            page.busy_changed.connect(lambda _busy: self._refresh_phase_badges())
            page.file_dropped.connect(self._handle_dropped_file)

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
        self._phase_list.currentRowChanged.connect(self._goto)
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
        components = {e.component_type for e in doc.entries}
        self._footer_stats.setText(
            f"{row_count:,} rows \u00b7 {len(components)} components"
        )

        # Target language
        lang_name = self._state.target_language_name or ""
        lang_code = self._state.target_language_code or ""
        if lang_name and lang_code:
            self._footer_lang.setText(f"{lang_name} ({lang_code})")
        elif lang_name:
            self._footer_lang.setText(lang_name)
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
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu: only Settings for now -- everything advanced lives there.
        edit_menu = bar.addMenu("&Edit")
        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._action_open_settings)
        edit_menu.addAction(settings_action)

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
        self._toggle_log_action.triggered.connect(lambda checked: self._status_dock.setVisible(checked))
        view_menu.addAction(self._toggle_log_action)
        self._status_dock.visibilityChanged.connect(self._toggle_log_action.setChecked)

        help_menu = bar.addMenu("&Help")
        guide_action = QAction("&User guide", self)
        guide_action.setShortcut("F1")
        guide_action.triggered.connect(self._show_user_guide)
        help_menu.addAction(guide_action)
        about = QAction("&About", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _wire_shortcuts(self) -> None:
        # Ctrl+0..6 to switch phases.
        for index in range(len(_PHASES)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda i=index: self._goto(i))

    # ------------------------------------------------------------------ navigation

    def _goto(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return
        self._stack.setCurrentIndex(index)
        self._phase_list.blockSignals(True)
        self._phase_list.setCurrentRow(index)
        self._phase_list.blockSignals(False)
        self._pages[index].on_enter()
        self._refresh_phase_badges()
        self._update_sidebar_footer()

    def _jump_to_row(self, key: str) -> None:
        # Phase 4 (Review) is now at index 3 in the simplified flow.
        self._goto(3)
        review = self._pages[3]
        if hasattr(review, "focus_key"):
            review.focus_key(key)

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

    def _handle_dropped_file(self, path: str) -> None:
        path_obj = Path(path)
        if not path_obj.exists():
            QMessageBox.warning(self, "File not found", f"Could not find: {path_obj}")
            return

        suffix = path_obj.suffix.lower()
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
        # Phase 0 (Import STF) is now complete -- jump to Phase 1 (STF -> Excel).
        self._state.set_phase(0, PhaseStatus.DONE)
        self._goto(1)
        self._log(f"Loaded {len(doc.entries):,} rows from {path.name}")

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
            stem = path.stem.lower()
            if "translated" in stem:
                self._state.translated_xlsx_path = path
                target_phase = 3
            elif "organized" in stem or "organised" in stem:
                self._state.organized_xlsx_path = path
                target_phase = 2
            elif "reviewed" in stem or "fixed" in stem:
                self._state.reviewed_xlsx_path = path
                target_phase = 4
            self._state.set_phase(target_phase, PhaseStatus.DONE)
            self._goto(target_phase)
            self._log(f"Loaded {len(doc.entries):,} rows from {path.name}")

        worker.finished_ok.connect(_loaded)
        worker.failed.connect(lambda msg: QMessageBox.critical(self, "Load failed", msg))
        worker.start()

    # ------------------------------------------------------------------ theme + geometry

    def _switch_theme(self, name: str) -> None:
        gui_settings.set_theme(name)
        theme.apply_theme(name)
        self._log(f"Theme switched to {name}.")

    def _action_open_settings(self) -> None:
        """Open the Settings dialog (Edit -> Settings... or Ctrl+,).

        On accept, refresh the active phase so it picks up any changed
        values immediately (e.g. Phase 3's settings summary line).
        """
        from .settings_dialog import open_settings

        if open_settings(self):
            self._log("Settings updated.")
            current = self._stack.currentIndex()
            if 0 <= current < len(self._pages):
                self._pages[current].on_enter()

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
        s = gui_settings.settings()
        s.setValue(gui_settings.KEYS.window_geometry, self.saveGeometry())
        s.setValue(gui_settings.KEYS.window_state, self.saveState())
        super().closeEvent(event)

    def _show_about(self) -> None:
        from .about_dialog import AboutDialog

        dialog = AboutDialog(self)
        dialog.exec()
