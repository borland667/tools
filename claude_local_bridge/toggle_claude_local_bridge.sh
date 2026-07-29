#!/usr/bin/env bash
# Toggle a Claude Desktop/Cowork 3P local bridge provider on or off.
set -euo pipefail

INSTANCE_BASE="${CLAUDE_INSTANCES_BASE:-$HOME/.claude-instances}"
PROFILE_NAME="${CLAUDE_PROFILE_NAME:-}"
PROFILE_DIR="${CLAUDE_PROFILE_DIR:-}"
CONFIG_LIB="${CLAUDE_3P_CONFIG_LIB:-}"
LAUNCH_AGENT="${CLAUDE_LOCAL_BRIDGE_LAUNCH_AGENT:-${BRIDGE_LAUNCH_AGENT:-$HOME/Library/LaunchAgents/com.borland.claude-local-bridge.plist}}"

usage() {
  cat <<'EOF'
Toggle a Claude Desktop/Cowork 3P local bridge on or off.

Usage:
  toggle_claude_local_bridge.sh --disable [--baseline <path>] [--profile <name>]
  toggle_claude_local_bridge.sh --enable [--profile <name>]
  toggle_claude_local_bridge.sh --status [--profile <name>]
  toggle_claude_local_bridge.sh --profile-dir <path> --status

Options:
  --profile <name>      Use an isolated Claude profile under
                        ~/.claude-instances/<name>. Use "default" for the
                        stock Claude Desktop/Cowork profile.
  --profile-dir <path>  Use an explicit Electron user-data directory.
  --config-lib <path>   Override the configLibrary directory directly.
  --launch-agent <path> Override the bridge LaunchAgent plist path.
  --disable             Restore the pre-bridge provider config and stop the
                        bridge LaunchAgent.
  --enable              Restore the bridge-active provider config and start
                        the bridge LaunchAgent.
  --status              Print provider snapshot and LaunchAgent state.
  --baseline <path>     Seed the disabled snapshot on first --disable.
  -h, --help            Show this help.

Environment aliases:
  CLAUDE_PROFILE_NAME, CLAUDE_PROFILE_DIR, CLAUDE_3P_CONFIG_LIB,
  CLAUDE_LOCAL_BRIDGE_LAUNCH_AGENT, BRIDGE_LAUNCH_AGENT.

Restart the target Claude profile after toggling so the provider change takes effect.
EOF
}

