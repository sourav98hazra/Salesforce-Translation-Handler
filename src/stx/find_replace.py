"""Find & Replace utility for batch text replacement across Document entries.

This module provides the core replacement logic used by both the GUI
Find & Replace dialog and the CLI ``stx replace`` command.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List

from .model import Document, Entry


class ReplaceScope(Enum):
    """Which field(s) to search in."""

    TRANSLATION = "translation"
    LABEL = "label"
    KEY = "key"
    ALL = "all"


@dataclass
class Replacement:
    """A single replacement result.

    Attributes
    ----------
    row:
        Index into Document.entries.
    field:
        Which field was modified ('translation', 'label', or 'key').
    old_value:
        The original field value before replacement.
    new_value:
        The field value after replacement.
    """

    row: int
    field: str
    old_value: str
    new_value: str


def find_matches(
    doc: Document,
    find: str,
    *,
    case_sensitive: bool = False,
    use_regex: bool = False,
    scope: ReplaceScope = ReplaceScope.TRANSLATION,
) -> int:
    """Count how many entries have at least one match.

    Returns the total number of field matches (one entry can contribute
    multiple matches if scope is ALL and multiple fields match).
    """
    if not find:
        return 0
    pattern = _compile_pattern(find, case_sensitive=case_sensitive, use_regex=use_regex)
    if pattern is None:
        return 0

    count = 0
    for entry in doc.entries:
        for _field_name, value in _iter_fields(entry, scope):
            if pattern.search(value):
                count += 1
    return count


def compute_replacements(
    doc: Document,
    find: str,
    replace: str,
    *,
    case_sensitive: bool = False,
    use_regex: bool = False,
    scope: ReplaceScope = ReplaceScope.TRANSLATION,
) -> List[Replacement]:
    """Compute all replacements without modifying the document.

    Returns a list of :class:`Replacement` objects describing each change.
    """
    if not find:
        return []
    pattern = _compile_pattern(find, case_sensitive=case_sensitive, use_regex=use_regex)
    if pattern is None:
        return []

    results: List[Replacement] = []
    for row, entry in enumerate(doc.entries):
        for field_name, value in _iter_fields(entry, scope):
            new_value = pattern.sub(replace, value)
            if new_value != value:
                results.append(Replacement(row=row, field=field_name, old_value=value, new_value=new_value))
    return results


def apply_replacements(doc: Document, replacements: List[Replacement]) -> int:
    """Apply pre-computed replacements to the document in place.

    Returns the number of replacements applied.
    """
    for rep in replacements:
        entry = doc.entries[rep.row]
        if rep.field == "translation":
            doc.entries[rep.row] = Entry(
                key=entry.key, label=entry.label, translation=rep.new_value, approved=entry.approved
            )
        elif rep.field == "label":
            doc.entries[rep.row] = Entry(
                key=entry.key, label=rep.new_value, translation=entry.translation, approved=entry.approved
            )
        elif rep.field == "key":
            doc.entries[rep.row] = Entry(
                key=rep.new_value, label=entry.label, translation=entry.translation, approved=entry.approved
            )
    return len(replacements)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compile_pattern(find: str, *, case_sensitive: bool, use_regex: bool) -> "re.Pattern | None":
    """Compile the search pattern. Returns None on invalid regex."""
    flags = 0 if case_sensitive else re.IGNORECASE
    if use_regex:
        try:
            return re.compile(find, flags)
        except re.error:
            return None
    else:
        return re.compile(re.escape(find), flags)


def _iter_fields(entry: Entry, scope: ReplaceScope):
    """Yield (field_name, value) tuples for the given scope."""
    if scope == ReplaceScope.TRANSLATION:
        yield ("translation", entry.translation)
    elif scope == ReplaceScope.LABEL:
        yield ("label", entry.label)
    elif scope == ReplaceScope.KEY:
        yield ("key", entry.key)
    elif scope == ReplaceScope.ALL:
        yield ("key", entry.key)
        yield ("label", entry.label)
        yield ("translation", entry.translation)
