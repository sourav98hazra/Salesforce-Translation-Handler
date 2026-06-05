"""End-to-end round-trip tests for the STF parser/writer + Excel I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from stx.excel import export_document_to_excel, import_document_from_excel
from stx.model import Document, Entry
from stx.stf import parse_stf, parse_stf_text, render_full_stf, render_translated_only_stf, render_untranslated_only_stf, write_stf_files


SAMPLE_STF = """\
# Notes:
# Lines that begin with the # symbol are ignored during import.

# Language: Japanese
Language code: ja
Type: Outdated and untranslated
Translation type: Metadata

# KEY\tLABEL

CustomApp.Inside_Sales\tInside Sales
CustomApp.Sales_Leader\tSales Leader\tセールスリーダー\t-
CustomField.Account.Name.FieldLabel\tAccount Name
"""


def test_parse_metadata() -> None:
    doc = parse_stf_text(SAMPLE_STF)
    assert doc.language == "Japanese"
    assert doc.language_code == "ja"
    assert doc.stf_type == "Outdated and untranslated"
    assert doc.translation_type == "Metadata"
    assert len(doc.entries) == 3


def test_parse_separates_translated_from_untranslated() -> None:
    doc = parse_stf_text(SAMPLE_STF)
    assert doc.entries[0].translation == ""
    assert doc.entries[1].translation == "セールスリーダー"
    assert doc.entries[2].translation == ""


def test_render_full_stf_uses_exact_separators() -> None:
    doc = parse_stf_text(SAMPLE_STF)
    text = render_full_stf(doc)
    assert "# Language: Japanese" in text
    assert "Language code: ja" in text
    assert "Type: Bilingual" in text
    assert "------------------TRANSLATED-------------------" in text
    assert "------------------OUTDATED AND UNTRANSLATED-----------------" in text
    assert "# KEY\tLABEL\tTRANSLATION\tOUT OF DATE" in text


def test_render_translated_only_includes_only_translated() -> None:
    doc = parse_stf_text(SAMPLE_STF)
    text = render_translated_only_stf(doc)
    assert "Sales_Leader" in text
    assert "Account.Name" not in text  # untranslated
    assert "Inside_Sales" not in text


def test_write_stf_files_uses_lf_no_bom(tmp_path: Path) -> None:
    doc = parse_stf_text(SAMPLE_STF)
    res = write_stf_files(doc, tmp_path, language_name="Japanese", language_code="ja")
    data = res.full.read_bytes()
    assert b"\r\n" not in data
    assert b"\r" not in data
    assert not data.startswith(b"\xef\xbb\xbf")


def test_excel_round_trip(tmp_path: Path) -> None:
    doc = parse_stf_text(SAMPLE_STF)
    xlsx = tmp_path / "out.xlsx"
    export_document_to_excel(doc, xlsx)

    restored = import_document_from_excel(
        xlsx, language=doc.language, language_code=doc.language_code
    )
    assert len(restored.entries) == len(doc.entries)
    assert {e.key for e in restored.entries} == {e.key for e in doc.entries}
    by_key = {e.key: e for e in restored.entries}
    for entry in doc.entries:
        round_tripped = by_key[entry.key]
        assert round_tripped.label == entry.label
        assert round_tripped.translation == entry.translation


def test_stf_then_excel_then_stf_preserves_data(tmp_path: Path) -> None:
    doc = parse_stf_text(SAMPLE_STF)
    xlsx = tmp_path / "out.xlsx"
    export_document_to_excel(doc, xlsx)

    reimported = import_document_from_excel(
        xlsx, language=doc.language, language_code=doc.language_code
    )
    res = write_stf_files(reimported, tmp_path, language_name="Japanese", language_code="ja")
    full_text = res.full.read_text(encoding="utf-8")
    for entry in doc.entries:
        assert entry.key in full_text
        assert entry.label in full_text


def test_formula_injection_safe_on_export(tmp_path: Path) -> None:
    doc = Document(
        language="Japanese",
        language_code="ja",
        entries=[
            Entry(key="CustomLabel.Sneaky", label="=cmd|'/c calc'!A1"),
            Entry(key="CustomLabel.OK", label="Normal label"),
        ],
    )
    xlsx = tmp_path / "out.xlsx"
    export_document_to_excel(doc, xlsx)

    restored = import_document_from_excel(xlsx)
    by_key = {e.key: e for e in restored.entries}
    # Round-trip: the original label is recovered (importer strips our guard prefix).
    assert by_key["CustomLabel.Sneaky"].label == "=cmd|'/c calc'!A1"


def test_sheet_name_collision_handling() -> None:
    """Two component types differing only after 28 chars should each get their own sheet."""

    long_a = "VeryLongComponentNameThatDefinitelyExceedsTwentyEightChars" + "_A"
    long_b = "VeryLongComponentNameThatDefinitelyExceedsTwentyEightChars" + "_B"
    doc = Document(
        entries=[
            Entry(key=f"{long_a}.x", label="A"),
            Entry(key=f"{long_b}.y", label="B"),
        ],
    )
    # We expect different physical sheet names even after truncation.
    from stx.excel.exporter import _allocate_sheet_name

    used: set[str] = set()
    a = _allocate_sheet_name(f"{long_a}_Untranslated", used); used.add(a)
    b = _allocate_sheet_name(f"{long_b}_Untranslated", used); used.add(b)
    assert a != b


# ---------------------------------------------------------------------------
# BOM and CRLF handling tests
# ---------------------------------------------------------------------------

def test_parse_stf_with_bom(tmp_path: Path) -> None:
    """STF file with UTF-8 BOM parses correctly."""
    content = "# Language: Japanese\nLanguage code: ja\nType: Bilingual\nTranslation type: Metadata\nCustomLabel.X\tHello\tKonnichiwa\t-"
    bom_content = "\ufeff" + content
    stf_file = tmp_path / "bom_test.stf"
    stf_file.write_bytes(bom_content.encode("utf-8-sig"))

    doc = parse_stf(stf_file)
    assert doc.language == "Japanese"
    assert doc.language_code == "ja"
    assert len(doc.entries) == 1
    assert doc.entries[0].key == "CustomLabel.X"


def test_parse_stf_text_with_bom() -> None:
    """parse_stf_text handles BOM in string input."""
    text = "\ufeff# Language: Japanese\nLanguage code: ja\nCustomLabel.X\tHello"
    doc = parse_stf_text(text)
    assert doc.language == "Japanese"
    assert len(doc.entries) == 1


def test_parse_stf_with_crlf(tmp_path: Path) -> None:
    """STF file with CRLF line endings parses correctly."""
    content = "# Language: Japanese\r\nLanguage code: ja\r\nCustomLabel.X\tHello\tKonnichiwa\t-\r\n"
    stf_file = tmp_path / "crlf_test.stf"
    stf_file.write_bytes(content.encode("utf-8"))

    doc = parse_stf(stf_file)
    assert doc.language == "Japanese"
    assert len(doc.entries) == 1
    assert doc.entries[0].translation == "Konnichiwa"  # no trailing \r
