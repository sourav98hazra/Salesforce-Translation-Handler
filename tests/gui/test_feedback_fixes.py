"""Tests for feedback issues 8-20 fixes."""

import pytest

from stx.gui.state import AppState, PhaseStatus


class TestResetPageExists:
    """Every phase page must expose a reset_page() method."""

    @pytest.fixture
    def state(self):
        return AppState()

    def test_phase1_has_reset_page(self, state, qtbot):
        from stx.gui.pages.phase1_import import Phase1ImportPage
        page = Phase1ImportPage(state)
        qtbot.addWidget(page)
        assert hasattr(page, "reset_page")
        page.reset_page()  # should not raise

    def test_phase2_has_reset_page(self, state, qtbot):
        from stx.gui.pages.phase2_excel import Phase2ExcelPage
        page = Phase2ExcelPage(state)
        qtbot.addWidget(page)
        assert hasattr(page, "reset_page")
        page.reset_page()

    def test_phase3_has_reset_page(self, state, qtbot):
        from stx.gui.pages.phase3_translate import Phase3TranslatePage
        page = Phase3TranslatePage(state)
        qtbot.addWidget(page)
        assert hasattr(page, "reset_page")
        page.reset_page()

    def test_phase4_has_reset_page(self, state, qtbot):
        from stx.gui.pages.phase4_review import Phase4ReviewPage
        page = Phase4ReviewPage(state)
        qtbot.addWidget(page)
        assert hasattr(page, "reset_page")
        page.reset_page()

    def test_phase5_has_reset_page(self, state, qtbot):
        from stx.gui.pages.phase5_validate import Phase5ValidatePage
        page = Phase5ValidatePage(state)
        qtbot.addWidget(page)
        assert hasattr(page, "reset_page")
        page.reset_page()

    def test_phase6_has_reset_page(self, state, qtbot):
        from stx.gui.pages.phase6_export import Phase6ExportPage
        page = Phase6ExportPage(state)
        qtbot.addWidget(page)
        assert hasattr(page, "reset_page")
        page.reset_page()


class TestButtonLabels:
    """Verify renamed button labels (issue 16)."""

    @pytest.fixture
    def state(self):
        return AppState()

    def test_phase5_save_button_label(self, state, qtbot):
        from stx.gui.pages.phase5_validate import Phase5ValidatePage
        page = Phase5ValidatePage(state)
        qtbot.addWidget(page)
        assert page._save_btn.text() == "Save Workbook"

    def test_phase5_report_button_label(self, state, qtbot):
        from stx.gui.pages.phase5_validate import Phase5ValidatePage
        page = Phase5ValidatePage(state)
        qtbot.addWidget(page)
        assert page._download_report_btn.text() == "Export Validation Report"

    def test_phase2_save_copy_label(self, state, qtbot):
        from stx.gui.pages.phase2_excel import Phase2ExcelPage
        page = Phase2ExcelPage(state)
        qtbot.addWidget(page)
        assert page._save_copy_btn.text() == "Save a Copy..."

    def test_phase4_save_button_label(self, state, qtbot):
        from stx.gui.pages.phase4_review import Phase4ReviewPage
        page = Phase4ReviewPage(state)
        qtbot.addWidget(page)
        assert page._save_btn.text() == "Save Workbook"


class TestSettingsDialogFlags:
    """Settings dialog must have proper window flags (issue 19)."""

    def test_settings_has_window_flags(self, qtbot):
        from PySide6.QtCore import Qt
        from stx.gui.settings_dialog import SettingsDialog
        dialog = SettingsDialog()
        qtbot.addWidget(dialog)
        flags = dialog.windowFlags()
        assert flags & Qt.WindowType.WindowMinimizeButtonHint
        assert flags & Qt.WindowType.WindowMaximizeButtonHint
        assert flags & Qt.WindowType.WindowCloseButtonHint


class TestPreviousPhaseNavigation:
    """Previous Phase action navigates backward (issue 12)."""

    def test_previous_phase_from_phase3(self, qtbot):
        from stx.gui.main_window import MainWindow
        win = MainWindow()
        qtbot.addWidget(win)
        win._goto(2)  # Phase 3
        win._action_previous_phase()
        assert win._stack.currentIndex() == 1

    def test_previous_phase_clamped_at_zero(self, qtbot):
        from stx.gui.main_window import MainWindow
        win = MainWindow()
        qtbot.addWidget(win)
        win._goto(0)  # Phase 1
        win._action_previous_phase()
        assert win._stack.currentIndex() == 0


class TestPhaseGating:
    """Continue buttons mark phase as DONE (issue 15)."""

    @pytest.fixture
    def state(self):
        return AppState()

    def test_phase4_continue_marks_done(self, state, qtbot):
        from stx.gui.pages.phase4_review import Phase4ReviewPage
        from stx.model import Document, Entry
        state.document = Document(
            entries=[Entry(key="k1", label="Hello", translation="Hola")],
            language="Spanish",
            language_code="es",
        )
        page = Phase4ReviewPage(state)
        qtbot.addWidget(page)
        # Simulate continue (just call the handler directly)
        page._on_continue_to_phase5()
        assert state.phase_status[3] == PhaseStatus.DONE
