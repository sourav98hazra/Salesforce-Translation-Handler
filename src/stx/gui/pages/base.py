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
    * Convenience signals -- :pyattr:`status_message`, :pyattr:`request_navigate`,
      and :pyattr:`request_jump_to_row` for cross-phase navigation.
    * A :pyattr:`is_busy` guard so subclasses can refuse double-clicks
      from the user without each one re-implementing the same dance.
    """

    status_message = Signal(str)
    request_navigate = Signal(int)
    request_jump_to_row = Signal(str)  # entry key
    file_dropped = Signal(str)         # absolute path of a dropped file
    busy_changed = Signal(bool)

    def __init__(
        self,
        state: AppState,
        title: str,
        subtitle: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._busy = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(16)

        heading = QVBoxLayout()
        heading.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("class", "phase-title")
        title_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        heading.addWidget(title_label)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("color: #4a5568;")
        subtitle_label.setWordWrap(True)
        heading.addWidget(subtitle_label)

        outer.addLayout(heading)

        # Subclass-supplied content lives in ``self._content_layout``.
        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(8)
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
        line.setProperty("role", "separator")
        self._content_layout.addWidget(line)

    # ------------------------------------------------------------------ busy guard

    @property
    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """Toggle the busy state.

        Subclasses that start work via :meth:`run_when_idle` get
        protection from double-clicks for free; explicit callers can
        also use this directly to gate UI elements.
        """
        if self._busy == busy:
            return
        self._busy = busy
        self.busy_changed.emit(busy)

    def run_when_idle(self, callable_, *args, **kwargs) -> bool:
        """Invoke ``callable_`` only if the page isn't already running work.

        Returns ``True`` if the call ran, ``False`` if it was suppressed.
        Used by every ``_on_<action>`` slot so that a user mashing the
        mouse can never trigger overlapping operations.
        """
        if self._busy:
            self.status_message.emit("Operation already in progress -- ignoring duplicate click.")
            return False
        callable_(*args, **kwargs)
        return True

    # ------------------------------------------------------------------ dialogs

    def info(self, message: str, title: str = "Information") -> None:
        QMessageBox.information(self, title, message)

    def warn(self, message: str, title: str = "Warning") -> None:
        QMessageBox.warning(self, title, message)

    def error(self, message: str, title: str = "Error") -> None:
        QMessageBox.critical(self, title, message)

    def confirm(self, message: str, title: str = "Confirm") -> bool:
        return (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def pick_open_file(
        self,
        caption: str,
        filter_str: str,
        start_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            caption,
            str(start_dir or Path.cwd()),
            filter_str,
        )
        return Path(path_str) if path_str else None

    def pick_save_file(
        self,
        caption: str,
        filter_str: str,
        default_name: str,
    ) -> Optional[Path]:
        start = self._state.output_dir or Path.cwd()
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            caption,
            str(Path(start) / default_name),
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
        """Called by :class:`MainWindow` when this page becomes active."""

    # ------------------------------------------------------------------ drag-and-drop

    def dragEnterEvent(self, event) -> None:  # noqa: N802 -- Qt API
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    self.file_dropped.emit(url.toLocalFile())
                    event.acceptProposedAction()
                    return
        event.ignore()


# ---------------------------------------------------------------------------
# Re-usable widgets
# ---------------------------------------------------------------------------

def make_action_row(*buttons: QPushButton) -> QHBoxLayout:
    """Lay out a row of action buttons, left-aligned with spacer pushing right."""
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for btn in buttons:
        btn.setMinimumHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(btn)
    layout.addStretch(1)
    return layout


def primary(button: QPushButton) -> QPushButton:
    """Mark a button as primary (themed accent colour)."""
    button.setProperty("primary", True)
    return button


def danger(button: QPushButton) -> QPushButton:
    """Mark a button as destructive."""
    button.setProperty("danger", True)
    return button


# ---------------------------------------------------------------------------
# Pop-out icon helper
# ---------------------------------------------------------------------------

from PySide6.QtCore import QObject, QEvent
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QGroupBox  # noqa: F401  (re-export for callers)


def add_popout_to_groupbox(groupbox, callback):
    """Add a tiny \u2197 pop-out icon to the top-right of a QGroupBox border.

    Qt does not natively allow widgets in QGroupBox titles, so this
    workaround positions a tiny QPushButton as a *child* of the
    QGroupBox at absolute coordinates aligned to the top-right of the
    group box border, overlapping the title bar area.

    The button automatically repositions whenever the group box is
    resized or shown so it stays glued to the corner.

    Returns the QPushButton for further customization.
    """
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtWidgets import QPushButton

    btn = QPushButton("\u2197", groupbox)
    btn.setFixedSize(18, 18)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        "QPushButton { font-size: 11px; padding: 0; border: none; "
        "background: transparent; color: #94a3b8; } "
        "QPushButton:hover { color: #4338ca; background: rgba(67,56,202,0.10); border-radius: 3px; }"
    )
    btn.setToolTip("Pop out into a separate window")
    btn.clicked.connect(callback)

    def reposition():
        btn.move(groupbox.width() - btn.width() - 6, 2)

    class Repositioner(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Resize or event.type() == QEvent.Type.Show:
                reposition()
            return False

    repositioner = Repositioner(groupbox)
    groupbox.installEventFilter(repositioner)
    btn.show()
    btn.raise_()
    reposition()

    groupbox._popout_repositioner = repositioner
    groupbox._popout_btn = btn
    return btn
