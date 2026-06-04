"""Tests for the fuzzy translation memory module."""

from __future__ import annotations

from pathlib import Path

import pytest

from stx.fuzzy import FuzzyMatch, FuzzyMatcher
from stx.memory import TranslationMemory
from stx.model import Document, Entry
from stx.translate.runner import translate_document


# ---------------------------------------------------------------------------
# FuzzyMatcher unit tests
# ---------------------------------------------------------------------------


class TestFuzzyMatcher:
    """Direct tests on FuzzyMatcher.find_matches."""

    def test_similar_strings_score_high(self) -> None:
        matcher = FuzzyMatcher(threshold=75.0, max_results=5)
        candidates = [("Hello World", "X")]
        results = matcher.find_matches("Hello Worlds", candidates, "en", "ja")
        assert len(results) == 1
        assert results[0].score > 90
        assert results[0].source == "Hello World"
        assert results[0].translation == "X"

    def test_dissimilar_strings_score_low(self) -> None:
        matcher = FuzzyMatcher(threshold=75.0, max_results=5)
        candidates = [("Goodbye", "Y")]
        results = matcher.find_matches("Hello", candidates, "en", "ja")
        # "Hello" vs "Goodbye" should not meet the 75 threshold
        assert len(results) == 0

    def test_threshold_filtering(self) -> None:
        matcher = FuzzyMatcher(threshold=95.0, max_results=5)
        # "Hello World" vs "Hello Worlds" scores ~91-95 depending on algorithm
        # With threshold 95, might not pass - test filtering works
        candidates = [("Hello World", "X"), ("Something else", "Y")]
        results = matcher.find_matches("Hello World!", candidates, "en", "ja")
        # All results should be above threshold
        for r in results:
            assert r.score >= 95.0

    def test_max_results_limits_output(self) -> None:
        matcher = FuzzyMatcher(threshold=50.0, max_results=2)
        candidates = [
            ("Hello World", "A"),
            ("Hello Earth", "B"),
            ("Hello Planet", "C"),
            ("Hello Universe", "D"),
        ]
        results = matcher.find_matches("Hello World", candidates, "en", "ja")
        assert len(results) <= 2

    def test_empty_candidates_returns_empty(self) -> None:
        matcher = FuzzyMatcher(threshold=75.0, max_results=5)
        results = matcher.find_matches("Hello", [], "en", "ja")
        assert results == []

    def test_empty_query_returns_empty(self) -> None:
        matcher = FuzzyMatcher(threshold=75.0, max_results=5)
        results = matcher.find_matches("", [("Hello", "X")], "en", "ja")
        assert results == []

    def test_results_sorted_by_score_desc(self) -> None:
        matcher = FuzzyMatcher(threshold=50.0, max_results=10)
        candidates = [
            ("Save", "A"),
            ("Save As", "B"),
            ("Save All", "C"),
            ("Delete", "D"),
        ]
        results = matcher.find_matches("Save", candidates, "en", "ja")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_result_carries_language_codes(self) -> None:
        matcher = FuzzyMatcher(threshold=50.0, max_results=5)
        candidates = [("Hello", "Hola")]
        results = matcher.find_matches("Hello!", candidates, "en", "es")
        assert len(results) >= 1
        assert results[0].source_lang == "en"
        assert results[0].target_lang == "es"


# ---------------------------------------------------------------------------
# TranslationMemory integration tests
# ---------------------------------------------------------------------------


class TestTranslationMemoryFuzzy:
    """Tests for the fuzzy_search and all_sources methods on TranslationMemory."""

    def test_all_sources_returns_correct_pairs(self, tmp_path: Path) -> None:
        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        tm.put("Hello", "en", "ja", "Konnichiwa")
        tm.put("World", "en", "ja", "Sekai")
        tm.put("Bonjour", "fr", "en", "Hello")

        pairs = tm.all_sources("en", "ja")
        assert len(pairs) == 2
        assert ("Hello", "Konnichiwa") in pairs
        assert ("World", "Sekai") in pairs

    def test_all_sources_empty_for_missing_pair(self, tmp_path: Path) -> None:
        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        tm.put("Hello", "en", "ja", "Konnichiwa")
        pairs = tm.all_sources("en", "fr")
        assert pairs == []

    def test_fuzzy_search_returns_ranked_results(self, tmp_path: Path) -> None:
        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        tm.put("Hello World", "en", "ja", "Konnichiwa Sekai")
        tm.put("Hello Earth", "en", "ja", "Konnichiwa Chikyuu")
        tm.put("Goodbye", "en", "ja", "Sayonara")

        results = tm.fuzzy_search("Hello Worlds", "en", "ja", threshold=70.0)
        assert len(results) >= 1
        # "Hello World" should be the closest match
        assert results[0].source == "Hello World"
        assert results[0].translation == "Konnichiwa Sekai"
        assert results[0].score > 80

    def test_fuzzy_search_respects_threshold(self, tmp_path: Path) -> None:
        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        tm.put("Hello World", "en", "ja", "Konnichiwa Sekai")
        tm.put("Goodbye Cruel World", "en", "ja", "Sayonara")

        # Very high threshold - only very close matches
        results = tm.fuzzy_search("Hello World", "en", "ja", threshold=99.0)
        for r in results:
            assert r.score >= 99.0

    def test_fuzzy_search_empty_tm(self, tmp_path: Path) -> None:
        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        results = tm.fuzzy_search("Hello", "en", "ja")
        assert results == []


