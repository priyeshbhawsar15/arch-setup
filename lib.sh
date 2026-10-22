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

  local path
  for path in "$HOME/.local/share/applications/$desktop_file" "/usr/share/applications/$desktop_file" "$HOME/.nix-profile/share/applications/$desktop_file"; do
    [[ -f "$path" ]] || continue
    # Stale launchers are not installed applications. Resolve the advertised
    # executable without running/evaluating any desktop-entry command.
    if python3 - "$path" <<'PY'
import configparser, os, shlex, shutil, sys
try:
    entry = configparser.ConfigParser(interpolation=None, strict=False)
    entry.read(sys.argv[1])
    value = entry['Desktop Entry'].get('TryExec') or entry['Desktop Entry'].get('Exec', '')
    args = shlex.split(value)
    if args and os.path.basename(args[0]) == 'env':
        args.pop(0)
        while args and '=' in args[0]:
            args.pop(0)
    command = os.path.expanduser(args[0]) if args else ''
    good = bool(command and shutil.which(command))
except (ValueError, KeyError, configparser.Error):
    good = False
sys.exit(0 if good else 1)
PY
    then return 0; fi
  done
  return 1
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

managed_plugin_checkout_current() {
  local dir="$1" url="$2" revision="$3"
  [[ -d "$dir/.git" && ! -L "$dir" ]] || return 1
  [[ "$(git -C "$dir" remote get-url origin 2>/dev/null)" == "$url" ]] || return 1
  [[ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" == "$revision" ]] || return 1
  [[ -z "$(git -C "$dir" status --porcelain --untracked-files=all)" ]]
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


# Validate a staged, exact revision before replacing an existing clean checkout.
# The subshell EXIT trap also cleans staging directories on failed commands.
install_pinned_plugin() (
  set -euo pipefail
  local dir="$1" url="$2" revision="$3" id="$4" reviewed_origin="${5:-}" parent stage previous="" origin
  if [[ -e "$dir" || -L "$dir" ]]; then
    [[ -d "$dir/.git" && ! -L "$dir" ]] || {
      printf 'Plugin path is not a managed checkout: %s\n' "$dir" >&2; return 1;
    }
    origin="$(git -C "$dir" remote get-url origin)"
    [[ "$origin" == "$url" || ( -n "$reviewed_origin" && "$origin" == "$reviewed_origin" ) ]] || {
      printf 'Refusing foreign plugin origin: %s\n' "$dir" >&2; return 1;
    }
    [[ -z "$(git -C "$dir" status --porcelain --untracked-files=all)" ]] || {
      printf 'Plugin has local changes; refusing to overwrite: %s\n' "$dir" >&2; return 1;
    }
    if managed_plugin_checkout_current "$dir" "$url" "$revision"; then return 0; fi
  fi
  parent="$(dirname -- "$dir")"
  mkdir -p -- "$parent"
  stage="$(mktemp -d "$parent/.${id}.install.XXXXXX")"
  trap 'rm -rf -- "$stage"; if [[ -n "$previous" && -e "$previous" && ! -e "$dir" ]]; then mv -- "$previous" "$dir"; fi' EXIT
  GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$url" "$stage"
  git -C "$stage" checkout --quiet --detach "$revision"
  git -C "$stage" submodule update --init --recursive
  [[ "$(jq -r '.id // empty' "$stage/manifest.json")" == "$id" ]] || {
    printf 'Pinned checkout has unexpected plugin ID (expected %s)\n' "$id" >&2; return 1;
  }
  omarchy plugin validate "$stage" || {
    printf 'Pinned plugin validation failed: %s\n' "$id" >&2; return 1;
  }
  if [[ -e "$dir" ]]; then
    previous="$(mktemp -d "$parent/.${id}.previous.XXXXXX")"
    rmdir -- "$previous"
    mv -- "$dir" "$previous"
  fi
  mv -- "$stage" "$dir"
  [[ -z "$previous" ]] || rm -rf -- "$previous"
  trap - EXIT
)

reconcile_plugin_helper() {
  local name="$1" executable="$2" link="${3:-$HOME/.local/bin/$1}"
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

remove_plugin_helper() {
  local name="$1" executable="$2" link="$HOME/.local/bin/$1"
  if [[ -L "$link" && "$(readlink "$link")" == "$executable" ]]; then rm -- "$link"; fi
}

# A direct installer invocation is an explicit choice; install-all honors it.
remember_feature_choice() {
  [[ "${ARCH_SETUPS_AUTOMATED:-}" != 1 ]] || return 0
  python3 "$SCRIPT_DIR/config/feature-profile.py" --profile "${ARCH_SETUPS_PROFILE:-$SCRIPT_DIR/features.json}" \
    remember "$(basename -- "$1")" "$2"
}

feature_is_enabled() {
  local status=0
  python3 "$SCRIPT_DIR/config/feature-profile.py" --profile "${ARCH_SETUPS_PROFILE:-$SCRIPT_DIR/features.json}" enabled "$1" || status=$?
  if ((status > 1)); then
    log "Invalid feature configuration; refusing to treat it as disabled." >&2
    exit "$status"
  fi
  return "$status"
}

# Remember only successful explicit plugin lifecycle actions. Automatic setup
# must not overwrite an operator's choices, including disabled dependencies.
feature_lifecycle() {
  [[ "${ARCH_SETUPS_AUTOMATED:-}" != 1 && "${ARCH_SETUPS_LIFECYCLE_RUNNING:-}" != 1 && "$(basename -- "$1")" == install-*.sh ]] || return 0
  local script="$1" choice=true status=0
  shift
  case "${1:-}" in
    --disable|--remove) choice=false ;;
    ""|--enable) ;;
    *) return 0 ;;
  esac
  python3 "$SCRIPT_DIR/config/feature-profile.py" validate || exit $?
  # A separate Bash keeps installer staging/rollback traps independent of this
  # success hook. Never source/eval an installer inside a conditional context.
  ARCH_SETUPS_LIFECYCLE_RUNNING=1 bash "$script" "$@" || status=$?
  if ((status == 0)); then remember_feature_choice "$script" "$choice" || status=$?; fi
  exit "$status"
}

# Render display identity selectors from the selected host policy.
monitor_layout_render() {
  python3 "$SCRIPT_DIR/hypr/scripts/monitor-layout.py" \
    --config "${ARCH_SETUPS_MONITOR_LAYOUT:-$SCRIPT_DIR/monitor-layout.json}" render "$1"
}

# Deploy a protocol-safe mise wrapper, replacing only explicitly known versions.
# Additional arguments are complete legacy file contents (without final newline).
install_mise_cli() {
  local tool="$1" source_wrapper="$2"
  shift 2
  local target_wrapper="$HOME/.local/bin/$tool" executable legacy stock_wrapper
  local replace=false changed=false backup_dir
  # Exact Omarchy 4.0.6 stock shim; --quiet still installs/updates at runtime.
  printf -v stock_wrapper '#!/bin/bash\nexport MISE_MINIMUM_RELEASE_AGE=0\nmise use -g --quiet "%s" || exit 1\nexec mise x "%s" -- "%s" "$@"' "$tool" "$tool" "$tool"

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
      for legacy in "$@" "$stock_wrapper"; do
        if cmp -s "$target_wrapper" <(printf '%s\n' "$legacy"); then
          replace=true
          break
        fi
      done
      # Exact previous protocol-safe wrappers performed mise installation at
      # runtime. Migrate those known bytes; preserve all unknown custom code.
      case "$tool:$(sha256sum "$target_wrapper" | cut -d' ' -f1)" in
        codex:f0cf7a3c426d4666f75e3484a4d52a01a53eedac49dca53f5e474404ac05601c|gh:6c99d2be357fdf139e73dbaa604f9a778c225bca78aa0911744fb8f9413bb691) replace=true ;;
      esac
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
      mkdir -p -m 700 "$backup_dir"
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

