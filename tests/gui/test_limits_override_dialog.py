"""Tests for the LimitsOverrideDialog."""

from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from stx.validate import (
    clear_limit_overrides,
    get_all_limits,
    get_limit_overrides,
    set_limit_overrides,
)


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    """Ensure overrides are cleared before and after each test."""
    clear_limit_overrides()
    yield
    clear_limit_overrides()


def test_dialog_constructs(qtbot):
    """LimitsOverrideDialog can be instantiated without error."""
    from stx.gui.dialogs.limits_override_dialog import LimitsOverrideDialog

    dlg = LimitsOverrideDialog()
    qtbot.addWidget(dlg)
    assert dlg is not None


def test_dialog_table_populated(qtbot):
    """Dialog table is populated with all entries from get_all_limits()."""
    from stx.gui.dialogs.limits_override_dialog import LimitsOverrideDialog

    dlg = LimitsOverrideDialog()
    qtbot.addWidget(dlg)

    all_limits = get_all_limits()
    assert dlg._table.rowCount() == len(all_limits)

    # Verify that component types from get_all_limits are present in the table
    table_keys = set()
    for row in range(dlg._table.rowCount()):
        item = dlg._table.item(row, 0)
        table_keys.add(item.text())

    assert table_keys == set(all_limits.keys())


def test_apply_sets_overrides(qtbot, monkeypatch):
    """After setting a custom limit and triggering apply, overrides are set."""
    from stx.gui.dialogs.limits_override_dialog import LimitsOverrideDialog
    from PySide6.QtWidgets import QMessageBox

    dlg = LimitsOverrideDialog()
    qtbot.addWidget(dlg)

    # Find the row for "CustomLabel" and change its spinbox value
    all_limits = get_all_limits()
    sorted_keys = sorted(all_limits.keys())
    target_key = "CustomLabel"
    target_row = sorted_keys.index(target_key)

    spinbox = dlg._table.cellWidget(target_row, 2)
    original_value = all_limits[target_key]
    new_value = original_value + 100
    spinbox.setValue(new_value)

    # Monkeypatch QMessageBox.warning to auto-confirm
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    # Trigger apply
    dlg._on_apply()

    # Verify override was set
    overrides = get_limit_overrides()
    assert target_key in overrides
    assert overrides[target_key] == new_value


def test_reset_clears_spinbox_values(qtbot):
    """Reset to Defaults sets all spinboxes back to default values."""
    from stx.gui.dialogs.limits_override_dialog import LimitsOverrideDialog

    dlg = LimitsOverrideDialog()
    qtbot.addWidget(dlg)

    all_limits = get_all_limits()
    sorted_keys = sorted(all_limits.keys())

    # Change a spinbox value
    spinbox = dlg._table.cellWidget(0, 2)
    spinbox.setValue(99999)

    # Reset
    dlg._on_reset()

    # Verify all spinboxes match defaults
    for row, comp_key in enumerate(sorted_keys):
        spinbox = dlg._table.cellWidget(row, 2)
        assert spinbox.value() == all_limits[comp_key]
