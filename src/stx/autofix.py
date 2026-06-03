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
    _MESSAGE_FORMAT_RE,
    _PLACEHOLDER_RE,
    get_length_limit,
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
    manual_review: List[Tuple[str, str]] = None  # (key, reason)

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = []
        if self.manual_review is None:
            self.manual_review = []


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


def _smart_truncate(text: str, max_len: int, preserve_tokens: list | None = None) -> str:
    """Truncate text to max_len, preserving important tokens at the end.

    Steps:
    1. Collapse multiple spaces to single spaces.
    2. Reserve space for tokens that must be preserved.
    3. Truncate at a word boundary when possible.
    4. Append ellipsis and preserved tokens.
    """
    # Step 1: Collapse multiple spaces.
    text = re.sub(r" {2,}", " ", text).strip()

    if len(text) <= max_len:
        return text

    # Step 2: Calculate reserved space for tokens.
    reserved = 0
    if preserve_tokens:
        # Space needed: 1 leading space + each token + spaces between them
        reserved = sum(len(t) for t in preserve_tokens)
        if preserve_tokens:
            reserved += len(preserve_tokens)  # 1 space before each token

    # Step 3: Available length = max_len - reserved - 1 (for ellipsis char).
    available = max_len - reserved - 1
    if available < 1:
        # Edge case: tokens alone nearly exceed max_len.
        # Allow at least 1 char of text; Step 6 will hard-truncate if needed.
        available = 1

    # Step 4: Truncate and find word boundary.
    truncated = text[:available]
    last_space = truncated.rfind(" ")
    if last_space > available * 0.5:
        truncated = truncated[:last_space]

    # Step 5: Build result with ellipsis and tokens.
    result = truncated.rstrip() + "\u2026"
    if preserve_tokens:
        result += " " + " ".join(preserve_tokens)

    # Step 6: If result still exceeds max_len, hard-truncate.
    if len(result) > max_len:
        result = result[: max_len - 1] + "\u2026"

    return result


def fix_trim_to_length(entry: Entry) -> Optional[FixResult]:
    """Truncate the translation to the Salesforce length limit for its component.

    This is the fallback fixer used when no translator backend is available.
    It truncates at a word boundary and appends an ellipsis character.
    """
    limit = get_length_limit(entry.component_type, entry.key)
    if limit is None or not entry.translation.strip():
        return None
    if len(entry.translation) <= limit:
        return None

    # First try: collapsing whitespace may bring it under the limit.
    collapsed = re.sub(r" {2,}", " ", entry.translation).strip()
    if len(collapsed) <= limit:
        return FixResult(
            fixed=True,
            entry=Entry(key=entry.key, label=entry.label, translation=collapsed, approved=entry.approved),
            description=f"Collapsed whitespace to fit within limit ({len(collapsed)}/{limit} chars).",
        )

    # Gather placeholders and message format tokens present in the translation.
    tokens_to_preserve: list[str] = []
    src_placeholders = _PLACEHOLDER_RE.findall(entry.label)
    src_msg_tokens = _MESSAGE_FORMAT_RE.findall(entry.label)
    for tok in src_placeholders:
        if tok in entry.translation:
            tokens_to_preserve.append(tok)
    for tok in src_msg_tokens:
        if tok in entry.translation:
            tokens_to_preserve.append(tok)

    truncated = _smart_truncate(
        entry.translation, limit, preserve_tokens=tokens_to_preserve or None
    )

    return FixResult(
        fixed=True,
        entry=Entry(key=entry.key, label=entry.label, translation=truncated, approved=entry.approved),
        description=f"Trimmed from {len(entry.translation)} to {len(truncated)} chars (limit {limit}).",
    )


