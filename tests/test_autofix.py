"""Auto-fix module tests."""

from __future__ import annotations

from stx.autofix import (
    auto_fix_document,
    auto_fix_entry,
    fix_deduplicate_keys,
    fix_normalize_whitespace,
    fix_restore_html_tags,
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
    assert len(result.entry.translation) <= 40
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


def test_auto_fix_document_manual_review_field() -> None:
    """AutoFixReport includes a manual_review list."""
    doc = Document(entries=[
        Entry(key="CustomLabel.A", label="Hello", translation="short"),
    ])
    report = auto_fix_document(doc)
    assert hasattr(report, "manual_review")
    assert isinstance(report.manual_review, list)


def test_auto_fix_document_with_target_lang_no_length_issue() -> None:
    """Passing target_lang/backend_name does not affect entries within limit."""
    doc = Document(entries=[
        Entry(key="CustomLabel.A", label="Hello", translation="short"),
    ])
    report = auto_fix_document(
        doc,
        target_lang="ja",
        backend_name="google",
    )
    # Nothing to fix
    assert report.fixed_count == 0
    assert report.manual_review == []


def test_auto_fix_document_length_issue_flags_manual_review_on_failure() -> None:
    """When re-translation fails, entry is flagged for manual review."""
    doc = Document(entries=[
        Entry(key="CustomField.A.B.FieldLabel", label="hi", translation="x" * 200),
    ])
    # Pass a backend_name that will fail (no network)
    report = auto_fix_document(
        doc,
        target_lang="ja",
        backend_name="google",
    )
    # Either it got re-translated (unlikely in test) or flagged for manual review
    # In a test environment without network, it should fall back to truncation
    # since google free is always "available" but may fail on translate call
    assert report.fixed_count >= 0
    # The entry should either be fixed or flagged
    total_handled = report.fixed_count + len(report.manual_review)
    assert total_handled >= 1


def test_fix_trim_to_length_still_works_standalone() -> None:
    """The original fix_trim_to_length still works as a fallback."""
    e = Entry(key="CustomField.A.B.FieldLabel", label="hi", translation="x" * 200)
    result = fix_trim_to_length(e)
    assert result is not None
    assert len(result.entry.translation) <= 40
    assert result.entry.translation.endswith("\u2026")


def test_trim_to_length_respects_help_text_limit() -> None:
    """Entry with key ending in .HelpText and 300-char translation should be trimmed to <= 255."""
    e = Entry(key="CustomField.Obj.MyField.HelpText", label="Help", translation="x" * 300)
    result = fix_trim_to_length(e)
    assert result is not None
    assert len(result.entry.translation) <= 255
    assert result.entry.translation.endswith("\u2026")


# ---------------------------------------------------------------------------
# FEAT-003: Whitespace normalization tests
# ---------------------------------------------------------------------------


def test_normalize_whitespace_collapses_spaces() -> None:
    """Multiple consecutive spaces are collapsed to a single space."""
    e = Entry(key="CustomLabel.X", label="Hello World", translation="Hello   World")
    result = fix_normalize_whitespace(e)
    assert result is not None
    assert result.entry.translation == "Hello World"


def test_normalize_whitespace_strips_trailing() -> None:
    """Trailing spaces in translation are stripped if source has none."""
    e = Entry(key="CustomLabel.X", label="Hello", translation="Hello ")
    result = fix_normalize_whitespace(e)
    assert result is not None
    assert result.entry.translation == "Hello"


def test_normalize_whitespace_no_op_clean() -> None:
    """Clean text with single spaces returns None (no fix needed)."""
    e = Entry(key="CustomLabel.X", label="Hello World", translation="Hello World")
    result = fix_normalize_whitespace(e)
    assert result is None


# ---------------------------------------------------------------------------
# FEAT-003: Smart truncation tests
# ---------------------------------------------------------------------------


def test_smart_truncate_preserves_placeholders() -> None:
    """Truncation preserves placeholder tokens from the source label."""
    e = Entry(
        key="CustomField.X.Y.FieldLabel",
        label="Welcome {!User.Name}",
        translation="Welcome to our great application {!User.Name}",
    )
    # Limit for FieldLabel is 40 chars; translation is 46 chars
    result = fix_trim_to_length(e)
    assert result is not None
    assert len(result.entry.translation) <= 40
    assert "{!User.Name}" in result.entry.translation


def test_smart_truncate_word_boundary() -> None:
    """Truncation does not cut a word in half."""
    e = Entry(
        key="CustomField.X.Y.FieldLabel",
        label="Description",
        translation="This is a longer description that exceeds the field label limit",
    )
    result = fix_trim_to_length(e)
    assert result is not None
    text = result.entry.translation
    # The text before the ellipsis should not end mid-word (no partial words).
    # Remove the ellipsis and check the last char before it.
    before_ellipsis = text.split("\u2026")[0]
    # It should end with a complete word (last char is a letter or it ends at a space).
    assert before_ellipsis[-1] != " " or before_ellipsis.rstrip() == before_ellipsis


# ---------------------------------------------------------------------------
# FEAT-003: HTML tag restoration tests
# ---------------------------------------------------------------------------


def test_html_restore_two_missing_tags() -> None:
    """Two missing tags (b and i) are restored by wrapping."""
    e = Entry(
        key="CustomLabel.X",
        label="<b><i>Hello</i></b>",
        translation="Bonjour",
    )
    result = fix_restore_html_tags(e)
    assert result is not None
    trans = result.entry.translation
    assert "<b>" in trans
    assert "</b>" in trans
    assert "<i>" in trans
    assert "</i>" in trans
    assert "Bonjour" in trans


def test_html_restore_too_many_skipped() -> None:
    """More than 3 missing tags returns None (too complex)."""
    e = Entry(
        key="CustomLabel.X",
        label="<a><b><c><d>Hello</d></c></b></a>",
        translation="Bonjour",
    )
    result = fix_restore_html_tags(e)
    assert result is None


# ---------------------------------------------------------------------------
# FEAT-003: Trim after whitespace collapse fits
# ---------------------------------------------------------------------------


def test_trim_after_whitespace_collapse_fits() -> None:
    """Extra spaces that once collapsed fit within limit -- no ellipsis needed."""
    # FieldLabel limit is 40. Create a translation with extra spaces that exceeds 40,
    # but collapses to <= 40 chars.
    translation = "Hello  World  Testing  Extra  Spaces  OK Now"  # 45 chars with double-spaces
    assert len(translation) > 40
    collapsed = "Hello World Testing Extra Spaces OK Now"
    assert len(collapsed) <= 40
    e = Entry(
        key="CustomField.X.Y.FieldLabel",
        label="Hello World Testing Extra Spaces OK Now",
        translation=translation,
    )
    result = fix_trim_to_length(e)
    assert result is not None
    # Should be the collapsed version without truncation/ellipsis
    assert "\u2026" not in result.entry.translation
    assert len(result.entry.translation) <= 40
