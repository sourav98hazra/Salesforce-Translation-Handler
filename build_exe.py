"""Build a standalone executable using PyInstaller.

Produces a single-file binary in ``dist/`` that can be distributed to
machines without Python or pip installed.  Run this on the target OS
(Windows -> .exe, macOS -> .app, Linux -> ELF binary); PyInstaller does
not cross-compile.

Usage
-----
::

    pip install -e ".[gui]" pyinstaller
    python build_exe.py

The resulting binary is fully self-contained: it bundles Python, the
``stx`` package, PySide6, openpyxl, deep_translator, and beautifulsoup4.

Notes
-----
* ``--onefile`` produces a single executable; users on antivirus-strict
  Windows can switch to ``--onedir`` (faster startup, less suspicious to
  AV scanners) by editing ``EXTRA_FLAGS`` below.
* Code-signing is left to the distributor.  Pass ``--codesign-identity``
  on macOS or use ``signtool`` after the build on Windows.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ENTRY = ROOT / "launcher.py"
NAME = "SalesforceTranslationHandler"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / f"{NAME}.spec"

# ``--windowed`` hides the console on Windows / produces a Mac .app bundle.
# Add ``--icon path/to/icon.{ico,icns}`` if you have one.
EXTRA_FLAGS: list[str] = [
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
]

# Hidden imports openpyxl / deep_translator / bs4 sometimes need explicitly.
HIDDEN_IMPORTS: list[str] = [
    "stx",
    "stx.cli",
    "stx.gui.app",
    "stx.gui.main_window",
    "openpyxl",
    "openpyxl.cell._writer",
    "deep_translator",
    "bs4",
    "PySide6",
]


def main() -> int:
    if not ENTRY.exists():
        sys.stderr.write(f"Entry script {ENTRY} not found.\n")
        return 1

    # Verify pyinstaller is available before doing anything destructive.
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.stderr.write(
            "PyInstaller is not installed in this environment.\n"
            "Install it with:  pip install pyinstaller\n"
            f"Underlying error: {exc}\n"
        )
        return 1

    # Clean prior outputs (PyInstaller --clean alone leaves stale spec files).
    for path in (DIST, BUILD, SPEC):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()

    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        NAME,
        *EXTRA_FLAGS,
    ]
    for module in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", module])
    cmd.append(str(ENTRY))

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        return result.returncode

    print()
    print("Build complete.  Artifacts in:", DIST.resolve())
    if DIST.exists():
        for entry in DIST.iterdir():
            print("  -", entry.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
