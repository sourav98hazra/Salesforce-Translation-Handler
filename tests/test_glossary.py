"""Glossary tests."""

from __future__ import annotations

from pathlib import Path

from stx.glossary import Glossary, GlossaryEntry


def test_dnt_protect_round_trip() -> None:
    gloss = Glossary(entries=[GlossaryEntry(source="Bayer", do_not_translate=True)])
    text = "Welcome to Bayer support"
    safe, mp = gloss.protect(text)
    assert "Bayer" not in safe
    assert mp[0][1] == "Bayer"


def test_forced_translation_replaces_term() -> None:
    gloss = Glossary(entries=[GlossaryEntry(source="case", target="ケース")])
    assert gloss.apply_forced("Open a new case for review") == "Open a new ケース for review"


def test_forced_translation_is_case_insensitive_match_but_keeps_target_case() -> None:
    gloss = Glossary(entries=[GlossaryEntry(source="record", target="レコード")])
    assert gloss.apply_forced("View the Record details") == "View the レコード details"


def test_csv_round_trip(tmp_path: Path) -> None:
    gloss = Glossary(entries=[
        GlossaryEntry(source="Bayer", do_not_translate=True),
        GlossaryEntry(source="case", target="ケース"),
    ])
    path = tmp_path / "g.csv"
    gloss.save_csv(path)
    loaded = Glossary.load_csv(path)
    assert len(loaded) == 2
    assert any(e.source == "Bayer" and e.do_not_translate for e in loaded.entries)
    assert any(e.source == "case" and e.target == "ケース" for e in loaded.entries)


def test_inactive_rows_are_dropped_on_load(tmp_path: Path) -> None:
    path = tmp_path / "g.csv"
    path.write_text("source,target,do_not_translate\n,empty,\nfoo,,\n", encoding="utf-8")
    loaded = Glossary.load_csv(path)
    assert len(loaded) == 0  # both rows are inactive
