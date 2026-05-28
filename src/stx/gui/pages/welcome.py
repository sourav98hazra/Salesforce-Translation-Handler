"""Welcome screen -- the landing page on app launch.

Shows recent files, quick actions (open STF, load project), and a
short pitch describing what the app does.  Selecting a recent file
auto-routes the user to the appropriate phase based on the file's
extension.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from .. import settings
from ..state import AppState
from .base import PhasePage, make_action_row, primary

_DESCRIPTION = (
    "Salesforce Translation Handler converts Translation Workbench STF "
    "exports to organised Excel, auto-translates them with placeholder / ID "
    "/ HTML protection, lets you review the result, and re-emits the three "
    "STF files Salesforce expects.\n\n"
    "Every phase produces a downloadable artifact so you can verify outputs "
    "outside the app and re-enter the workflow at any point."
)


class WelcomePage(PhasePage):
    """Phase 0 -- welcome / recent files / quick actions."""

    request_open_path = Signal(str)
    request_open_project = Signal(str)
    request_new_run = Signal()

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(
            state,
            title="Welcome",
            subtitle="Pick up where you left off, or start a new translation run.",
            parent=parent,
        )
        self.setAcceptDrops(True)
        self._build()

    def _build(self) -> None:
        # ---------- pitch
        pitch = QLabel(_DESCRIPTION)
        pitch.setWordWrap(True)
        pitch.setStyleSheet("font-size: 13px; padding: 8px 0;")
        self.add_widget(pitch)

        # ---------- two-column layout: quick actions | recent files
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # Quick actions
        actions_box = QGroupBox("Quick actions")
        actions_layout = QVBoxLayout(actions_box)

        new_btn = primary(QPushButton("Open STF file..."))
        new_btn.clicked.connect(self._on_open_stf)
        actions_layout.addWidget(new_btn)

        proj_btn = QPushButton("Open project (.stxproject)...")
        proj_btn.clicked.connect(self._on_open_project)
        actions_layout.addWidget(proj_btn)

        load_xlsx = QPushButton("Load existing organised Excel...")
        load_xlsx.clicked.connect(self._on_open_xlsx)
        actions_layout.addWidget(load_xlsx)

        actions_layout.addStretch(1)

        hint = QLabel(
            "Tip: drag and drop an .stf, .xlsx, or .stxproject file "
            "anywhere in the window."
        )
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        hint.setWordWrap(True)
        actions_layout.addWidget(hint)

        cols.addWidget(actions_box, stretch=1)

        # Recent files
        recent_box = QGroupBox("Recent files")
        recent_layout = QVBoxLayout(recent_box)
        self._recent_list = QListWidget()
        self._recent_list.itemActivated.connect(self._on_recent_activated)
        recent_layout.addWidget(self._recent_list)

        clear_btn = QPushButton("Clear list")
        clear_btn.clicked.connect(self._on_clear_recent)
        clear_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        recent_layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignRight)

        cols.addWidget(recent_box, stretch=2)

        self.add_layout(cols)

        # ---------- footer
        footer = make_action_row(
            primary(self._make_button("Continue \u2192", self._on_continue))
        )
        self.add_layout(footer)

    def _make_button(self, label: str, handler) -> QPushButton:
        btn = QPushButton(label)
        btn.clicked.connect(handler)
        return btn

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        self._reload_recent()

    def _reload_recent(self) -> None:
        self._recent_list.clear()
        for path in settings.get_recent_files():
            p = Path(path)
            display = f"{p.name}\n   {p.parent}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            item.setToolTip(str(p))
            self._recent_list.addItem(item)

    # ------------------------------------------------------------------ slots

    def _on_open_stf(self) -> None:
        path = self.pick_open_file("Select Salesforce STF file", "STF files (*.stf);;All files (*)")
        if path:
            self.request_open_path.emit(str(path))

    def _on_open_xlsx(self) -> None:
        path = self.pick_open_file("Select Excel workbook", "Excel files (*.xlsx)")
        if path:
            self.request_open_path.emit(str(path))

    def _on_open_project(self) -> None:
        path = self.pick_open_file("Select project file", "Project files (*.stxproject)")
        if path:
            self.request_open_project.emit(str(path))

    def _on_continue(self) -> None:
        self.request_navigate.emit(1)

    def _on_recent_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        if path.endswith(".stxproject"):
            self.request_open_project.emit(path)
        else:
            self.request_open_path.emit(path)

    def _on_clear_recent(self) -> None:
        if self.confirm("Clear the recent files list?"):
            settings.clear_recent_files()
            self._reload_recent()
