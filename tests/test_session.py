"""Tests for the session persistence module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stx.model import Document, Entry
from stx.session import SessionManager, _file_hash
from stx.translate.runner import SheetSummary, StatusEntry


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Return a temporary sessions directory."""
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def mgr(session_dir: Path) -> SessionManager:
    """Return a SessionManager backed by the temp directory."""
    return SessionManager(sessions_dir=session_dir)


@pytest.fixture
def sample_state(tmp_path: Path):
    """Return a minimal mock AppState-like object."""

    class FakeState:
        pass

    state = FakeState()
    state.document = Document(
        language="Japanese",
        language_code="ja",
        stf_type="Bilingual",
        translation_type="Metadata",
        entries=[
            Entry(key="CustomLabel.Greeting", label="Hello", translation="Konnichiwa", approved=True),
            Entry(key="CustomLabel.Farewell", label="Goodbye", translation="", approved=False),
            Entry(key="ButtonOrLink.Save", label="Save", translation="Hozon", approved=False),
        ],
    )
    source = tmp_path / "input.stf"
    source.write_text("dummy", encoding="utf-8")
    state.source_stf_path = source
    state.target_language_code = "ja"
    state.target_language_name = "Japanese"
    state.source_language_code = "en"
    state.backend_key = "google"
    state.scope_path = None
    state.glossary_path = tmp_path / "glossary.csv"
    state.memory_path = None
    state.translation_summaries = [
        SheetSummary(
            sheet_name="CustomLabel_Translated",
            total_rows=10,
            translated_rows=8,
            skipped_rows=2,
            cached_rows=3,
            deduped_rows=1,
        ),
    ]
    state.translation_statuses = [
        StatusEntry(
            sheet_name="CustomLabel_Translated",
            row_index=0,
            key="CustomLabel.Greeting",
            label="Hello",
            translation="Konnichiwa",
            status="Translated",
        ),
    ]
    state.phase_status = [0, 0, 2, 0, 0, 0]
    return state


