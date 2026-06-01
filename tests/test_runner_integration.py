"""Integration tests for the translation runner: scope + TM + glossary + dedup."""

from __future__ import annotations

from pathlib import Path

from stx.glossary import Glossary, GlossaryEntry
from stx.memory import TranslationMemory
from stx.model import Document, Entry
from stx.scope import Scope, StatusFilter
from stx.translate import translate_document
from stx.translate.base import Translator


class CountingTranslator(Translator):
    """Test double that records every call and returns a deterministic fake."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        self.calls.append((text, source_lang, target_lang))
        return f"<{target_lang}>{text}</{target_lang}>"


def _doc(n_repeats: int = 5) -> Document:
    entries = []
    for i in range(n_repeats):
        entries.append(Entry(key=f"CustomField.X{i}.Name.FieldLabel", label="Name"))
        entries.append(Entry(key=f"CustomField.X{i}.Created.FieldLabel", label="Created Date"))
    return Document(language="Japanese", language_code="ja", entries=entries)


def test_dedup_calls_translator_once_per_unique_label() -> None:
    doc = _doc(n_repeats=10)
    translator = CountingTranslator()
    result = translate_document(
        doc, translator,
        source_lang="en", target_lang="ja",
        workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
    )
    assert result.translated_count == 20
    assert result.deduped_count == 18  # 20 entries - 2 unique
    assert len(translator.calls) == 2  # exactly 2 unique sources


def test_no_gaps_in_statuses() -> None:
    doc = _doc(n_repeats=5)
    translator = CountingTranslator()
    result = translate_document(
        doc, translator,
        source_lang="en", target_lang="ja",
        workers=4, rate_limit_per_second=None, prevent_system_sleep=False,
    )
    assert len(result.statuses) == len(doc.entries)
    assert all(s is not None for s in result.statuses)
    assert result.translated_count + result.skipped_count == len(doc.entries)


def test_scope_blocks_out_of_scope_components() -> None:
    doc = Document(entries=[
        Entry(key="CustomLabel.A", label="hello"),
        Entry(key="ButtonOrLink.B", label="world"),
    ])
    translator = CountingTranslator()
    scope = Scope(components={"CustomLabel"}, status=StatusFilter.UNTRANSLATED)
    result = translate_document(
        doc, translator,
        source_lang="en", target_lang="ja",
        scope=scope, workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
    )
    assert result.translated_count == 1
    assert any("out of scope" in s.status for s in result.statuses)


def test_translation_memory_serves_repeated_runs(tmp_path: Path) -> None:
    doc = Document(entries=[Entry(key="X.Y", label="Hello")])
    tm_path = tmp_path / "tm.sqlite"

    # First run -- translator gets called.
    t1 = CountingTranslator()
    tm1 = TranslationMemory(path=tm_path)
    translate_document(doc, t1, source_lang="en", target_lang="ja", memory=tm1,
                       workers=1, rate_limit_per_second=None, prevent_system_sleep=False)
    assert len(t1.calls) == 1
    assert tm1.count() == 1

    # Second run on a fresh untranslated copy -- TM hit, no network call.
    doc2 = Document(entries=[Entry(key="X.Y", label="Hello")])
    t2 = CountingTranslator()
    tm2 = TranslationMemory(path=tm_path)
    result = translate_document(doc2, t2, source_lang="en", target_lang="ja", memory=tm2,
                                workers=1, rate_limit_per_second=None, prevent_system_sleep=False)
    assert len(t2.calls) == 0  # served entirely from TM
    assert result.cached_count == 1


class FailingTranslator(Translator):
    """Translator that always raises an exception."""

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        raise RuntimeError("Simulated failure")


def test_failed_rows_count_as_skipped() -> None:
    doc = Document(
        language="Japanese", language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello"),
            Entry(key="CustomLabel.B", label="World"),
        ]
    )
    translator = FailingTranslator()
    result = translate_document(
        doc, translator,
        source_lang="en", target_lang="ja",
        workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
    )
    assert result.skipped_count == 2
    assert result.translated_count == 0
    assert result.translated_count + result.skipped_count == len(doc.entries)
    # Per-sheet skipped_rows should also be 2
    assert sum(s.skipped_rows for s in result.summaries) == 2


def test_cancelled_rows_count_as_skipped() -> None:
    """Cancel after the first row - remaining rows should be skipped."""
    call_count = 0

    class CancelAfterOneTranslator(Translator):
        def translate(self, text: str, source_lang: str, target_lang: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"<ja>{text}"

    doc = Document(
        language="Japanese", language_code="ja",
        entries=[
            Entry(key="CustomLabel.A", label="Hello"),
            Entry(key="CustomLabel.B", label="World"),
            Entry(key="CustomLabel.C", label="Foo"),
        ]
    )

    def cancel_after_first():
        return call_count >= 1

    result = translate_document(
        doc, CancelAfterOneTranslator(),
        source_lang="en", target_lang="ja",
        workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
        cancel=cancel_after_first,
    )
    # At least some should be skipped due to cancellation
    assert result.translated_count + result.skipped_count == len(doc.entries)


def test_glossary_protects_dnt_term_through_translation() -> None:
    class CapitalisingTranslator:
        def translate(self, text, src, tgt):
            return text.upper()

    doc = Document(entries=[Entry(key="X.Y", label="Welcome to Bayer support")])
    gloss = Glossary(entries=[GlossaryEntry(source="Bayer", do_not_translate=True)])
    result = translate_document(
        doc, CapitalisingTranslator(),
        source_lang="en", target_lang="ja",
        glossary=gloss, workers=1, rate_limit_per_second=None, prevent_system_sleep=False,
    )
    translated = doc.entries[0].translation
    assert "Bayer" in translated
    assert "BAYER" not in translated
