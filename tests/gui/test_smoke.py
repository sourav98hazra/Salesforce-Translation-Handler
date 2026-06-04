"""GUI smoke tests using pytest-qt in offscreen mode.

These tests verify that the main window and key dialogs can be
constructed without errors. They do NOT test visual rendering
(that requires a real display and is verified via user screenshots).
"""
from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def test_main_window_constructs(qtbot):
    """MainWindow can be instantiated with all 6 phase pages."""
    from stx.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    assert window is not None


def test_settings_dialog_constructs(qtbot):
    """SettingsDialog opens without error."""
    from stx.gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_about_dialog_constructs(qtbot):
    """AboutDialog opens without error."""
    from stx.gui.about_dialog import AboutDialog

    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    assert dialog is not None
