"""Validator unit tests."""

from __future__ import annotations

from stx.model import Document, Entry
from stx.validate import validate_document


def test_duplicate_keys_are_flagged() -> None:
    doc = Document(
        entries=[
            Entry(key="CustomLabel.X", label="Hello"),
            Entry(key="CustomLabel.X", label="Hello"),
        ]
    )
    report = validate_document(doc)
    assert report.has_errors
    assert any(i.category == "duplicate_key" for i in report.errors)


def test_length_limit_violation_flagged_for_known_components() -> None:
    long_translation = "x" * 200
    doc = Document(
        entries=[
            Entry(key="CustomField.A.Foo.FieldLabel", label="hi", translation=long_translation),
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "length_limit" for i in report.errors)


def test_token_drift_caught() -> None:
    doc = Document(
        entries=[
            Entry(
                key="CustomLabel.Greeting",
                label="Hello {!User.Name}",
                translation="Bonjour",  # placeholder dropped
            )
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "token_drift" for i in report.errors)


def test_html_mismatch_warns() -> None:
    doc = Document(
        entries=[
            Entry(
                key="CustomLabel.Body",
                label="<p>Hello</p>",
                translation="Bonjour",  # tag dropped
            )
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "html_mismatch" for i in report.warnings)


def test_clean_document_has_no_issues() -> None:
    doc = Document(
        entries=[
            Entry(key="CustomLabel.A", label="Hello", translation="Bonjour"),
            Entry(key="CustomLabel.B", label="World", translation="Monde"),
        ]
    )
    report = validate_document(doc)
    assert not report.has_errors
    assert len(report.warnings) == 0


def test_whitespace_only_translation_emits_empty_translation_warning() -> None:
    doc = Document(
        entries=[
            Entry(key="CustomLabel.X", label="Hello", translation="   "),
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "empty_translation" for i in report.warnings)


def test_empty_translation_no_issue() -> None:
    doc = Document(
        entries=[
            Entry(key="CustomLabel.X", label="Hello", translation=""),
        ]
    )
    report = validate_document(doc)
    assert not report.issues  # completely untranslated is not an issue


def test_tab_only_translation_emits_empty_translation_warning() -> None:
    doc = Document(
        entries=[
            Entry(key="CustomLabel.X", label="Hello", translation="\t\n "),
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "empty_translation" for i in report.warnings)
