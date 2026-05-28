"""Shared helpers used by every phase page."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..state import AppState


class PhasePage(QWidget):
    """Base class for every phase page.

    Provides:

    * A reference to the shared :class:`AppState`.
    * A standard heading layout (title + subtitle).
    * Two convenience signals -- :pyattr:`status_message` (logged in
      the dock at the bottom of the main window) and :pyattr:`request_navigate`
      (asks the main window to switch to a different phase index).
    """

    status_message = Signal(str)
    request_navigate = Signal(int)

    def __init__(
        self,
        state: AppState,
        title: str,
        subtitle: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        heading = QVBoxLayout()
        heading.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("class", "phase-title")
        title_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        heading.addWidget(title_label)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("color: #4a5568;")
        subtitle_label.setWordWrap(True)
        heading.addWidget(subtitle_label)

        outer.addLayout(heading)

        # Subclass-supplied content lives in ``self._content_layout``.
        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(12)
        outer.addLayout(self._content_layout, stretch=1)

    # ------------------------------------------------------------------ helpers

    @property
    def state(self) -> AppState:
        return self._state

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._content_layout.addWidget(widget, stretch=stretch)

    def add_layout(self, layout) -> None:
        self._content_layout.addLayout(layout)

    def add_separator(self) -> None:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #e2e8f0;")
        self._content_layout.addWidget(line)

    # ------------------------------------------------------------------ dialogs

    def info(self, message: str, title: str = "Information") -> None:
        QMessageBox.information(self, title, message)

    def warn(self, message: str, title: str = "Warning") -> None:
        QMessageBox.warning(self, title, message)

    def error(self, message: str, title: str = "Error") -> None:
        QMessageBox.critical(self, title, message)

    def pick_open_file(self, caption: str, filter_str: str, start_dir: Optional[Path] = None) -> Optional[Path]:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            caption,
            str(start_dir or Path.cwd()),
            filter_str,
        )
        return Path(path_str) if path_str else None

    def pick_save_file(self, caption: str, filter_str: str, default_name: str) -> Optional[Path]:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            caption,
            str(self._state.output_dir or Path.cwd() / default_name),
            filter_str,
        )
        return Path(path_str) if path_str else None

    def pick_directory(self, caption: str, start_dir: Optional[Path] = None) -> Optional[Path]:
        path_str = QFileDialog.getExistingDirectory(
            self,
            caption,
            str(start_dir or self._state.output_dir or Path.cwd()),
        )
        return Path(path_str) if path_str else None

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        """Called by :class:`MainWindow` when this page becomes active.

        Subclasses override to refresh state-dependent widgets.
        """


# ---------------------------------------------------------------------------
# Re-usable widgets
# ---------------------------------------------------------------------------

def make_action_row(*buttons: QPushButton) -> QHBoxLayout:
    """Lay out a row of action buttons, left-aligned with the layout pushing right."""
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for btn in buttons:
        btn.setMinimumHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(btn)
    layout.addStretch(1)
    return layout
