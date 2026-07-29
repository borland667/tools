#!/usr/bin/env bash
set -euo pipefail

TARGET="$HOME/Library/LaunchAgents/com.omlx.auto-router.plist"

launchctl bootout "gui/$(id -u)" "$TARGET" 2>/dev/null || true
rm -f "$TARGET"

echo "Removed oMLX Auto Router launchd service."
