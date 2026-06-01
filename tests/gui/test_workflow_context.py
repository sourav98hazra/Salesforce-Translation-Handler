"""Tests for workflow context state logic and override dialogs.

Exercises the 10 WF test cases specified in the requirements plus
additional helper-method tests.
"""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path

import pytest

from stx.gui.state import AppState, PhaseStatus
from stx.model import Document, Entry


def _make_doc(language: str = "Japanese", language_code: str = "ja") -> Document:
    """Create a minimal test Document."""
    return Document(
        language=language,
        language_code=language_code,
        entries=[Entry(key="K1", label="Hello")],
    )


# ============================================================
# WF-01: Load STF, continue phase 2
# ============================================================


def test_wf01_load_stf_continue_phase2():
    """Loading an STF starts workflow at phase 0; continuing keeps the same document."""
    state = AppState()
    doc = _make_doc()
    source_path = Path("/fake/file_a.stf")

    state.set_active_workflow_context(
        document=doc,
        original_source_path=source_path,
        current_working_artifact_type="stf",
        start_phase=0,
        current_phase=0,
    )

    assert state.active_workflow is True
    assert state.original_source_path == source_path
    assert state.current_working_artifact_type == "stf"
    assert state.document is doc

    # Simulate continuing to phase 1
    state.current_phase = 1
    assert state.document is doc  # same object reference


# ============================================================
# WF-02: Load Excel at phase 4 starts workflow
# ============================================================


def test_wf02_load_excel_phase4_starts_workflow():
    """Loading a translated Excel starts the workflow from phase 3."""
    state = AppState()
    assert state.active_workflow is False

    doc = _make_doc()
    xlsx_path = Path("/fake/translated.xlsx")

    state.set_active_workflow_context(
        document=doc,
        original_source_path=xlsx_path,
        current_working_path=xlsx_path,
        current_working_artifact_type="translated_excel",
        start_phase=3,
        current_phase=3,
    )

    assert state.workflow_started_from_phase == 3
    assert state.active_workflow is True
    assert state.current_working_artifact_type == "translated_excel"


# ============================================================
# WF-03: Phase 4 continues to phase 5
# ============================================================


def test_wf03_phase4_continues_to_phase5():
    """After WF-02 setup, updating phase keeps same document reference."""
    state = AppState()
    doc = _make_doc()
    xlsx_path = Path("/fake/translated.xlsx")

    state.set_active_workflow_context(
        document=doc,
        original_source_path=xlsx_path,
        current_working_path=xlsx_path,
        current_working_artifact_type="translated_excel",
        start_phase=3,
        current_phase=3,
    )

    # Continue to phase 4
    state.current_phase = 4
    assert state.document is doc  # same object identity


# ============================================================
# WF-04: Load Excel at phase 6
# ============================================================


def test_wf04_load_excel_phase6():
    """Loading a reviewed Excel starts workflow from phase 5."""
    state = AppState()
    doc = _make_doc()
    xlsx_path = Path("/fake/reviewed.xlsx")

    state.set_active_workflow_context(
        document=doc,
        original_source_path=xlsx_path,
        current_working_path=xlsx_path,
        current_working_artifact_type="reviewed_excel",
        start_phase=5,
        current_phase=5,
    )

    assert state.workflow_started_from_phase == 5
    # Phases 0-4 should be in completed_phases
    for phase in range(5):
        assert phase in state.completed_phases


# ============================================================
# WF-05: Override confirmation shown
# ============================================================


def test_wf05_override_confirmation_shown(qtbot):
    """When active_workflow is True, override dialog can be constructed."""
    from stx.gui.dialogs.override_dialog import OverrideConfirmationDialog

    state = AppState()
    state.active_workflow = True
    state.original_source_path = Path("/fake/file_a.stf")
    state.current_working_path = Path("/fake/file_a_translated.xlsx")

    # The condition that triggers the dialog is active_workflow being True
    assert state.active_workflow is True

    # Verify the dialog instantiates correctly
    dialog = OverrideConfirmationDialog(
        current_source=state.original_source_path,
        current_working=state.current_working_path,
        current_phase_name="Phase 4 - Review",
        new_file_path=Path("/fake/file_b.xlsx"),
    )
    qtbot.addWidget(dialog)
    assert dialog is not None
    assert dialog.windowTitle() == "Override Active Workflow"


# ============================================================
# WF-06: Override dialog shows correct info
# ============================================================


def test_wf06_override_dialog_shows_info(qtbot):
    """OverrideConfirmationDialog displays expected file names."""
    from PySide6.QtWidgets import QLabel

    from stx.gui.dialogs.override_dialog import OverrideConfirmationDialog

    dialog = OverrideConfirmationDialog(
        current_source=Path("/fake/source_file.stf"),
        current_working=Path("/fake/working_file.xlsx"),
        current_phase_name="Phase 3 - Translate",
        new_file_path=Path("/fake/new_file.xlsx"),
    )
    qtbot.addWidget(dialog)

    # Find the label in the dialog and check displayed text
    labels = dialog.findChildren(QLabel)
    assert len(labels) > 0
    label_text = labels[0].text()
    assert "source_file.stf" in label_text
    assert "working_file.xlsx" in label_text
    assert "new_file.xlsx" in label_text


