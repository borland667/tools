#!/usr/bin/env bash
# Toggle the LM Studio Claude 3p bridge on or off.
#
# Switches the active Claude Desktop / Cowork 3p provider config between two
# snapshots and starts/stops the bridge LaunchAgent.
#
# State files (siblings of the active provider JSON in configLibrary):
#   <id>.json.bridge-on.bak    captured bridge-enabled provider config
#   <id>.json.bridge-off.bak   captured bridge-disabled provider config
set -euo pipefail

CONFIG_LIB="${CLAUDE_3P_CONFIG_LIB:-$HOME/Library/Application Support/Claude-3p/configLibrary}"
LAUNCH_AGENT="${BRIDGE_LAUNCH_AGENT:-$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist}"

usage() {
  cat <<'EOF'
Toggle the LM Studio Claude 3p bridge on or off.

Usage:
  toggle_claude_lmstudio_bridge.sh --disable [--baseline <path>]
  toggle_claude_lmstudio_bridge.sh --enable
  toggle_claude_lmstudio_bridge.sh --status
  toggle_claude_lmstudio_bridge.sh -h | --help

Options:
  --disable           Restore the pre-bridge 3p provider config and stop the
                      bridge LaunchAgent. The current bridge-active config is
                      kept as a sibling .bridge-on.bak snapshot.
  --enable            Restore the bridge-active 3p provider config and start
                      the bridge LaunchAgent. The current disabled config is
                      kept as a sibling .bridge-off.bak snapshot.
  --status            Print the current state of the 3p provider config and
                      the bridge LaunchAgent, then exit.
  --baseline <path>   Path to a JSON file used to seed the disabled snapshot
                      on the first --disable run. Required if no
                      .bridge-off.bak and no auto-detectable
                      .bak-bridge-<timestamp> backup exist.
  -h, --help          Show this help.

Environment overrides:
  CLAUDE_3P_CONFIG_LIB    Override the configLibrary directory.
  BRIDGE_LAUNCH_AGENT     Override the bridge plist path.

Examples:
  toggle_claude_lmstudio_bridge.sh --status
  toggle_claude_lmstudio_bridge.sh --disable
  toggle_claude_lmstudio_bridge.sh --disable --baseline ./pre-bridge.json
  toggle_claude_lmstudio_bridge.sh --enable

Restart Claude Desktop after toggling so the provider change takes effect.
EOF
}

err() { printf 'error: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }

read_active_id() {
  local meta="$CONFIG_LIB/_meta.json"
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

# Pick a single existing pre-bridge backup file matching <id>.json.bak-bridge-*,
# excluding the script's own managed snapshot suffixes. Prints the path on
# success, returns non-zero if zero or multiple candidates are found.
auto_detect_baseline() {
  local id="$1"
  local matches=()
  shopt -s nullglob
  for f in "$CONFIG_LIB/$id.json".bak-bridge-*; do
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
  local id="$1" slot="$2"
  printf '%s/%s.json.bridge-%s.bak' "$CONFIG_LIB" "$id" "$slot"
}

cmd_disable() {
  local baseline="${1:-}"
  local id active on_snap off_snap
  id="$(read_active_id)"
  active="$CONFIG_LIB/$id.json"
  on_snap="$(snapshot_path "$id" on)"
  off_snap="$(snapshot_path "$id" off)"

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
      if detected="$(auto_detect_baseline "$id")"; then
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
      err "active config matches neither enabled nor disabled snapshot. Refusing to overwrite $on_snap. Inspect manually, then remove the snapshot you no longer trust and rerun."
    fi
    cp -p "$active" "$on_snap"
    log "saved current active config -> $(basename "$on_snap")"
    cp -p "$off_snap" "$active"
    log "restored disabled config -> $(basename "$active")"
  fi

  agent_bootout
  log "bridge disabled. Restart Claude Desktop for the provider change to take effect."
}

cmd_enable() {
  local id active on_snap off_snap
  id="$(read_active_id)"
  active="$CONFIG_LIB/$id.json"
  on_snap="$(snapshot_path "$id" on)"
  off_snap="$(snapshot_path "$id" off)"

  [[ -f "$active" ]] || err "active provider config missing: $active"
  [[ -f "$on_snap" ]] || err "no enabled snapshot at $on_snap. Run --disable first from the bridge-active state, or copy a known bridge-active config there."

  if cmp -s "$active" "$on_snap"; then
    log "active config already matches enabled snapshot, leaving file alone"
  else
    if [[ -f "$off_snap" ]] && ! cmp -s "$active" "$off_snap"; then
      err "active config matches neither enabled nor disabled snapshot. Refusing to overwrite $off_snap. Inspect manually, then remove the snapshot you no longer trust and rerun."
    fi
    cp -p "$active" "$off_snap"
    log "saved current active config -> $(basename "$off_snap")"
    cp -p "$on_snap" "$active"
    log "restored enabled config -> $(basename "$active")"
  fi

  agent_bootstrap
  log "bridge enabled. Restart Claude Desktop for the provider change to take effect."
}

snapshot_presence() {
  if [[ -f "$1" ]]; then
    printf 'present'
  else
    printf 'absent'
  fi
}

cmd_status() {
  local id active on_snap off_snap state
  id="$(read_active_id)"
  active="$CONFIG_LIB/$id.json"
  on_snap="$(snapshot_path "$id" on)"
  off_snap="$(snapshot_path "$id" off)"

  if [[ ! -f "$active" ]]; then
    state="missing active config"
  elif [[ -f "$on_snap" ]] && cmp -s "$active" "$on_snap"; then
    state="enabled"
  elif [[ -f "$off_snap" ]] && cmp -s "$active" "$off_snap"; then
    state="disabled"
  else
    state="custom (matches neither snapshot)"
  fi

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
      --enable)
        [[ -n "$action" ]] && err "specify only one of --enable / --disable / --status"
        action=enable; shift ;;
      --disable)
        [[ -n "$action" ]] && err "specify only one of --enable / --disable / --status"
        action=disable; shift ;;
      --status)
        [[ -n "$action" ]] && err "specify only one of --enable / --disable / --status"
        action=status; shift ;;
      --baseline)
        baseline="${2:-}"
        [[ -n "$baseline" ]] || err "--baseline requires a path"
        shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) err "unknown argument: $1" ;;
    esac
  done

  if [[ -z "$action" ]]; then
    usage
    err "must specify --enable, --disable, or --status"
  fi

  if [[ -n "$baseline" && "$action" != "disable" ]]; then
    err "--baseline only applies to --disable"
  fi

  case "$action" in
    enable)  cmd_enable ;;
    disable) cmd_disable "$baseline" ;;
    status)  cmd_status ;;
  esac
}

main "$@"
