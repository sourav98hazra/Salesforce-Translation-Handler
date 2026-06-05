"""Tests for the professional default-filename helper (Issue 13)."""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from datetime import date

from stx.gui.pages.base import clean_source_stem, default_output_filename

_DAY = date(2024, 3, 9)


def test_organized_pattern():
    assert (
        default_output_filename("MyLabels", "organized", "ja", today=_DAY)
        == "MyLabels_Organized_2024-03-09.xlsx"
    )


def test_translated_pattern_includes_code():
    assert (
        default_output_filename("MyLabels", "translated", "fr", today=_DAY)
        == "MyLabels_Translated_fr_2024-03-09.xlsx"
    )


def test_reviewed_pattern_includes_code():
    assert (
        default_output_filename("MyLabels", "reviewed", "de", today=_DAY)
        == "MyLabels_Reviewed_de_2024-03-09.xlsx"
    )


def test_validated_pattern_includes_code():
    assert (
        default_output_filename("MyLabels", "validated", "es", today=_DAY)
        == "MyLabels_Validated_es_2024-03-09.xlsx"
    )


def test_organized_has_no_code_even_when_supplied():
    # Phase 2 organised name should not carry a language code.
    name = default_output_filename("MyLabels", "organized", "ja", today=_DAY)
    assert "_ja_" not in name


def test_missing_code_omitted():
    assert (
        default_output_filename("MyLabels", "translated", None, today=_DAY)
        == "MyLabels_Translated_2024-03-09.xlsx"
    )


def test_empty_stem_falls_back_to_workbook():
    assert default_output_filename("", "organized", today=_DAY).startswith("workbook_Organized")


def test_clean_stem_strips_prior_stage_tokens():
    # Re-saving a derived artifact must not stack suffixes.
    assert clean_source_stem("MyLabels_organized") == "MyLabels"
    assert clean_source_stem("MyLabels_Translated_ja_2024-01-01") == "MyLabels"
    assert clean_source_stem("MyLabels_Reviewed_de") == "MyLabels"


def test_clean_stem_preserves_plain_stem():
    assert clean_source_stem("Acme_Product_Labels") == "Acme_Product_Labels"
    # A short trailing word that is not preceded by a stage token is kept.
    assert clean_source_stem("my_id") == "my_id"


def test_rebuild_from_derived_stem_is_clean():
    # Simulate building a translated name from an already-organised stem.
    name = default_output_filename("MyLabels_Organized_2024-01-01", "translated", "ja", today=_DAY)
    assert name == "MyLabels_Translated_ja_2024-03-09.xlsx"
