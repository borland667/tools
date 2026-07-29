#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT_DIR/launchd/com.omlx.auto-router.plist.template"
TARGET="$HOME/Library/LaunchAgents/com.omlx.auto-router.plist"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Missing .venv. Run: make install" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

sed   -e "s|__PROJECT_DIR__|$ROOT_DIR|g"   -e "s|__HOME__|$HOME|g"   "$TEMPLATE" > "$TARGET"

launchctl bootout "gui/$(id -u)" "$TARGET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/com.omlx.auto-router"

echo "Installed: $TARGET"
echo "Logs:"
echo "  $HOME/Library/Logs/omlx-auto-router.log"
echo "  $HOME/Library/Logs/omlx-auto-router.error.log"
