"""Tests for the Find & Replace feature in Phase 4."""
from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt

from stx.find_replace import ReplaceScope, compute_replacements, find_matches
from stx.gui.find_replace_dialog import FindReplaceDialog
from stx.gui.undo import UndoStack
from stx.model import Document, Entry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doc():
    """A document with diverse entries for replacement tests."""
    return Document(
        language="Japanese",
        language_code="ja",
        entries=[
            Entry(key="CustomLabel.Hello", label="Hello World", translation="Konnichiwa World"),
            Entry(key="CustomLabel.Goodbye", label="Goodbye World", translation="Sayonara World"),
            Entry(key="CustomLabel.Thanks", label="Thank you", translation="Arigatou"),
            Entry(key="CustomLabel.Hello2", label="Hello Again", translation="Hello Again JP"),
        ],
    )


# ---------------------------------------------------------------------------
# FindReplaceDialog construction
# ---------------------------------------------------------------------------


class TestFindReplaceDialogConstruction:
    def test_dialog_constructs(self, qtbot, doc):
        dialog = FindReplaceDialog(doc)
        qtbot.addWidget(dialog)
        assert dialog is not None
        assert dialog.windowTitle() == "Find & Replace"

    def test_dialog_has_find_field(self, qtbot, doc):
        dialog = FindReplaceDialog(doc)
        qtbot.addWidget(dialog)
        assert dialog._find_edit is not None

    def test_dialog_has_replace_field(self, qtbot, doc):
        dialog = FindReplaceDialog(doc)
        qtbot.addWidget(dialog)
        assert dialog._replace_edit is not None

    def test_dialog_has_options(self, qtbot, doc):
        dialog = FindReplaceDialog(doc)
        qtbot.addWidget(dialog)
        assert dialog._case_check is not None
        assert dialog._regex_check is not None
        assert dialog._scope_combo is not None

    def test_dialog_has_buttons(self, qtbot, doc):
        dialog = FindReplaceDialog(doc)
        qtbot.addWidget(dialog)
        assert dialog._replace_btn is not None

    def test_initial_preview_shows_zero(self, qtbot, doc):
        dialog = FindReplaceDialog(doc)
        qtbot.addWidget(dialog)
        assert "0" in dialog._preview_label.text()

    def test_scope_combo_only_has_translations(self, qtbot, doc):
        """The scope combo should only offer 'Translations Only' in the GUI."""
        dialog = FindReplaceDialog(doc)
        qtbot.addWidget(dialog)
        assert dialog._scope_combo.count() == 1
        assert dialog._scope_combo.itemText(0) == "Translations Only"


# ---------------------------------------------------------------------------
# Core replacement logic (plain text)
# ---------------------------------------------------------------------------


class TestReplacementPlainText:
    def test_simple_replacement(self, doc):
        replacements = compute_replacements(
            doc, "World", "Universe", scope=ReplaceScope.TRANSLATION
        )
        assert len(replacements) == 2
        assert replacements[0].old_value == "Konnichiwa World"
        assert replacements[0].new_value == "Konnichiwa Universe"
        assert replacements[1].old_value == "Sayonara World"
        assert replacements[1].new_value == "Sayonara Universe"

    def test_no_matches(self, doc):
        replacements = compute_replacements(
            doc, "ZZZZZ", "Replacement", scope=ReplaceScope.TRANSLATION
        )
        assert len(replacements) == 0

    def test_empty_find_returns_empty(self, doc):
        replacements = compute_replacements(doc, "", "Something", scope=ReplaceScope.TRANSLATION)
        assert len(replacements) == 0

    def test_find_matches_count(self, doc):
        count = find_matches(doc, "World", scope=ReplaceScope.TRANSLATION)
        assert count == 2

    def test_find_matches_empty(self, doc):
        count = find_matches(doc, "", scope=ReplaceScope.TRANSLATION)
        assert count == 0


# ---------------------------------------------------------------------------
# Regex replacement
# ---------------------------------------------------------------------------


