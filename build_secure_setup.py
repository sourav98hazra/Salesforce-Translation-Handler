"""Build a secure setup.exe with integrity verification.

Usage:
    python build_secure_setup.py

Output:
    dist/installer/SalesforceTranslationHandler_Setup_2.0.0.exe
    dist/installer/SalesforceTranslationHandler_Setup_2.0.0.exe.sha256

Prerequisites:
    - Python 3.9+
    - pip install -e ".[gui]" pyinstaller
    - Inno Setup 6 installed (Windows only)
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
VERSION = "2.0.0"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def main() -> int:
    print()
    print("=" * 60)
    print("  Salesforce Translation Handler - Secure Setup Builder")
    print("=" * 60)
    print()

    # Step 1: Build the executable
    print("[1/3] Building executable with PyInstaller...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "build_exe.py")],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print("ERROR: PyInstaller build failed.")
        return 1
    print("      Done.\n")

    # Step 2: Build the installer
    print("[2/3] Building installer with Inno Setup...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "installer" / "build_installer.py"), "--skip-build"],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print("ERROR: Installer build failed.")
        print("       Make sure Inno Setup 6 is installed.")
        print("       Download: https://jrsoftware.org/isinfo.php")
        return 1
    print("      Done.\n")

    # Step 3: Generate checksum
    print("[3/3] Generating SHA-256 checksum...")
    installer_dir = ROOT / "dist" / "installer"
    setup_files = list(installer_dir.glob("*Setup*.exe"))
    if not setup_files:
        print("ERROR: No installer .exe found in dist/installer/")
        return 1

    setup_exe = setup_files[0]
    checksum = compute_sha256(setup_exe)
    checksum_file = setup_exe.with_suffix(".exe.sha256")
    checksum_file.write_text(
        f"{checksum}  {setup_exe.name}\n", encoding="utf-8"
    )
    print("      Done.\n")

    # Summary
    print("=" * 60)
    print("  BUILD COMPLETE")
    print("=" * 60)
    print()
    print(f"  Installer:  {setup_exe}")
    print(f"  Checksum:   {checksum_file}")
    print(f"  SHA-256:    {checksum}")
    print()
    print("  To verify integrity after download:")
    print(f"    certutil -hashfile {setup_exe.name} SHA256")
    print(f"    # Compare with: {checksum}")
    print()
    size_mb = setup_exe.stat().st_size / (1024 * 1024) if setup_exe.exists() else 0
    print(f"  Size: {size_mb:.1f} MB")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
