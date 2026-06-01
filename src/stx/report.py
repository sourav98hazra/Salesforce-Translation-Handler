"""Export validation reports to CSV, JSON, and HTML formats.

Each function takes a :class:`~stx.validate.ValidationReport` and writes
a formatted report to the given path.
"""

from __future__ import annotations

import csv
import json
from html import escape as html_escape
from pathlib import Path

from .validate import ValidationReport


def _component_from_key(key: str) -> str:
    """Extract component type from the first dot-segment of a key."""
    if "." in key:
        head = key.split(".", 1)[0]
        return head if head else "Unknown"
    return key or "Unknown"


def export_csv(report: ValidationReport, path: Path) -> None:
    """Write a CSV report with a summary row and one row per issue."""
    path = Path(path)
    error_count = len(report.errors)
    warning_count = len(report.warnings)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Summary row at top
        writer.writerow([
            f"# Summary: {error_count} error(s), {warning_count} warning(s), "
            f"{len(report.issues)} total issue(s)",
        ])
        # Header
        writer.writerow(["severity", "category", "component", "key", "message"])
        # Data rows
        for issue in report.issues:
            component = issue.component if issue.component else _component_from_key(issue.key)
            writer.writerow([
                issue.severity,
                issue.category,
                component,
                issue.key,
                issue.message,
            ])


def export_json(report: ValidationReport, path: Path) -> None:
    """Write a JSON report with summary, issues grouped by category, and flat list."""
    path = Path(path)
    error_count = len(report.errors)
    warning_count = len(report.warnings)

    issues_by_category: dict[str, list[dict]] = {}
    issues_flat: list[dict] = []

    for issue in report.issues:
        component = issue.component if issue.component else _component_from_key(issue.key)
        issue_dict = {
            "severity": issue.severity,
            "category": issue.category,
            "component": component,
            "key": issue.key,
            "message": issue.message,
        }
        issues_flat.append(issue_dict)
        issues_by_category.setdefault(issue.category, []).append(issue_dict)

    data = {
        "summary": {
            "errors": error_count,
            "warnings": warning_count,
            "total": len(report.issues),
        },
        "issues_by_category": issues_by_category,
        "issues": issues_flat,
    }

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_html(report: ValidationReport, path: Path) -> None:
    """Write a standalone HTML report with embedded CSS."""
    path = Path(path)
    error_count = len(report.errors)
    warning_count = len(report.warnings)

    # Group issues by category
    by_category: dict[str, list] = {}
    for issue in report.issues:
        by_category.setdefault(issue.category, []).append(issue)

    # Build table rows grouped by category
    table_rows = []
    for category, issues in by_category.items():
        table_rows.append(
            f'<tr class="category-header"><td colspan="5">'
            f'{html_escape(category)} ({len(issues)} issue(s))</td></tr>'
        )
        for issue in issues:
            component = issue.component if issue.component else _component_from_key(issue.key)
            sev_class = issue.severity
            table_rows.append(
                f"<tr>"
                f'<td class="{sev_class}">{html_escape(issue.severity)}</td>'
                f"<td>{html_escape(issue.category)}</td>"
                f"<td>{html_escape(component)}</td>"
                f"<td>{html_escape(issue.key)}</td>"
                f"<td>{html_escape(issue.message)}</td>"
                f"</tr>"
            )

    rows_html = "\n".join(table_rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Validation Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2em; color: #1a1a1a; }}
h1 {{ color: #1e3a5f; }}
.summary {{ background: #f0f4f8; padding: 1em; border-radius: 6px; margin-bottom: 1.5em; }}
.summary span {{ margin-right: 2em; font-weight: 600; }}
.errors {{ color: #dc2626; }}
.warnings {{ color: #d97706; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1em; }}
th, td {{ border: 1px solid #d1d5db; padding: 0.5em 0.75em; text-align: left; }}
th {{ background: #1e3a5f; color: white; }}
tr:nth-child(even) {{ background: #f9fafb; }}
tr.category-header {{ background: #e2e8f0; font-weight: 700; }}
td.error {{ color: #dc2626; font-weight: 600; }}
td.warning {{ color: #d97706; font-weight: 600; }}
td.info {{ color: #2563eb; font-weight: 600; }}
</style>
</head>
<body>
<h1>Validation Report</h1>
<div class="summary">
<span class="errors">Errors: {error_count}</span>
<span class="warnings">Warnings: {warning_count}</span>
<span>Total: {len(report.issues)}</span>
</div>
<table>
<thead>
<tr><th>Severity</th><th>Category</th><th>Component</th><th>Key</th><th>Message</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
