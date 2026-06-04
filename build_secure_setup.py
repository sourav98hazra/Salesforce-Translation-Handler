"""Build a distributable setup.exe for Salesforce Translation Handler.

Usage:
    python build_secure_setup.py          # Full installer (needs Inno Setup)
    python build_secure_setup.py --exe    # Just the standalone .exe (no installer needed)

Prerequisites:
    - Windows OS
    - Python 3.9+
    - pip install -e ".[gui]" pyinstaller
    - Inno Setup 6 (only for full installer mode)
      Download: https://jrsoftware.org/isdl.php
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
VERSION = "3.0.0"
APP_NAME = "SalesforceTranslationHandler"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def check_prerequisites(need_inno: bool = True) -> bool:
    """Check that all prerequisites are met. Print clear errors if not."""
    ok = True

    # Check OS
    if platform.system() != "Windows":
        print("ERROR: This script must be run on Windows.")
        print("       PyInstaller builds are OS-specific.")
        print()
        ok = False

    # Check PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("ERROR: PyInstaller is not installed.")
        print("       Fix: pip install pyinstaller")
        print()
        ok = False

    # Check the app is installed
    try:
        import stx  # noqa: F401
    except ImportError:
        print("ERROR: The app is not installed.")
        print('       Fix: pip install -e ".[gui]"')
        print()
        ok = False

    # Check Inno Setup (only for full installer)
    if need_inno:
        iscc = _find_inno_setup()
        if not iscc:
            print("ERROR: Inno Setup 6 is not installed.")
            print("       Download: https://jrsoftware.org/isdl.php")
            print("       Install it, then re-run this script.")
            print()
            print("       TIP: If you just want a standalone .exe without an installer,")
            print("            run: python build_secure_setup.py --exe")
            print()
            ok = False

    return ok


def _find_inno_setup() -> str | None:
    """Locate ISCC.exe (Inno Setup Compiler)."""
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if iscc:
        return iscc
    for path in [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]:
        if Path(path).is_file():
            return path
    return None


def build_exe_only() -> int:
    """Build just the standalone .exe (no installer)."""
    print()
    print("=" * 60)
    print("  Building Standalone .exe")
    print("=" * 60)
    print()

    if not check_prerequisites(need_inno=False):
        return 1

    print("[1/2] Building executable with PyInstaller...")
    print()
    result = subprocess.run(
        [sys.executable, str(ROOT / "build_exe.py")],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print()
        print("ERROR: PyInstaller build failed. Check the output above.")
        return 1

    # Find the output
    dist_dir = ROOT / "dist"
    exe_path = dist_dir / f"{APP_NAME}.exe"
    dir_path = dist_dir / APP_NAME / f"{APP_NAME}.exe"

    output = exe_path if exe_path.exists() else dir_path if dir_path.exists() else None

    if not output:
        print(f"ERROR: Expected output not found in {dist_dir}")
        return 1

    # Generate checksum
    print()
    print("[2/2] Generating SHA-256 checksum...")
    checksum = compute_sha256(output)
    checksum_file = output.with_suffix(".exe.sha256")
    checksum_file.write_text(f"{checksum}  {output.name}\n", encoding="utf-8")

    size_mb = output.stat().st_size / (1024 * 1024)

    print()
    print("=" * 60)
    print("  DONE!")
    print("=" * 60)
    print()
    print(f"  Output:   {output}")
    print(f"  Size:     {size_mb:.1f} MB")
    print(f"  SHA-256:  {checksum}")
    print()
    print("  Share this .exe file with your users.")
    print("  They just double-click it to run -- no install needed.")
    print()
    return 0


def build_full_installer() -> int:
    """Build the full Inno Setup installer."""
    print()
    print("=" * 60)
    print("  Building Setup Installer")
    print("=" * 60)
    print()

    if not check_prerequisites(need_inno=True):
        return 1

    # Step 1: PyInstaller
    print("[1/3] Building executable with PyInstaller...")
    print()
    result = subprocess.run(
        [sys.executable, str(ROOT / "build_exe.py")],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print()
        print("ERROR: PyInstaller build failed. Check the output above.")
        return 1
    print()

    # Step 2: Inno Setup
    print("[2/3] Building installer with Inno Setup...")
    print()
    result = subprocess.run(
        [sys.executable, str(ROOT / "installer" / "build_installer.py"), "--skip-build"],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print()
        print("ERROR: Inno Setup compilation failed.")
        return 1
    print()

    # Step 3: Checksum
    print("[3/3] Generating SHA-256 checksum...")
    installer_dir = ROOT / "dist" / "installer"
    setup_files = list(installer_dir.glob("*Setup*.exe"))
    if not setup_files:
        print("ERROR: No installer .exe found in dist/installer/")
        return 1

    setup_exe = setup_files[0]
    checksum = compute_sha256(setup_exe)
    checksum_file = setup_exe.with_suffix(".exe.sha256")
    checksum_file.write_text(f"{checksum}  {setup_exe.name}\n", encoding="utf-8")

    size_mb = setup_exe.stat().st_size / (1024 * 1024)

    print()
    print("=" * 60)
    print("  DONE!")
    print("=" * 60)
    print()
    print(f"  Installer:  {setup_exe}")
    print(f"  Size:       {size_mb:.1f} MB")
    print(f"  SHA-256:    {checksum}")
    print()
    print("  Share this installer with your users.")
    print("  They double-click it to install (Start Menu + Desktop shortcut).")
    print()
    print("  Verify integrity:")
    print(f"    certutil -hashfile {setup_exe.name} SHA256")
    print()
    return 0


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0

    if "--exe" in sys.argv:
        return build_exe_only()
    else:
        return build_full_installer()


if __name__ == "__main__":
    sys.exit(main())
