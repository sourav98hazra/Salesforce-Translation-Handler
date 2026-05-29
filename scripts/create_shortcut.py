#!/usr/bin/env python3
"""Create a Windows desktop shortcut (.lnk) for Salesforce Translation Manager.

This script uses PowerShell COM automation (WScript.Shell) to create a
shortcut on the current user's Desktop.  It does not require pywin32.

The shortcut points to the PyInstaller-built .exe if it exists in dist/,
otherwise it falls back to launch.bat.

Usage:
  python scripts/create_shortcut.py [--target exe|bat]

Options:
  --target exe   Force the shortcut to point to the .exe (must exist in dist/)
  --target bat   Force the shortcut to point to launch.bat
  -h, --help     Show this help message
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE_PATH = ROOT / "dist" / "SalesforceTranslationHandler.exe"
BAT_PATH = ROOT / "launch.bat"
ICON_PATH = ROOT / "src" / "stx" / "gui" / "assets" / "logo.ico"
SHORTCUT_NAME = "Salesforce Translation Manager.lnk"


def get_desktop() -> Path:
    """Return the path to the current user's Desktop folder."""
    import os

    desktop = Path(os.path.expanduser("~/Desktop"))
    if not desktop.exists():
        # Fallback for non-English Windows where Desktop may be localized
        desktop = Path(os.environ.get("USERPROFILE", "~")) / "Desktop"
    return desktop


def create_shortcut_powershell(target: Path, icon: Path, desktop: Path) -> int:
    """Create a .lnk shortcut using PowerShell COM automation."""
    shortcut_path = desktop / SHORTCUT_NAME
    working_dir = ROOT

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{target}"
$Shortcut.WorkingDirectory = "{working_dir}"
$Shortcut.IconLocation = "{icon}, 0"
$Shortcut.Description = "Salesforce Translation Manager - STF workflow tool"
$Shortcut.Save()
"""

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        sys.stderr.write(f"PowerShell error:\n{result.stderr}\n")
        return 1

    print(f"Shortcut created: {shortcut_path}")
    print(f"  Target: {target}")
    print(f"  Icon:   {icon}")
    return 0


def main() -> int:
    if sys.platform != "win32":
        print(
            "This script creates a Windows desktop shortcut (.lnk) and "
            "can only run on Windows."
        )
        print("For Linux, use the SalesforceTranslationHandler.desktop file instead.")
        return 0

    parser = argparse.ArgumentParser(
        description="Create a Windows desktop shortcut for Salesforce Translation Manager."
    )
    parser.add_argument(
        "--target",
        choices=["exe", "bat"],
        default=None,
        help="Force shortcut target: 'exe' for the PyInstaller build, 'bat' for launch.bat",
    )
    args = parser.parse_args()

    # Determine target
    if args.target == "exe":
        if not EXE_PATH.exists():
            sys.stderr.write(
                f"Error: {EXE_PATH} not found.\n"
                "Build it first with:  python build_exe.py\n"
            )
            return 1
        target = EXE_PATH
    elif args.target == "bat":
        target = BAT_PATH
    else:
        # Auto-detect: prefer exe if available
        target = EXE_PATH if EXE_PATH.exists() else BAT_PATH

    if not target.exists():
        sys.stderr.write(f"Error: target not found: {target}\n")
        return 1

    if not ICON_PATH.exists():
        sys.stderr.write(
            f"Warning: icon not found at {ICON_PATH}\n"
            "The shortcut will be created without a custom icon.\n"
        )

    desktop = get_desktop()
    if not desktop.exists():
        sys.stderr.write(f"Error: Desktop folder not found at {desktop}\n")
        return 1

    icon = ICON_PATH if ICON_PATH.exists() else target
    return create_shortcut_powershell(target, icon, desktop)


if __name__ == "__main__":
    sys.exit(main())