def fix_length_with_retranslation(
    entry: Entry,
    *,
    target_lang: str,
    backend_name: str = "google",
    api_key: Optional[str] = None,
) -> FixResult:
    """Attempt to fix a length_limit issue by re-translating with a length constraint.

    Step 1: Call the configured translator backend with an instruction to
    produce a shorter translation that fits within the character limit.

    Step 2: If re-translation still exceeds the limit or fails, flag the
    entry for manual review (do not truncate).

    Parameters
    ----------
    entry:
        The entry whose translation exceeds the length limit.
    target_lang:
        Target language code (e.g. "ja", "fr").
    backend_name:
        Translator backend key (e.g. "google", "deepl", "openai").
    api_key:
        Optional API key for backends that require one.

    Returns
    -------
    FixResult
        Either a successfully shortened translation or a manual-review flag.
    """
    limit = get_length_limit(entry.component_type, entry.key)
    if limit is None:
        return FixResult(fixed=False, entry=entry, description="")

    # Build a constrained translation prompt
    prompt = (
        f"Translate the following text into {target_lang} using no more than "
        f"{limit} characters: {entry.label}"
    )

    try:
        from .translate.factory import make_backend, check_backend_available

        available, reason = check_backend_available(backend_name, api_key=api_key)
        if not available:
            # Backend not available - fall back to word-boundary truncation
            fallback = fix_trim_to_length(entry)
            if fallback is not None:
                fallback.description += " (backend unavailable: " + reason + ")"
                return fallback
            return FixResult(fixed=False, entry=entry, description="")

        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key

        translator = make_backend(backend_name, **kwargs)
        new_translation = translator.translate(prompt, "en", target_lang)

        # Check if the re-translated text fits within the limit
        if new_translation and len(new_translation.strip()) <= limit:
            return FixResult(
                fixed=True,
                entry=Entry(
                    key=entry.key,
                    label=entry.label,
                    translation=new_translation.strip(),
                    approved=entry.approved,
                ),
                description=(
                    f"Re-translated with length constraint "
                    f"({len(new_translation.strip())}/{limit} chars)."
                ),
            )
        else:
            # Re-translation still exceeds limit - flag for manual review
            return FixResult(
                fixed=False,
                entry=entry,
                description=(
                    f"Re-translation still exceeds limit "
                    f"({len(new_translation.strip()) if new_translation else 0}/{limit} chars). "
                    f"Requires manual review."
                ),
            )
    except Exception:  # noqa: BLE001
        # Any failure (network, import, etc.) - flag for manual review
        return FixResult(
            fixed=False,
            entry=entry,
            description=(
                f"Re-translation failed. "
                f"Translation length {len(entry.translation)} exceeds limit {limit}. "
                f"Requires manual review."
            ),
        )


