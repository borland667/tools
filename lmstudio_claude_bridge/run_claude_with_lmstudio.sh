#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_SCRIPT="${SCRIPT_DIR}/bridge.mjs"
DEFAULT_CLAUDE_CODE_MAIN_MODEL="qwen3.6-35b-a3b-abliterated-heretic-mlx"
DEFAULT_CLAUDE_CODE_SMALL_MODEL="qwen/qwen3-coder-30b"
NODE_BIN="${NODE_BIN:-}"
CLAUDE_BIN="${CLAUDE_BIN:-}"

if [[ -z "${NODE_BIN}" ]]; then
  if command -v node >/dev/null 2>&1; then
    NODE_BIN="$(command -v node)"
  elif [[ -x /usr/local/bin/node ]]; then
    NODE_BIN="/usr/local/bin/node"
  elif [[ -x /opt/homebrew/bin/node ]]; then
    NODE_BIN="/opt/homebrew/bin/node"
  fi
fi

if [[ -z "${NODE_BIN}" ]]; then
  echo "node is required to run the local inference bridge" >&2
  exit 1
fi

if [[ -z "${CLAUDE_BIN}" ]]; then
  if command -v claude >/dev/null 2>&1; then
    CLAUDE_BIN="$(command -v claude)"
  elif [[ -x "${HOME}/.local/bin/claude" ]]; then
    CLAUDE_BIN="${HOME}/.local/bin/claude"
  fi
fi

if [[ -z "${CLAUDE_BIN}" ]]; then
  echo "claude is required to launch Claude Code" >&2
  exit 1
fi

export CLAUDE_LMSTUDIO_MAIN_MODEL="${CLAUDE_LMSTUDIO_MAIN_MODEL:-${DEFAULT_CLAUDE_CODE_MAIN_MODEL}}"
export CLAUDE_LMSTUDIO_SMALL_MODEL="${CLAUDE_LMSTUDIO_SMALL_MODEL:-${DEFAULT_CLAUDE_CODE_SMALL_MODEL}}"
export CLAUDE_LMSTUDIO_TOOL_MODEL="${CLAUDE_LMSTUDIO_TOOL_MODEL:-${DEFAULT_CLAUDE_CODE_SMALL_MODEL}}"
export CLAUDE_LOCAL_INFERENCE_BACKEND="${CLAUDE_LOCAL_INFERENCE_BACKEND:-${CLAUDE_LMSTUDIO_BACKEND:-}}"

# Replace any previous bridge instance so the current model mapping wins.
if command -v pgrep >/dev/null 2>&1; then
  mapfile -t EXISTING_BRIDGE_PIDS < <(pgrep -f "${BRIDGE_SCRIPT} serve" || true)
  if [[ "${#EXISTING_BRIDGE_PIDS[@]}" -gt 0 ]]; then
    kill "${EXISTING_BRIDGE_PIDS[@]}" >/dev/null 2>&1 || true
    sleep 1
  fi
fi

"${NODE_BIN}" "${BRIDGE_SCRIPT}" sync-models
"${NODE_BIN}" "${BRIDGE_SCRIPT}" serve &
BRIDGE_PID=$!

cleanup() {
  kill "${BRIDGE_PID}" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

export ANTHROPIC_BASE_URL="http://${CLAUDE_LMSTUDIO_BRIDGE_HOST:-127.0.0.1}:${CLAUDE_LMSTUDIO_BRIDGE_PORT:-1245}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-lmstudio}"
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-${ANTHROPIC_API_KEY}}"
export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1
export ENABLE_TOOL_SEARCH=false
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_DISABLE_THINKING=1

exec "${CLAUDE_BIN}" "$@"
