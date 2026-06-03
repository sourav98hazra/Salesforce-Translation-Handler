"""Top-level window: sidebar phase navigation + stacked phase pages."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from .pages.base import PhasePage
from .pages.phase1_import import Phase1ImportPage
from .pages.phase2_excel import Phase2ExcelPage
from .pages.phase3_translate import Phase3TranslatePage
from .pages.phase4_review import Phase4ReviewPage
from .pages.phase5_export import Phase5ExportPage
from .state import AppState

_PHASES = [
    ("1. Import STF", "Pick the source .stf file"),
    ("2. STF \u2192 Excel", "Convert to organised workbook"),
    ("3. Translate", "Auto-translate untranslated rows"),
    ("4. Review", "Inspect and edit translations"),
    ("5. Export STF", "Validate and write final STF files"),
]


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Salesforce Translation Handler")
        self.resize(1280, 820)
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
        self._status_log.setStyleSheet("font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace; font-size: 11px;")
        dock = QDockWidget("Status log", self)
        dock.setWidget(self._status_log)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

        # ---- status bar
        bar = QStatusBar()
        self.setStatusBar(bar)
        bar.showMessage(f"Ready  (stx {__version__})")

        # ---- menu
        self._build_menu()

        # ---- wire phase signals + select phase 1
        for page in self._pages:
            page.status_message.connect(self._log)
            page.request_navigate.connect(self._goto)
        self._goto(0)

    # ------------------------------------------------------------------ build

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("background:#0f172a;color:#e2e8f0;")
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
        self._phase_list.setStyleSheet("""
            QListWidget { background: transparent; border: 0; outline: 0; }
            QListWidget::item {
                padding: 12px 12px;
                margin-bottom: 4px;
                color: #cbd5e1;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #1e40af;
                color: white;
            }
            QListWidget::item:hover { background: #1e293b; }
        """)
        self._phase_list.setSpacing(0)
        self._phase_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label, hint in _PHASES:
            item = QListWidgetItem(f"{label}\n   {hint}")
            self._phase_list.addItem(item)
        self._phase_list.currentRowChanged.connect(self._goto)
        v.addWidget(self._phase_list)
        v.addStretch(1)
        return sidebar

    def _build_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("color:#cbd5e1;")
        return line

    def _build_pages(self) -> QWidget:
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:#f8fafc;")
        self._pages: list[PhasePage] = [
            Phase1ImportPage(self._state, self),
            Phase2ExcelPage(self._state, self),
            Phase3TranslatePage(self._state, self),
            Phase4ReviewPage(self._state, self),
            Phase5ExportPage(self._state, self),
        ]
        for page in self._pages:
            self._stack.addWidget(page)
        return self._stack

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        
        # Add reset current phase action
        reset_action = QAction("&Reset Current Phase", self)
        reset_action.setShortcut("Ctrl+R")
        reset_action.triggered.connect(self._reset_current_phase)
        file_menu.addAction(reset_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = bar.addMenu("&Help")
        about = QAction("&About", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    # ------------------------------------------------------------------ navigation

    def _goto(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return
        self._stack.setCurrentIndex(index)
        self._phase_list.blockSignals(True)
        self._phase_list.setCurrentRow(index)
        self._phase_list.blockSignals(False)
        self._pages[index].on_enter()

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._status_log.appendPlainText(f"[{timestamp}] {message}")
        self.statusBar().showMessage(message, 5000)

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About",
            (
                f"<h3>Salesforce Translation Handler</h3>"
                f"<p>Version {__version__}</p>"
                f"<p>Professional desktop app for the Salesforce Translation "
                f"Workbench workflow: STF \u2192 Excel \u2192 Translate \u2192 "
                f"Review \u2192 STF.</p>"
                f"<p>Per-phase artifacts can be saved to disk for verification "
                f"outside the app.</p>"
            ),
        )

    def _reset_current_phase(self) -> None:
        """Reset the current active phase."""
        current_index = self._stack.currentIndex()
        if current_index >= 0 and current_index < len(self._pages):
            current_page = self._pages[current_index]
            # Call the reset method on the current page which handles confirmation
            current_page._on_reset_phase(current_index + 1)
