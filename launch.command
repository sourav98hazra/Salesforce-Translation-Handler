#!/usr/bin/env bash
# =============================================================================
#  Salesforce Translation Handler -- macOS double-click launcher.
#
#  Double-click in Finder to start the application.  First run sets up a venv
#  and installs the app; subsequent runs start instantly.
#
#  Requires Python 3.9+ (install from https://www.python.org/downloads/ or
#  via Homebrew: ``brew install python``).
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"
VENV_DIR=".venv"

# Pick a python interpreter (prefer python3, fall back to python).
PY="$(command -v python3 || command -v python || true)"
if [ -z "${PY}" ]; then
    /usr/bin/osascript -e 'display alert "Python missing" message "Install Python 3.9+ from python.org and re-run this launcher."'
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
