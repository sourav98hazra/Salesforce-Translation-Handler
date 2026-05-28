"""STF (Salesforce Translation Format) parsing and writing.

The :mod:`stx.stf` package converts between :class:`stx.model.Document`
instances and the on-disk ``.stf`` file format used by Salesforce's
Translation Workbench.

The writer produces files that are byte-compatible with the format
emitted by the legacy ``ExcelToSTFV2.ps1`` script: UTF-8, ``LF`` line
endings, no BOM, with the exact header and section-separator layout.
"""

from __future__ import annotations

from .parser import parse_stf, parse_stf_text
from .writer import (
    STFWriteResult,
    write_stf_files,
    render_full_stf,
    render_translated_only_stf,
    render_untranslated_only_stf,
)

__all__ = [
    "parse_stf",
    "parse_stf_text",
    "write_stf_files",
    "render_full_stf",
    "render_translated_only_stf",
    "render_untranslated_only_stf",
    "STFWriteResult",
]
