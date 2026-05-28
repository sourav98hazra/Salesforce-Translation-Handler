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
    """Launch the desktop GUI.

    Parameters
    ----------
    argv:
        Optional argv list, defaults to :data:`sys.argv`.

    Returns
    -------
    int
        Exit code from the Qt event loop.
    """

    # Fail clearly if PySide6 isn't installed -- the CLI surfaces a friendly
    # message but a direct call from elsewhere should also degrade gracefully.
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - guarded by extras
        raise RuntimeError(
            "PySide6 is not installed. Install with: pip install '.[gui]'"
        ) from exc

    from .main_window import MainWindow

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Allow Ctrl+C to terminate the GUI when launched from a terminal.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Salesforce Translation Handler")
    app.setOrganizationName("Salesforce Translation Handler")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