err() { printf 'error: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }

resolve_config_lib() {
  if [[ -n "$CONFIG_LIB" ]]; then
    printf '%s\n' "$CONFIG_LIB"
    return
  fi

  if [[ -n "$PROFILE_DIR" ]]; then
    printf '%s/configLibrary\n' "$PROFILE_DIR"
    return
  fi

  if [[ -n "$PROFILE_NAME" && "$PROFILE_NAME" != "default" ]]; then
    printf '%s/%s/configLibrary\n' "$INSTANCE_BASE" "$PROFILE_NAME"
    return
  fi

  printf '%s/Library/Application Support/Claude-3p/configLibrary\n' "$HOME"
}

read_active_id() {
  local config_lib="$1"
  local meta="$config_lib/_meta.json"
  [[ -f "$meta" ]] || err "missing $meta"
  python3 - "$meta" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
applied = data.get("appliedId")
if not applied:
    print("appliedId missing from _meta.json", file=sys.stderr)
    sys.exit(2)
print(applied)
PY
}

agent_label() {
  basename "$LAUNCH_AGENT" .plist
}

agent_loaded() {
  launchctl print "gui/$(id -u)/$(agent_label)" >/dev/null 2>&1
}

agent_bootout() {
  if [[ ! -f "$LAUNCH_AGENT" ]]; then
    log "launch agent plist not found at $LAUNCH_AGENT, skipping bootout"
    return 0
  fi
  if agent_loaded; then
    log "stopping bridge LaunchAgent"
    launchctl bootout "gui/$(id -u)" "$LAUNCH_AGENT"
  else
    log "bridge LaunchAgent already not loaded"
  fi
}

agent_bootstrap() {
  [[ -f "$LAUNCH_AGENT" ]] || err "launch agent plist not found at $LAUNCH_AGENT"
  if agent_loaded; then
    log "bridge LaunchAgent already loaded"
  else
    log "starting bridge LaunchAgent"
    launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENT"
  fi
}

auto_detect_baseline() {
  local config_lib="$1" id="$2"
  local matches=()
  shopt -s nullglob
  for f in "$config_lib/$id.json".bak-bridge-*; do
    matches+=("$f")
  done
  shopt -u nullglob
  if [[ "${#matches[@]}" -eq 1 ]]; then
    printf '%s\n' "${matches[0]}"
    return 0
  fi
  return 1
}

snapshot_path() {
  local config_lib="$1" id="$2" slot="$3"
  printf '%s/%s.json.bridge-%s.bak' "$config_lib" "$id" "$slot"
}

cmd_disable() {
  local config_lib="$1" baseline="${2:-}"
  local id active on_snap off_snap
  id="$(read_active_id "$config_lib")"
  active="$config_lib/$id.json"
  on_snap="$(snapshot_path "$config_lib" "$id" on)"
  off_snap="$(snapshot_path "$config_lib" "$id" off)"

  [[ -f "$active" ]] || err "active provider config missing: $active"

  if [[ ! -f "$off_snap" ]]; then
    if [[ -n "$baseline" ]]; then
      [[ -f "$baseline" ]] || err "baseline file not found: $baseline"
      python3 -c 'import json, sys; json.load(open(sys.argv[1]))' "$baseline" \
        || err "baseline is not valid JSON: $baseline"
      cp -p "$baseline" "$off_snap"
      log "seeded disabled snapshot from $baseline"
    else
      local detected
      if detected="$(auto_detect_baseline "$config_lib" "$id")"; then
        cp -p "$detected" "$off_snap"
        log "seeded disabled snapshot from $detected"
      else
        err "no $off_snap and no --baseline provided. Pass --baseline <path> to a pre-bridge provider JSON."
      fi
    fi
  fi

  if cmp -s "$active" "$off_snap"; then
    log "active config already matches disabled snapshot, leaving file alone"
  else
    if [[ -f "$on_snap" ]] && ! cmp -s "$active" "$on_snap"; then
      err "active config matches neither enabled nor disabled snapshot. Refusing to overwrite $on_snap."
    fi
    cp -p "$active" "$on_snap"
    log "saved current active config -> $(basename "$on_snap")"
    cp -p "$off_snap" "$active"
    log "restored disabled config -> $(basename "$active")"
  fi

  agent_bootout
  log "bridge disabled. Restart the target Claude profile for the change to take effect."
}

cmd_enable() {
  local config_lib="$1"
  local id active on_snap off_snap
  id="$(read_active_id "$config_lib")"
  active="$config_lib/$id.json"
  on_snap="$(snapshot_path "$config_lib" "$id" on)"
  off_snap="$(snapshot_path "$config_lib" "$id" off)"

  [[ -f "$active" ]] || err "active provider config missing: $active"
  [[ -f "$on_snap" ]] || err "no enabled snapshot at $on_snap"

  if cmp -s "$active" "$on_snap"; then
    log "active config already matches enabled snapshot, leaving file alone"
  else
    if [[ -f "$off_snap" ]] && ! cmp -s "$active" "$off_snap"; then
      err "active config matches neither enabled nor disabled snapshot. Refusing to overwrite $off_snap."
    fi
    cp -p "$active" "$off_snap"
    log "saved current active config -> $(basename "$off_snap")"
    cp -p "$on_snap" "$active"
    log "restored enabled config -> $(basename "$active")"
  fi

  agent_bootstrap
  log "bridge enabled. Restart the target Claude profile for the change to take effect."
}

snapshot_presence() {
  if [[ -f "$1" ]]; then
    printf 'present'
  else
    printf 'absent'
  fi
}

cmd_status() {
  local config_lib="$1"
  local id active on_snap off_snap state
  id="$(read_active_id "$config_lib")"
  active="$config_lib/$id.json"
  on_snap="$(snapshot_path "$config_lib" "$id" on)"
  off_snap="$(snapshot_path "$config_lib" "$id" off)"

  if [[ ! -f "$active" ]]; then
    state="missing active config"
  elif [[ -f "$on_snap" ]] && cmp -s "$active" "$on_snap"; then
    state="enabled"
  elif [[ -f "$off_snap" ]] && cmp -s "$active" "$off_snap"; then
    state="disabled"
  else
    state="custom (matches neither snapshot)"
  fi

  log "profile name:          ${PROFILE_NAME:-default}"
  log "profile dir:           ${PROFILE_DIR:-${PROFILE_NAME:+$INSTANCE_BASE/$PROFILE_NAME}}"
  log "config library:        $config_lib"
  log "active provider id:    $id"
  log "config state:          $state"
  log "  active:              $active"
  log "  enabled snapshot:    $(snapshot_presence "$on_snap")  ($on_snap)"
  log "  disabled snapshot:   $(snapshot_presence "$off_snap")  ($off_snap)"
  if agent_loaded; then
    log "launch agent:          loaded ($(agent_label))"
  else
    log "launch agent:          not loaded ($(agent_label))"
  fi
}

main() {
  local action="" baseline=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --enable) [[ -n "$action" ]] && err "specify one action"; action=enable; shift ;;
      --disable) [[ -n "$action" ]] && err "specify one action"; action=disable; shift ;;
      --status) [[ -n "$action" ]] && err "specify one action"; action=status; shift ;;
      --baseline) baseline="${2:-}"; [[ -n "$baseline" ]] || err "--baseline requires a path"; shift 2 ;;
      --profile) PROFILE_NAME="${2:-}"; [[ -n "$PROFILE_NAME" ]] || err "--profile requires a name"; shift 2 ;;
      --profile-dir) PROFILE_DIR="${2:-}"; [[ -n "$PROFILE_DIR" ]] || err "--profile-dir requires a path"; shift 2 ;;
      --config-lib) CONFIG_LIB="${2:-}"; [[ -n "$CONFIG_LIB" ]] || err "--config-lib requires a path"; shift 2 ;;
      --launch-agent) LAUNCH_AGENT="${2:-}"; [[ -n "$LAUNCH_AGENT" ]] || err "--launch-agent requires a path"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) err "unknown argument: $1" ;;
    esac
  done

  [[ -n "$action" ]] || { usage; err "must specify --enable, --disable, or --status"; }
  [[ -z "$baseline" || "$action" == "disable" ]] || err "--baseline only applies to --disable"

  local config_lib
  config_lib="$(resolve_config_lib)"
  case "$action" in
    enable) cmd_enable "$config_lib" ;;
    disable) cmd_disable "$config_lib" "$baseline" ;;
    status) cmd_status "$config_lib" ;;
  esac
}

main "$@"
