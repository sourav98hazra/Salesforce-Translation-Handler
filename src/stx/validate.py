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
    "CustomField": 80,
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
}

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

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "key": self.key,
            "message": self.message,
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
    for entry in doc.entries:
        _check_entry(entry, report)
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
            report.issues.append(
                ValidationIssue(
                    category="duplicate_key",
                    severity="error",
                    key=key,
                    message=f"Key occurs {count} times; Salesforce import will fail or overwrite.",
                )
            )


def _check_entry(entry: Entry, report: ValidationReport) -> None:
    if not entry.translation.strip():
        return  # untranslated rows are valid by definition

    # Length limit
    limit = _LENGTH_LIMITS.get(entry.component_type)
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
            )
        )

    # Empty translation that nevertheless made it into the file
    if entry.translation and not entry.translation.strip():
        report.issues.append(
            ValidationIssue(
                category="empty_translation",
                severity="warning",
                key=entry.key,
                message="Translation is whitespace-only; will re-import as untranslated.",
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
            )
        )
