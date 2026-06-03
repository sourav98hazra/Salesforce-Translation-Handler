"""Dialog for overriding Salesforce character length limits."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...validate import get_all_limits, get_limit_overrides, set_limit_overrides


class LimitsOverrideDialog(QDialog):
    """Dialog to view and override Salesforce character limits.

    Displays all known component types with their default limits
    in an editable table. The user can set custom limits which
    apply for the current session only.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Custom Length Limits")
        self.setMinimumWidth(550)
        self.setMinimumHeight(400)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        # Info label
        info = QLabel(
            "Override Salesforce character limits for this session only. "
            "Changes are not saved to disk."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #475569; padding: 6px; font-style: italic;")
        layout.addWidget(info)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(
            ["Component Type", "Default Limit", "Custom Limit"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table, stretch=1)

        # Populate
        self._populate_table()

        # Buttons
        btn_layout = QHBoxLayout()
        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.setToolTip("Clear all custom values back to defaults.")
        self._reset_btn.clicked.connect(self._on_reset)
        btn_layout.addWidget(self._reset_btn)

        btn_layout.addStretch(1)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setToolTip("Apply custom limits for this session.")
        self._apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self._apply_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

    def _populate_table(self) -> None:
        """Populate the table with all known limits and current overrides."""
        all_limits = get_all_limits()
        current_overrides = get_limit_overrides()

        sorted_keys = sorted(all_limits.keys())
        self._table.setRowCount(len(sorted_keys))

        for row, comp_key in enumerate(sorted_keys):
            default_limit = all_limits[comp_key]

            # Component Type (read-only)
            type_item = QTableWidgetItem(comp_key)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, type_item)

            # Default Limit (read-only)
            default_item = QTableWidgetItem(str(default_limit))
            default_item.setFlags(default_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            default_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(row, 1, default_item)

            # Custom Limit (editable spinbox)
            spinbox = QSpinBox()
            spinbox.setMinimum(1)
            spinbox.setMaximum(99999)
            custom_value = current_overrides.get(comp_key, default_limit)
            spinbox.setValue(custom_value)
            self._table.setCellWidget(row, 2, spinbox)

    def _on_reset(self) -> None:
        """Reset all custom values back to defaults."""
        all_limits = get_all_limits()
        sorted_keys = sorted(all_limits.keys())
        for row, comp_key in enumerate(sorted_keys):
            spinbox = self._table.cellWidget(row, 2)
            if spinbox is not None:
                spinbox.setValue(all_limits[comp_key])

    def _on_apply(self) -> None:
        """Apply custom limits after user confirmation."""
        result = QMessageBox.warning(
            self,
            "Override Character Limits",
            "You are overriding Salesforce character limits. "
            "Translations exceeding the actual platform limits may fail on import. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        # Collect overrides (only where value differs from default)
        all_limits = get_all_limits()
        sorted_keys = sorted(all_limits.keys())
        overrides: dict[str, int] = {}

        for row, comp_key in enumerate(sorted_keys):
            spinbox = self._table.cellWidget(row, 2)
            if spinbox is not None:
                custom_value = spinbox.value()
                default_value = all_limits[comp_key]
                if custom_value != default_value:
                    overrides[comp_key] = custom_value

        set_limit_overrides(overrides)
        self.accept()
