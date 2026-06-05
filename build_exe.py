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

# All paths are resolved to absolutes from the location of THIS script, so
# `python build_exe.py` works no matter which directory you run it from.
# (Previously the relative "src" / "src/stx/gui/assets/logo.ico" paths only
# resolved when invoked from the repo root; running it from anywhere else
# made PyInstaller miss the `stx` package -> "No module named stx.gui.app"
# at runtime.)
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
ENTRY = ROOT / "launcher.py"
ICON = ROOT / "src" / "stx" / "gui" / "assets" / "logo.ico"
ASSETS = ROOT / "src" / "stx" / "gui" / "assets"
NAME = "SalesforceTranslationHandler"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / f"{NAME}.spec"

# PyInstaller's --add-data separator differs by OS (";" on Windows, ":" else).
_DATA_SEP = ";" if sys.platform == "win32" else ":"

# ``--windowed`` hides the console on Windows / produces a Mac .app bundle.
# Built dynamically so we can use absolute paths and only add --icon when the
# icon actually exists on disk.
# Use --onedir when building for the installer (env var set by installer/build_installer.py)
import os as _os
_ONEDIR = _os.environ.get("STX_PYINSTALLER_ONEDIR", "") == "1"

EXTRA_FLAGS: list[str] = [
    "--onedir" if _ONEDIR else "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
    "--paths",
    str(SRC),
    "--distpath",
    str(DIST),
    "--workpath",
    str(BUILD),
    "--specpath",
    str(ROOT),
    "--add-data",
    f"{ASSETS}{_DATA_SEP}stx/gui/assets",
]
if ICON.is_file():
    EXTRA_FLAGS += ["--icon", str(ICON)]

# Hidden imports openpyxl / deep_translator / bs4 sometimes need explicitly.
HIDDEN_IMPORTS: list[str] = [
    "stx",
    "stx.cli",
    "stx.model",
    "stx.languages",
    "stx.stf",
    "stx.stf.parser",
    "stx.stf.writer",
    "stx.excel",
    "stx.excel.exporter",
    "stx.excel.importer",
    "stx.validate",
    "stx.autofix",
    "stx.scope",
    "stx.memory",
    "stx.glossary",
    "stx.project",
    "stx.wakelock",
    "stx.fuzzy",
    "stx.translate",
    "stx.translate.base",
    "stx.translate.factory",
    "stx.translate.google_free",
    "stx.translate.deepl_paid",
    "stx.translate.azure",
    "stx.translate.openai_llm",
    "stx.translate.protect",
    "stx.translate.runner",
    "stx.translate.rate_limit",
    "stx.gui",
    "stx.gui.app",
    "stx.gui.main_window",
    "stx.gui.state",
    "stx.gui.workers",
    "stx.gui.theme",
    "stx.gui.settings",
    "stx.gui.settings_dialog",
    "stx.gui.about_dialog",
    "stx.gui.pages",
    "stx.gui.pages.base",
    "stx.gui.pages.phase1_import",
    "stx.gui.pages.phase2_excel",
    "stx.gui.pages.phase3_translate",
    "stx.gui.pages.phase4_review",
    "stx.gui.pages.phase5_validate",
    "stx.gui.pages.phase6_export",
    "stx.gui.app_history",
    "stx.gui.find_replace_dialog",
    "stx.find_replace",
    "stx.gui.undo",
    "stx.gui.secrets",
    "stx.gui.dialogs",
    "stx.gui.dialogs.override_dialog",
    "stx.gui.dialogs.limits_override_dialog",
    "stx.session",
    "stx.checkpoint",
    "stx.lang_detect",
    "openpyxl",
    "openpyxl.cell._writer",
    "deep_translator",
    "bs4",
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
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
        "--collect-submodules",
        "stx",
        *EXTRA_FLAGS,
    ]
    for module in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", module])
    cmd.append(str(ENTRY))

    print("Building from project root:", ROOT)
    print("Running:", " ".join(cmd))
    # cwd=ROOT guarantees PyInstaller resolves everything from the repo root
    # regardless of the directory the user launched this script from.
    result = subprocess.run(cmd, check=False, cwd=str(ROOT))
    if result.returncode != 0:
        return result.returncode

    print()
    print("Build complete.  Artifacts in:", DIST.resolve())
    produced = sorted(DIST.iterdir()) if DIST.exists() else []
    for entry in produced:
        print("  -", entry.name)

    exe_suffix = ".exe" if sys.platform == "win32" else ""
    exe_path = DIST / f"{NAME}{exe_suffix}"
    if exe_path.exists():
        print()
        print("Double-click this file to launch the app:")
        print("   ", exe_path.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
