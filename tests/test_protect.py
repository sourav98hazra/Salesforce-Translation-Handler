"""Token protection / restoration unit tests."""

from __future__ import annotations

import pytest

from stx.translate.protect import all_tokens_restored, protect_tokens, restore_tokens


def _round_trip(text: str) -> str:
    safe, mp = protect_tokens(text)
    return restore_tokens(safe, mp)


@pytest.mark.parametrize(
    "text",
    [
        "Click {!Account.Name} for details",
        "Email support@example.com or visit https://help.salesforce.com",
        "Please call API endpoint",
        "Record 01JD00000080e3FMAQ has been migrated",
        "Old ID 001D000000IqhSL needs review",
        "MessageFormat: Hello {0}, you have {1} unread",
        "Use \\n for line break and \\t for tab",
        "Mix it all: {!Org.Email} {0} WO ID 001D000000IqhSL via https://x.com",
        "<p>Please contact <b>Support</b> at {!Org.Email}</p>",
    ],
)
def test_round_trip_preserves_input(text: str) -> None:
    assert _round_trip(text) == text


def test_pure_digits_are_not_protected_as_id() -> None:
    safe, mp = protect_tokens("Number 810225277674347 is just a number")
    assert "810225277674347" in safe
    assert not any(orig == "810225277674347" for _, orig in mp)


def test_short_identifiers_are_not_treated_as_ids() -> None:
    # 14 chars -- not a Salesforce ID (15/18 only).
    safe, _mp = protect_tokens("Token abc123def4567x is not 15+ chars")
    assert "abc123def4567x" in safe


def test_token_loss_detection_catches_dropped_placeholder() -> None:
    text = "Click {!Account.Name} for details"
    safe, mp = protect_tokens(text)
    # Simulate a translator that lost the sentinel entirely.
    translated = "Klick fuer Details"
    restored = restore_tokens(translated, mp)
    assert not all_tokens_restored(restored, mp)


def test_full_restore_succeeds() -> None:
    text = "Click {!Account.Name} for details and email support@x.com"
    safe, mp = protect_tokens(text)
    fake_translated = safe.replace("Click", "Klick").replace("for", "fuer")
    restored = restore_tokens(fake_translated, mp)
    assert all_tokens_restored(restored, mp)


def test_url_absorbs_embedded_id() -> None:
    """A Salesforce ID embedded in a URL should be protected by the URL rule."""
    text = "See https://help.salesforce.com/articleView?id=01JD00000080e3FMAQ"
    safe, mp = protect_tokens(text)
    # Only one token expected: the whole URL (not a separate SFID).
    assert sum(1 for _, orig in mp if "01JD00000080e3FMAQ" in orig) == 1


def test_message_format_tokens_protected() -> None:
    text = "Hello {0}, you have {1} unread"
    safe, mp = protect_tokens(text)
    assert "{0}" not in safe
    assert "{1}" not in safe
    originals = [orig for _, orig in mp]
    assert "{0}" in originals and "{1}" in originals
