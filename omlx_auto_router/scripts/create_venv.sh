#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${1:-.venv}"
PYTHON_RUNNER="$ROOT_DIR/scripts/resolve_python.sh"

selected_version="$(
  "$PYTHON_RUNNER" -c \
    'import sys; print(".".join(map(str, sys.version_info[:3])))'
)"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  existing_version="$(
    "$VENV_DIR/bin/python" -c \
      'import sys; print(".".join(map(str, sys.version_info[:3])))'
  )"

  if [[ "$existing_version" != "$selected_version" ]]; then
    echo "Existing $VENV_DIR uses Python $existing_version." >&2
    echo "Selected project Python is $selected_version; recreating the virtual environment." >&2
    rm -rf "$VENV_DIR"
  fi
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Creating $VENV_DIR with Python $selected_version..."
  "$PYTHON_RUNNER" -m venv "$VENV_DIR"
else
  echo "$VENV_DIR already uses Python $selected_version."
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
