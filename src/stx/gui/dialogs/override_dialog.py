"""Dialogs for confirming workflow override and unsaved changes."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PHASE_NAMES = {
    0: "Phase 1 - Import STF",
    1: "Phase 2 - STF to Excel",
    2: "Phase 3 - Translate",
    3: "Phase 4 - Review",
    4: "Phase 5 - Validate & Fix",
    5: "Phase 6 - Export STF",
}


class OverrideConfirmationDialog(QDialog):
    """Asks the user to confirm replacing the active workflow with a new file."""

    def __init__(
        self,
        current_source: Optional[Path],
        current_working: Optional[Path],
        current_phase_name: str,
        new_file_path: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Override Active Workflow")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        current_source_name = current_source.name if current_source else "(none)"
        current_working_name = current_working.name if current_working else "(none)"
        new_file_name = new_file_path.name

        message = (
            "A workflow is already active.\n"
            "\n"
            f"Current source: {current_source_name}\n"
            f"Current working file: {current_working_name}\n"
            f"Current phase: {current_phase_name}\n"
            "\n"
            f"New file: {new_file_name}\n"
            "\n"
            "Loading this file will replace the current workflow.\n"
            "Any unsaved progress in downstream phases will be lost."
        )

        label = QLabel(message)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(label)

        button_box = QDialogButtonBox()
        self._override_btn = QPushButton("Override and Continue with New File")
        self._cancel_btn = QPushButton("Cancel")
        button_box.addButton(self._override_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(self._cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(button_box)

        self._override_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)


class UnsavedChangesResult(Enum):
    """Result of the UnsavedChangesDialog."""

    SAVE_AND_OVERRIDE = "save_and_override"
    DISCARD_AND_OVERRIDE = "discard_and_override"
    CANCEL = "cancel"


class UnsavedChangesDialog(QDialog):
    """Asks the user how to handle unsaved changes before an override."""

    def __init__(
        self,
        current_working_path: Optional[Path],
        new_file_path: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Unsaved Changes")
        self.setMinimumWidth(400)
        self._result = UnsavedChangesResult.CANCEL

        layout = QVBoxLayout(self)

        working_name = current_working_path.name if current_working_path else "(none)"
        new_name = new_file_path.name

        message = (
            "You have unsaved changes in the current workflow.\n"
            "\n"
            f"Current working file: {working_name}\n"
            f"New file: {new_name}\n"
            "\n"
            "Would you like to save your changes before overriding?"
        )

        label = QLabel(message)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(label)

        button_box = QDialogButtonBox()
        self._save_btn = QPushButton("Save and Override")
        self._discard_btn = QPushButton("Discard and Override")
        self._cancel_btn = QPushButton("Cancel")
        button_box.addButton(self._save_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(self._discard_btn, QDialogButtonBox.ButtonRole.DestructiveRole)
        button_box.addButton(self._cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(button_box)

        self._save_btn.clicked.connect(self._on_save)
        self._discard_btn.clicked.connect(self._on_discard)
        self._cancel_btn.clicked.connect(self._on_cancel)

    @property
    def result_action(self) -> UnsavedChangesResult:
        """The user's chosen action."""
        return self._result

    def _on_save(self) -> None:
        self._result = UnsavedChangesResult.SAVE_AND_OVERRIDE
        self.accept()

    def _on_discard(self) -> None:
        self._result = UnsavedChangesResult.DISCARD_AND_OVERRIDE
        self.accept()

    def _on_cancel(self) -> None:
        self._result = UnsavedChangesResult.CANCEL
        self.reject()
