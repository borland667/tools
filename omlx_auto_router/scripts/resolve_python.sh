#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# An explicit PYTHON_BIN override takes precedence.
if [[ -n "${PYTHON_BIN:-}" ]]; then
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "PYTHON_BIN points to an unavailable interpreter: $PYTHON_BIN" >&2
    exit 1
  fi

  exec "$PYTHON_BIN" "$@"
fi

# Explicitly honor the repository's .python-version when pyenv is available.
# Using `pyenv exec` does not depend on pyenv shell shims being initialized.
if [[ -f "$ROOT_DIR/.python-version" ]] && command -v pyenv >/dev/null 2>&1; then
  if ! selected_version="$(pyenv version-name 2>/dev/null)"; then
    requested_version="$(
      sed -e 's/#.*$//' -e '/^[[:space:]]*$/d' \
        "$ROOT_DIR/.python-version" | head -n 1 | xargs
    )"

    echo "pyenv could not resolve .python-version${requested_version:+ ($requested_version)}." >&2
    echo "Install the requested version with:" >&2
    echo "  pyenv install ${requested_version:-<version-from-.python-version>}" >&2
    exit 1
  fi

  echo "Using pyenv Python: $selected_version" >&2
  exec pyenv exec python "$@"
fi

if [[ -f "$ROOT_DIR/.python-version" ]] && ! command -v pyenv >/dev/null 2>&1; then
  echo "Warning: .python-version exists, but pyenv is not installed; using a system interpreter." >&2
fi

for candidate in python3.13 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" "$@"
  fi
done

echo "No suitable Python interpreter was found." >&2
echo "Install Python 3.13.14 or install pyenv and run:" >&2
echo "  pyenv install 3.13.14" >&2
exit 1
