"""Auto-fix module tests."""

from __future__ import annotations

from stx.autofix import (
    auto_fix_document,
    auto_fix_entry,
    fix_deduplicate_keys,
    fix_restore_placeholders,
    fix_restore_message_format,
    fix_strip_whitespace_translation,
    fix_trim_to_length,
)
from stx.model import Document, Entry


def test_restore_placeholders_appends_missing() -> None:
    e = Entry(key="CustomLabel.X", label="Hello {!User.Name}", translation="こんにちは")
    result = fix_restore_placeholders(e)
    assert result is not None
    assert "{!User.Name}" in result.entry.translation


def test_restore_placeholders_no_op_when_present() -> None:
    e = Entry(key="CustomLabel.X", label="Hello {!User.Name}", translation="こんにちは {!User.Name}")
    result = fix_restore_placeholders(e)
    assert result is None


def test_restore_message_format_appends_missing() -> None:
    e = Entry(key="CustomLabel.X", label="Hello {0}, you have {1} unread", translation="こんにちは")
    result = fix_restore_message_format(e)
    assert result is not None
    assert "{0}" in result.entry.translation
    assert "{1}" in result.entry.translation


def test_trim_to_length_for_custom_field() -> None:
    e = Entry(key="CustomField.A.B.FieldLabel", label="hi", translation="x" * 200)
    result = fix_trim_to_length(e)
    assert result is not None
    assert len(result.entry.translation) <= 80
    assert result.entry.translation.endswith("…")


def test_trim_no_op_when_within_limit() -> None:
    e = Entry(key="CustomField.A.B.FieldLabel", label="hi", translation="short")
    result = fix_trim_to_length(e)
    assert result is None


def test_strip_whitespace_translation() -> None:
    e = Entry(key="X.Y", label="hello", translation="   ")
    result = fix_strip_whitespace_translation(e)
    assert result is not None
    assert result.entry.translation == ""


def test_deduplicate_keys_keeps_last() -> None:
    doc = Document(entries=[
        Entry(key="A.X", label="first"),
        Entry(key="A.X", label="second"),
        Entry(key="B.Y", label="unique"),
    ])
    report = fix_deduplicate_keys(doc)
    assert report.fixed_count == 1
    assert len(doc.entries) == 2
    assert doc.entries[0].label == "second"  # last occurrence of A.X
    assert doc.entries[1].label == "unique"


def test_auto_fix_document_combines_all_fixers() -> None:
    doc = Document(entries=[
        Entry(key="CustomLabel.A", label="Hello {!Org.Name}", translation="こんにちは"),
        Entry(key="CustomLabel.B", label="World", translation="   "),
        Entry(key="CustomField.X.Y.FieldLabel", label="hi", translation="x" * 200),
        Entry(key="CustomLabel.A", label="Hello {!Org.Name}", translation="修正済み {!Org.Name}"),
    ])
    report = auto_fix_document(doc)
    assert report.fixed_count >= 3  # dedup + whitespace + trim (placeholder may or may not fire after dedup)
    # Verify dedup removed one entry.
    assert len(doc.entries) == 3


def test_auto_fix_entry_returns_descriptions() -> None:
    e = Entry(key="CustomLabel.X", label="Hello {!User.Name}", translation="こんにちは")
    fixed, descriptions = auto_fix_entry(e)
    assert len(descriptions) >= 1
    assert "{!User.Name}" in fixed.translation


def test_auto_fix_entry_no_op_on_clean_entry() -> None:
    e = Entry(key="CustomLabel.X", label="Hello", translation="こんにちは")
    fixed, descriptions = auto_fix_entry(e)
    assert descriptions == []
    assert fixed.translation == "こんにちは"
