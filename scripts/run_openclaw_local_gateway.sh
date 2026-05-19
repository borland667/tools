#!/usr/bin/env bash

set -euo pipefail

PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/run_openclaw_local_gateway.sh [options] [-- <openclaw-gateway-args...>]

Start the OpenClaw gateway in localhost-only mode.

This helper forces loopback binding in both persistent config and the current
process so the gateway does not listen on LAN interfaces by accident.

Options:
  --port <port>         Override the gateway port (default: 18789)
  --dry-run             Print the commands that would run without executing them
  -h, --help            Show this help

Examples:
  scripts/run_openclaw_local_gateway.sh
  scripts/run_openclaw_local_gateway.sh --port 19001
  scripts/run_openclaw_local_gateway.sh -- --startup-trace
EOF
}

die() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

OPENCLAW_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      [[ $# -ge 2 ]] || die "--port requires a value"
      PORT="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      OPENCLAW_ARGS+=("$@")
      break
      ;;
    *)
      OPENCLAW_ARGS+=("$1")
      shift
      ;;
  esac
done

for arg in "${OPENCLAW_ARGS[@]}"; do
  case "$arg" in
    --bind|--bind=*|--port|--port=*)
      die "pass port with --port and do not override bind; this helper always uses loopback"
      ;;
  esac
done

CONFIG_MODE_CMD=(openclaw config set gateway.mode local)
CONFIG_BIND_CMD=(openclaw config set gateway.bind loopback)
CONFIG_PORT_CMD=(openclaw config set gateway.port "$PORT" --strict-json)
RUN_CMD=(openclaw gateway run --bind loopback --port "$PORT")

RUN_CMD+=("${OPENCLAW_ARGS[@]}")

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '%q ' "${CONFIG_MODE_CMD[@]}"
  printf '\n'
  printf '%q ' "${CONFIG_BIND_CMD[@]}"
  printf '\n'
  printf '%q ' "${CONFIG_PORT_CMD[@]}"
  printf '\n'
  printf '%q ' "${RUN_CMD[@]}"
  printf '\n'
  exit 0
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  die "port must be numeric"
fi

require_command openclaw

"${CONFIG_MODE_CMD[@]}"
"${CONFIG_BIND_CMD[@]}"
"${CONFIG_PORT_CMD[@]}"

exec "${RUN_CMD[@]}"
