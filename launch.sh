#!/usr/bin/env bash
# =============================================================================
#  Salesforce Translation Handler -- Linux double-click launcher.
#
#  Mark this file as executable (``chmod +x launch.sh``) and double-click in
#  your file manager, or invoke from a terminal.  First run sets up a venv and
#  installs the app; subsequent runs start instantly.
#
#  Requires Python 3.9+.  On a minimal install you may also need:
#    - Debian/Ubuntu: sudo apt install libgl1 libegl1 libxkbcommon0 libdbus-1-3
#    - Fedora/RHEL:   sudo dnf install mesa-libGL mesa-libEGL libxkbcommon
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"
VENV_DIR=".venv"

PY="$(command -v python3 || command -v python || true)"
if [ -z "${PY}" ]; then
    echo "Python 3.9+ is required.  Install it via your package manager."
    exit 1
fi

if [ ! -x "${VENV_DIR}/bin/stx-app" ]; then
    echo "Setting up the virtual environment for the first run..."
    "${PY}" -m venv "${VENV_DIR}"
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip
    pip install -e ".[gui]"
fi

exec "${VENV_DIR}/bin/stx-app"
