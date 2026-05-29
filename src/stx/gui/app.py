"""GUI application entry point.

Invoked via the ``stx-app`` console script (registered in
``pyproject.toml`` under ``[project.gui-scripts]``) or via ``stx gui``
on the CLI.
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    """Launch the desktop GUI."""

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - guarded by extras
        raise RuntimeError(
            "PySide6 is not installed. Install with: pip install '.[gui]'"
        ) from exc

    from . import settings as gui_settings
    from . import theme
    from .main_window import MainWindow

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Salesforce Translation Manager")
    app.setOrganizationName("Salesforce Translation Manager")

    # Force the Fusion style engine -- it fully honours QSS on every platform
    # (Windows / macOS / Linux).  Without this, the native Windows style
    # ignores most background-color rules and renders everything white.
    app.setStyle("Fusion")

    # Apply our custom theme (colors, borders, typography) on top of Fusion.
    theme.apply_theme(gui_settings.get_theme())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
