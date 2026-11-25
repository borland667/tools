#!/usr/bin/env bash
# Give each git worktree of a repo its own port range. Source it from a shell
# hook to set the variables; run it (./worktree-ports.sh) to print what this
# checkout resolved.
#
# Each worktree claims a numbered slot once, atomically, in the git common dir,
# so two worktrees can never share one. The main checkout is slot 0. Ports are
# BASE + STRIDE * slot, and COMPOSE_PROJECT_NAME is the repo name plus the slot.
# Edit _wt_ports for the target stack and delete pairs it lacks. Any of them
# can be overridden in the gitignored .env.worktree, sourced last. Slots of
# worktrees git no longer registers are reclaimed.

_wt_stride=10
_wt_max_slots=50

# Docker Compose project names take lowercase letters, digits, "-" and "_",
# and must start with a letter or digit.
_wt_slug() {
  local slug
  slug="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-_')"
  case "$slug" in
    [a-z0-9]*) printf '%s' "$slug" ;;
    *) printf 'repo%s' "$slug" ;;
  esac
}

# Claim $dir/$slot for $top only if the slot is still free: a hard link cannot
# overwrite an existing file, so there is no window where the slot exists but
# is empty.
_wt_claim() {
  local dir="$1" slot="$2" top="$3" tmp
  tmp="$dir/.claim-$slot.$$"
  if printf '%s' "$top" > "$tmp" && ln "$tmp" "$dir/$slot" 2>/dev/null; then
    rm -f "$tmp"
    return 0
  fi
  rm -f "$tmp"
  return 1
}

_wt_slot() {
  # Note: "path" is a tied parameter in zsh (it shadows PATH), so it is not
  # used as a local name here.
  local common top dir claim wtpath known slot
  common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
  top="$(git rev-parse --show-toplevel 2>/dev/null)" || return 1
  if [ "$(git rev-parse --path-format=absolute --git-dir)" = "$common" ]; then
    echo 0
    return 0
  fi
  dir="$common/worktree-slots"
  mkdir -p "$dir" || return 1
  # Slot files are plain integers, so ls is safe and avoids zsh's
  # "no matches found" on an empty glob.
  # shellcheck disable=SC2045
  for claim in $(ls "$dir"); do
    [ -s "$dir/$claim" ] || continue
    if [ "$(cat "$dir/$claim")" = "$top" ]; then
      echo "$claim"
      return 0
    fi
  done
  # Reclaim only slots git no longer registers, so a worktree whose directory
  # is briefly unmounted keeps its slot.
  known="$(git worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')"
  # shellcheck disable=SC2045
  for claim in $(ls "$dir"); do
    [ -s "$dir/$claim" ] || continue
    wtpath="$(cat "$dir/$claim")"
    case "
$known
" in
      *"
$wtpath
"*) continue ;;
    esac
    rm -f "$dir/$claim"
  done
  slot=1
  while [ "$slot" -le "$_wt_max_slots" ]; do
    if _wt_claim "$dir" "$slot" "$top"; then
      echo "$slot"
      return 0
    fi
    slot=$((slot + 1))
  done
  printf 'worktree-ports: all %s slots are claimed; this checkout reuses slot 0 ports\n' \
    "$_wt_max_slots" >&2
  echo 0
  return 0
}

# One "NAME BASE" pair per line; each NAME becomes an exported variable.
_wt_ports() {
  printf '%s\n' "WEB_PORT 3000" "DB_PORT 5432" "CACHE_PORT 6379"
}

WORKTREE_SLOT="$(_wt_slot)"
if [ -z "$WORKTREE_SLOT" ]; then
  printf 'worktree-ports: git did not report a checkout; keeping the base ports\n' >&2
  WORKTREE_SLOT=0
fi
export WORKTREE_SLOT

while read -r _wt_name _wt_base; do
  export "$_wt_name=$((_wt_base + _wt_stride * WORKTREE_SLOT))"
done <<EOF
$(_wt_ports)
EOF
COMPOSE_PROJECT_NAME="$(_wt_slug "$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")")-$WORKTREE_SLOT"
export COMPOSE_PROJECT_NAME

_wt_local="$(git rev-parse --show-toplevel 2>/dev/null)/.env.worktree"
# shellcheck disable=SC1090
[ -f "$_wt_local" ] && . "$_wt_local"

# Only print when run directly, so sourcing from a shell hook stays quiet.
# zsh reports "file" in ZSH_EVAL_CONTEXT when a script is sourced.
_wt_direct=0
if [ -n "${ZSH_EVAL_CONTEXT:-}" ]; then
  [ "$ZSH_EVAL_CONTEXT" = "toplevel" ] && _wt_direct=1
elif [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  _wt_direct=1
fi

if [ "$_wt_direct" = 1 ]; then
  printf 'slot %s\n' "$WORKTREE_SLOT"
  while read -r _wt_name _wt_base; do
    eval "printf '%s=%s\n' \"\$_wt_name\" \"\$$_wt_name\""
  done <<EOF
$(_wt_ports)
EOF
  printf 'COMPOSE_PROJECT_NAME=%s\n' "$COMPOSE_PROJECT_NAME"
fi

unset _wt_stride _wt_max_slots _wt_direct _wt_name _wt_base _wt_local
unset -f _wt_slot _wt_claim _wt_ports _wt_slug
