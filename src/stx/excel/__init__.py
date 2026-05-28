"""Excel exporters and importers for STF documents.

The on-disk layout matches the legacy ``stftoexcel_v2.ps1`` and
``translate_excel_fixed.py`` scripts: one sheet per
``ComponentType_Status`` group, plus a ``Content Details`` index sheet
that lists the contents of the workbook.

After translation, two additional sheets are appended to record progress:

* ``Translation_Summary`` -- per-sheet counts.
* ``Translation_Status_Log`` -- per-row status / failure reason.
"""

from __future__ import annotations

from .exporter import (
    ExcelExportResult,
    export_document_to_excel,
    write_translation_audit_sheets,
)
from .importer import import_document_from_excel

__all__ = [
    "ExcelExportResult",
    "export_document_to_excel",
    "write_translation_audit_sheets",
    "import_document_from_excel",
]
