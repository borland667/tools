#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv; creating it with the project-selected Python interpreter." >&2
  "$ROOT_DIR/scripts/create_venv.sh" .venv
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python omlx_auto_router.py
