"""Shared fixtures for the test suite."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest

from stx.model import Document, Entry
from stx.memory import TranslationMemory
from stx.translate.base import Translator


# Ensure Qt runs offscreen for GUI tests
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class MockTranslator(Translator):
    """Test double that returns a deterministic translation."""

    def __init__(self, prefix: str = "TRANSLATED") -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.prefix = prefix

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        self.calls.append((text, source_lang, target_lang))
        return f"[{self.prefix}:{target_lang}] {text}"


@pytest.fixture
def sample_doc() -> Document:
    """A small Document with mixed translated/untranslated entries."""
    return Document(
        language="Japanese",
        language_code="ja",
        stf_type="Bilingual",
        translation_type="Metadata",
        entries=[
            Entry(key="CustomLabel.Greeting", label="Hello", translation="Konnichiwa"),
            Entry(key="CustomLabel.Farewell", label="Goodbye"),
            Entry(key="CustomField.Name.FieldLabel", label="Name"),
            Entry(key="CustomField.Date.FieldLabel", label="Created Date", translation="Sakusei Bi"),
            Entry(key="ButtonOrLink.Save", label="Save"),
        ],
    )


@pytest.fixture
def mock_translator() -> MockTranslator:
    return MockTranslator()


@pytest.fixture
def tmp_stf(tmp_path: Path, sample_doc: Document) -> Path:
    """Write sample_doc to a temp .stf file and return the path."""
    from stx.stf import render_full_stf

    stf_path = tmp_path / "test.stf"
    stf_path.write_text(render_full_stf(sample_doc), encoding="utf-8")
    return stf_path


@pytest.fixture
def temp_tm(tmp_path: Path) -> TranslationMemory:
    """A TranslationMemory backed by a temp file."""
    return TranslationMemory(path=tmp_path / "test_tm.sqlite")
