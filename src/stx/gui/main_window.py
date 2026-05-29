"""Top-level window: sidebar phase navigation + stacked phase pages.

v1.1 additions over the MVP:

* **Welcome page** as Phase 0, with recent files and quick actions.
* **Status badges** in the sidebar (idle / running / done / error).
* **Drag-and-drop** anywhere in the window opens a dropped file in the
  appropriate phase.
* **Keyboard shortcuts**: ``Ctrl+1..6`` (phase), ``Ctrl+O`` (open),
  ``Ctrl+S`` (save current phase), ``Ctrl+Q`` (quit), ``Ctrl+Shift+L`` /
  ``Ctrl+Shift+D`` (light / dark theme).
* **File menu** with recent files submenu (auto-routes by extension).
* **View menu** with theme toggle.
* **Settings persistence** for window geometry, theme, last language.
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
from .pages.welcome import WelcomePage
from .state import AppState, PhaseStatus
from .workers import ImportExcelWorker, ParseStfWorker

_PHASES = [
    ("0. Welcome", "Recent files and quick actions"),
    ("1. Import STF", "Pick the source .stf file"),
    ("2. STF \u2192 Excel", "Convert to organised workbook"),
    ("3. Translate", "Auto-translate untranslated rows"),
    ("4. Review", "Inspect, edit, re-upload Excel"),
    ("5. Validate & Fix", "Auto-fix errors, re-validate"),
    ("6. Export STF", "Write final STF files"),
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
        self.setWindowTitle("Salesforce Translation Handler")
        self.resize(1400, 900)
        self.setAcceptDrops(True)
        self._state = AppState()

        # ---- central layout
        central = QWidget(self)
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
        self._status_log.setMaximumBlockCount(500)
        dock = QDockWidget("Status log", self)
        dock.setWidget(self._status_log)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

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

        welcome = self._pages[0]
        if isinstance(welcome, WelcomePage):
            welcome.request_open_path.connect(self._handle_dropped_file)
            welcome.request_open_project.connect(self._open_project)

        # Phase 5 (Validate & Fix) -> Phase 4 jump-to-issue wiring.
        phase5 = self._pages[5]
        if hasattr(phase5, "request_jump_to_row"):
            phase5.request_jump_to_row.connect(self._jump_to_row)

        # Phase 6 (Export) might also have jump-to-row in the future.
        phase6 = self._pages[6]
        if hasattr(phase6, "request_jump_to_row"):
            phase6.request_jump_to_row.connect(self._jump_to_row)

        # ---- restore window geometry / theme from settings
        self._apply_remembered_theme()
        self._restore_geometry()

        self._goto(0)

    # ------------------------------------------------------------------ build

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        sidebar.setObjectName("sidebar")
        v = QVBoxLayout(sidebar)
        v.setContentsMargins(16, 24, 16, 16)
        v.setSpacing(12)

        title = QLabel("Salesforce\nTranslation\nHandler")
        title.setFont(QFont("Inter, Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet("color:#f8fafc;")
        v.addWidget(title)

        version = QLabel(f"v{__version__}")
        version.setStyleSheet("color:#64748b; font-size:11px;")
        v.addWidget(version)

        v.addSpacing(16)

        self._phase_list = QListWidget()
        self._phase_list.setSpacing(0)
        self._phase_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label, hint in _PHASES:
            item = QListWidgetItem(self._format_phase_label(label, hint, PhaseStatus.IDLE))
            item.setData(Qt.ItemDataRole.UserRole, label)
            self._phase_list.addItem(item)
        self._phase_list.currentRowChanged.connect(self._goto)
        v.addWidget(self._phase_list)
        v.addStretch(1)
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

    def _build_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        return line

    def _build_pages(self) -> QWidget:
        self._stack = QStackedWidget()
        self._pages: List[PhasePage] = [
            WelcomePage(self._state, self),           # 0
            Phase1ImportPage(self._state, self),      # 1
            Phase2ExcelPage(self._state, self),       # 2
            Phase3TranslatePage(self._state, self),   # 3
            Phase4ReviewPage(self._state, self),      # 4
            Phase5ValidatePage(self._state, self),    # 5
            Phase6ExportPage(self._state, self),      # 6
        ]
        for page in self._pages:
            self._stack.addWidget(page)
        return self._stack

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        open_action = QAction("&Open file...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._action_open_file)
        file_menu.addAction(open_action)

        save_action = QAction("&Save current phase", self)
        save_action.setShortcut("Ctrl+S")
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

        view_menu = bar.addMenu("&View")
        for name, label in (("light", "&Light theme"), ("dark", "&Dark theme"), ("auto", "&Auto theme")):
            act = QAction(label, self)
            act.triggered.connect(lambda _checked=False, n=name: self._switch_theme(n))
            view_menu.addAction(act)

        help_menu = bar.addMenu("&Help")
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

    def _jump_to_row(self, key: str) -> None:
        self._goto(4)
        page4 = self._pages[4]
        if hasattr(page4, "focus_key"):
            page4.focus_key(key)

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
            "All supported (*.stf *.xlsx *.stxproject);;STF (*.stf);;Excel (*.xlsx);;Project (*.stxproject)",
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
        elif suffix == ".stxproject":
            self._open_project(str(path_obj))
        else:
            QMessageBox.warning(
                self,
                "Unsupported file type",
                f"Don't know how to open {suffix} files.  "
                "Supported: .stf, .xlsx, .stxproject",
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
        self._state.set_phase(1, PhaseStatus.DONE)
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
            # Heuristically route based on file name.
            target_phase = 4  # default review
            stem = path.stem.lower()
            if "translated" in stem:
                self._state.translated_xlsx_path = path
                target_phase = 4
            elif "organized" in stem or "organised" in stem:
                self._state.organized_xlsx_path = path
                target_phase = 3
            elif "reviewed" in stem:
                self._state.reviewed_xlsx_path = path
                target_phase = 5
            self._state.set_phase(target_phase, PhaseStatus.DONE)
            self._goto(target_phase)
            self._log(f"Loaded {len(doc.entries):,} rows from {path.name}")

        worker.finished_ok.connect(_loaded)
        worker.failed.connect(lambda msg: QMessageBox.critical(self, "Load failed", msg))
        worker.start()

    def _open_project(self, path: str) -> None:
        from ..project import StxProject

        try:
            project = StxProject.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open project", f"Failed to open project: {exc}")
            return

        self._state.project_path = Path(path)
        if project.target_language_code:
            self._state.target_language_code = project.target_language_code
        if project.target_language_name:
            self._state.target_language_name = project.target_language_name
        if project.source_stf_path:
            stf = Path(project.source_stf_path)
            if stf.exists():
                self._load_stf(stf)
                return
        QMessageBox.information(self, "Project", f"Opened project: {project.name}")

    # ------------------------------------------------------------------ theme + geometry

    def _switch_theme(self, name: str) -> None:
        gui_settings.set_theme(name)
        theme.apply_theme(name)
        self._log(f"Theme switched to {name}.")

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
        QMessageBox.about(
            self,
            "About",
            (
                f"<h3>Salesforce Translation Handler</h3>"
                f"<p>Version {__version__}</p>"
                f"<p>Professional desktop app for the Salesforce Translation "
                f"Workbench workflow: STF \u2192 Excel \u2192 Translate \u2192 "
                f"Review \u2192 Validate & Fix \u2192 STF.</p>"
                f"<p>v1.2 features: auto-validation on review entry, dedicated "
                f"Validate & Fix phase with auto-fix, re-upload Excel in Review, "
                f"direct Excel \u2192 STF in Export, plus all v1.1 features "
                f"(TM, glossary, scope, backends, dark theme, drag-drop, etc.).</p>"
            ),
        )
