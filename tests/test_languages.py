"""Tests for the language name/code mapping module."""
from __future__ import annotations

from stx.languages import (
    code_for_language,
    language_for_code,
    to_google_code,
    supported_language_names,
)


def test_code_for_language_exact():
    assert code_for_language("Japanese") == "ja"
    assert code_for_language("English") == "en_US"
    assert code_for_language("French") == "fr"


def test_code_for_language_case_insensitive():
    assert code_for_language("japanese") == "ja"
    assert code_for_language("JAPANESE") == "ja"
    assert code_for_language("JaPaNeSe") == "ja"


def test_code_for_language_unknown():
    assert code_for_language("Klingon") is None
    assert code_for_language("") is None
    assert code_for_language("   ") is None


def test_language_for_code():
    assert language_for_code("ja") == "Japanese"
    assert language_for_code("fr") == "French"
    assert language_for_code("") is None
    assert language_for_code("xx") is None


def test_to_google_code_salesforce_specific():
    assert to_google_code("iw") == "he"
    assert to_google_code("in") == "id"


def test_to_google_code_regional():
    assert to_google_code("pt_BR") == "pt"
    assert to_google_code("fr_CA") == "fr"
    assert to_google_code("zh_CN") == "zh-CN"
    assert to_google_code("zh_TW") == "zh-TW"


def test_to_google_code_fallback_to_prefix():
    assert to_google_code("xx_YY") == "xx"
    assert to_google_code("ja") == "ja"


def test_to_google_code_empty():
    assert to_google_code("") == ""


def test_supported_language_names_sorted():
    names = supported_language_names()
    assert names == sorted(names)
    assert "Japanese" in names
    assert "English" in names
    assert len(names) > 30
