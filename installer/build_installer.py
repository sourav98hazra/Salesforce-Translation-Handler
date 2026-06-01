"""Build the Windows installer for Salesforce Translation Handler.

Orchestrates the full build pipeline:
1. Run build_exe.py to produce PyInstaller output (--onedir mode).
2. Invoke ISCC (Inno Setup Compiler) to compile the .iss script.
3. Optionally sign the resulting Setup.exe with signtool.

Usage
-----
::

    python installer/build_installer.py
    python installer/build_installer.py --skip-build
    python installer/build_installer.py --sign
    python installer/build_installer.py --help

Prerequisites
-------------
- Python 3.9+
- PyInstaller (``pip install pyinstaller``)
- Inno Setup 6 (ISCC.exe on PATH or at default install location)
- (Optional) signtool.exe for code-signing
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_EXE = ROOT / "build_exe.py"
ISS_SCRIPT = Path(__file__).resolve().parent / "stx_installer.iss"
DIST_DIR = ROOT / "dist"
INSTALLER_OUTPUT = DIST_DIR / "installer"

# Common Inno Setup install locations on Windows
ISCC_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]


def find_iscc() -> str | None:
    """Locate the Inno Setup Compiler (ISCC.exe)."""
    # Check PATH first
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if iscc:
        return iscc

    # Check common install locations
    for path in ISCC_PATHS:
        if Path(path).is_file():
            return path

    return None


def run_pyinstaller(onedir: bool = True) -> int:
    """Run build_exe.py to produce PyInstaller output.

    By default, patches build_exe.py to use --onedir mode for the installer
    (produces a directory instead of a single file).
    """
    print("=" * 60)
    print("STEP 1: Building executable with PyInstaller")
    print("=" * 60)
    print()

    if not BUILD_EXE.is_file():
        print(f"ERROR: build_exe.py not found at {BUILD_EXE}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    if onedir:
        env["STX_PYINSTALLER_ONEDIR"] = "1"

    # Run build_exe.py with --onedir override
    cmd = [sys.executable, str(BUILD_EXE)]
    print(f"Running: {' '.join(cmd)}")
    if onedir:
        print("  (Using --onedir mode for installer packaging)")
    print()

    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if result.returncode != 0:
        print(f"\nERROR: PyInstaller build failed (exit code {result.returncode})", file=sys.stderr)
        return result.returncode

    print("\nPyInstaller build completed successfully.")
    return 0


def run_inno_setup() -> int:
    """Compile the Inno Setup script into a Windows installer."""
    print()
    print("=" * 60)
    print("STEP 2: Compiling installer with Inno Setup")
    print("=" * 60)
    print()

    iscc = find_iscc()
    if not iscc:
        print(
            "ERROR: ISCC.exe (Inno Setup Compiler) not found.\n"
            "Install Inno Setup 6 from https://jrsoftware.org/isinfo.php\n"
            "or add ISCC.exe to your PATH.",
            file=sys.stderr,
        )
        return 1

    if not ISS_SCRIPT.is_file():
        print(f"ERROR: Inno Setup script not found at {ISS_SCRIPT}", file=sys.stderr)
        return 1

    # Ensure output directory exists
    INSTALLER_OUTPUT.mkdir(parents=True, exist_ok=True)

    cmd = [iscc, str(ISS_SCRIPT)]
    print(f"Running: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\nERROR: Inno Setup compilation failed (exit code {result.returncode})", file=sys.stderr)
        return result.returncode

    # List produced installer files
    print("\nInstaller compilation completed successfully.")
    if INSTALLER_OUTPUT.exists():
        for f in sorted(INSTALLER_OUTPUT.iterdir()):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  Output: {f.name} ({size_mb:.1f} MB)")

    return 0


def run_signing() -> int:
    """Sign the installer executable using signtool."""
    print()
    print("=" * 60)
    print("STEP 3: Signing installer with signtool")
    print("=" * 60)
    print()

    sign_script = Path(__file__).resolve().parent / "sign_executable.ps1"

    if not INSTALLER_OUTPUT.exists():
        print("ERROR: Installer output directory not found.", file=sys.stderr)
        return 1

    # Find the setup exe
    setup_files = list(INSTALLER_OUTPUT.glob("*Setup*.exe"))
    if not setup_files:
        print("ERROR: No Setup*.exe found in installer output.", file=sys.stderr)
        return 1

    setup_exe = setup_files[0]
    print(f"Signing: {setup_exe.name}")

    # Use the PowerShell signing script
    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(sign_script),
        "-FilePath",
        str(setup_exe),
    ]
    print(f"Running: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\nWARNING: Signing failed (exit code {result.returncode})", file=sys.stderr)
        print("The installer was built but is unsigned.", file=sys.stderr)
        return result.returncode

    print("\nSigning completed successfully.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the installer build pipeline."""
    parser = argparse.ArgumentParser(
        description="Build the Windows installer for Salesforce Translation Handler.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python installer/build_installer.py              # Full build\n"
            "  python installer/build_installer.py --skip-build # ISS only (reuse existing dist/)\n"
            "  python installer/build_installer.py --sign       # Build + sign\n"
        ),
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip PyInstaller build step (reuse existing dist/ output)",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Sign the installer with signtool after building",
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Use PyInstaller --onefile mode instead of --onedir",
    )

    args = parser.parse_args(argv)

    print()
    print("Salesforce Translation Handler - Installer Build")
    print("=" * 60)
    print()

    # Step 1: PyInstaller build
    if not args.skip_build:
        rc = run_pyinstaller(onedir=not args.onefile)
        if rc != 0:
            return rc
    else:
        print("Skipping PyInstaller build (--skip-build).")
        if not DIST_DIR.exists():
            print(f"WARNING: dist/ directory not found at {DIST_DIR}", file=sys.stderr)

    # Step 2: Inno Setup compilation
    rc = run_inno_setup()
    if rc != 0:
        return rc

    # Step 3: Signing (optional)
    if args.sign:
        rc = run_signing()
        if rc != 0:
            return rc

    print()
    print("=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
