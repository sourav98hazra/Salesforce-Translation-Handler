"""Translation memory (SQLite) tests."""

from __future__ import annotations

from pathlib import Path

from stx.memory import TranslationMemory


def test_round_trip(tmp_path: Path) -> None:
    tm = TranslationMemory(path=tmp_path / "tm.sqlite")
    tm.put("Hello", "en", "ja", "こんにちは")
    assert tm.get("Hello", "en", "ja") == "こんにちは"
    assert tm.get("Goodbye", "en", "ja") is None


def test_persists_across_open(tmp_path: Path) -> None:
    path = tmp_path / "tm.sqlite"
    tm = TranslationMemory(path=path)
    tm.put("Hello", "en", "ja", "こんにちは")
    del tm
    tm2 = TranslationMemory(path=path)
    assert tm2.get("Hello", "en", "ja") == "こんにちは"
    assert tm2.count() == 1


def test_hits_are_counted(tmp_path: Path) -> None:
    tm = TranslationMemory(path=tmp_path / "tm.sqlite")
    tm.put("Hello", "en", "ja", "こんにちは")
    for _ in range(3):
        tm.get("Hello", "en", "ja")
    stats = tm.stats()
    assert stats["entries"] == 1
    assert stats["hits"] == 3


def test_clear_removes_everything(tmp_path: Path) -> None:
    tm = TranslationMemory(path=tmp_path / "tm.sqlite")
    tm.put("a", "en", "ja", "x")
    tm.put("b", "en", "ja", "y")
    assert tm.count() == 2
    tm.clear()
    assert tm.count() == 0


def test_target_lang_isolation(tmp_path: Path) -> None:
    tm = TranslationMemory(path=tmp_path / "tm.sqlite")
    tm.put("Hello", "en", "ja", "こんにちは")
    tm.put("Hello", "en", "fr", "Bonjour")
    assert tm.get("Hello", "en", "ja") == "こんにちは"
    assert tm.get("Hello", "en", "fr") == "Bonjour"
    assert tm.get("Hello", "en", "de") is None
