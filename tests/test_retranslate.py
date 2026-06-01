"""Tests for the retranslate_existing feature (Feature 11)."""

from __future__ import annotations

import pytest

from stx.model import Document, Entry
from stx.translate import translate_document
from stx.translate.base import Translator
from stx.translate.runner import TranslationResult


# ---------------------------------------------------------------------------
# Fake translator that uppercases the label
# ---------------------------------------------------------------------------


class _UpperTranslator(Translator):
    """Deterministic fake: translates by uppercasing the source text."""

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        return text.upper()


def _make_doc(entries: list[Entry]) -> Document:
    return Document(
        language="Japanese",
        language_code="ja",
        stf_type="Bilingual",
        translation_type="",
        entries=entries,
    )


# ---------------------------------------------------------------------------
# Tests: retranslate_existing=False (default) skips already-translated rows
# ---------------------------------------------------------------------------


class TestRetranslateExistingFalse:
    """Verify the default behaviour: rows with translations are skipped."""

    def test_skips_already_translated(self) -> None:
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation="Existing"),
            Entry(key="k2", label="World", translation=""),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=False,
        )
        # k1 should keep its existing translation
        assert doc.entries[0].translation == "Existing"
        # k2 should be translated
        assert doc.entries[1].translation == "WORLD"
        assert result.translated_count == 1
        assert result.skipped_count == 1
        assert result.retranslated_count == 0

    def test_all_translated_all_skipped(self) -> None:
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation="Hola"),
            Entry(key="k2", label="World", translation="Mundo"),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=False,
        )
        assert doc.entries[0].translation == "Hola"
        assert doc.entries[1].translation == "Mundo"
        assert result.translated_count == 0
        assert result.skipped_count == 2
        assert result.retranslated_count == 0


# ---------------------------------------------------------------------------
# Tests: retranslate_existing=True retranslates already-translated rows
# ---------------------------------------------------------------------------


class TestRetranslateExistingTrue:
    """Verify retranslate_existing=True causes retranslation of existing rows."""

    def test_retranslates_existing(self) -> None:
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation="Old translation"),
            Entry(key="k2", label="World", translation=""),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=True,
        )
        # Both should be translated via the uppercase translator
        assert doc.entries[0].translation == "HELLO"
        assert doc.entries[1].translation == "WORLD"
        assert result.translated_count == 2
        assert result.skipped_count == 0
        # Only k1 was retranslated (it had existing translation)
        assert result.retranslated_count == 1

    def test_all_retranslated(self) -> None:
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation="Hola"),
            Entry(key="k2", label="World", translation="Mundo"),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=True,
        )
        assert doc.entries[0].translation == "HELLO"
        assert doc.entries[1].translation == "WORLD"
        assert result.translated_count == 2
        assert result.skipped_count == 0
        assert result.retranslated_count == 2

    def test_blank_label_still_skipped(self) -> None:
        """Rows with blank labels are always skipped regardless of retranslate_existing."""
        doc = _make_doc([
            Entry(key="k1", label="", translation="Something"),
            Entry(key="k2", label="Hello", translation="Old"),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=True,
        )
        # Blank label row is skipped even with retranslate_existing=True
        assert doc.entries[0].translation == "Something"
        assert doc.entries[1].translation == "HELLO"
        assert result.skipped_count == 1
        assert result.retranslated_count == 1


# ---------------------------------------------------------------------------
# Tests: imported_translations takes priority over retranslation
# ---------------------------------------------------------------------------


class TestImportedPriorityWithRetranslate:
    """Imported translations should win even when retranslate_existing=True."""

    def test_imported_takes_priority(self) -> None:
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation="Old translation"),
            Entry(key="k2", label="World", translation="Old world"),
            Entry(key="k3", label="Foo", translation="Old foo"),
        ])
        imported = {"Hello": "Imported Hello", "World": "Imported World"}
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=True,
            imported_translations=imported,
        )
        # k1 and k2 get imported translations (highest priority)
        assert doc.entries[0].translation == "Imported Hello"
        assert doc.entries[1].translation == "Imported World"
        # k3 has no imported match, so it goes through the translator
        assert doc.entries[2].translation == "FOO"
        assert result.imported_reuse_count == 2
        # All 3 had existing translations and were retranslated
        assert result.retranslated_count == 3

    def test_imported_priority_without_retranslate(self) -> None:
        """When retranslate_existing=False but row has no translation, imported still works."""
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation=""),
            Entry(key="k2", label="World", translation="Existing"),
        ])
        imported = {"Hello": "Imported Hello", "World": "Imported World"}
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=False,
            imported_translations=imported,
        )
        # k1 has no translation, so it goes through translate_one -> imported wins
        assert doc.entries[0].translation == "Imported Hello"
        # k2 is already translated and retranslate_existing=False, so it stays
        assert doc.entries[1].translation == "Existing"
        assert result.imported_reuse_count == 1
        assert result.skipped_count == 1


