"""Shared helpers used by every phase page."""

from __future__ import annotations

import re
from datetime import date as _date
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

# Stage tokens previously appended to artifact filenames.  Stripped from a
# stem before building a fresh professional name so re-saving never stacks
# suffixes like ``file_Organized_Translated_ja_...``.
_STAGE_TOKENS = (
    "organized",
    "organised",
    "translated",
    "reviewed",
    "validated",
    "fixed",
    "copy",
)

_STAGE_LABELS = {
    "organized": ("Organized", False),
    "translated": ("Translated", True),
    "reviewed": ("Reviewed", True),
    "validated": ("Validated", True),
    "validation_report": ("Validation_Report", True),
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CODE_RE = re.compile(r"^[a-z]{2,3}(_[a-z]{2,4})?$")


def clean_source_stem(stem: str) -> str:
    """Strip previously-appended stage / date / language-code tokens.

    Keeps re-saving a derived workbook from producing names like
    ``file_Organized_Translated_ja_2024-01-01`` -- we always rebuild from
    the original source stem.
    """
    parts = stem.split("_")
    changed = True
    while changed and len(parts) > 1:
        changed = False
        last = parts[-1]
        low = last.lower()
        if _DATE_RE.match(last):
            parts.pop()
            changed = True
            continue
        if low in _STAGE_TOKENS:
            parts.pop()
            changed = True
            continue
        # A short language code is only stripped when it directly follows a
        # stage word (e.g. ``..._Translated_ja``), never a normal stem word.
        if (
            _CODE_RE.match(low)
            and len(parts) >= 2
            and parts[-2].lower() in _STAGE_TOKENS
        ):
            parts.pop()
            changed = True
            continue
    return "_".join(parts) if parts else stem


def default_output_filename(
    source_stem: str,
    stage: str,
    target_code: Optional[str] = None,
    *,
    today: Optional[_date] = None,
    suffix: str = ".xlsx",
) -> str:
    """Build a professional, dated default save filename.

    Patterns (``<stem>`` is the cleaned original source stem)::

        organized   -> <stem>_Organized_<YYYY-MM-DD>.xlsx
        translated  -> <stem>_Translated_<code>_<YYYY-MM-DD>.xlsx
        reviewed    -> <stem>_Reviewed_<code>_<YYYY-MM-DD>.xlsx
        validated   -> <stem>_Validated_<code>_<YYYY-MM-DD>.xlsx
    """
    label, needs_code = _STAGE_LABELS.get(stage, (stage.capitalize(), False))
    stem = clean_source_stem(source_stem) or "workbook"
    day = (today or _date.today()).strftime("%Y-%m-%d")
    parts = [stem, label]
    if needs_code and target_code:
        parts.append(target_code)
    parts.append(day)
    return "_".join(parts) + suffix


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
    action_recorded = Signal(str)      # a major action completed (label) -> app history

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
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(6)

        heading = QVBoxLayout()
        heading.setSpacing(1)
        title_label = QLabel(title)
        title_label.setProperty("class", "phase-title")
        title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        heading.addWidget(title_label)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("color: #4a5568; font-size: 11px;")
        subtitle_label.setWordWrap(True)
        heading.addWidget(subtitle_label)

        outer.addLayout(heading)

        # Subclass-supplied content lives in ``self._content_layout``.
        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(6)
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

    # ------------------------------------------------------------------ default save names

    def default_save_name(self, stage: str, suffix: str = ".xlsx") -> str:
        """Build a professional dated default filename for a save dialog.

        Derives the stem from the original source artifact (falling back to
        any organised / translated / reviewed path) and appends the stage
        label, target language code (where relevant), and today's date.
        See :func:`default_output_filename`.
        """
        base = (
            self._state.source_stf_path
            or self._state.organized_xlsx_path
            or self._state.translated_xlsx_path
            or self._state.reviewed_xlsx_path
        )
        stem = Path(base).stem if base else "workbook"
        return default_output_filename(
            stem,
            stage,
            self._state.target_language_code,
            suffix=suffix,
        )

    # ------------------------------------------------------------------ workflow override

    def check_workflow_override(self, file_path: Path) -> bool:
        """Ask MainWindow to check workflow override. Returns True if load should proceed."""
        main_win = self.window()
        if hasattr(main_win, '_check_workflow_override'):
            return main_win._check_workflow_override(file_path, self._state.current_phase)
        return True

    # ------------------------------------------------------------------ lifecycle

    def on_enter(self) -> None:
        """Called by :class:`MainWindow` when this page becomes active."""

    def reset_page(self) -> None:
        """Called by Reset Session to clear all displayed widgets back to defaults."""

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
# Re-usable widgets / sizing helpers
# ---------------------------------------------------------------------------

def clamp_to_screen(widget: QWidget, w: int, h: int, h_margin: int = 80, v_margin: int = 120) -> None:
    """Resize *widget* to at most ``(w, h)``, then center it on screen.

    Prevents dialogs and pop-out windows from opening larger than the
    available screen area or starting off-screen (common on small laptops,
    secondary monitors, or 1366x768 displays).
    """
    from PySide6.QtGui import QGuiApplication

    screen = widget.screen() if hasattr(widget, "screen") else None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        w = min(w, max(640, avail.width() - h_margin))
        h = min(h, max(480, avail.height() - v_margin))

    widget.resize(w, h)

    # Center on the parent / screen so it never opens partially off-screen.
    if screen is not None:
        avail = screen.availableGeometry()
        x = avail.x() + (avail.width() - w) // 2
        y = avail.y() + (avail.height() - h) // 2
        widget.move(x, y)


def make_action_row(*buttons: QPushButton) -> QHBoxLayout:
    """Lay out a row of action buttons, left-aligned with spacer pushing right."""
    layout = QHBoxLayout()
    layout.setSpacing(6)
    for btn in buttons:
        btn.setMinimumHeight(28)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(btn)
    layout.addStretch(1)
    return layout


def primary(button: QPushButton) -> QPushButton:
    """Mark a button as primary (themed accent colour)."""
    button.setProperty("primary", True)
    return button


def compact_btn(btn: QPushButton) -> QPushButton:
    """Apply compact styling to a secondary button (smaller padding)."""
    btn.setStyleSheet(
        "QPushButton { padding: 4px 10px; font-size: 12px; }"
    )
    return btn


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

    Double-clicking on the group box title area also triggers the
    pop-out, so users have two clear ways to activate it.

    Returns the QPushButton for further customization.
    """
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtWidgets import QPushButton

    btn = QPushButton("\u2197", groupbox)
    btn.setFixedSize(22, 22)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    # Soft-white pill with dark bold arrow -- stands out on both light
    # content backgrounds and the dark sidebar.
    btn.setStyleSheet(
        "QPushButton { font-size: 14px; font-weight: 900; padding: 0; border: 1px solid transparent; "
        "background: rgba(241, 245, 249, 0.85); color: #0f172a; border-radius: 3px; } "
        "QPushButton:hover { background: #4338ca; color: white; border: 1px solid #4338ca; }"
    )
    btn.setToolTip("Pop out into a separate window (double-click also works)")
    btn.clicked.connect(callback)

    def reposition():
        btn.move(groupbox.width() - btn.width() - 6, 2)

    class DoubleClickFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.MouseButtonDblClick:
                # Only trigger if click is in the title area (top ~22px)
                if event.position().y() < 22:
                    callback()
                    return True
            if event.type() == QEvent.Type.Resize or event.type() == QEvent.Type.Show:
                reposition()
            return False

    double_click_filter = DoubleClickFilter(groupbox)
    groupbox.installEventFilter(double_click_filter)
    btn.show()
    btn.raise_()
    reposition()

    groupbox._popout_double_click_filter = double_click_filter
    groupbox._popout_btn = btn
    return btn
