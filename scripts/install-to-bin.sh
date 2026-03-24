#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_DIR="${HOME}/bin"

DRY_RUN=0
FORCE=0
COPY_MODE=0

usage() {
  cat <<'EOF'
Install repo scripts into ~/bin for PATH usage.

Usage:
  scripts/install-to-bin.sh [options] <script-path> [<script-path> ...]
  scripts/install-to-bin.sh [options] --all

Options:
  --all       Install all top-level executable scripts from repo root
  --copy      Copy files instead of creating symlinks
  --force     Replace existing target in ~/bin if present
  --dry-run   Print planned actions without writing
  -h, --help  Show this help

Examples:
  scripts/install-to-bin.sh media_carver.py
  scripts/install-to-bin.sh --all --dry-run
EOF
}

log() {
  printf '%s\n' "$*"
}

run_or_echo() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "[dry-run] $*"
  else
    eval "$@"
  fi
}

is_installable_root_script() {
  local path="$1"
  [[ -f "${path}" ]] || return 1
  [[ "$(dirname "${path}")" == "${REPO_ROOT}" ]] || return 1
  [[ -x "${path}" ]] || return 1
  [[ "$(basename "${path}")" != .* ]] || return 1
  return 0
}

collect_all_root_scripts() {
  local candidates=()
  local file
  for file in "${REPO_ROOT}"/*; do
    if is_installable_root_script "${file}"; then
      candidates+=("$(basename "${file}")")
    fi
  done
  printf '%s\n' "${candidates[@]}"
}

install_one() {
  local rel_path="$1"
  local src="${REPO_ROOT}/${rel_path}"
  local name
  local dest

  if [[ ! -f "${src}" ]]; then
    log "ERROR: script not found: ${rel_path}"
    return 1
  fi

  name="$(basename "${src}")"
  dest="${BIN_DIR}/${name}"

  if [[ ! -x "${src}" ]]; then
    log "WARN: ${rel_path} is not executable; setting +x"
    run_or_echo "chmod +x \"${src}\""
  fi

  if [[ -e "${dest}" || -L "${dest}" ]]; then
    if [[ "${FORCE}" -ne 1 ]]; then
      log "SKIP: ${dest} exists (use --force to replace)"
      return 0
    fi
    run_or_echo "rm -f \"${dest}\""
  fi

  if [[ "${COPY_MODE}" -eq 1 ]]; then
    run_or_echo "cp \"${src}\" \"${dest}\""
    log "INSTALLED (copy): ${name} -> ${dest}"
  else
    run_or_echo "ln -s \"${src}\" \"${dest}\""
    log "INSTALLED (symlink): ${name} -> ${dest}"
  fi
}

main() {
  local install_all=0
  local scripts=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --all)
        install_all=1
        shift
        ;;
      --copy)
        COPY_MODE=1
        shift
        ;;
      --force)
        FORCE=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      -*)
        log "ERROR: unknown option: $1"
        usage
        exit 1
        ;;
      *)
        scripts+=("$1")
        shift
        ;;
    esac
  done

  if [[ "${install_all}" -eq 1 && "${#scripts[@]}" -gt 0 ]]; then
    log "ERROR: use either --all or explicit script paths"
    exit 1
  fi

  if [[ "${install_all}" -eq 0 && "${#scripts[@]}" -eq 0 ]]; then
    log "ERROR: provide script paths or use --all"
    usage
    exit 1
  fi

  run_or_echo "mkdir -p \"${BIN_DIR}\""

  if [[ "${install_all}" -eq 1 ]]; then
    mapfile -t scripts < <(collect_all_root_scripts)
    if [[ "${#scripts[@]}" -eq 0 ]]; then
      log "No top-level executable scripts found to install."
      exit 0
    fi
  fi

  local item
  for item in "${scripts[@]}"; do
    install_one "${item}"
  done

  log "Done."
}

main "$@"
