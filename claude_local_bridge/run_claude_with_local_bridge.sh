#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_SCRIPT="${SCRIPT_DIR}/bridge.mjs"
DEFAULT_CLAUDE_CODE_MAIN_MODEL="Qwen3.5-9b-Sushi-Coder-RL-MLX"
DEFAULT_CLAUDE_CODE_SMALL_MODEL="Qwen3.5-9b-Sushi-Coder-RL-MLX"
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
  echo "node is required to run the local Claude bridge" >&2
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

export CLAUDE_LOCAL_MAIN_MODEL="${CLAUDE_LOCAL_MAIN_MODEL:-${DEFAULT_CLAUDE_CODE_MAIN_MODEL}}"
export CLAUDE_LOCAL_SMALL_MODEL="${CLAUDE_LOCAL_SMALL_MODEL:-${DEFAULT_CLAUDE_CODE_SMALL_MODEL}}"
export CLAUDE_LOCAL_TOOL_MODEL="${CLAUDE_LOCAL_TOOL_MODEL:-${CLAUDE_LOCAL_SMALL_MODEL}}"
export CLAUDE_LOCAL_INFERENCE_BACKEND="${CLAUDE_LOCAL_INFERENCE_BACKEND:-omlx}"
case "${CLAUDE_LOCAL_BRIDGE_HOST:-127.0.0.1}" in
  127.0.0.1|localhost|::1)
    export CLAUDE_LOCAL_BRIDGE_HOST="${CLAUDE_LOCAL_BRIDGE_HOST:-127.0.0.1}"
    ;;
  *)
    echo "refusing non-loopback CLAUDE_LOCAL_BRIDGE_HOST=${CLAUDE_LOCAL_BRIDGE_HOST}; using 127.0.0.1" >&2
    export CLAUDE_LOCAL_BRIDGE_HOST="127.0.0.1"
    ;;
esac

BRIDGE_BASE_URL="http://${CLAUDE_LOCAL_BRIDGE_HOST}:${CLAUDE_LOCAL_BRIDGE_PORT:-1245}"
BRIDGE_PID=""

if command -v curl >/dev/null 2>&1 && curl -fsS "${BRIDGE_BASE_URL}/healthz" >/dev/null 2>&1; then
  echo "using existing local Claude bridge at ${BRIDGE_BASE_URL}" >&2
else
  "${NODE_BIN}" "${BRIDGE_SCRIPT}" sync-models
  "${NODE_BIN}" "${BRIDGE_SCRIPT}" serve &
  BRIDGE_PID=$!
fi

cleanup() {
  if [[ -n "${BRIDGE_PID}" ]]; then
    kill "${BRIDGE_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

export ANTHROPIC_BASE_URL="${BRIDGE_BASE_URL}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-local-bridge}"
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-${ANTHROPIC_API_KEY}}"
export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1
export ENABLE_TOOL_SEARCH=false
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_DISABLE_THINKING=1

exec "${CLAUDE_BIN}" "$@"
