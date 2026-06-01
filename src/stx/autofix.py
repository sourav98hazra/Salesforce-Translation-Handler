"""Automatic fixers for common validation issues.

Each fixer is a pure function that takes an :class:`Entry` (and
optionally its source :class:`Entry` for cross-reference) and returns
either a *fixed* :class:`Entry` or ``None`` if the fixer cannot help.

Fixers are designed to be **deterministic and safe** -- they never
introduce data that wasn't already present in the source, and they
never corrupt working translations.  If in doubt, a fixer returns
``None`` and the row remains flagged for manual attention.

Supported auto-fix categories
------------------------------

* ``restore_placeholders`` -- if the translation dropped a placeholder
  that exists in the source label, re-insert it at the end of the
  translation (obvious position, flagged in a comment so the reviewer
  knows).
* ``restore_message_format`` -- same but for ``{0}``, ``{1}`` tokens.
* ``trim_to_length`` -- if the translation exceeds the Salesforce
  length limit for its component type, truncate it at a word boundary
  and append ``…``.
* ``deduplicate_key`` -- when the *same* key appears multiple times,
  keep only the last occurrence (Salesforce's own behaviour on import)
  and mark earlier duplicates for removal.
* ``restore_html_tags`` -- if a tag present in the source is missing
  from the translation, wrap the translation in the missing tag.
* ``strip_whitespace_translation`` -- if the translation is
  whitespace-only, clear it so it re-imports as untranslated (honest
  rather than misleading).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .model import Document, Entry
from .validate import (
    ValidationIssue,
    ValidationReport,
    _HTML_TAG_RE,
    _LENGTH_LIMITS,
    _MESSAGE_FORMAT_RE,
    _PLACEHOLDER_RE,
    validate_document,
)


@dataclass
class FixResult:
    """Outcome of a single fix attempt."""

    fixed: bool
    entry: Entry
    description: str = ""


@dataclass
class AutoFixReport:
    """Summary of all auto-fix attempts."""

    fixed_count: int = 0
    unfixable_count: int = 0
    details: List[Tuple[str, str]] = None  # (key, description)

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = []


# ---------------------------------------------------------------------------
# Individual fixers
# ---------------------------------------------------------------------------

def fix_restore_placeholders(entry: Entry) -> Optional[FixResult]:
    """Re-insert source placeholders that are missing from the translation."""
    if not entry.translation.strip():
        return None
    src_phs = set(_PLACEHOLDER_RE.findall(entry.label))
    tgt_phs = set(_PLACEHOLDER_RE.findall(entry.translation))
    missing = src_phs - tgt_phs
    if not missing:
        return None
    # Append missing placeholders at the end, separated by a space.
    appended = " ".join(sorted(missing))
    new_translation = f"{entry.translation.rstrip()} {appended}"
    return FixResult(
        fixed=True,
        entry=Entry(key=entry.key, label=entry.label, translation=new_translation, approved=entry.approved),
        description=f"Restored {len(missing)} placeholder(s): {', '.join(sorted(missing))}",
    )


def fix_restore_message_format(entry: Entry) -> Optional[FixResult]:
    """Re-insert source MessageFormat tokens that are missing from the translation."""
    if not entry.translation.strip():
        return None
    src_tokens = set(_MESSAGE_FORMAT_RE.findall(entry.label))
    tgt_tokens = set(_MESSAGE_FORMAT_RE.findall(entry.translation))
    missing = src_tokens - tgt_tokens
    if not missing:
        return None
    appended = " ".join(sorted(missing))
    new_translation = f"{entry.translation.rstrip()} {appended}"
    return FixResult(
        fixed=True,
        entry=Entry(key=entry.key, label=entry.label, translation=new_translation, approved=entry.approved),
        description=f"Restored {len(missing)} MessageFormat token(s): {', '.join(sorted(missing))}",
    )


def fix_trim_to_length(entry: Entry) -> Optional[FixResult]:
    """Truncate the translation to the Salesforce length limit for its component."""
    limit = _LENGTH_LIMITS.get(entry.component_type)
    if limit is None or not entry.translation.strip():
        return None
    if len(entry.translation) <= limit:
        return None
    # Truncate at a word boundary, leaving room for the ellipsis.
    target_len = limit - 1  # room for "…"
    truncated = entry.translation[:target_len]
    # Find the last space so we don't chop mid-word.
    last_space = truncated.rfind(" ")
    if last_space > target_len * 0.6:
        truncated = truncated[:last_space]
    truncated = truncated.rstrip() + "\u2026"
    return FixResult(
        fixed=True,
        entry=Entry(key=entry.key, label=entry.label, translation=truncated, approved=entry.approved),
        description=f"Trimmed from {len(entry.translation)} to {len(truncated)} chars (limit {limit}).",
    )


def fix_strip_whitespace_translation(entry: Entry) -> Optional[FixResult]:
    """Clear whitespace-only translations so they re-import as untranslated."""
    if entry.translation and not entry.translation.strip():
        return FixResult(
            fixed=True,
            entry=Entry(key=entry.key, label=entry.label, translation="", approved=entry.approved),
            description="Cleared whitespace-only translation.",
        )
    return None


def fix_restore_html_tags(entry: Entry) -> Optional[FixResult]:
    """If a tag present in the source is missing from the translation, wrap it."""
    if not entry.translation.strip():
        return None
    src_tags = sorted(set(_HTML_TAG_RE.findall(entry.label)))
    tgt_tags = sorted(set(_HTML_TAG_RE.findall(entry.translation)))
    if src_tags == tgt_tags or not src_tags:
        return None
    missing_tags = set(src_tags) - set(tgt_tags)
    if not missing_tags:
        return None
    # Simple strategy: wrap the translation in the outermost missing tag pair.
    # This is a heuristic; complex cases (nested mismatches) should be fixed
    # manually.  We only wrap if there's exactly one missing tag to keep it safe.
    if len(missing_tags) == 1:
        tag = missing_tags.pop()
        new_translation = f"<{tag}>{entry.translation}</{tag}>"
        return FixResult(
            fixed=True,
            entry=Entry(key=entry.key, label=entry.label, translation=new_translation, approved=entry.approved),
            description=f"Wrapped translation in <{tag}>...</{tag}> to match source HTML structure.",
        )
    return None


# ---------------------------------------------------------------------------
# Deduplication (operates on the full document rather than a single entry)
# ---------------------------------------------------------------------------

def fix_deduplicate_keys(doc: Document) -> AutoFixReport:
    """Remove duplicate-key entries, keeping the last occurrence.

    This mirrors Salesforce's own behaviour: when importing an STF with
    duplicate keys, the last value wins.  We mark earlier duplicates by
    clearing their key so they're dropped on the next write.

    Returns
    -------
    AutoFixReport
        How many duplicates were resolved.
    """
    report = AutoFixReport()
    # Find duplicates: key -> list of indices.
    seen: dict[str, list[int]] = {}
    for idx, entry in enumerate(doc.entries):
        seen.setdefault(entry.key, []).append(idx)

    to_remove: set[int] = set()
    for key, indices in seen.items():
        if len(indices) <= 1:
            continue
        # Keep last, remove earlier.
        for idx in indices[:-1]:
            to_remove.add(idx)
            report.details.append((key, f"Removed duplicate (keeping last occurrence at row {indices[-1] + 1})."))
            report.fixed_count += 1

    if to_remove:
        doc.entries = [e for i, e in enumerate(doc.entries) if i not in to_remove]

    return report


# ---------------------------------------------------------------------------
# Orchestrator: apply all fixers to a document
# ---------------------------------------------------------------------------

# Registry of per-entry fixers in priority order.
_ENTRY_FIXERS: List[Callable[[Entry], Optional[FixResult]]] = [
    fix_strip_whitespace_translation,
    fix_restore_placeholders,
    fix_restore_message_format,
    fix_restore_html_tags,
    fix_trim_to_length,
]


def auto_fix_document(doc: Document, *, fix_duplicates: bool = True) -> AutoFixReport:
    """Apply every safe fixer to ``doc`` in place.

    Parameters
    ----------
    doc:
        Document to fix.  Modified in place.
    fix_duplicates:
        If ``True``, also deduplicate keys (keeps last occurrence).

    Returns
    -------
    AutoFixReport
        Summary of what was fixed and what couldn't be.
    """
    report = AutoFixReport()

    # Deduplicate keys first (changes the entry list).
    if fix_duplicates:
        dedup_report = fix_deduplicate_keys(doc)
        report.fixed_count += dedup_report.fixed_count
        report.details.extend(dedup_report.details)

    # Per-entry fixes.
    new_entries: list[Entry] = []
    for entry in doc.entries:
        fixed_this_row = False
        current = entry
        for fixer in _ENTRY_FIXERS:
            result = fixer(current)
            if result is not None and result.fixed:
                current = result.entry
                report.fixed_count += 1
                report.details.append((current.key, result.description))
                fixed_this_row = True
        new_entries.append(current)

    doc.entries = new_entries
    return report


def auto_fix_entry(entry: Entry) -> Tuple[Entry, List[str]]:
    """Apply all per-entry fixers to a single entry.

    Returns the (possibly fixed) entry and a list of fix descriptions.
    Useful for the "Fix this row" button in the GUI.
    """
    descriptions: list[str] = []
    current = entry
    for fixer in _ENTRY_FIXERS:
        result = fixer(current)
        if result is not None and result.fixed:
            current = result.entry
            descriptions.append(result.description)
    return current, descriptions
