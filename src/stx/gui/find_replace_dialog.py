"""Find & Replace dialog for Phase 4 (Review).

Opens as a modal dialog that previews match counts in real-time and
returns a list of Replacement objects when the user clicks Replace All.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..find_replace import Replacement, ReplaceScope, compute_replacements, find_matches
from ..model import Document


_SCOPE_LABELS = [
    ("Translations Only", ReplaceScope.TRANSLATION),
]


class FindReplaceDialog(QDialog):
    """Modal dialog for global find-and-replace across document entries.

    After the dialog is accepted (Replace All clicked), call
    :meth:`replacements` to get the list of computed replacements.
    """

    def __init__(self, doc: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._replacements: List[Replacement] = []
        self.setWindowTitle("Find & Replace")
        self.setMinimumWidth(420)
        self._build()
        self._update_preview()

    # ------------------------------------------------------------------ public

    @property
    def replacements(self) -> List[Replacement]:
        """Computed replacements from the last Replace All click."""
        return self._replacements

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Find field
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Find:"))
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("Text to find...")
        self._find_edit.textChanged.connect(self._on_find_changed)
        find_row.addWidget(self._find_edit, stretch=1)
        layout.addLayout(find_row)

        # Replace field
        replace_row = QHBoxLayout()
        replace_row.addWidget(QLabel("Replace:"))
        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("Replacement text...")
        replace_row.addWidget(self._replace_edit, stretch=1)
        layout.addLayout(replace_row)

        # Options row
        options_row = QHBoxLayout()
        self._case_check = QCheckBox("Match Case")
        self._case_check.toggled.connect(self._on_option_changed)
        options_row.addWidget(self._case_check)

        self._regex_check = QCheckBox("Regex")
        self._regex_check.toggled.connect(self._on_option_changed)
        options_row.addWidget(self._regex_check)

        options_row.addWidget(QLabel("Scope:"))
        self._scope_combo = QComboBox()
        for label, _scope in _SCOPE_LABELS:
            self._scope_combo.addItem(label)
        self._scope_combo.currentIndexChanged.connect(self._on_option_changed)
        options_row.addWidget(self._scope_combo)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        # Scope clarity banner -- spells out exactly what will be searched
        # and changed so users are never surprised by what Replace All hits.
        self._scope_label = QLabel("Scope: Translations only (labels and keys are never modified).")
        self._scope_label.setWordWrap(True)
        self._scope_label.setStyleSheet(
            "color: #3730a3; background: #e0e7ff; padding: 6px 8px; "
            "border-radius: 4px; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(self._scope_label)

        # Preview count
        self._preview_label = QLabel("0 matches")
        self._preview_label.setStyleSheet("color: #475569; font-weight: 600;")
        layout.addWidget(self._preview_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        # "Find" counts and reports matches WITHOUT changing anything.
        self._find_btn = QPushButton("Find")
        self._find_btn.setToolTip(
            "Count how many matches exist for the search text, without "
            "replacing anything."
        )
        self._find_btn.clicked.connect(self._on_find)
        btn_row.addWidget(self._find_btn)

        self._replace_btn = QPushButton("Replace All")
        self._replace_btn.setDefault(True)
        self._replace_btn.clicked.connect(self._on_replace_all)
        btn_row.addWidget(self._replace_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        # Debounce timer for preview updates
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._update_preview)

    # ------------------------------------------------------------------ options

    def _get_scope(self) -> ReplaceScope:
        idx = self._scope_combo.currentIndex()
        if 0 <= idx < len(_SCOPE_LABELS):
            return _SCOPE_LABELS[idx][1]
        return ReplaceScope.TRANSLATION

    # ------------------------------------------------------------------ slots

    def _on_find_changed(self) -> None:
        self._debounce.start()

    def _on_option_changed(self) -> None:
        self._debounce.start()

    def _update_preview(self) -> None:
        find_text = self._find_edit.text()
        if not find_text:
            self._preview_label.setText("0 matches")
            self._replace_btn.setEnabled(False)
            return
        count = find_matches(
            self._doc,
            find_text,
            case_sensitive=self._case_check.isChecked(),
            use_regex=self._regex_check.isChecked(),
            scope=self._get_scope(),
        )
        self._preview_label.setText(f"{count} match{'es' if count != 1 else ''}")
        self._replace_btn.setEnabled(count > 0)

    def _on_find(self) -> None:
        """Count and report matches without performing any replacement."""
        find_text = self._find_edit.text()
        if not find_text:
            self._preview_label.setText("Enter text in the Find field to search.")
            self._replace_btn.setEnabled(False)
            return
        count = find_matches(
            self._doc,
            find_text,
            case_sensitive=self._case_check.isChecked(),
            use_regex=self._regex_check.isChecked(),
            scope=self._get_scope(),
        )
        scope_text = self._scope_combo.currentText().lower()
        noun = "match" if count == 1 else "matches"
        self._preview_label.setText(
            f"Found {count} {noun} in {scope_text} (nothing changed yet)."
        )
        self._replace_btn.setEnabled(count > 0)

    def _on_replace_all(self) -> None:
        find_text = self._find_edit.text()
        replace_text = self._replace_edit.text()
        if not find_text:
            return
        self._replacements = compute_replacements(
            self._doc,
            find_text,
            replace_text,
            case_sensitive=self._case_check.isChecked(),
            use_regex=self._regex_check.isChecked(),
            scope=self._get_scope(),
        )
        self.accept()
