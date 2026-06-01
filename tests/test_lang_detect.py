"""Tests for the auto-detect source language module."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from stx.lang_detect import detect_source_language, map_detected_to_salesforce


class TestDetectSourceLanguage:
    """Tests for detect_source_language()."""

    def test_detect_english(self):
        texts = [
            "Hello, how are you today?",
            "The quick brown fox jumps over the lazy dog.",
            "Please save your changes before exiting.",
            "This is a sample label for testing purposes.",
            "Enter your username and password below.",
        ]
        results = detect_source_language(texts)
        assert len(results) > 0
        # Top result should be English
        top_lang, top_confidence = results[0]
        assert top_lang == "en"
        assert top_confidence > 0.5

    def test_detect_japanese(self):
        texts = [
            "こんにちは、今日はお元気ですか？",
            "保存する前に変更を確認してください。",
            "ユーザー名とパスワードを入力してください。",
            "これはテスト用のサンプルラベルです。",
            "設定を変更するにはここをクリックしてください。",
        ]
        results = detect_source_language(texts)
        assert len(results) > 0
        top_lang, top_confidence = results[0]
        assert top_lang == "ja"
        assert top_confidence > 0.5

    def test_detect_french(self):
        texts = [
            "Bonjour, comment allez-vous aujourd'hui?",
            "Veuillez enregistrer vos modifications avant de quitter.",
            "Entrez votre nom d'utilisateur et votre mot de passe.",
            "Ceci est un exemple de libelle pour les tests.",
            "Cliquez ici pour modifier les parametres.",
        ]
        results = detect_source_language(texts)
        assert len(results) > 0
        top_lang, top_confidence = results[0]
        assert top_lang == "fr"
        assert top_confidence > 0.5

    def test_empty_input(self):
        assert detect_source_language([]) == []
        assert detect_source_language([""]) == []
        assert detect_source_language(["", "   ", ""]) == []

    def test_importerror_graceful(self):
        """If langdetect is not importable, return empty list."""
        with patch.dict("sys.modules", {"langdetect": None}):
            # Force reimport by removing cached module
            import importlib
            import stx.lang_detect

            # Patch the import inside the function
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def mock_import(name, *args, **kwargs):
                if name == "langdetect" or name.startswith("langdetect."):
                    raise ImportError("No module named 'langdetect'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = detect_source_language(["Hello world"])
                assert result == []

    def test_multi_language_mixed_input(self):
        """Mixed-language input should return multiple candidates."""
        texts = [
            "Hello, how are you?",
            "Bonjour, comment allez-vous?",
            "Hola, como estas?",
            "Good morning everyone!",
            "Bonsoir mes amis",
            "Buenos dias a todos",
            "The weather is nice today",
            "Il fait beau aujourd'hui",
            "El clima esta agradable hoy",
        ]
        results = detect_source_language(texts, top_n=3)
        assert len(results) > 1
        # No single language should dominate overwhelmingly with mixed input
        langs = [r[0] for r in results]
        assert len(set(langs)) > 1


class TestMapDetectedToSalesforce:
    """Tests for map_detected_to_salesforce()."""

    def test_english_maps_to_en_us(self):
        assert map_detected_to_salesforce("en") == "en_US"

    def test_japanese_maps_to_ja(self):
        assert map_detected_to_salesforce("ja") == "ja"

    def test_french_maps_to_fr(self):
        assert map_detected_to_salesforce("fr") == "fr"

    def test_chinese_simplified(self):
        assert map_detected_to_salesforce("zh-cn") == "zh_CN"

    def test_hebrew_maps_to_iw(self):
        assert map_detected_to_salesforce("he") == "iw"

    def test_indonesian_maps_to_in(self):
        assert map_detected_to_salesforce("id") == "in"

    def test_empty_returns_none(self):
        assert map_detected_to_salesforce("") is None

    def test_unknown_code_returns_none(self):
        assert map_detected_to_salesforce("xx") is None

    def test_case_insensitive(self):
        assert map_detected_to_salesforce("EN") == "en_US"
        assert map_detected_to_salesforce("JA") == "ja"


class TestConfidenceThreshold:
    """Tests for CONFIDENCE_THRESHOLD constant."""

    def test_threshold_value(self):
        from stx.lang_detect import CONFIDENCE_THRESHOLD
        assert CONFIDENCE_THRESHOLD == 0.60

    def test_high_confidence_detection_exceeds_threshold(self):
        """Uniform language text should exceed the 60% threshold."""
        from stx.lang_detect import CONFIDENCE_THRESHOLD

        texts = [
            "Hello, how are you today?",
            "The quick brown fox jumps over the lazy dog.",
            "Please save your changes before exiting.",
            "This is a sample label for testing purposes.",
            "Enter your username and password below.",
        ]
        results = detect_source_language(texts)
        assert len(results) > 0
        _, confidence = results[0]
        assert confidence >= CONFIDENCE_THRESHOLD