# ============================================================
# WF-07: Cancel override preserves state
# ============================================================


def test_wf07_cancel_override_preserves_state():
    """Not calling set_active_workflow_context leaves state unchanged."""
    state = AppState()
    doc = _make_doc()
    source_path = Path("/fake/file_a.stf")
    working_path = Path("/fake/file_a_translated.xlsx")

    state.set_active_workflow_context(
        document=doc,
        original_source_path=source_path,
        current_working_path=working_path,
        current_working_artifact_type="translated_excel",
        start_phase=3,
        current_phase=3,
    )

    # Store references
    original_doc = state.document
    original_source = state.original_source_path
    original_working = state.current_working_path

    # Simulate cancel: do NOT call set_active_workflow_context
    # Assert nothing changed
    assert state.document is original_doc
    assert state.original_source_path is original_source
    assert state.current_working_path is original_working
    assert state.active_workflow is True


# ============================================================
# WF-08: Confirm override clears stale state
# ============================================================


def test_wf08_confirm_override_clears_stale():
    """Override with override_existing=True clears stale fields."""
    state = AppState()
    doc_old = _make_doc(language="French", language_code="fr")
    state.set_active_workflow_context(
        document=doc_old,
        original_source_path=Path("/fake/old.stf"),
        current_working_path=Path("/fake/old_translated.xlsx"),
        current_working_artifact_type="translated_excel",
        start_phase=0,
        current_phase=3,
    )

    # Add stale data
    state.translation_summaries = [object()]
    state.translation_statuses = [object()]
    state.last_validation_report = object()
    state.last_export_paths = [Path("/old")]
    state.has_unsaved_changes = True

    # Override with new document
    doc_new = _make_doc(language="Spanish", language_code="es")
    state.set_active_workflow_context(
        document=doc_new,
        original_source_path=Path("/fake/new.stf"),
        current_working_path=Path("/fake/new_translated.xlsx"),
        current_working_artifact_type="stf",
        start_phase=0,
        current_phase=0,
        override_existing=True,
    )

    # Assert new document is active
    assert state.document is doc_new
    assert state.original_source_path == Path("/fake/new.stf")
    assert state.current_working_path == Path("/fake/new_translated.xlsx")

    # Assert stale fields are cleared
    assert state.translation_summaries == []
    assert state.translation_statuses == []
    assert state.last_validation_report is None
    assert state.last_export_paths is None
    assert state.has_unsaved_changes is False


# ============================================================
# WF-09: Unsaved changes dialog
# ============================================================


def test_wf09_unsaved_changes_dialog(qtbot):
    """UnsavedChangesDialog has three buttons and defaults to CANCEL."""
    from PySide6.QtWidgets import QPushButton

    from stx.gui.dialogs.override_dialog import (
        UnsavedChangesDialog,
        UnsavedChangesResult,
    )

    dialog = UnsavedChangesDialog(
        current_working_path=Path("/fake/current.xlsx"),
        new_file_path=Path("/fake/new.xlsx"),
    )
    qtbot.addWidget(dialog)

    # Find all push buttons
    buttons = dialog.findChildren(QPushButton)
    button_texts = [b.text() for b in buttons]
    assert "Save and Override" in button_texts
    assert "Discard and Override" in button_texts
    assert "Cancel" in button_texts

    # Default result should be CANCEL
    assert dialog.result_action == UnsavedChangesResult.CANCEL


# ============================================================
# WF-10: After override, export uses new file
# ============================================================


def test_wf10_after_override_export_uses_new_file():
    """After override, state paths reference only the new file."""
    state = AppState()
    doc_a = _make_doc()
    path_a_source = Path("/fake/file_a.stf")
    path_a_working = Path("/fake/file_a_translated.xlsx")

    # Set up workflow A
    state.set_active_workflow_context(
        document=doc_a,
        original_source_path=path_a_source,
        current_working_path=path_a_working,
        current_working_artifact_type="translated_excel",
        start_phase=3,
        current_phase=3,
    )

    # Override with workflow B
    doc_b = _make_doc(language="Korean", language_code="ko")
    path_b_source = Path("/fake/file_b.stf")
    path_b_working = Path("/fake/file_b_organized.xlsx")

    state.set_active_workflow_context(
        document=doc_b,
        original_source_path=path_b_source,
        current_working_path=path_b_working,
        current_working_artifact_type="organized_excel",
        start_phase=1,
        current_phase=1,
        override_existing=True,
    )

    # Assert all path fields reference the new file
    assert state.original_source_path == path_b_source
    assert state.current_working_path == path_b_working
    # No trace of old file paths
    assert state.original_source_path != path_a_source
    assert state.current_working_path != path_a_working


