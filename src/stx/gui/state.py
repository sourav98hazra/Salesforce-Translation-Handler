"""Shared application state passed between GUI pages.

The state object is created once by :class:`stx.gui.main_window.MainWindow`
and handed to every page.  Pages mutate the state rather than passing
data through signals, which keeps page code small and focused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..model import Document
from ..translate.runner import SheetSummary, StatusEntry


@dataclass
class AppState:
    """Mutable run-state that the GUI threads through every phase.

    Attributes
    ----------
    document:
        The active :class:`Document`.  Set by phase 1 (Import STF) or by
        loading an existing Excel workbook in any later phase.
    source_stf_path / organized_xlsx_path / translated_xlsx_path / reviewed_xlsx_path:
        Last on-disk artifact for each phase, populated when the user
        clicks "Save..." -- used by subsequent phases as the default
        suggested path.
    output_dir:
        Last directory the user picked for STF export.
    translation_summaries / translation_statuses:
        Audit data captured during phase 3, used to write the audit
        sheets in subsequent saves.
    target_language_name / target_language_code / source_language_code:
        Selected translation parameters.  Pre-populated from the source
        STF's metadata header when available.
    """

    document: Optional[Document] = None

    source_stf_path: Optional[Path] = None
    organized_xlsx_path: Optional[Path] = None
    translated_xlsx_path: Optional[Path] = None
    reviewed_xlsx_path: Optional[Path] = None
    output_dir: Optional[Path] = None

    translation_summaries: List[SheetSummary] = field(default_factory=list)
    translation_statuses: List[StatusEntry] = field(default_factory=list)

    source_language_code: str = "en"
    target_language_code: str = "ja"
    target_language_name: str = "Japanese"

    def reset_translation_audit(self) -> None:
        self.translation_summaries = []
        self.translation_statuses = []
    
    def reset_all(self) -> None:
        """Reset all application state to initial values."""
        self.document = None
        self.source_stf_path = None
        self.organized_xlsx_path = None
        self.translated_xlsx_path = None
        self.reviewed_xlsx_path = None
        self.output_dir = None
        self.translation_summaries = []
        self.translation_statuses = []
        self.source_language_code = "en"
        self.target_language_code = "ja"
        self.target_language_name = "Japanese"
    
    def reset_from_phase(self, phase: int) -> None:
        """Reset state starting from a specific phase onwards."""
        if phase <= 1:
            # Reset everything from Phase 1 onwards
            self.reset_all()
        elif phase <= 2:
            # Reset from Phase 2 onwards - keep source STF and document
            self.organized_xlsx_path = None
            self.translated_xlsx_path = None
            self.reviewed_xlsx_path = None
            self.output_dir = None
            self.translation_summaries = []
            self.translation_statuses = []
        elif phase <= 3:
            # Reset from Phase 3 onwards - keep source and organized workbook
            self.translated_xlsx_path = None
            self.reviewed_xlsx_path = None
            self.translation_summaries = []
            self.translation_statuses = []
        elif phase <= 4:
            # Reset from Phase 4 onwards - keep everything up to translation
            self.reviewed_xlsx_path = None
        elif phase <= 5:
            # Reset Phase 5 - keep everything up to review
            pass
