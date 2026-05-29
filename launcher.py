"""Single entry-point script used by PyInstaller and the OS launchers.

Distinct from ``src/stx/gui/app.py`` so the bundled executable has a
predictable, non-package top-level script that PyInstaller can hash and
sign cleanly.  Importing the GUI is still done lazily so a missing
PySide6 produces a friendly error rather than a stack trace.
"""

from __future__ import annotations

import sys
import traceback


def _show_fatal_error(message: str) -> None:
    """Best-effort fatal-error dialog when the GUI fails to start.

    On a packaged Windows / macOS build the launcher is detached from a
    terminal, so a printed traceback would simply disappear.  We try a
    Tkinter message box (in the standard library) before falling back
    to ``stderr``.
    """
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Salesforce Translation Manager", message)
        root.destroy()
    except Exception:  # noqa: BLE001
        sys.stderr.write(message + "\n")


def main() -> int:
    try:
        from stx.gui.app import main as gui_main
    except ImportError as exc:
        _show_fatal_error(
            "Could not start the GUI because PySide6 is not installed.\n\n"
            "Open a terminal in the project folder and run:\n"
            "    pip install -e \".[gui]\"\n\n"
            f"Underlying error: {exc}"
        )
        return 1

    try:
        return gui_main()
    except Exception:  # noqa: BLE001
        _show_fatal_error(
            "The application crashed unexpectedly.\n\n"
            + traceback.format_exc()
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
