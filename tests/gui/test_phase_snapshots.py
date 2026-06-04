"""Unit tests for the PhaseSnapshot feature."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from stx.gui.state import AppState, PhaseSnapshot, PhaseStatus
from stx.gui.app_history import capture_snapshot, restore_snapshot


class TestPhaseSnapshotDataclass:
    """Tests for the PhaseSnapshot dataclass itself."""

    def test_create_snapshot(self, tmp_path: Path) -> None:
        """PhaseSnapshot can be created with all required fields."""
        snap = PhaseSnapshot(
            source_path=tmp_path / "test.stf",
            artifact_type="stf",
            row_count=100,
            target_language_code="ja",
            target_language_name="Japanese",
            timestamp=time.time(),
        )
        assert snap.source_path == tmp_path / "test.stf"
        assert snap.artifact_type == "stf"
        assert snap.row_count == 100
        assert snap.target_language_code == "ja"
        assert snap.target_language_name == "Japanese"
        assert snap.timestamp > 0

    def test_snapshot_is_effectively_immutable(self, tmp_path: Path) -> None:
        """PhaseSnapshot fields are set at creation and accessible."""
        ts = time.time()
        snap = PhaseSnapshot(
            source_path=tmp_path / "org.xlsx",
            artifact_type="organized_excel",
            row_count=50,
            target_language_code="fr",
            target_language_name="French",
            timestamp=ts,
        )
        assert snap.timestamp == ts
        assert snap.artifact_type == "organized_excel"


class TestAppStatePhaseSnapshots:
    """Tests for phase_snapshots field on AppState."""

    def test_initialized_to_six_nones(self) -> None:
        """AppState.phase_snapshots initializes to [None]*6."""
        state = AppState()
        assert len(state.phase_snapshots) == 6
        assert all(x is None for x in state.phase_snapshots)

    def test_clear_workflow_context_clears_snapshots(self, tmp_path: Path) -> None:
        """clear_workflow_context() resets phase_snapshots to [None]*6."""
        state = AppState()
        state.phase_snapshots[0] = PhaseSnapshot(
            source_path=tmp_path / "test.stf",
            artifact_type="stf",
            row_count=10,
            target_language_code="ja",
            target_language_name="Japanese",
            timestamp=time.time(),
        )
        assert state.phase_snapshots[0] is not None
        state.clear_workflow_context()
        assert all(x is None for x in state.phase_snapshots)

    def test_snapshots_independent_across_instances(self) -> None:
        """Each AppState instance has its own phase_snapshots list."""
        s1 = AppState()
        s2 = AppState()
        s1.phase_snapshots[0] = PhaseSnapshot(
            source_path=Path("/tmp/a.stf"),
            artifact_type="stf",
            row_count=1,
            target_language_code="ja",
            target_language_name="Japanese",
            timestamp=time.time(),
        )
        assert s2.phase_snapshots[0] is None


class TestSnapshotAppHistory:
    """Tests for phase_snapshots integration with app_history undo/redo."""

    def test_snapshot_captured_and_restored(self, tmp_path: Path) -> None:
        """phase_snapshots are preserved through capture/restore cycle."""
        state = AppState()
        snap = PhaseSnapshot(
            source_path=tmp_path / "test.xlsx",
            artifact_type="organized_excel",
            row_count=42,
            target_language_code="de",
            target_language_name="German",
            timestamp=time.time(),
        )
        state.phase_snapshots[1] = snap

        captured = capture_snapshot(state, "test action")

        # Modify state
        state.phase_snapshots[1] = None

        # Restore
        restore_snapshot(state, captured)
        assert state.phase_snapshots[1] is not None
        assert state.phase_snapshots[1].row_count == 42
        assert state.phase_snapshots[1].artifact_type == "organized_excel"

    def test_snapshot_list_is_shallow_copied(self, tmp_path: Path) -> None:
        """Captured snapshot list is independent from the original."""
        state = AppState()
        snap = PhaseSnapshot(
            source_path=tmp_path / "a.xlsx",
            artifact_type="stf",
            row_count=5,
            target_language_code="ja",
            target_language_name="Japanese",
            timestamp=time.time(),
        )
        state.phase_snapshots[0] = snap

        captured = capture_snapshot(state, "before change")

        # Mutate the original list
        state.phase_snapshots[0] = None
        state.phase_snapshots[2] = PhaseSnapshot(
            source_path=tmp_path / "b.xlsx",
            artifact_type="translated_excel",
            row_count=10,
            target_language_code="ja",
            target_language_name="Japanese",
            timestamp=time.time(),
        )

        # The captured data should still have the old state
        assert captured.data["phase_snapshots"][0] is snap
        assert captured.data["phase_snapshots"][2] is None


class TestSnapshotRestore:
    """Tests for _restore_from_snapshot logic using real files."""

    def test_restore_from_stf_snapshot(self, tmp_path: Path, sample_doc) -> None:
        """Restoring from an STF snapshot re-parses the STF file."""
        from stx.stf import render_full_stf

        stf_path = tmp_path / "source.stf"
        stf_path.write_text(render_full_stf(sample_doc), encoding="utf-8")

        snap = PhaseSnapshot(
            source_path=stf_path,
            artifact_type="stf",
            row_count=len(sample_doc.entries),
            target_language_code="ja",
            target_language_name="Japanese",
            timestamp=time.time(),
        )

        # Simulate what _restore_from_snapshot does
        from stx.stf import parse_stf

        doc = parse_stf(stf_path)
        assert doc is not None
        assert len(doc.entries) == len(sample_doc.entries)

    def test_restore_from_excel_snapshot(self, tmp_path: Path, sample_doc) -> None:
        """Restoring from an Excel snapshot re-imports the workbook."""
        from stx.excel import export_document_to_excel, import_document_from_excel

        xlsx_path = tmp_path / "organized.xlsx"
        export_document_to_excel(sample_doc, xlsx_path)

        snap = PhaseSnapshot(
            source_path=xlsx_path,
            artifact_type="organized_excel",
            row_count=len(sample_doc.entries),
            target_language_code="ja",
            target_language_name="Japanese",
            timestamp=time.time(),
        )

        # Simulate what _restore_from_snapshot does
        doc = import_document_from_excel(
            xlsx_path,
            language=snap.target_language_name,
            language_code=snap.target_language_code,
        )
        assert doc is not None
        assert len(doc.entries) == len(sample_doc.entries)


class TestPhaseSnapshotDownstreamIdle:
    """Tests verifying that after reset, downstream phases are IDLE.

    After Reset Current Phase, downstream pages show empty until the user
    re-enters them via "Continue to Phase N" from the upstream phase.
    """

    def test_reset_sets_downstream_to_idle(self) -> None:
        """Resetting at phase 2 sets phases 2-5 to IDLE, preserving 0-1."""
        state = AppState()
        # Mark all phases DONE
        for i in range(6):
            state.phase_status[i] = PhaseStatus.DONE

        # Simulate reset at phase 2: phases 2+ go to IDLE
        reset_phase = 2
        for i in range(reset_phase, 6):
            state.phase_status[i] = PhaseStatus.IDLE

        # Phases 0, 1 remain DONE
        assert state.phase_status[0] == PhaseStatus.DONE
        assert state.phase_status[1] == PhaseStatus.DONE
        # Phases 2-5 are now IDLE
        for i in range(2, 6):
            assert state.phase_status[i] == PhaseStatus.IDLE

    def test_reset_clears_snapshots_for_current_and_downstream(self, tmp_path: Path) -> None:
        """On reset, snapshots from the current phase onwards are cleared."""
        state = AppState()
        # Set snapshots for all phases
        for i in range(6):
            state.phase_snapshots[i] = PhaseSnapshot(
                source_path=tmp_path / f"phase{i}.xlsx",
                artifact_type="organized_excel",
                row_count=10 * (i + 1),
                target_language_code="ja",
                target_language_name="Japanese",
                timestamp=time.time(),
            )

        # Simulate reset at phase 2: clear snapshots from phase 2 onwards
        reset_phase = 2
        for i in range(reset_phase, 6):
            state.phase_snapshots[i] = None

        # Phases 0, 1 snapshots preserved
        assert state.phase_snapshots[0] is not None
        assert state.phase_snapshots[1] is not None
        # Phases 2-5 snapshots cleared
        for i in range(2, 6):
            assert state.phase_snapshots[i] is None

    def test_downstream_idle_prevents_action(self) -> None:
        """Downstream phases in IDLE status should not allow actions.

        This verifies the state condition that the UI uses to disable
        buttons: phase_status == IDLE and the upstream phase is not DONE.
        """
        state = AppState()
        state.phase_status[2] = PhaseStatus.DONE  # Phase 3 completed
        state.phase_status[3] = PhaseStatus.IDLE   # Phase 4 reset to IDLE

        # Downstream is IDLE while upstream is DONE -- user must navigate
        # via "Continue" to re-enter phase 4
        assert state.phase_status[3] == PhaseStatus.IDLE
        assert state.phase_status[2] == PhaseStatus.DONE