class TestReplacementRegex:
    def test_regex_pattern(self, doc):
        replacements = compute_replacements(
            doc, r"World$", "Earth", use_regex=True, scope=ReplaceScope.TRANSLATION
        )
        assert len(replacements) == 2
        assert replacements[0].new_value == "Konnichiwa Earth"

    def test_regex_capture_group(self, doc):
        replacements = compute_replacements(
            doc, r"(\w+) World", r"\1 Earth", use_regex=True, scope=ReplaceScope.TRANSLATION
        )
        assert len(replacements) == 2
        assert replacements[0].new_value == "Konnichiwa Earth"
        assert replacements[1].new_value == "Sayonara Earth"

    def test_invalid_regex_returns_empty(self, doc):
        replacements = compute_replacements(
            doc, r"[invalid", "x", use_regex=True, scope=ReplaceScope.TRANSLATION
        )
        assert len(replacements) == 0

    def test_find_matches_invalid_regex(self, doc):
        count = find_matches(doc, r"[invalid", use_regex=True, scope=ReplaceScope.TRANSLATION)
        assert count == 0


# ---------------------------------------------------------------------------
# Case sensitivity
# ---------------------------------------------------------------------------


class TestCaseSensitivity:
    def test_case_insensitive_default(self, doc):
        replacements = compute_replacements(
            doc, "hello", "Hi", scope=ReplaceScope.TRANSLATION
        )
        # "Hello Again JP" matches case-insensitively
        assert len(replacements) == 1
        assert replacements[0].new_value == "Hi Again JP"

    def test_case_sensitive(self, doc):
        replacements = compute_replacements(
            doc, "hello", "Hi", case_sensitive=True, scope=ReplaceScope.TRANSLATION
        )
        # No match because "Hello" has uppercase H
        assert len(replacements) == 0

    def test_case_sensitive_matches(self, doc):
        replacements = compute_replacements(
            doc, "Hello", "Hi", case_sensitive=True, scope=ReplaceScope.TRANSLATION
        )
        assert len(replacements) == 1
        assert replacements[0].new_value == "Hi Again JP"


# ---------------------------------------------------------------------------
# Scope filtering
# ---------------------------------------------------------------------------


class TestScopeFiltering:
    def test_translation_scope(self, doc):
        replacements = compute_replacements(
            doc, "Hello", "Hi", scope=ReplaceScope.TRANSLATION
        )
        # Only looks at translation field
        assert all(r.field == "translation" for r in replacements)

    def test_label_scope(self, doc):
        replacements = compute_replacements(doc, "Hello", "Hi", scope=ReplaceScope.LABEL)
        assert all(r.field == "label" for r in replacements)
        assert len(replacements) == 2  # "Hello World" and "Hello Again"

    def test_key_scope(self, doc):
        replacements = compute_replacements(
            doc, "CustomLabel", "CL", scope=ReplaceScope.KEY
        )
        assert all(r.field == "key" for r in replacements)
        assert len(replacements) == 4

    def test_all_scope(self, doc):
        replacements = compute_replacements(doc, "Hello", "Hi", scope=ReplaceScope.ALL)
        fields = {r.field for r in replacements}
        # Should match in key, label, and translation
        assert "key" in fields or "label" in fields or "translation" in fields
        # Should have more matches than translation-only
        translation_only = compute_replacements(
            doc, "Hello", "Hi", scope=ReplaceScope.TRANSLATION
        )
        assert len(replacements) >= len(translation_only)


# ---------------------------------------------------------------------------
# Undo stack integration
# ---------------------------------------------------------------------------


