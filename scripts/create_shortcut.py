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


def _escape_ps_string(value: str) -> str:
    """Escape a string for safe interpolation inside a PowerShell double-quoted string.

    PowerShell special characters inside double-quoted strings:
    - " (double quote) -> `" (backtick-escaped)
    - ` (backtick)     -> `` (doubled)
    - $ (dollar sign)  -> `$ (backtick-escaped)
    """
    # Order matters: escape backticks first so we don't double-escape later insertions
    value = value.replace("`", "``")
    value = value.replace('"', '`"')
    value = value.replace("$", "`$")
    return value


def create_shortcut_powershell(target: Path, icon: Path) -> int:
    """Create a .lnk shortcut using PowerShell COM automation.

    The Desktop folder is resolved inside PowerShell using
    [Environment]::GetFolderPath('Desktop') so it works correctly
    on non-English Windows installations where the Desktop folder
    may be at a localized path.
    """
    working_dir = ROOT

    # Escape all path values for safe PowerShell interpolation
    safe_target = _escape_ps_string(str(target))
    safe_working_dir = _escape_ps_string(str(working_dir))
    safe_icon = _escape_ps_string(str(icon))
    safe_shortcut_name = _escape_ps_string(SHORTCUT_NAME)

    ps_script = f"""
$Desktop = [Environment]::GetFolderPath('Desktop')
if (-not $Desktop) {{
    Write-Error "Could not determine Desktop folder path."
    exit 1
}}
$ShortcutPath = Join-Path $Desktop "{safe_shortcut_name}"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "{safe_target}"
$Shortcut.WorkingDirectory = "{safe_working_dir}"
$Shortcut.IconLocation = "{safe_icon}, 0"
$Shortcut.Description = "Salesforce Translation Manager - STF workflow tool"
$Shortcut.Save()
Write-Output $ShortcutPath
"""

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        sys.stderr.write(f"PowerShell error:\n{result.stderr}\n")
        return 1

    shortcut_path = result.stdout.strip()
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

    icon = ICON_PATH if ICON_PATH.exists() else target
    return create_shortcut_powershell(target, icon)


if __name__ == "__main__":
    sys.exit(main())
