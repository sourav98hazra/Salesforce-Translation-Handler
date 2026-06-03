"""Pre-export validation for STF documents.

The validator runs a battery of cheap checks and produces a structured
report.  The desktop GUI shows the report in a panel before phase 5;
the CLI emits it as a table.  None of the checks block export -- they
surface issues so a human can decide whether to ship.

Categories
----------
* ``duplicate_key``      -- two rows share the same Salesforce key.
* ``length_limit``       -- translation exceeds the limit Salesforce
                            enforces for that component type.
* ``empty_translation``  -- whitespace-only translation produced (will
                            re-import as untranslated).
* ``token_drift``        -- translation lost (or gained) a sentinel-style
                            placeholder relative to the source label.
* ``html_mismatch``      -- source and translation have different HTML
                            tag structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .model import Document, Entry

# Salesforce length limits per component type (best-effort; the platform
# enforces these on import).  When the component type is not in this map we
# simply skip the length check for that row.
_LENGTH_LIMITS: dict[str, int] = {
    "CustomLabel": 1000,
    "CustomField": 40,          # default for field labels
    "ButtonOrLink": 1000,
    "CustomApp": 40,
    "CustomTab": 40,
    "CustomReportType": 80,
    "DataCategory": 40,
    "PicklistValue": 255,
    "QuickAction": 80,
    "RecordType": 80,
    "WebLink": 1000,
    "ManagedContentNodeType": 4000,
    "ApexSharingReason": 80,
    "PathAssistantStepInfo": 4000,
    "GlobalValueSet": 255,
    "StandardValueSet": 255,
    "ValidationRule": 255,
    "Flow": 4000,
}

# CustomField has different limits depending on the key suffix.
# HelpText/InlineHelpText allow up to 255 chars; Description up to 1000;
# field labels and RelatedListLabel are 40.
_CUSTOM_FIELD_SUFFIX_LIMITS: dict[str, int] = {
    "FieldLabel": 40,
    "HelpText": 255,
    "InlineHelpText": 255,
    "Description": 1000,
    "RelatedListLabel": 40,
}

# User-defined overrides. Keys use the format from get_all_limits(),
# e.g. 'CustomField.FieldLabel', 'CustomLabel', etc.
_limit_overrides: dict[str, int] = {}


def set_limit_overrides(overrides: dict[str, int]) -> None:
    """Set user-defined limit overrides (replaces any existing overrides)."""
    global _limit_overrides
    _limit_overrides = dict(overrides)


def clear_limit_overrides() -> None:
    """Clear all user-defined limit overrides."""
    global _limit_overrides
    _limit_overrides = {}


def get_limit_overrides() -> dict[str, int]:
    """Return the current user-defined limit overrides."""
    return dict(_limit_overrides)


def get_all_limits() -> dict[str, int]:
    """Return a merged view of all known limits including sub-types.

    Format: {'CustomField.FieldLabel': 40, 'CustomField.HelpText': 255, ...}
    """
    result: dict[str, int] = {}
    for comp_type, limit in _LENGTH_LIMITS.items():
        if comp_type == "CustomField":
            # CustomField sub-types are listed individually
            for suffix, suffix_limit in _CUSTOM_FIELD_SUFFIX_LIMITS.items():
                result[f"CustomField.{suffix}"] = suffix_limit
            # Also include the base entry for unrecognized suffixes
            result["CustomField"] = limit
        else:
            result[comp_type] = limit
    return result


def get_length_limit(component_type: str, key: str) -> int | None:
    """Return the Salesforce length limit for a given component type and key.

    Checks user-defined overrides first, then falls back to built-in defaults.
    For CustomField, the limit varies by suffix (FieldLabel=40, HelpText=255,
    Description=1000).
    """
    if component_type == "CustomField":
        # Check key suffix after the last dot
        suffix = key.rsplit(".", 1)[-1] if "." in key else ""
        # Check override for specific sub-type first
        override_key = f"CustomField.{suffix}" if suffix in _CUSTOM_FIELD_SUFFIX_LIMITS else None
        if override_key and override_key in _limit_overrides:
            return _limit_overrides[override_key]
        if suffix in _CUSTOM_FIELD_SUFFIX_LIMITS:
            return _CUSTOM_FIELD_SUFFIX_LIMITS[suffix]
        # Fall through to default CustomField limit
        if "CustomField" in _limit_overrides:
            return _limit_overrides["CustomField"]
        return _LENGTH_LIMITS.get(component_type)
    # Non-CustomField types: check override, then default
    if component_type in _limit_overrides:
        return _limit_overrides[component_type]
    return _LENGTH_LIMITS.get(component_type)


# Keep private alias for internal/backward compatibility
_get_length_limit = get_length_limit

_HTML_TAG_RE = re.compile(r"<\s*/?\s*([A-Za-z][\w-]*)\b")
_PLACEHOLDER_RE = re.compile(r"\{![^}]+\}")
_MESSAGE_FORMAT_RE = re.compile(r"\{(?!!)[A-Za-z0-9_,\.\s]+\}")


@dataclass
class ValidationIssue:
    """A single issue raised during validation."""

    category: str
    severity: str  # "error" | "warning" | "info"
    key: str
    message: str
    component: str = ""

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "key": self.key,
            "message": self.message,
            "component": self.component,
        }


@dataclass
class ValidationReport:
    """Result of :func:`validate_document`."""

    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def by_category(self) -> dict[str, List[ValidationIssue]]:
        grouped: dict[str, List[ValidationIssue]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.category, []).append(issue)
        return grouped


def validate_document(doc: Document) -> ValidationReport:
    """Run every validator over ``doc`` and return a structured report."""

    report = ValidationReport()
    _check_duplicate_keys(doc, report)
    approved_count = 0
    for entry in doc.entries:
        if entry.approved:
            approved_count += 1
            continue
        _check_entry(entry, report)
    if approved_count > 0:
        report.issues.append(
            ValidationIssue(
                category="approved_skipped",
                severity="info",
                key="",
                message=f"{approved_count} approved entry(ies) skipped during validation.",
                component="",
            )
        )
    return report


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_duplicate_keys(doc: Document, report: ValidationReport) -> None:
    seen: dict[str, int] = {}
    for entry in doc.entries:
        seen[entry.key] = seen.get(entry.key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            # Extract component from the key's first dot-segment
            if "." in key:
                component = key.split(".", 1)[0] or "Unknown"
            else:
                component = key or "Unknown"
            report.issues.append(
                ValidationIssue(
                    category="duplicate_key",
                    severity="error",
                    key=key,
                    message=f"Key occurs {count} times; Salesforce import will fail or overwrite.",
                    component=component,
                )
            )


def _check_entry(entry: Entry, report: ValidationReport) -> None:
    component = entry.component_type

    # Completely empty (no translation at all) - not an issue
    if not entry.translation:
        return

    # Whitespace-only translation - warn and return (no further checks needed)
    if not entry.translation.strip():
        report.issues.append(
            ValidationIssue(
                category="empty_translation",
                severity="warning",
                key=entry.key,
                message="Translation is whitespace-only; will re-import as untranslated.",
                component=component,
            )
        )
        return

    # Length limit
    limit = get_length_limit(entry.component_type, entry.key)
    if limit is not None and len(entry.translation) > limit:
        report.issues.append(
            ValidationIssue(
                category="length_limit",
                severity="error",
                key=entry.key,
                message=(
                    f"Translation length {len(entry.translation)} exceeds limit {limit} "
                    f"for {entry.component_type}."
                ),
                component=component,
            )
        )

    # Token drift -- placeholders / message-format tokens must round-trip.
    src_placeholders = sorted(_PLACEHOLDER_RE.findall(entry.label))
    tgt_placeholders = sorted(_PLACEHOLDER_RE.findall(entry.translation))
    if src_placeholders != tgt_placeholders:
        report.issues.append(
            ValidationIssue(
                category="token_drift",
                severity="error",
                key=entry.key,
                message=(
                    f"Placeholder mismatch -- source has {src_placeholders}, "
                    f"translation has {tgt_placeholders}."
                ),
                component=component,
            )
        )

    src_msgfmt = sorted(_MESSAGE_FORMAT_RE.findall(entry.label))
    tgt_msgfmt = sorted(_MESSAGE_FORMAT_RE.findall(entry.translation))
    if src_msgfmt != tgt_msgfmt:
        report.issues.append(
            ValidationIssue(
                category="token_drift",
                severity="error",
                key=entry.key,
                message=(
                    f"MessageFormat token mismatch -- source has {src_msgfmt}, "
                    f"translation has {tgt_msgfmt}."
                ),
                component=component,
            )
        )

    # HTML tag structure
    src_tags = sorted(_HTML_TAG_RE.findall(entry.label))
    tgt_tags = sorted(_HTML_TAG_RE.findall(entry.translation))
    if src_tags != tgt_tags:
        report.issues.append(
            ValidationIssue(
                category="html_mismatch",
                severity="warning",
                key=entry.key,
                message=(
                    f"HTML tag set differs -- source: {src_tags}, "
                    f"translation: {tgt_tags}."
                ),
                component=component,
            )
        )
