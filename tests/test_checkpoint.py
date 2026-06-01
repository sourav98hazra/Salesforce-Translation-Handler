"""Tests for checkpoint-based translation resume."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stx.checkpoint import CheckpointStore
from stx.memory import TranslationMemory
from stx.model import Document, Entry
from stx.translate import translate_document
from stx.translate.base import Translator


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class CountingTranslator(Translator):
    """Test double that counts calls and returns a deterministic translation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        self.calls.append((text, source_lang, target_lang))
        return f"<{target_lang}>{text}</{target_lang}>"


def _make_doc(n: int = 5) -> Document:
    """Create a document with n untranslated entries."""
    entries = [
        Entry(key=f"CustomLabel.Row{i}", label=f"Label {i}")
        for i in range(n)
    ]
    return Document(language="Japanese", language_code="ja", entries=entries)


# ---------------------------------------------------------------------------
# Unit tests: CheckpointStore
# ---------------------------------------------------------------------------

class TestCheckpointStore:
    """Unit tests for CheckpointStore save/load/clear/exists."""

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        store = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        store.save_progress(0, "Key.A", "Translation A", "Translated")
        store.save_progress(3, "Key.D", "Translation D", "Translated (TM hit)")

        # Load in a fresh instance
        store2 = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        data = store2.load()
        assert 0 in data
        assert data[0]["key"] == "Key.A"
        assert data[0]["translation"] == "Translation A"
        assert data[0]["status"] == "Translated"
        assert 3 in data
        assert data[3]["key"] == "Key.D"
        assert data[3]["translation"] == "Translation D"

    def test_clear_removes_file(self, tmp_path: Path) -> None:
        store = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        store.save_progress(0, "Key.A", "T", "Translated")
        assert store.exists()
        store.clear()
        assert not store.exists()
        assert not store.path.is_file()

    def test_exists_false_when_no_file(self, tmp_path: Path) -> None:
        store = CheckpointStore("nonexistent.xlsx", "fr", checkpoint_dir=tmp_path)
        assert not store.exists()

    def test_load_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        store = CheckpointStore("missing.xlsx", "de", checkpoint_dir=tmp_path)
        assert store.load() == {}

    def test_atomic_write_file_exists_after_save(self, tmp_path: Path) -> None:
        store = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        store.save_progress(1, "Key.B", "Trans B", "Translated")
        # File should exist and be valid JSON
        assert store.path.is_file()
        with open(store.path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 1
        assert data["source_file"] == "test.xlsx"
        assert data["target_lang"] == "ja"
        assert "1" in data["entries"]

    def test_version_field_present(self, tmp_path: Path) -> None:
        store = CheckpointStore("v.xlsx", "ko", checkpoint_dir=tmp_path)
        store.save_progress(0, "K", "T", "S")
        with open(store.path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 1

    def test_same_run_id_for_same_params(self, tmp_path: Path) -> None:
        s1 = CheckpointStore("input.xlsx", "ja", checkpoint_dir=tmp_path)
        s2 = CheckpointStore("input.xlsx", "ja", checkpoint_dir=tmp_path)
        assert s1.path == s2.path

    def test_different_run_id_for_different_params(self, tmp_path: Path) -> None:
        s1 = CheckpointStore("input.xlsx", "ja", checkpoint_dir=tmp_path)
        s2 = CheckpointStore("input.xlsx", "fr", checkpoint_dir=tmp_path)
        assert s1.path != s2.path

    def test_load_ignores_invalid_json(self, tmp_path: Path) -> None:
        store = CheckpointStore("bad.xlsx", "ja", checkpoint_dir=tmp_path)
        store._dir.mkdir(parents=True, exist_ok=True)
        store.path.write_text("not valid json", encoding="utf-8")
        assert store.load() == {}

    def test_load_ignores_wrong_version(self, tmp_path: Path) -> None:
        store = CheckpointStore("ver.xlsx", "ja", checkpoint_dir=tmp_path)
        store._dir.mkdir(parents=True, exist_ok=True)
        store.path.write_text(json.dumps({"version": 99, "entries": {"0": {"key": "x"}}}), encoding="utf-8")
        assert store.load() == {}


# ---------------------------------------------------------------------------
# Integration tests: runner + checkpoint
# ---------------------------------------------------------------------------

class TestRunnerCheckpointResume:
    """Test that the runner resumes from checkpoint (skips already-translated rows)."""

    def test_runner_resumes_from_checkpoint(self, tmp_path: Path) -> None:
        """Rows present in checkpoint are not sent to the translator."""
        doc = _make_doc(5)
        translator = CountingTranslator()

        # Pre-populate a checkpoint with entries at indices 0, 2, 4.
        store = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        store.save_progress(0, "CustomLabel.Row0", "<ja>Label 0</ja>", "Translated")
        store.save_progress(2, "CustomLabel.Row2", "<ja>Label 2</ja>", "Translated")
        store.save_progress(4, "CustomLabel.Row4", "<ja>Label 4</ja>", "Translated")

        # Run with checkpoint -- only rows 1 and 3 should hit the translator.
        cp = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        result = translate_document(
            doc, translator,
            source_lang="en", target_lang="ja",
            checkpoint=cp,
            workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
        )

        # Only 2 rows should have been sent to the translator.
        assert len(translator.calls) == 2
        assert result.resumed_count == 3
        # Total translated includes both resumed and freshly translated.
        assert result.translated_count == 5

        # Verify the resumed entries have correct translations.
        assert doc.entries[0].translation == "<ja>Label 0</ja>"
        assert doc.entries[2].translation == "<ja>Label 2</ja>"
        assert doc.entries[4].translation == "<ja>Label 4</ja>"
        # Freshly translated
        assert doc.entries[1].translation == "<ja>Label 1</ja>"
        assert doc.entries[3].translation == "<ja>Label 3</ja>"

    def test_runner_clears_checkpoint_on_success(self, tmp_path: Path) -> None:
        """On successful completion, checkpoint file is removed."""
        doc = _make_doc(3)
        translator = CountingTranslator()

        store = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        store.save_progress(0, "CustomLabel.Row0", "<ja>Label 0</ja>", "Translated")

        cp = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        assert cp.exists()

        translate_document(
            doc, translator,
            source_lang="en", target_lang="ja",
            checkpoint=cp,
            workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
        )

        # Checkpoint should be cleared after successful run.
        assert not cp.exists()

    def test_checkpoint_persists_during_translation(self, tmp_path: Path) -> None:
        """Each translated row is checkpointed so progress is preserved."""
        doc = _make_doc(3)
        translator = CountingTranslator()

        cp = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        translate_document(
            doc, translator,
            source_lang="en", target_lang="ja",
            checkpoint=cp,
            workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
        )

        # After successful completion, checkpoint is cleared.
        # But let's verify the mechanism works by checking a cancelled run.
        doc2 = _make_doc(5)
        call_count = [0]

        class InterruptingTranslator(Translator):
            def translate(self, text, source_lang, target_lang):
                call_count[0] += 1
                return f"<{target_lang}>{text}</{target_lang}>"

        # Translate with cancel after 2 rows
        cancel_after = 2
        translated_so_far = [0]

        def cancel_fn():
            return translated_so_far[0] >= cancel_after

        def on_progress(event):
            if "Translated" in event.status:
                translated_so_far[0] += 1

        cp2 = CheckpointStore("test2.xlsx", "ja", checkpoint_dir=tmp_path)
        translate_document(
            doc2, InterruptingTranslator(),
            source_lang="en", target_lang="ja",
            checkpoint=cp2,
            progress=on_progress,
            cancel=cancel_fn,
            workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
        )

        # Checkpoint should still exist because run was cancelled.
        assert cp2.exists()
        data = cp2.load()
        # At least the translated rows should be checkpointed.
        assert len(data) >= 1

    def test_checkpoint_integrates_with_tm(self, tmp_path: Path) -> None:
        """Checkpointed rows skip both TM and translator -- no re-billing."""
        doc = _make_doc(3)
        translator = CountingTranslator()
        tm = TranslationMemory(path=tmp_path / "tm.sqlite")

        # Pre-populate checkpoint for row 0
        store = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        store.save_progress(0, "CustomLabel.Row0", "Cached from checkpoint", "Translated")

        # Pre-populate TM for row 1
        tm.put("Label 1", "en", "ja", "From TM")

        cp = CheckpointStore("test.xlsx", "ja", checkpoint_dir=tmp_path)
        result = translate_document(
            doc, translator,
            source_lang="en", target_lang="ja",
            checkpoint=cp,
            memory=tm,
            workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
        )

        # Row 0: from checkpoint (no translator, no TM lookup).
        # Row 1: from TM (no translator call).
        # Row 2: from translator.
        assert len(translator.calls) == 1  # only row 2
        assert result.resumed_count == 1
        assert result.cached_count == 1
        assert doc.entries[0].translation == "Cached from checkpoint"
        assert doc.entries[1].translation == "From TM"
