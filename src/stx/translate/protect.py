"""Token protection for translation.

Salesforce labels and rich-text fields embed several kinds of fragments
that must survive translation untouched:

==================================  ====================================
Construct                            Examples
==================================  ====================================
Translation Workbench placeholders   ``{!$Label.Foo}``, ``{!Record.Id}``
Salesforce record IDs (15 / 18 ch)   ``001D000000IqhSL``, ``01JD00000080e3FMAQ``
URLs                                 ``https://help.salesforce.com``
Email addresses                      ``support@example.com``
HTML / rich-text tags                ``<p>``, ``<a href="...">``, ``<br/>``
ALL-CAPS acronyms                    ``API``, ``URL``, ``WO``
==================================  ====================================

Each fragment is replaced with an opaque sentinel of the form
``__SFID_3__`` before invoking the translator and restored afterwards.
The sentinel format uses only ASCII letters / digits / underscores so
that translators don't try to "fix" them.

HTML tags themselves are *not* protected here -- the HTML branch of
:mod:`stx.translate.google_free` walks the DOM via BeautifulSoup and
only sends text nodes to the translator, which preserves tags and
attributes natively.  The ``<`` / ``>`` characters that *do* reach this
module are therefore expected to belong to plain text and are left
alone.
"""

from __future__ import annotations

import re
from typing import List, Pattern, Tuple

# ---------------------------------------------------------------------------
# Patterns -- order matters: URLs and emails are matched first so they don't
# get partially eaten by the more permissive ID / CAPS patterns.
# ---------------------------------------------------------------------------

_URL_RE: Pattern[str] = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_EMAIL_RE: Pattern[str] = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)

# Salesforce Translation Workbench placeholders (and Visualforce/Aura merge
# fields).  ``\{![^}]+\}`` matches everything between ``{!`` and ``}``.
_PLACEHOLDER_RE: Pattern[str] = re.compile(r"\{![^}]+\}")

# Apex / Java ``MessageFormat`` tokens like ``{0}``, ``{1}``, ``{name}``.  These
# are used for runtime substitution and must round-trip exactly.  We exclude
# ``{!...}`` (handled above) by forbidding a leading ``!``.
_MESSAGE_FORMAT_RE: Pattern[str] = re.compile(r"\{(?!!)[A-Za-z0-9_,\.\s]+\}")

# Literal escape sequences as they appear *in the STF file* -- the file uses
# ``\t``, ``\n``, ``\r`` as two-character sequences that Salesforce decodes on
# import.  A translator might happily "fix" them to a real tab/newline, which
# would corrupt the import.
_ESCAPE_RE: Pattern[str] = re.compile(r"\\[tnr\"\\]")

# Salesforce record IDs are exactly 15 or 18 case-sensitive base-62 characters
# *and* always contain at least one digit AND at least one letter.  The
# look-aheads enforce the digit/letter requirement so we don't match common
# English words of the same length (e.g. ``internationalization``).
_SALESFORCE_ID_RE: Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9_])"                       # left boundary (allow underscores around it)
    r"(?=[A-Za-z0-9]*[0-9])"                   # must contain a digit
    r"(?=[A-Za-z0-9]*[A-Za-z])"                # must contain a letter
    r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?"      # 15 or 18 chars
    r"(?![A-Za-z0-9_])"                        # right boundary
)

# ALL-CAPS acronyms / mnemonics of length >= 2.  Numbers and underscores are
# allowed mid-word (matches ``HTTP2``, ``OAUTH_TOKEN``).
_CAPS_RE: Pattern[str] = re.compile(r"\b[A-Z][A-Z0-9_]+\b")


# Each protector is a (label, regex) pair.  ``label`` is embedded in the
# sentinel so that debugging / status logs are readable.
_PROTECTORS: List[Tuple[str, Pattern[str]]] = [
    ("URL", _URL_RE),
    ("EMAIL", _EMAIL_RE),
    ("PLACEHOLDER", _PLACEHOLDER_RE),
    ("MSGFMT", _MESSAGE_FORMAT_RE),
    ("ESC", _ESCAPE_RE),
    ("SFID", _SALESFORCE_ID_RE),
    ("CAPS", _CAPS_RE),
]


def protect_tokens(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Replace sensitive fragments in ``text`` with sentinel tokens.

    Returns the protected text alongside an ordered list of
    ``(token, original)`` pairs that :func:`restore_tokens` consumes.
    Detection runs in priority order (URLs first, CAPS last), so a
    Salesforce ID embedded in a URL is protected by the URL rule rather
    than being double-tokenised.
    """

    token_map: List[Tuple[str, str]] = []
    counter = 0
    safe = text

    for label, pattern in _PROTECTORS:
        def _repl(match: "re.Match[str]", _label: str = label) -> str:
            nonlocal counter
            token = f"__{_label}_{counter}__"
            token_map.append((token, match.group(0)))
            counter += 1
            return token

        safe = pattern.sub(_repl, safe)

    return safe, token_map


def restore_tokens(text: str, token_map: List[Tuple[str, str]]) -> str:
    """Restore originals into ``text`` after translation.

    The implementation is tolerant of two common translator quirks:

    1. Case differences (some translators lowercase sentinels).
    2. Whitespace inserted between sentinel characters (rare but seen).

    Trailing whitespace after the sentinel is *not* consumed -- otherwise
    we'd merge the sentinel into the following word.
    """

    restored = text
    for token, original in token_map:
        # Fast path: simple string substitution.  Using ``str.replace`` rather
        # than ``re.subn`` avoids backslash interpretation in the replacement
        # (e.g. so that an original value of ``\\n`` is restored literally
        # rather than becoming a real newline).
        idx = _find_case_insensitive(restored, token)
        if idx >= 0:
            restored = restored[:idx] + original + restored[idx + len(token):]
            continue

        # Slow path: tolerate whitespace *between* sentinel characters but
        # not after the final character.  We use a regex *match* (not sub)
        # so we can splice the original in literally.
        slow_pattern = re.compile(
            r"\s*".join(re.escape(ch) for ch in token),
            re.IGNORECASE,
        )
        match = slow_pattern.search(restored)
        if match is not None:
            restored = restored[: match.start()] + original + restored[match.end():]
    return restored


def _find_case_insensitive(haystack: str, needle: str) -> int:
    """Return the index of ``needle`` in ``haystack`` ignoring case, or ``-1``."""
    if not needle:
        return -1
    return haystack.lower().find(needle.lower())


def all_tokens_restored(restored_text: str, token_map: List[Tuple[str, str]]) -> bool:
    """Return ``True`` if every original fragment is present in ``restored_text``.

    Used by :mod:`stx.translate.runner` as a final integrity check: if the
    translator dropped a placeholder or Salesforce ID, the row is rolled
    back to its source label rather than shipped with corrupt data.
    """

    for _token, original in token_map:
        if original not in restored_text:
            return False
    # Also confirm no sentinel slipped through unrestored.
    if re.search(r"__[A-Z]+_\d+__", restored_text):
        return False
    return True
