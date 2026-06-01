"""Undo/Redo infrastructure for the Phase 4 editor.

Provides a lightweight command-based undo stack that records cell-level
changes to translation text and approved status.  Emits a Qt signal on
every mutation so the UI can enable/disable buttons reactively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class UndoCommand:
    """A single reversible cell edit.

    Attributes
    ----------
    row:
        Row index in the entries list.
    column:
        Column index (_TRANSLATION_COL or _APPROVED_COL).
    old_value:
        The value before the edit.
    new_value:
        The value after the edit.
    """

    row: int
    column: int
    old_value: Any
    new_value: Any


class UndoStack(QObject):
    """Manages a linear undo/redo history of :class:`UndoCommand` objects.

    Signals
    -------
    stack_changed:
        Emitted after every push, undo, redo, or clear so that toolbar
        buttons and menu actions can update their enabled state.
    """

    stack_changed = Signal()

    MAX_SIZE = 500
    """Maximum number of commands retained. Oldest are evicted when exceeded."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._commands: List[UndoCommand] = []
        self._index: int = 0  # points to *next* command to push (past end of undo history)

    # ------------------------------------------------------------------ public API

    def push(self, command: UndoCommand) -> None:
        """Record a new command, discarding any redo history."""
        # Truncate redo tail
        self._commands = self._commands[: self._index]
        self._commands.append(command)
        self._index += 1
        # Evict oldest commands when exceeding max size
        if len(self._commands) > self.MAX_SIZE:
            overflow = len(self._commands) - self.MAX_SIZE
            self._commands = self._commands[overflow:]
            self._index -= overflow
        self.stack_changed.emit()

    def undo(self) -> Optional[UndoCommand]:
        """Undo the most recent command. Returns it (or None if nothing to undo)."""
        if not self.can_undo:
            return None
        self._index -= 1
        cmd = self._commands[self._index]
        self.stack_changed.emit()
        return cmd

    def redo(self) -> Optional[UndoCommand]:
        """Redo the next command. Returns it (or None if nothing to redo)."""
        if not self.can_redo:
            return None
        cmd = self._commands[self._index]
        self._index += 1
        self.stack_changed.emit()
        return cmd

    def clear(self) -> None:
        """Discard all history."""
        self._commands.clear()
        self._index = 0
        self.stack_changed.emit()

    @property
    def can_undo(self) -> bool:
        """True when there is at least one command to undo."""
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        """True when there is at least one command to redo."""
        return self._index < len(self._commands)