# ---------------------------------------------------------------------------
# Tests: retranslated_count tracking
# ---------------------------------------------------------------------------


class TestRetranslatedCount:
    """Verify retranslated_count is correctly tracked in various scenarios."""

    def test_mixed_scenario(self) -> None:
        """Some rows translated, some not - all get processed with retranslate."""
        doc = _make_doc([
            Entry(key="k1", label="Alpha", translation="Old Alpha"),
            Entry(key="k2", label="Beta", translation=""),
            Entry(key="k3", label="Gamma", translation="Old Gamma"),
            Entry(key="k4", label="Delta", translation=""),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=True,
        )
        assert doc.entries[0].translation == "ALPHA"
        assert doc.entries[1].translation == "BETA"
        assert doc.entries[2].translation == "GAMMA"
        assert doc.entries[3].translation == "DELTA"
        assert result.translated_count == 4
        # Only k1 and k3 had existing translations
        assert result.retranslated_count == 2
        assert result.skipped_count == 0

    def test_retranslated_count_zero_when_disabled(self) -> None:
        """retranslated_count is 0 when retranslate_existing=False."""
        doc = _make_doc([
            Entry(key="k1", label="Alpha", translation="Old"),
            Entry(key="k2", label="Beta", translation=""),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=False,
        )
        assert result.retranslated_count == 0

    def test_retranslated_count_with_dedup(self) -> None:
        """Deduped rows that had existing translations also count."""
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation="Old1"),
            Entry(key="k2", label="Hello", translation="Old2"),
            Entry(key="k3", label="World", translation=""),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=True,
        )
        assert doc.entries[0].translation == "HELLO"
        assert doc.entries[1].translation == "HELLO"
        assert doc.entries[2].translation == "WORLD"
        assert result.translated_count == 3
        # k1 and k2 both had existing translations
        assert result.retranslated_count == 2


# ---------------------------------------------------------------------------
# Tests: clearing a row's translation makes it eligible for retranslation
# ---------------------------------------------------------------------------


class TestClearForRetranslation:
    """Verify that clearing a translation makes the row translatable on next run."""

    def test_cleared_row_gets_translated(self) -> None:
        """After clearing translation, the row is translated on next run."""
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation="Existing"),
            Entry(key="k2", label="World", translation="Also existing"),
        ])
        # Simulate clearing k1's translation (as Phase 4 does)
        doc.entries[0] = Entry(
            key="k1", label="Hello", translation="", approved=False
        )
        # Now run with default retranslate_existing=False
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=False,
        )
        # k1 was cleared, so it should be translated now
        assert doc.entries[0].translation == "HELLO"
        # k2 still has its existing translation
        assert doc.entries[1].translation == "Also existing"
        assert result.translated_count == 1
        assert result.skipped_count == 1

    def test_cleared_row_with_retranslate_all(self) -> None:
        """With retranslate_existing=True, both cleared and existing rows get translated."""
        doc = _make_doc([
            Entry(key="k1", label="Hello", translation=""),  # cleared
            Entry(key="k2", label="World", translation="Existing"),
        ])
        result = translate_document(
            doc,
            _UpperTranslator(),
            source_lang="en",
            target_lang="ja",
            workers=1,
            rate_limit_per_second=None,
            prevent_system_sleep=False,
            retranslate_existing=True,
        )
        assert doc.entries[0].translation == "HELLO"
        assert doc.entries[1].translation == "WORLD"
        assert result.translated_count == 2
        # Only k2 counts as retranslated (k1 was already empty)
        assert result.retranslated_count == 1


# ---------------------------------------------------------------------------
# Tests: TranslationResult dataclass fields
# ---------------------------------------------------------------------------


class TestTranslationResultFields:
    """Verify TranslationResult has the retranslated_count field."""

    def test_result_has_retranslated_count(self) -> None:
        result = TranslationResult(document=_make_doc([]))
        assert hasattr(result, "retranslated_count")
        assert result.retranslated_count == 0

    def test_result_retranslated_count_set(self) -> None:
        result = TranslationResult(document=_make_doc([]), retranslated_count=5)
        assert result.retranslated_count == 5