def fix_normalize_whitespace(entry: Entry) -> Optional[FixResult]:
    """Collapse runs of spaces and strip leading/trailing whitespace differences."""
    if not entry.translation:
        return None
    text = entry.translation
    # Collapse runs of spaces (not newlines) to a single space.
    normalized = re.sub(r" {2,}", " ", text)
    # Strip leading/trailing whitespace that differs from the source.
    src_leading = len(entry.label) - len(entry.label.lstrip())
    src_trailing = len(entry.label) - len(entry.label.rstrip())
    tgt_leading = len(normalized) - len(normalized.lstrip())
    tgt_trailing = len(normalized) - len(normalized.rstrip())
    if tgt_leading > src_leading:
        normalized = normalized.lstrip()
        if src_leading:
            normalized = entry.label[:src_leading] + normalized
    if tgt_trailing > src_trailing:
        normalized = normalized.rstrip()
        if src_trailing:
            normalized = normalized + entry.label[-src_trailing:]
    if normalized == entry.translation:
        return None
    return FixResult(
        fixed=True,
        entry=Entry(key=entry.key, label=entry.label, translation=normalized, approved=entry.approved),
        description="Normalized whitespace (collapsed multiple spaces or stripped extra leading/trailing).",
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
    """If tags present in the source are missing from the translation, restore them."""
    if not entry.translation.strip():
        return None
    src_tags = _HTML_TAG_RE.findall(entry.label)
    tgt_tags = _HTML_TAG_RE.findall(entry.translation)
    if sorted(set(src_tags)) == sorted(set(tgt_tags)) or not src_tags:
        return None
    # Preserve source order: deduplicate while keeping first-occurrence order.
    tgt_set = set(tgt_tags)
    missing_tags = [t for t in dict.fromkeys(src_tags) if t not in tgt_set]
    if not missing_tags:
        return None
    # Safety limit: more than 3 missing tags is too complex for auto-fix.
    if len(missing_tags) > 3:
        return None

    # Detect self-closing tags in the source (e.g., <br/>, <br>, <hr/>).
    _self_closing_re = re.compile(r"<\s*(" + "|".join(re.escape(t) for t in missing_tags) + r")\s*/?\s*>")
    self_closing_in_source = set()
    for m in _self_closing_re.finditer(entry.label):
        tag_name = m.group(1)
        # Check if there's no corresponding closing tag in the source.
        if f"</{tag_name}" not in entry.label:
            self_closing_in_source.add(tag_name)

    new_translation = entry.translation
    paired_tags = [t for t in missing_tags if t not in self_closing_in_source]
    sc_tags = [t for t in missing_tags if t in self_closing_in_source]

    # Wrap in paired tags (outermost first, source order).
    for tag in paired_tags:
        new_translation = f"<{tag}>{new_translation}</{tag}>"

    # Append self-closing tags at the end.
    for tag in sc_tags:
        new_translation = f"{new_translation}<{tag}/>"

    desc_parts = []
    if paired_tags:
        desc_parts.append(
            "Wrapped translation in " + ", ".join(f"<{t}>...</{t}>" for t in paired_tags)
        )
    if sc_tags:
        desc_parts.append("Appended " + ", ".join(f"<{t}/>" for t in sc_tags))
    description = "; ".join(desc_parts) + " to match source HTML structure."

    return FixResult(
        fixed=True,
        entry=Entry(key=entry.key, label=entry.label, translation=new_translation, approved=entry.approved),
        description=description,
    )


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
    fix_normalize_whitespace,
    fix_strip_whitespace_translation,
    fix_restore_placeholders,
    fix_restore_message_format,
    fix_restore_html_tags,
    fix_trim_to_length,
]


def auto_fix_document(
    doc: Document,
    *,
    fix_duplicates: bool = True,
    target_lang: Optional[str] = None,
    backend_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> AutoFixReport:
    """Apply every safe fixer to ``doc`` in place.

    Parameters
    ----------
    doc:
        Document to fix.  Modified in place.
    fix_duplicates:
        If ``True``, also deduplicate keys (keeps last occurrence).
    target_lang:
        Target language code for re-translation of length-limit issues.
        If not provided, falls back to simple truncation.
    backend_name:
        Translator backend key (e.g. "google", "deepl").
        If not provided, falls back to simple truncation.
    api_key:
        Optional API key for backends that require one.

    Returns
    -------
    AutoFixReport
        Summary of what was fixed, what couldn't be, and what needs
        manual review.
    """
    report = AutoFixReport()

    # Deduplicate keys first (changes the entry list).
    if fix_duplicates:
        dedup_report = fix_deduplicate_keys(doc)
        report.fixed_count += dedup_report.fixed_count
        report.details.extend(dedup_report.details)

    # Determine whether smart length fixing is available.
    use_smart_length = bool(target_lang and backend_name)

    # Per-entry fixes.
    new_entries: list[Entry] = []
    for entry in doc.entries:
        current = entry
        for fixer in _ENTRY_FIXERS:
            if fixer is fix_trim_to_length and use_smart_length:
                # Use smart re-translation for length issues instead of truncation
                limit = get_length_limit(current.component_type, current.key)
                if limit is not None and current.translation.strip() and len(current.translation) > limit:
                    result = fix_length_with_retranslation(
                        current,
                        target_lang=target_lang,
                        backend_name=backend_name,
                        api_key=api_key,
                    )
                    if result.fixed:
                        current = result.entry
                        report.fixed_count += 1
                        report.details.append((current.key, result.description))
                    else:
                        # Flag for manual review
                        report.unfixable_count += 1
                        report.manual_review.append((current.key, result.description))
                continue

            result = fixer(current)
            if result is not None and result.fixed:
                current = result.entry
                report.fixed_count += 1
                report.details.append((current.key, result.description))
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
