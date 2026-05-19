#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${OPENHANDS_LMSTUDIO_BASE_URL:-http://127.0.0.1:1234/v1}"
API_KEY="${OPENHANDS_LMSTUDIO_API_KEY:-lmstudio}"
MODEL="${OPENHANDS_LMSTUDIO_MODEL:-openai/qwen/qwen3-coder-30b}"
START_LMSTUDIO=0

usage() {
  cat <<'EOF'
Usage: scripts/run_openhands_with_lmstudio.sh [options] [-- <openhands-args...>]

Launch OpenHands against LM Studio's local OpenAI-compatible API.

Options:
  --model <id>       Override the OpenHands model id
  --base-url <url>   Override the LM Studio base URL
  --api-key <key>    Override the API key sent to LM Studio
  --start-lmstudio   Try `lms server start` if the API is not already reachable
  -h, --help         Show this help

Examples:
  scripts/run_openhands_with_lmstudio.sh
  scripts/run_openhands_with_lmstudio.sh -- --task "Summarize this repo"
  scripts/run_openhands_with_lmstudio.sh --model openai/google/gemma-4-31b -- --headless --task "Reply with hello"
EOF
}

die() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

check_lmstudio_api() {
  local curl_args=(
    -fsS
    "${BASE_URL%/}/models"
  )

  if [[ -n "${API_KEY}" ]]; then
    curl_args=(
      -H "x-api-key: ${API_KEY}"
      "${curl_args[@]}"
    )
  fi

  curl "${curl_args[@]}" >/dev/null 2>&1
}

start_lmstudio_server() {
  local lms_bin
  lms_bin="${HOME}/.lmstudio/bin/lms"

  if [[ ! -x "${lms_bin}" ]]; then
    die "LM Studio API is unreachable and ${lms_bin} was not found"
  fi

  printf 'Starting LM Studio server via %s\n' "${lms_bin}" >&2
  "${lms_bin}" server start >/dev/null 2>&1 || true

  for _ in 1 2 3 4 5; do
    if check_lmstudio_api; then
      return 0
    fi
    sleep 1
  done

  die "LM Studio API is still unreachable at ${BASE_URL%/}/models"
}

OPENHANDS_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      [[ $# -ge 2 ]] || die "--model requires a value"
      MODEL="$2"
      shift 2
      ;;
    --base-url)
      [[ $# -ge 2 ]] || die "--base-url requires a value"
      BASE_URL="$2"
      shift 2
      ;;
    --api-key)
      [[ $# -ge 2 ]] || die "--api-key requires a value"
      API_KEY="$2"
      shift 2
      ;;
    --start-lmstudio)
      START_LMSTUDIO=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      OPENHANDS_ARGS+=("$@")
      break
      ;;
    *)
      OPENHANDS_ARGS+=("$1")
      shift
      ;;
  esac
done

require_command openhands
require_command curl

if ! check_lmstudio_api; then
  if [[ "${START_LMSTUDIO}" -eq 1 ]]; then
    start_lmstudio_server
  else
    die "LM Studio API is unreachable at ${BASE_URL%/}/models; rerun with --start-lmstudio if the local server is installed but stopped"
  fi
fi

export OPENHANDS_SUPPRESS_BANNER="${OPENHANDS_SUPPRESS_BANNER:-1}"
export LLM_MODEL="${MODEL}"
export LLM_BASE_URL="${BASE_URL}"
export LLM_API_KEY="${API_KEY}"

exec openhands --override-with-envs "${OPENHANDS_ARGS[@]}"