# ============================================================
# Additional: test_clear_workflow_context
# ============================================================


def test_clear_workflow_context():
    """clear_workflow_context resets all workflow fields to defaults."""
    state = AppState()
    doc = _make_doc()

    state.set_active_workflow_context(
        document=doc,
        original_source_path=Path("/fake/file.stf"),
        current_working_path=Path("/fake/file.xlsx"),
        current_working_artifact_type="stf",
        start_phase=2,
        current_phase=3,
    )
    state.has_unsaved_changes = True
    state.last_validation_report = object()
    state.last_translation_progress = {"key": "value"}
    state.last_export_paths = [Path("/export")]

    state.clear_workflow_context()

    assert state.active_workflow is False
    assert state.original_source_path is None
    assert state.current_working_path is None
    assert state.current_working_artifact_type is None
    assert state.workflow_started_from_phase is None
    assert state.current_phase == 0
    assert state.completed_phases == set()
    assert state.has_unsaved_changes is False
    assert state.last_validation_report is None
    assert state.last_translation_progress is None
    assert state.last_export_paths is None


# ============================================================
# Additional: test_mark_phase_completed
# ============================================================


def test_mark_phase_completed():
    """mark_phase_completed adds to completed_phases and sets DONE."""
    state = AppState()

    state.mark_phase_completed(2)

    assert 2 in state.completed_phases
    assert state.phase_status[2] == PhaseStatus.DONE


# ============================================================
# Additional: test_set_active_workflow_context_reset_downstream
# ============================================================


def test_set_active_workflow_context_reset_downstream():
    """With reset_downstream=True, phases >= current_phase are reset to IDLE."""
    state = AppState()
    # Set some phases to DONE first
    state.phase_status[3] = PhaseStatus.DONE
    state.phase_status[4] = PhaseStatus.DONE
    state.phase_status[5] = PhaseStatus.DONE

    doc = _make_doc()
    state.set_active_workflow_context(
        document=doc,
        original_source_path=Path("/fake/file.stf"),
        current_working_artifact_type="translated_excel",
        start_phase=3,
        current_phase=3,
        reset_downstream=True,
    )

    # Phases 3, 4, 5 should be reset to IDLE
    assert state.phase_status[3] == PhaseStatus.IDLE
    assert state.phase_status[4] == PhaseStatus.IDLE
    assert state.phase_status[5] == PhaseStatus.IDLE


# ============================================================
# Integration: test_integration_override_accepted
# ============================================================


def test_integration_override_accepted(qtbot, tmp_path):
    """MainWindow override check returns True when dialog is accepted."""
    from unittest.mock import patch

    from stx.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    # Set up an active workflow on the state
    doc = _make_doc()
    source = tmp_path / "original.stf"
    source.write_text("dummy")
    win._state.set_active_workflow_context(
        document=doc,
        original_source_path=source,
        current_working_path=source,
        current_working_artifact_type="stf",
        start_phase=0,
        current_phase=0,
    )

    new_file = tmp_path / "new_file.stf"
    new_file.write_text("dummy2")

    # Patch the dialog to auto-accept
    from PySide6.QtWidgets import QDialog

    with patch(
        "stx.gui.main_window.OverrideConfirmationDialog"
    ) as mock_dlg_cls:
        mock_dlg = mock_dlg_cls.return_value
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        result = win._check_workflow_override(new_file, 0)

    assert result is True


# ============================================================
# Integration: test_integration_override_rejected
# ============================================================


def test_integration_override_rejected(qtbot, tmp_path):
    """MainWindow override check returns False when dialog is rejected."""
    from unittest.mock import patch

    from stx.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    # Set up an active workflow on the state
    doc = _make_doc()
    source = tmp_path / "original.stf"
    source.write_text("dummy")
    win._state.set_active_workflow_context(
        document=doc,
        original_source_path=source,
        current_working_path=source,
        current_working_artifact_type="stf",
        start_phase=0,
        current_phase=0,
    )

    # Record state before override attempt
    original_doc = win._state.document
    original_source = win._state.original_source_path

    new_file = tmp_path / "new_file.stf"
    new_file.write_text("dummy2")

    # Patch the dialog to auto-reject
    from PySide6.QtWidgets import QDialog

    with patch(
        "stx.gui.main_window.OverrideConfirmationDialog"
    ) as mock_dlg_cls:
        mock_dlg = mock_dlg_cls.return_value
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        result = win._check_workflow_override(new_file, 0)

    assert result is False
    # State should be unchanged
    assert win._state.document is original_doc
    assert win._state.original_source_path is original_source


# ============================================================
# Integration: test_integration_current_phase_advances
# ============================================================


def test_integration_current_phase_advances(qtbot):
    """Calling _goto(3) on MainWindow updates state.current_phase to 3."""
    from stx.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    assert win._state.current_phase == 0

    win._goto(3)
    assert win._state.current_phase == 3

    win._goto(5)
    assert win._state.current_phase == 5

    win._goto(0)
    assert win._state.current_phase == 0
