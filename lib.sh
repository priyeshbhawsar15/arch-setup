#!/bin/bash

set -euo pipefail

log() {
  printf '%s\n' "$*"
}

is_command_available() {
  command -v "$1" >/dev/null 2>&1
}

desktop_file_exists() {
  local desktop_file="$1"

  [[ -f "$HOME/.local/share/applications/$desktop_file" ]] ||
    [[ -f "/usr/share/applications/$desktop_file" ]] ||
    [[ -f "$HOME/.nix-profile/share/applications/$desktop_file" ]]
}

require_omarchy() {
  if ! is_command_available omarchy; then
    log "omarchy is not available on PATH."
    exit 1
  fi
}

# Deploy a protocol-safe mise wrapper, replacing only explicitly known versions.
# Additional arguments are complete legacy file contents (without final newline).
install_mise_cli() {
  local tool="$1" source_wrapper="$2"
  shift 2
  local target_wrapper="$HOME/.local/bin/$tool" executable legacy
  local replace=false changed=false backup_dir

  if ! is_command_available mise; then
    log "mise is required to manage $tool; install mise before running this installer."
    return 1
  fi
  executable="$(mise which "$tool" 2>/dev/null || true)"
  if [[ ! -x "$executable" ]]; then
    # Keep setup/status output separate from any command's machine-readable stdout.
    MISE_MINIMUM_RELEASE_AGE=0 mise use -g "$tool" >&2 || return 1
    executable="$(mise which "$tool")" || return 1
    [[ -x "$executable" ]] || { log "mise did not provide an executable for $tool."; return 1; }
    changed=true
  fi

  if [[ ! -e "$target_wrapper" && ! -L "$target_wrapper" ]]; then
    replace=true
  elif [[ ! -L "$target_wrapper" && -f "$target_wrapper" ]]; then
    if cmp -s "$source_wrapper" "$target_wrapper"; then
      if [[ ! -x "$target_wrapper" ]]; then replace=true; fi
    else
      for legacy in "$@"; do
        if cmp -s "$target_wrapper" <(printf '%s\n' "$legacy"); then
          replace=true
          break
        fi
      done
      if [[ "$replace" == false ]]; then
        log "Preserving custom $tool wrapper at $target_wrapper; ensure stdout stays protocol-safe."
      fi
    fi
  else
    log "Preserving custom $tool executable/symlink at $target_wrapper."
  fi

  if [[ "$replace" == true ]]; then
    if [[ -e "$target_wrapper" ]]; then
      backup_dir="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/backups/$tool-mise-$(date +%Y%m%dT%H%M%S)-$$"
      mkdir -p "$backup_dir"
      cp -a "$target_wrapper" "$backup_dir/$tool"
      log "Backed up $tool wrapper to $backup_dir/$tool"
    fi
    mkdir -p "$(dirname -- "$target_wrapper")"
    install -m 755 "$source_wrapper" "$target_wrapper"
    changed=true
  fi

  if [[ "$changed" == false ]]; then
    log "$tool already installed through mise (custom wrappers preserved)."
    return 0
  fi
  log "$tool mise installation/configuration complete."
}

