"""Tests for Phase 4 undo/redo functionality."""
from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt

from stx.gui.undo import UndoCommand, UndoStack
from stx.model import Document, Entry


# ---------------------------------------------------------------------------
# UndoStack standalone tests
# ---------------------------------------------------------------------------


class TestUndoStackStandalone:
    """Unit tests for UndoStack push/undo/redo/clear logic."""

    def test_initial_state(self):
        stack = UndoStack()
        assert not stack.can_undo
        assert not stack.can_redo

    def test_push_enables_undo(self):
        stack = UndoStack()
        cmd = UndoCommand(row=0, column=5, old_value="old", new_value="new")
        stack.push(cmd)
        assert stack.can_undo
        assert not stack.can_redo

    def test_undo_returns_command(self):
        stack = UndoStack()
        cmd = UndoCommand(row=0, column=5, old_value="old", new_value="new")
        stack.push(cmd)
        result = stack.undo()
        assert result is cmd
        assert not stack.can_undo
        assert stack.can_redo

    def test_redo_returns_command(self):
        stack = UndoStack()
        cmd = UndoCommand(row=0, column=5, old_value="old", new_value="new")
        stack.push(cmd)
        stack.undo()
        result = stack.redo()
        assert result is cmd
        assert stack.can_undo
        assert not stack.can_redo

    def test_undo_multiple_restores_in_reverse_order(self):
        stack = UndoStack()
        cmd1 = UndoCommand(row=0, column=5, old_value="a", new_value="b")
        cmd2 = UndoCommand(row=1, column=5, old_value="c", new_value="d")
        cmd3 = UndoCommand(row=2, column=5, old_value="e", new_value="f")
        stack.push(cmd1)
        stack.push(cmd2)
        stack.push(cmd3)
        assert stack.undo() is cmd3
        assert stack.undo() is cmd2
        assert stack.undo() is cmd1
        assert not stack.can_undo

    def test_push_after_undo_clears_redo(self):
        stack = UndoStack()
        cmd1 = UndoCommand(row=0, column=5, old_value="a", new_value="b")
        cmd2 = UndoCommand(row=1, column=5, old_value="c", new_value="d")
        stack.push(cmd1)
        stack.push(cmd2)
        stack.undo()  # undo cmd2, redo available
        assert stack.can_redo
        cmd3 = UndoCommand(row=2, column=5, old_value="e", new_value="f")
        stack.push(cmd3)
        assert not stack.can_redo
        # Only cmd1 and cmd3 should be in the stack now
        assert stack.undo() is cmd3
        assert stack.undo() is cmd1
        assert not stack.can_undo

    def test_clear_resets_everything(self):
        stack = UndoStack()
        stack.push(UndoCommand(row=0, column=5, old_value="a", new_value="b"))
        stack.push(UndoCommand(row=1, column=5, old_value="c", new_value="d"))
        stack.clear()
        assert not stack.can_undo
        assert not stack.can_redo

    def test_undo_on_empty_returns_none(self):
        stack = UndoStack()
        assert stack.undo() is None

    def test_redo_on_empty_returns_none(self):
        stack = UndoStack()
        assert stack.redo() is None

    def test_max_size_evicts_oldest(self):
        """When stack exceeds MAX_SIZE, oldest commands are evicted."""
        stack = UndoStack()
        # Push MAX_SIZE + 10 commands
        for i in range(UndoStack.MAX_SIZE + 10):
            stack.push(UndoCommand(row=i, column=5, old_value=f"old{i}", new_value=f"new{i}"))
        # Stack should be capped at MAX_SIZE
        undo_count = 0
        while stack.can_undo:
            stack.undo()
            undo_count += 1
        assert undo_count == UndoStack.MAX_SIZE

    def test_max_size_preserves_newest(self):
        """After eviction, the newest commands are still accessible."""
        stack = UndoStack()
        for i in range(UndoStack.MAX_SIZE + 5):
            stack.push(UndoCommand(row=i, column=5, old_value=f"old{i}", new_value=f"new{i}"))
        # The most recent command should be undoable
        cmd = stack.undo()
        assert cmd is not None
        expected_row = UndoStack.MAX_SIZE + 5 - 1
        assert cmd.row == expected_row

    def test_stack_changed_signal_emitted(self):
        stack = UndoStack()
        signals_received = []
        stack.stack_changed.connect(lambda: signals_received.append("changed"))
        stack.push(UndoCommand(row=0, column=5, old_value="a", new_value="b"))
        assert len(signals_received) == 1
        stack.undo()
        assert len(signals_received) == 2
        stack.redo()
        assert len(signals_received) == 3
        stack.clear()
        assert len(signals_received) == 4