# ---------------------------------------------------------------------------
# Runner integration tests
# ---------------------------------------------------------------------------


class TestRunnerFuzzyIntegration:
    """Test that the runner uses fuzzy matches to avoid calling the translator."""

    def test_fuzzy_auto_accept_skips_translator(self, tmp_path: Path) -> None:
        """When fuzzy score >= auto_accept_threshold, translator should NOT be called."""
        from tests.conftest import MockTranslator

        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        # Put a known entry
        tm.put("Hello World", "en", "ja", "Konnichiwa Sekai")

        # Query with a very similar string
        doc = Document(
            language="Japanese",
            language_code="ja",
            stf_type="Bilingual",
            translation_type="Metadata",
            entries=[Entry(key="test.key", label="Hello Worlds")],
        )

        translator = MockTranslator()
        result = translate_document(
            doc,
            translator,
            source_lang="en",
            target_lang="ja",
            memory=tm,
            workers=1,
            rate_limit_per_second=None,
            fuzzy_threshold=75.0,
            fuzzy_max_results=5,
            fuzzy_auto_accept_threshold=90.0,
        )

        # The fuzzy match should have been auto-accepted
        assert result.fuzzy_accepted_count == 1
        # The translator should NOT have been called
        assert len(translator.calls) == 0
        # The translation should come from the fuzzy match
        assert doc.entries[0].translation == "Konnichiwa Sekai"

    def test_fuzzy_below_auto_accept_calls_translator(self, tmp_path: Path) -> None:
        """When fuzzy score < auto_accept_threshold, translator IS called."""
        from tests.conftest import MockTranslator

        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        # Put a somewhat similar entry
        tm.put("Hello World", "en", "ja", "Konnichiwa Sekai")

        doc = Document(
            language="Japanese",
            language_code="ja",
            stf_type="Bilingual",
            translation_type="Metadata",
            entries=[Entry(key="test.key", label="Hello Worlds")],
        )

        translator = MockTranslator()
        result = translate_document(
            doc,
            translator,
            source_lang="en",
            target_lang="ja",
            memory=tm,
            workers=1,
            rate_limit_per_second=None,
            fuzzy_threshold=75.0,
            fuzzy_max_results=5,
            fuzzy_auto_accept_threshold=99.9,  # Very high - won't auto-accept
        )

        # The translator SHOULD have been called because fuzzy didn't auto-accept
        assert result.fuzzy_accepted_count == 0
        assert len(translator.calls) == 1

    def test_fuzzy_disabled_when_threshold_none(self, tmp_path: Path) -> None:
        """When fuzzy_threshold is None, fuzzy matching is not used."""
        from tests.conftest import MockTranslator

        tm = TranslationMemory(path=tmp_path / "tm.sqlite")
        tm.put("Hello World", "en", "ja", "Konnichiwa Sekai")

        doc = Document(
            language="Japanese",
            language_code="ja",
            stf_type="Bilingual",
            translation_type="Metadata",
            entries=[Entry(key="test.key", label="Hello Worlds")],
        )

        translator = MockTranslator()
        result = translate_document(
            doc,
            translator,
            source_lang="en",
            target_lang="ja",
            memory=tm,
            workers=1,
            rate_limit_per_second=None,
            fuzzy_threshold=None,  # Disabled
        )

        # The translator should be called because fuzzy is disabled
        assert result.fuzzy_accepted_count == 0
        assert len(translator.calls) == 1
