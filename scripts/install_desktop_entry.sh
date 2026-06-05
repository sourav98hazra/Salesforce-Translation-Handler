#!/usr/bin/env bash
# Generate and install the Linux desktop entry with correct absolute paths.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/SalesforceTranslationHandler.desktop"

mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Salesforce Translation Manager
Comment=STF -> Excel -> Translate -> Review -> STF workflow
Exec=bash -c 'cd "$REPO_ROOT" && exec ./launch.sh'
Icon=$REPO_ROOT/src/stx/gui/assets/logo.png
Terminal=false
Categories=Utility;Development;
StartupNotify=true
EOF

echo "Desktop entry installed: $DESKTOP_FILE"
echo "  Exec: bash -c 'cd \"$REPO_ROOT\" && exec ./launch.sh'"
echo "  Icon: $REPO_ROOT/src/stx/gui/assets/logo.png"