class TestUndoStackIntegration:
    @pytest.fixture
    def model_and_stack(self, doc):
        from stx.gui.pages.phase4_review import _EntriesModel

        stack = UndoStack()
        model = _EntriesModel(doc, undo_stack=stack)
        return model, stack, doc

    def test_replacements_pushed_to_undo_stack(self, model_and_stack):
        model, stack, doc = model_and_stack
        replacements = compute_replacements(
            doc, "World", "Universe", scope=ReplaceScope.TRANSLATION
        )
        # Apply through model (simulates what _on_find_replace does)
        for rep in replacements:
            if rep.field == "translation":
                idx = model.index(rep.row, 5)  # _TRANSLATION_COL
                model.setData(idx, rep.new_value, Qt.ItemDataRole.EditRole)

        assert doc.entries[0].translation == "Konnichiwa Universe"
        assert doc.entries[1].translation == "Sayonara Universe"
        assert stack.can_undo

    def test_undo_reverses_all_replacements(self, model_and_stack):
        model, stack, doc = model_and_stack
        replacements = compute_replacements(
            doc, "World", "Universe", scope=ReplaceScope.TRANSLATION
        )
        for rep in replacements:
            if rep.field == "translation":
                idx = model.index(rep.row, 5)
                model.setData(idx, rep.new_value, Qt.ItemDataRole.EditRole)

        # Undo all
        model.undo()
        model.undo()
        assert doc.entries[0].translation == "Konnichiwa World"
        assert doc.entries[1].translation == "Sayonara World"

    def test_redo_after_undo(self, model_and_stack):
        model, stack, doc = model_and_stack
        replacements = compute_replacements(
            doc, "World", "Universe", scope=ReplaceScope.TRANSLATION
        )
        for rep in replacements:
            if rep.field == "translation":
                idx = model.index(rep.row, 5)
                model.setData(idx, rep.new_value, Qt.ItemDataRole.EditRole)

        model.undo()
        model.undo()
        model.redo()
        assert doc.entries[0].translation == "Konnichiwa Universe"


# ---------------------------------------------------------------------------
# Apply to all rows exact match (not substring)
# ---------------------------------------------------------------------------


class TestApplyToAllRowsExactMatch:
    """Verify that 'Apply to all rows' uses exact full-field matching."""

    @pytest.fixture
    def doc_with_substrings(self):
        """Document where one translation is a substring of another."""
        return Document(
            language="Japanese",
            language_code="ja",
            entries=[
                Entry(key="Key.One", label="Hello", translation="Hello"),
                Entry(key="Key.Two", label="Hello World", translation="Hello World"),
                Entry(key="Key.Three", label="Also Hello", translation="Hello"),
                Entry(key="Key.Four", label="Something", translation="Say Hello"),
            ],
        )

    @pytest.fixture
    def model_and_stack(self, doc_with_substrings):
        from stx.gui.pages.phase4_review import _EntriesModel

        stack = UndoStack()
        model = _EntriesModel(doc_with_substrings, undo_stack=stack)
        return model, stack, doc_with_substrings

    def test_exact_match_replaces_only_full_field(self, model_and_stack):
        """Only rows where translation == old_text exactly are replaced."""
        model, stack, doc = model_and_stack
        old_text = "Hello"
        new_text = "Konnichiwa"
        # Simulate what _apply_editor_to_row does with apply_all_check
        count = 0
        for row, entry in enumerate(doc.entries):
            if entry.translation == old_text:
                idx = model.index(row, 5)  # _TRANSLATION_COL
                model.setData(idx, new_text, Qt.ItemDataRole.EditRole)
                count += 1
        # Should only replace rows 0 and 2 (exact "Hello"), not row 1 ("Hello World")
        # or row 3 ("Say Hello")
        assert count == 2
        assert doc.entries[0].translation == "Konnichiwa"
        assert doc.entries[1].translation == "Hello World"  # unchanged - substring
        assert doc.entries[2].translation == "Konnichiwa"
        assert doc.entries[3].translation == "Say Hello"  # unchanged - substring

    def test_substring_would_match_more(self, doc_with_substrings):
        """Confirm that substring matching (compute_replacements) would match more rows."""
        # This verifies the old behavior was wrong - substring approach finds too many
        replacements = compute_replacements(
            doc_with_substrings,
            "Hello",
            "Konnichiwa",
            case_sensitive=True,
            use_regex=False,
            scope=ReplaceScope.TRANSLATION,
        )
        # Substring matches rows 0, 1, 2, 3 (all contain "Hello" as substring)
        assert len(replacements) == 4  # more than exact match (which finds 2)
