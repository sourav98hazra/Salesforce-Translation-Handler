"""Shared application state passed between GUI pages.

The state object is created once by :class:`stx.gui.main_window.MainWindow`
and handed to every page.  Pages mutate the state rather than passing
data through signals, which keeps page code small and focused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Set

from ..glossary import Glossary
from ..memory import TranslationMemory
from ..model import Document
from ..scope import Scope
from ..translate.runner import SheetSummary, StatusEntry

if TYPE_CHECKING:
    from ..validate import ValidationReport


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
        On-disk path of the active project file (reserved for future use).
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
    source_language_name: str = "English"
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

    imported_translations: Optional[dict] = None
    imported_translations_path: Optional[Path] = None
    imported_translations_enabled: bool = False

    retranslate_existing: bool = False

    # Phase 3 translation scope tracking
    translation_failed_indices: Set[int] = field(default_factory=set)
    translation_scope_indices: Set[int] = field(default_factory=set)

    phase_status: List[PhaseStatus] = field(
        default_factory=lambda: [PhaseStatus.IDLE for _ in range(6)]
    )

    # ---- Workflow context fields ----
    active_workflow: bool = False
    original_source_path: Optional[Path] = None
    current_working_path: Optional[Path] = None
    current_working_artifact_type: Optional[str] = None
    workflow_started_from_phase: Optional[int] = None
    current_phase: int = 0
    completed_phases: Set[int] = field(default_factory=set)
    has_unsaved_changes: bool = False
    last_validation_report: Optional[Any] = None
    last_translation_progress: Optional[dict] = None
    last_export_paths: Optional[List[Path]] = None

    def reset_translation_audit(self) -> None:
        self.translation_summaries = []
        self.translation_statuses = []

    def set_phase(self, index: int, status: PhaseStatus) -> None:
        if 0 <= index < len(self.phase_status):
            self.phase_status[index] = status

    def set_active_workflow_context(
        self,
        document: Optional[Document],
        original_source_path: Optional[Path] = None,
        current_working_path: Optional[Path] = None,
        current_working_artifact_type: Optional[str] = None,
        start_phase: Optional[int] = None,
        current_phase: Optional[int] = None,
        override_existing: bool = False,
        reset_downstream: bool = True,
    ) -> None:
        """Set the active workflow context after loading a file.

        Parameters
        ----------
        document:
            The loaded Document to set as active.
        original_source_path:
            The original source file path (e.g. the .stf or .xlsx).
        current_working_path:
            The current working artifact on disk.
        current_working_artifact_type:
            One of 'stf', 'organized_excel', 'translated_excel',
            'reviewed_excel', 'fixed_excel', 'in_memory'.
        start_phase:
            The phase the workflow started from.
        current_phase:
            The phase to navigate to.
        override_existing:
            If True, clears stale state from a previous workflow.
        reset_downstream:
            If True, resets phase statuses for phases >= current_phase to IDLE.
        """
        self.active_workflow = True
        if document is not None:
            self.document = document
        if original_source_path is not None:
            self.original_source_path = original_source_path
        if current_working_path is not None:
            self.current_working_path = current_working_path
        if current_working_artifact_type is not None:
            self.current_working_artifact_type = current_working_artifact_type
        if start_phase is not None:
            self.workflow_started_from_phase = start_phase
            # Mark phases before start_phase as completed
            for i in range(start_phase):
                self.completed_phases.add(i)
        if current_phase is not None:
            self.current_phase = current_phase

        if override_existing:
            self.translation_summaries = []
            self.translation_statuses = []
            self.last_validation_report = None
            self.last_export_paths = None
            self.has_unsaved_changes = False

        if reset_downstream:
            phase = current_phase if current_phase is not None else 0
            for i in range(phase, len(self.phase_status)):
                self.phase_status[i] = PhaseStatus.IDLE

    def clear_workflow_context(self) -> None:
        """Reset all workflow fields to their defaults."""
        self.active_workflow = False
        self.original_source_path = None
        self.current_working_path = None
        self.current_working_artifact_type = None
        self.workflow_started_from_phase = None
        self.current_phase = 0
        self.completed_phases = set()
        self.has_unsaved_changes = False
        self.last_validation_report = None
        self.last_translation_progress = None
        self.last_export_paths = None

    def mark_phase_completed(self, phase_index: int) -> None:
        """Mark a phase as completed in the workflow context."""
        self.completed_phases.add(phase_index)
        self.set_phase(phase_index, PhaseStatus.DONE)
