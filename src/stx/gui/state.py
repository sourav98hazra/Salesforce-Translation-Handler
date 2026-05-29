"""Shared application state passed between GUI pages.

The state object is created once by :class:`stx.gui.main_window.MainWindow`
and handed to every page.  Pages mutate the state rather than passing
data through signals, which keeps page code small and focused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import List, Optional

from ..glossary import Glossary
from ..memory import TranslationMemory
from ..model import Document
from ..scope import Scope
from ..translate.runner import SheetSummary, StatusEntry


class PhaseStatus(IntEnum):
    """Sidebar status indicator for a phase."""

    IDLE = 0
    RUNNING = 1
    DONE = 2
    ERROR = 3


@dataclass
class AppState:
    """Mutable run-state that the GUI threads through every phase.

    Attributes
    ----------
    document:
        The active :class:`Document`.  Set by phase 1 (Import STF) or by
        loading an existing Excel workbook in any later phase.
    source_stf_path / organized_xlsx_path / translated_xlsx_path / reviewed_xlsx_path:
        Last on-disk artifact for each phase.
    output_dir:
        Last directory the user picked for STF export.
    translation_summaries / translation_statuses:
        Audit data captured during phase 3.
    source_language_code / target_language_code / target_language_name:
        Translation parameters.
    target_languages_batch:
        Optional list of additional target codes for multi-language batch.
    backend_key:
        Translator backend (``google`` / ``deepl`` / ``azure`` / ``openai``).
    backend_options:
        Per-backend kwargs (e.g. ``api_key``).
    workers / rate_limit_per_second:
        Translation runner concurrency / pacing.
    scope, scope_path:
        Active translation scope and its on-disk source.
    glossary, glossary_path:
        Active glossary and its on-disk source.
    memory, memory_path:
        Active translation memory and its on-disk source.
    phase_status:
        Per-phase status flags driving the sidebar badges.
    project_path:
        On-disk path of the active ``.stxproject`` file (if any).
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
    target_languages_batch: List[str] = field(default_factory=list)

    backend_key: str = "google"
    backend_options: dict = field(default_factory=dict)
    workers: int = 4
    rate_limit_per_second: float = 8.0

    scope: Optional[Scope] = None
    scope_path: Optional[Path] = None
    glossary: Optional[Glossary] = None
    glossary_path: Optional[Path] = None
    memory: Optional[TranslationMemory] = None
    memory_path: Optional[Path] = None

    phase_status: List[PhaseStatus] = field(
        default_factory=lambda: [PhaseStatus.IDLE for _ in range(7)]
    )
    project_path: Optional[Path] = None

    def reset_translation_audit(self) -> None:
        self.translation_summaries = []
        self.translation_statuses = []

    def set_phase(self, index: int, status: PhaseStatus) -> None:
        if 0 <= index < len(self.phase_status):
            self.phase_status[index] = status
