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

# Archive feature data privately, preserving paths and leaving originals intact.
backup_feature_paths() {
  local label="$1" path relative backup parent
  shift
  parent="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/backups"
  mkdir -p -- "$parent"
  backup="$(mktemp -d "$parent/${label}-$(date +%Y%m%dT%H%M%S)-XXXXXX")"
  for path in "$@"; do
    [[ -e "$path" || -L "$path" ]] || continue
    relative="${path#/}"
    mkdir -p -- "$backup/$(dirname -- "$relative")"
    cp -a -- "$path" "$backup/$relative"
  done
  printf '%s\n' "$backup"
}

managed_git_checkout_current() {
  local dir="$1" url="$2" revision="$3"
  [[ -d "$dir/.git" && ! -L "$dir" ]] || return 1
  [[ "$(git -C "$dir" remote get-url origin 2>/dev/null)" == "$url" ]] || return 1
  [[ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" == "$revision" ]] || return 1
  [[ -z "$(git -C "$dir" status --porcelain --untracked-files=all)" ]]
}

# Clone or update an exact pinned commit into a dedicated managed git checkout.
# Requires matching origin + clean tree + HEAD; never overwrites unknown/dirty/symlink directories.
install_pinned_git_checkout() (
  set -euo pipefail
  local dir="$1" url="$2" revision="$3" label="${4:-source}" parent stage previous="" origin
  if [[ -e "$dir" || -L "$dir" ]]; then
    [[ -d "$dir/.git" && ! -L "$dir" ]] || {
      printf 'Managed path is not a git repository checkout: %s\n' "$dir" >&2; return 1;
    }
    origin="$(git -C "$dir" remote get-url origin 2>/dev/null || true)"
    [[ "$origin" == "$url" ]] || {
      printf 'Refusing foreign repository origin (%s != %s): %s\n' "$origin" "$url" "$dir" >&2; return 1;
    }
    [[ -z "$(git -C "$dir" status --porcelain --untracked-files=all)" ]] || {
      printf 'Managed repository has local changes; refusing to overwrite: %s\n' "$dir" >&2; return 1;
    }
    if managed_git_checkout_current "$dir" "$url" "$revision"; then return 0; fi
  fi
  parent="$(dirname -- "$dir")"
  mkdir -p -- "$parent"
  stage="$(mktemp -d "$parent/.${label}.install.XXXXXX")"
  trap 'rm -rf -- "$stage"; if [[ -n "$previous" && -e "$previous" && ! -e "$dir" ]]; then mv -- "$previous" "$dir"; fi' EXIT
  GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$url" "$stage"
  git -C "$stage" checkout --quiet --detach "$revision"
  if [[ -f "$stage/.gitmodules" ]]; then
    git -C "$stage" submodule update --init --recursive
  fi
  if [[ -e "$dir" ]]; then
    previous="$(mktemp -d "$parent/.${label}.previous.XXXXXX")"
    rmdir -- "$previous"
    mv -- "$dir" "$previous"
  fi
  mv -- "$stage" "$dir"
  [[ -z "$previous" ]] || rm -rf -- "$previous"
  trap - EXIT
)

reconcile_plugin_helper() {
  local name="$1" executable="$2" link="$HOME/.local/bin/$1"
  [[ -f "$executable" ]] || { printf 'Missing plugin helper: %s\n' "$executable" >&2; return 1; }
  if [[ -e "$link" || -L "$link" ]]; then
    [[ -L "$link" && "$(readlink "$link")" == "$executable" ]] || {
      printf 'Preserving custom helper at %s; resolve the conflict before installing.\n' "$link" >&2; return 1;
    }
  fi
  chmod +x -- "$executable"
  mkdir -p -- "$(dirname -- "$link")"
  [[ -L "$link" ]] || ln -s -- "$executable" "$link"
}

# A direct installer invocation is an explicit choice; install-all honors it.
remember_feature_choice() {
  [[ "${ARCH_SETUPS_AUTOMATED:-}" != 1 ]] || return 0
  python3 "$SCRIPT_DIR/config/feature-profile.py" --profile "$SCRIPT_DIR/features.json" \
    remember "$(basename -- "$1")" "$2"
}

feature_is_enabled() {
  python3 "$SCRIPT_DIR/config/feature-profile.py" --profile "$SCRIPT_DIR/features.json" enabled "$1"
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

