"""App-wide action history (coarse undo/redo).

This is **separate** from the Phase 4 per-translation undo stack
(:mod:`stx.gui.undo`).  Where that stack reverses a single cell edit,
this history reverses a *major application action* -- loading a file,
running a translation, auto-fixing, or resetting.

The history stores light snapshots of :class:`stx.gui.state.AppState`.
Only the mutable document is deep-copied; paths and scalar settings are
immutable or cheap to copy, and resource handles (translation memory,
glossary, scope) are kept by reference because undo never mutates them.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

# Fields captured/restored by a snapshot.  Document is handled separately
# (deep-copied); these are copied shallowly or kept by reference.
_SCALAR_FIELDS = (
    "source_stf_path",
    "organized_xlsx_path",
    "translated_xlsx_path",
    "reviewed_xlsx_path",
    "output_dir",
    "source_language_code",
    "source_language_name",
    "target_language_code",
    "target_language_name",
    "backend_key",
    "workers",
    "rate_limit_per_second",
    "scope",
    "scope_path",
    "glossary",
    "glossary_path",
    "memory",
    "memory_path",
    "imported_translations",
    "imported_translations_path",
    "imported_translations_enabled",
    "retranslate_existing",
    "active_workflow",
    "original_source_path",
    "current_working_path",
    "current_working_artifact_type",
    "workflow_started_from_phase",
    "current_phase",
    "has_unsaved_changes",
    "last_validation_report",
    "last_translation_progress",
)

# Fields that are list/set/dict containers -- copied one level deep.
_CONTAINER_FIELDS = (
    "translation_summaries",
    "translation_statuses",
    "target_languages_batch",
    "phase_status",
    "completed_phases",
    "backend_options",
    "last_export_paths",
)


@dataclass
class AppSnapshot:
    """A captured AppState plus a human label describing the action."""

    label: str
    data: Dict[str, Any] = field(default_factory=dict)


def capture_snapshot(state, label: str) -> AppSnapshot:
    """Build an :class:`AppSnapshot` from the current ``state``."""
    data: Dict[str, Any] = {}
    data["document"] = copy.deepcopy(state.document) if state.document is not None else None
    for name in _SCALAR_FIELDS:
        data[name] = getattr(state, name)
    for name in _CONTAINER_FIELDS:
        value = getattr(state, name)
        if isinstance(value, list):
            data[name] = list(value)
        elif isinstance(value, set):
            data[name] = set(value)
        elif isinstance(value, dict):
            data[name] = dict(value)
        else:
            data[name] = value
    return AppSnapshot(label=label, data=data)


def restore_snapshot(state, snapshot: AppSnapshot) -> None:
    """Apply a snapshot's captured data back onto ``state`` in place."""
    data = snapshot.data
    # Document: hand back a fresh deep copy so a later undo/redo to the same
    # snapshot is not corrupted by edits made after restore.
    doc = data.get("document")
    state.document = copy.deepcopy(doc) if doc is not None else None
    for name in _SCALAR_FIELDS:
        if name in data:
            setattr(state, name, data[name])
    for name in _CONTAINER_FIELDS:
        if name not in data:
            continue
        value = data[name]
        if isinstance(value, list):
            setattr(state, name, list(value))
        elif isinstance(value, set):
            setattr(state, name, set(value))
        elif isinstance(value, dict):
            setattr(state, name, dict(value))
        else:
            setattr(state, name, value)


class AppHistory(QObject):
    """Linear undo/redo history of :class:`AppSnapshot` objects.

    The snapshot at ``_index`` is the *current* state.  ``undo`` steps the
    index back one and returns the snapshot to restore; ``redo`` steps it
    forward.  ``record`` truncates any redo tail before appending.

    Signals
    -------
    changed:
        Emitted after every record / undo / redo / clear so menu actions
        can refresh their enabled state and dynamic labels.
    """

    changed = Signal()

    MAX_SIZE = 25
    """Maximum snapshots retained (bounds memory for large documents)."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._snaps: List[AppSnapshot] = []
        self._index: int = -1

    # ------------------------------------------------------------------ API

    def record(self, snapshot: AppSnapshot) -> None:
        """Append a snapshot, discarding any redo tail."""
        self._snaps = self._snaps[: self._index + 1]
        self._snaps.append(snapshot)
        self._index = len(self._snaps) - 1
        if len(self._snaps) > self.MAX_SIZE:
            overflow = len(self._snaps) - self.MAX_SIZE
            self._snaps = self._snaps[overflow:]
            self._index -= overflow
        self.changed.emit()

    def undo(self) -> Optional[AppSnapshot]:
        """Step back and return the snapshot to restore (or None)."""
        if not self.can_undo:
            return None
        self._index -= 1
        self.changed.emit()
        return self._snaps[self._index]

    def redo(self) -> Optional[AppSnapshot]:
        """Step forward and return the snapshot to restore (or None)."""
        if not self.can_redo:
            return None
        self._index += 1
        self.changed.emit()
        return self._snaps[self._index]

    def clear(self) -> None:
        """Discard all history."""
        self._snaps = []
        self._index = -1
        self.changed.emit()

    # ------------------------------------------------------------------ queries

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._snaps) - 1

    def undo_label(self) -> Optional[str]:
        """Label of the action that an undo would reverse (the current one)."""
        if self.can_undo:
            return self._snaps[self._index].label
        return None

    def redo_label(self) -> Optional[str]:
        """Label of the action that a redo would re-apply."""
        if self.can_redo:
            return self._snaps[self._index + 1].label
        return None