# ---------------------------------------------------------------------------
# Integration tests with _EntriesModel
# ---------------------------------------------------------------------------


class TestUndoWithEntriesModel:
    """Integration tests verifying undo/redo works with _EntriesModel.setData."""

    @pytest.fixture
    def doc(self):
        return Document(
            language="Japanese",
            language_code="ja",
            entries=[
                Entry(key="Key.One", label="Hello", translation="Konnichiwa"),
                Entry(key="Key.Two", label="Goodbye", translation="Sayonara"),
                Entry(key="Key.Three", label="Thanks", translation=""),
            ],
        )

    @pytest.fixture
    def model_and_stack(self, doc):
        from stx.gui.pages.phase4_review import _EntriesModel

        stack = UndoStack()
        model = _EntriesModel(doc, undo_stack=stack)
        return model, stack, doc

    def test_setdata_pushes_translation_command(self, model_and_stack):
        model, stack, doc = model_and_stack
        idx = model.index(0, 5)  # TRANSLATION_COL
        model.setData(idx, "NewTranslation", Qt.ItemDataRole.EditRole)
        assert stack.can_undo
        assert doc.entries[0].translation == "NewTranslation"

    def test_undo_restores_translation(self, model_and_stack):
        model, stack, doc = model_and_stack
        idx = model.index(0, 5)
        model.setData(idx, "Changed", Qt.ItemDataRole.EditRole)
        assert doc.entries[0].translation == "Changed"
        model.undo()
        assert doc.entries[0].translation == "Konnichiwa"

    def test_redo_reapplies_translation(self, model_and_stack):
        model, stack, doc = model_and_stack
        idx = model.index(0, 5)
        model.setData(idx, "Changed", Qt.ItemDataRole.EditRole)
        model.undo()
        assert doc.entries[0].translation == "Konnichiwa"
        model.redo()
        assert doc.entries[0].translation == "Changed"

    def test_setdata_pushes_approved_command(self, model_and_stack):
        model, stack, doc = model_and_stack
        idx = model.index(0, 6)  # APPROVED_COL
        model.setData(idx, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        assert stack.can_undo
        assert doc.entries[0].approved is True

    def test_undo_restores_approved(self, model_and_stack):
        model, stack, doc = model_and_stack
        idx = model.index(0, 6)
        model.setData(idx, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        assert doc.entries[0].approved is True
        model.undo()
        assert doc.entries[0].approved is False

    def test_redo_reapplies_approved(self, model_and_stack):
        model, stack, doc = model_and_stack
        idx = model.index(0, 6)
        model.setData(idx, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        model.undo()
        assert doc.entries[0].approved is False
        model.redo()
        assert doc.entries[0].approved is True

    def test_multiple_edits_undo_in_order(self, model_and_stack):
        model, stack, doc = model_and_stack
        idx0 = model.index(0, 5)
        idx1 = model.index(1, 5)
        model.setData(idx0, "First", Qt.ItemDataRole.EditRole)
        model.setData(idx1, "Second", Qt.ItemDataRole.EditRole)
        # Undo second edit
        model.undo()
        assert doc.entries[1].translation == "Sayonara"
        assert doc.entries[0].translation == "First"
        # Undo first edit
        model.undo()
        assert doc.entries[0].translation == "Konnichiwa"

    def test_edited_signal_emitted_on_undo(self, model_and_stack):
        model, stack, doc = model_and_stack
        edits = []
        model.edited.connect(lambda row: edits.append(row))
        idx = model.index(0, 5)
        model.setData(idx, "Changed", Qt.ItemDataRole.EditRole)
        edits.clear()
        model.undo()
        assert 0 in edits

    def test_edited_signal_emitted_on_redo(self, model_and_stack):
        model, stack, doc = model_and_stack
        edits = []
        model.edited.connect(lambda row: edits.append(row))
        idx = model.index(0, 5)
        model.setData(idx, "Changed", Qt.ItemDataRole.EditRole)
        model.undo()
        edits.clear()
        model.redo()
        assert 0 in edits

    def test_undo_does_not_push_new_command(self, model_and_stack):
        """Undoing should not add a new command to the stack."""
        model, stack, doc = model_and_stack
        idx = model.index(0, 5)
        model.setData(idx, "Edit1", Qt.ItemDataRole.EditRole)
        model.setData(idx, "Edit2", Qt.ItemDataRole.EditRole)
        # 2 commands on stack
        model.undo()  # undo Edit2
        model.undo()  # undo Edit1
        assert not stack.can_undo
        # Redo should still be available for both
        assert stack.can_redo
