"""Pre-flight confirmation dialog shown before starting translation.

Summarises the current translation options so the user can review
them and either proceed or cancel to adjust settings first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .pages.base import clamp_to_screen


class PreflightDialog(QDialog):
    """Show a summary of translation settings before the run starts.

    The user can tick "Don't show again" to suppress future dialogs.
    Returns ``Accepted`` if the user proceeds, ``Rejected`` if they cancel.
    """

    def __init__(
        self,
        *,
        source_lang: str,
        target_lang: str,
        rows_to_translate: int,
        total_rows: int,
        backend: str,
        workers: int,
        use_infile: bool,
        use_tm: bool,
        use_fuzzy: bool,
        use_imported: bool,
        imported_count: int,
        retranslate: bool,
        has_checkpoint: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ready to translate?")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )
        clamp_to_screen(self, 520, 480)
        self._build(
            source_lang=source_lang,
            target_lang=target_lang,
            rows_to_translate=rows_to_translate,
            total_rows=total_rows,
            backend=backend,
            workers=workers,
            use_infile=use_infile,
            use_tm=use_tm,
            use_fuzzy=use_fuzzy,
            use_imported=use_imported,
            imported_count=imported_count,
            retranslate=retranslate,
            has_checkpoint=has_checkpoint,
        )

    def dont_show_again(self) -> bool:
        return self._dont_show_check.isChecked()

    # ------------------------------------------------------------------ build

    def _build(self, **kw) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        header = QLabel(
            f"<b>Translating {kw['rows_to_translate']:,} rows</b> "
            f"&nbsp;({kw['source_lang']} → {kw['target_lang']})"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet("font-size: 14px; padding: 4px 0;")
        layout.addWidget(header)

        # --- Translation options summary
        opts_box = QGroupBox("Translation options (from Translation menu)")
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setSpacing(4)

        def _opt_row(enabled: bool, label: str, note: str = "") -> QHBoxLayout:
            row = QHBoxLayout()
            icon = QLabel("✓" if enabled else "✗")
            icon.setStyleSheet(
                f"color: {'#16a34a' if enabled else '#94a3b8'}; "
                "font-size: 14px; font-weight: 700; min-width: 20px;"
            )
            row.addWidget(icon)
            lbl = QLabel(f"<b>{label}</b>" + (f" <span style='color:#64748b;font-size:11px;'>— {note}</span>" if note else ""))
            lbl.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(lbl, stretch=1)
            return row

        opts_layout.addLayout(
            _opt_row(kw["use_infile"], "Use in-file translations",
                     "reuse translations already in this file")
        )
        opts_layout.addLayout(
            _opt_row(kw["use_tm"], "Use Translation Memory cache",
                     "reuse from previous runs")
        )
        opts_layout.addLayout(
            _opt_row(kw["use_fuzzy"] and kw["use_tm"], "Use Fuzzy matching",
                     "approximate TM matches" if kw["use_tm"] else "requires TM enabled")
        )

        if kw["use_imported"] and kw["imported_count"] > 0:
            opts_layout.addLayout(
                _opt_row(True, "Use imported translations",
                         f"{kw['imported_count']:,} translations from external file")
            )
        else:
            opts_layout.addLayout(
                _opt_row(False, "Use imported translations",
                         "no file imported" if not kw["use_imported"] else "no translations loaded")
            )

        if kw["retranslate"]:
            opts_layout.addLayout(
                _opt_row(True, "Retranslate existing rows",
                         "⚠ ALL rows will be retranslated — existing translations will be overwritten")
            )
        else:
            opts_layout.addLayout(
                _opt_row(False, "Retranslate existing rows",
                         "only untranslated rows will be processed (default)")
            )

        layout.addWidget(opts_box)

        # --- Scope / backend summary
        scope_box = QGroupBox("Run summary")
        scope_layout = QVBoxLayout(scope_box)
        scope_layout.setSpacing(4)

        def _info(label: str, value: str) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = QLabel(f"<span style='color:#64748b;'>{label}:</span>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setFixedWidth(160)
            val = QLabel(f"<b>{value}</b>")
            val.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(lbl)
            row.addWidget(val, stretch=1)
            return row

        scope_layout.addLayout(_info("Backend", kw["backend"]))
        scope_layout.addLayout(_info("Workers", str(kw["workers"])))
        scope_layout.addLayout(_info("Rows to translate", f"{kw['rows_to_translate']:,} of {kw['total_rows']:,} total"))
        if kw["has_checkpoint"]:
            scope_layout.addLayout(
                _info("Resume", "✓ Checkpoint found — will resume from last position")
            )

        layout.addWidget(scope_box)

        # --- Tip
        tip = QLabel(
            "<i>You can change options in the <b>Translation</b> menu before starting.</i>"
        )
        tip.setTextFormat(Qt.TextFormat.RichText)
        tip.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(tip)

        # --- Don't show again
        self._dont_show_check = QCheckBox("Don't show this dialog again")
        self._dont_show_check.setToolTip(
            "Skip this summary in future runs.  You can re-enable it via the Translation menu."
        )
        layout.addWidget(self._dont_show_check)

        # --- Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start translation")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel — review settings")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
