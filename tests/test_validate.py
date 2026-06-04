"""Validator unit tests."""

from __future__ import annotations

from stx.model import Document, Entry
from stx.validate import (
    clear_limit_overrides,
    get_all_limits,
    get_length_limit,
    set_limit_overrides,
    validate_document,
)


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


# --- New tests for accurate Salesforce limits ---


def test_custom_field_label_limit_is_40() -> None:
    """Entry with key ending in .FieldLabel and translation of 41 chars should flag error."""
    doc = Document(
        entries=[
            Entry(
                key="CustomField.Obj.MyField.FieldLabel",
                label="Name",
                translation="x" * 41,
            ),
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "length_limit" for i in report.errors)


def test_custom_field_help_text_limit_is_255() -> None:
    """Entry with key ending in .HelpText and translation of 256 chars should flag error."""
    doc = Document(
        entries=[
            Entry(
                key="CustomField.Obj.MyField.HelpText",
                label="Help",
                translation="x" * 256,
            ),
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "length_limit" for i in report.errors)


def test_custom_field_description_limit_is_1000() -> None:
    """Entry with key ending in .Description and translation of 1001 chars should flag error."""
    doc = Document(
        entries=[
            Entry(
                key="CustomField.Obj.MyField.Description",
                label="Desc",
                translation="x" * 1001,
            ),
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "length_limit" for i in report.errors)


def test_custom_label_limit_is_1000() -> None:
    """Entry with component CustomLabel and translation of 1001 chars should flag."""
    doc = Document(
        entries=[
            Entry(
                key="CustomLabel.MyLabel",
                label="Label",
                translation="x" * 1001,
            ),
        ]
    )
    report = validate_document(doc)
    assert any(i.category == "length_limit" for i in report.errors)


def test_override_mechanism() -> None:
    """set_limit_overrides lowers a limit; clear_limit_overrides restores default."""
    try:
        set_limit_overrides({"CustomLabel": 500})
        doc = Document(
            entries=[
                Entry(
                    key="CustomLabel.MyLabel",
                    label="Label",
                    translation="x" * 501,
                ),
            ]
        )
        report = validate_document(doc)
        assert any(i.category == "length_limit" for i in report.errors)

        # Clear overrides - same translation should pass (default is 1000)
        clear_limit_overrides()
        report2 = validate_document(doc)
        assert not any(i.category == "length_limit" for i in report2.issues)
    finally:
        clear_limit_overrides()


def test_get_all_limits_returns_all_types() -> None:
    """get_all_limits() contains expected keys for all component types."""
    limits = get_all_limits()
    assert "CustomField.FieldLabel" in limits
    assert "CustomField.HelpText" in limits
    assert "CustomField.Description" in limits
    assert "CustomField.InlineHelpText" in limits
    assert "CustomField.RelatedListLabel" in limits
    assert "CustomLabel" in limits
    assert "ButtonOrLink" in limits
    assert "PicklistValue" in limits
    assert "Flow" in limits
    assert limits["CustomField.FieldLabel"] == 40
    assert limits["CustomField.HelpText"] == 255
    assert limits["CustomField.Description"] == 1000
    assert limits["CustomLabel"] == 1000