class TestSaveLoadRoundTrip:
    """Test that save/load preserves all important fields."""

    def test_document_entries_preserved(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        doc = data["document"]
        assert doc is not None
        assert len(doc.entries) == 3
        assert doc.entries[0].key == "CustomLabel.Greeting"
        assert doc.entries[0].label == "Hello"
        assert doc.entries[0].translation == "Konnichiwa"
        assert doc.entries[0].approved is True
        assert doc.entries[1].translation == ""
        assert doc.entries[1].approved is False

    def test_language_fields_preserved(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        assert data["target_language_code"] == "ja"
        assert data["target_language_name"] == "Japanese"
        assert data["source_language_code"] == "en"
        assert data["backend_key"] == "google"

    def test_document_metadata_preserved(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        doc = data["document"]
        assert doc.language == "Japanese"
        assert doc.language_code == "ja"
        assert doc.stf_type == "Bilingual"
        assert doc.translation_type == "Metadata"

    def test_phase_status_preserved(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        assert data["phase_status"] == [0, 0, 2, 0, 0, 0]

    def test_translation_summaries_preserved(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        summaries = data["translation_summaries"]
        assert len(summaries) == 1
        assert summaries[0].sheet_name == "CustomLabel_Translated"
        assert summaries[0].total_rows == 10
        assert summaries[0].translated_rows == 8
        assert summaries[0].cached_rows == 3

    def test_translation_statuses_preserved(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        statuses = data["translation_statuses"]
        assert len(statuses) == 1
        assert statuses[0].key == "CustomLabel.Greeting"
        assert statuses[0].translation == "Konnichiwa"
        assert statuses[0].status == "Translated"

    def test_resource_paths_preserved(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        assert data["scope_path"] is None
        assert data["glossary_path"] == str(tmp_path / "glossary.csv")
        assert data["memory_path"] is None


class TestSessionIsolation:
    """Test that different source paths produce different sessions."""

    def test_different_paths_different_auto_save(self, mgr, tmp_path):
        path_a = tmp_path / "file_a.stf"
        path_b = tmp_path / "file_b.stf"
        path_a.write_text("a", encoding="utf-8")
        path_b.write_text("b", encoding="utf-8")

        auto_a = mgr.auto_save_path(path_a)
        auto_b = mgr.auto_save_path(path_b)

        assert auto_a != auto_b

    def test_same_path_same_auto_save(self, mgr, tmp_path):
        path = tmp_path / "file.stf"
        path.write_text("x", encoding="utf-8")

        assert mgr.auto_save_path(path) == mgr.auto_save_path(path)


class TestAutoSavePathDeterministic:
    """Test that auto_save_path is deterministic."""

    def test_deterministic(self, tmp_path):
        mgr1 = SessionManager(sessions_dir=tmp_path / "s1")
        mgr2 = SessionManager(sessions_dir=tmp_path / "s2")

        path = tmp_path / "source.stf"
        path.write_text("content", encoding="utf-8")

        # Same source_path should produce same filename (different dir)
        assert mgr1.auto_save_path(path).name == mgr2.auto_save_path(path).name


class TestClearSession:
    """Test clear_session removes the session file."""

    def test_clear_removes_file(self, mgr, sample_state, tmp_path):
        source = sample_state.source_stf_path
        save_path = mgr.auto_save_path(source)
        mgr.save(sample_state, save_path)

        assert mgr.has_session(source)
        mgr.clear_session(source)
        assert not mgr.has_session(source)
        assert not save_path.exists()

    def test_clear_nonexistent_is_noop(self, mgr, tmp_path):
        path = tmp_path / "nonexistent.stf"
        # Should not raise
        mgr.clear_session(path)


class TestClearAllSessions:
    """Test clear_all_sessions empties the sessions directory."""

    def test_clear_all(self, mgr, sample_state, session_dir):
        source = sample_state.source_stf_path
        save_path = mgr.auto_save_path(source)
        mgr.save(sample_state, save_path)

        assert save_path.exists()
        mgr.clear_all_sessions()
        assert not session_dir.exists()


class TestVersionField:
    """Test version field is included and validated."""

    def test_version_included(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)

        with open(proj_path, encoding="utf-8") as f:
            raw = json.load(f)
        assert raw["version"] == 1

    def test_load_validates_version(self, mgr, tmp_path):
        proj_path = tmp_path / "bad.stxproj"
        proj_path.write_text(json.dumps({"version": 99}), encoding="utf-8")

        with pytest.raises(ValueError, match="Incompatible session file version"):
            mgr.load(proj_path)

    def test_load_rejects_missing_version(self, mgr, tmp_path):
        proj_path = tmp_path / "no_version.stxproj"
        proj_path.write_text(json.dumps({"source_file_path": "/x"}), encoding="utf-8")

        with pytest.raises(ValueError, match="Incompatible session file version"):
            mgr.load(proj_path)

    def test_load_rejects_non_dict(self, mgr, tmp_path):
        proj_path = tmp_path / "list.stxproj"
        proj_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        with pytest.raises(ValueError, match="root is not a JSON object"):
            mgr.load(proj_path)


class TestOptionalFields:
    """Test handling of None/Optional fields."""

    def test_none_document(self, mgr, tmp_path):
        class MinimalState:
            document = None
            source_stf_path = tmp_path / "src.stf"
            target_language_code = "ja"
            target_language_name = "Japanese"
            source_language_code = "en"
            backend_key = "google"
            scope_path = None
            glossary_path = None
            memory_path = None
            translation_summaries = []
            translation_statuses = []
            phase_status = [0, 0, 0, 0, 0, 0]

        MinimalState.source_stf_path.write_text("x", encoding="utf-8")

        proj_path = tmp_path / "minimal.stxproj"
        mgr.save(MinimalState(), proj_path)
        data = mgr.load(proj_path)

        assert data["document"] is None
        assert data["scope_path"] is None
        assert data["glossary_path"] is None
        assert data["memory_path"] is None

    def test_empty_summaries_and_statuses(self, mgr, tmp_path):
        class EmptyState:
            document = Document(entries=[])
            source_stf_path = tmp_path / "src.stf"
            target_language_code = "ja"
            target_language_name = "Japanese"
            source_language_code = "en"
            backend_key = "google"
            scope_path = None
            glossary_path = None
            memory_path = None
            translation_summaries = []
            translation_statuses = []
            phase_status = [0, 0, 0, 0, 0, 0]

        EmptyState.source_stf_path.write_text("x", encoding="utf-8")

        proj_path = tmp_path / "empty.stxproj"
        mgr.save(EmptyState(), proj_path)
        data = mgr.load(proj_path)

        assert data["translation_summaries"] == []
        assert data["translation_statuses"] == []


class TestUndoCommandsSerialization:
    """Test undo commands serialization."""

    def test_empty_undo_list(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        assert data["undo_commands"] == []

    def test_undo_commands_with_data(self, mgr, sample_state, tmp_path):
        from stx.gui.undo import UndoCommand

        # Add undo commands to the state
        sample_state._undo_commands = [
            UndoCommand(row=0, column=2, old_value="old_text", new_value="new_text"),
            UndoCommand(row=1, column=3, old_value=False, new_value=True),
        ]

        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        assert len(data["undo_commands"]) == 2
        assert data["undo_commands"][0]["row"] == 0
        assert data["undo_commands"][0]["column"] == 2
        assert data["undo_commands"][0]["old_value"] == "old_text"
        assert data["undo_commands"][0]["new_value"] == "new_text"
        assert data["undo_commands"][1]["row"] == 1
        assert data["undo_commands"][1]["new_value"] is True


class TestHasSession:
    """Test has_session correctly detects existing sessions."""

    def test_returns_false_when_no_session(self, mgr, tmp_path):
        path = tmp_path / "nosession.stf"
        path.write_text("x", encoding="utf-8")
        assert not mgr.has_session(path)

    def test_returns_true_after_save(self, mgr, sample_state):
        source = sample_state.source_stf_path
        save_path = mgr.auto_save_path(source)
        mgr.save(sample_state, save_path)
        assert mgr.has_session(source)


class TestFileHashIsolation:
    """Test that the file_hash field correctly isolates sessions by path."""

    def test_hash_in_saved_file(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)

        with open(proj_path, encoding="utf-8") as f:
            raw = json.load(f)

        expected_hash = _file_hash(sample_state.source_stf_path)
        assert raw["file_hash"] == expected_hash

    def test_file_not_found_raises(self, mgr, tmp_path):
        path = tmp_path / "does_not_exist.stxproj"
        with pytest.raises(FileNotFoundError):
            mgr.load(path)


class TestTimestamps:
    """Test created_at and updated_at handling."""

    def test_timestamps_present(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)
        data = mgr.load(proj_path)

        assert data["created_at"] != ""
        assert data["updated_at"] != ""

    def test_created_at_preserved_on_overwrite(self, mgr, sample_state, tmp_path):
        proj_path = tmp_path / "test.stxproj"
        mgr.save(sample_state, proj_path)

        data1 = mgr.load(proj_path)
        created1 = data1["created_at"]

        # Save again
        mgr.save(sample_state, proj_path)
        data2 = mgr.load(proj_path)

        assert data2["created_at"] == created1
