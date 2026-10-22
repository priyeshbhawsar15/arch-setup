#!/usr/bin/env bash

# Installs the Wallpaper Controller at an audited commit. `omarchy plugin add`
# clones a branch tip, so it cannot satisfy this setup's pinned-revision rule.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"

plugin_id="priyesh.wallpaper-controller"
plugin_url="https://github.com/priyeshbhawsar15/omawallpaper-manager.git"
plugin_ssh_url="git@github.com:priyeshbhawsar15/omawallpaper-manager.git"
plugin_commit="418884ce00419798dfbb0cb5eff27eefa6c4bf4d"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
config_seed="$SCRIPT_DIR/omarchy/wallpaper-controller.json"
config_file="$HOME/.config/omarchy/wallpaper-controller.json"
menu_file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
disabled_binding_toggle="$HOME/.local/state/omarchy/toggles/hypr/wallpaper-controller-disabled.lua"

require_omarchy

fail() {
  log "Wallpaper Controller: $*"
  exit 1
}

plugin_is_enabled() {
  omarchy plugin list --json | jq -e --arg id "$plugin_id" \
    'any(.[]; .id == $id and .enabled)' >/dev/null 2>&1
}

plugin_checkout_is_current() {
  managed_plugin_checkout_current "$plugin_dir" "$plugin_url" "$plugin_commit" ||
    managed_plugin_checkout_current "$plugin_dir" "$plugin_ssh_url" "$plugin_commit"
}

install_dependency() {
  local command_name="$1"
  local package_name="$2"
  local package_kind="$3"

  if is_command_available "$command_name"; then
    return
  fi

  log "Installing $package_name..."
  if [[ "$package_kind" == "aur" ]]; then
    omarchy pkg aur add "$package_name"
  else
    omarchy pkg add "$package_name"
  fi
}

# The old payload remains available until installation AND activation succeed.
# Use the shared staging validator; never disable a working plugin to download.
stage_replacement() {
  local parent
  parent="$(dirname -- "$plugin_dir")"
  mkdir -p -- "$parent"
  transaction="$(mktemp -d "$parent/.wallpaper-transaction.XXXXXX")"
  trap rollback_replacement EXIT
  install_pinned_plugin "$transaction/source" "$plugin_url" "$plugin_commit" "$plugin_id"
  if [[ -e "$plugin_dir" || -L "$plugin_dir" ]]; then
    [[ ! -L "$plugin_dir" && -d "$plugin_dir/.git" ]] || fail "refusing an unmanaged plugin path"
    origin="$(git -C "$plugin_dir" remote get-url origin)"
    [[ "$origin" == "$plugin_url" || "$origin" == "$plugin_ssh_url" ]] || fail "refusing a foreign plugin origin"
    [[ -z "$(git -C "$plugin_dir" status --porcelain --untracked-files=all)" ]] || fail "preserving local plugin changes"
  fi
  replacement_backup="$(backup_feature_paths wallpaper-controller-update "$plugin_dir" "$config_file" "$menu_file" "$HOME/.config/omarchy/shell.json")"
  plugin_is_enabled && previously_enabled=true
  if [[ -e "$plugin_dir" ]]; then
    omarchy plugin disable "$plugin_id"
    mv -- "$plugin_dir" "$transaction/previous"
  fi
  mv -- "$transaction/source" "$plugin_dir"
  swapped=true
  omarchy-shell shell rescanPlugins >/dev/null
}

rollback_replacement() {
  local status="$?" path relative
  trap - EXIT
  if [[ "$status" != 0 && -n "$replacement_backup" ]]; then
    if [[ -d "$transaction/previous" ]]; then
      [[ "$swapped" != true ]] || rm -rf -- "$plugin_dir"
      mv -- "$transaction/previous" "$plugin_dir"
    elif [[ "$swapped" == true ]]; then
      rm -rf -- "$plugin_dir"
    fi
    for path in "$config_file" "$menu_file" "$HOME/.config/omarchy/shell.json"; do
      relative="${path#/}"
      if [[ -e "$replacement_backup/$relative" ]]; then
        cp -a -- "$replacement_backup/$relative" "$path"
      elif [[ -f "$path" && ! -L "$path" ]]; then
        rm -- "$path"
      fi
    done
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
    if [[ "$previously_enabled" == true ]]; then omarchy plugin enable "$plugin_id" >/dev/null 2>&1 || true; fi
    log "Wallpaper replacement failed; restored the previous checkout. Backup: $replacement_backup"
  fi
  [[ -z "$transaction" ]] || rm -rf -- "$transaction"
  exit "$status"
}

transaction="" swapped=false previously_enabled=false replacement_backup=""

seed_configuration() {
  [[ -f "$config_seed" ]] || fail "missing managed configuration seed: $config_seed"
  if [[ -f "$config_file" ]]; then
    return
  fi

  install -Dm600 "$config_seed" "$config_file"
  log "Restored the saved Wallpaper Controller settings."
}

remove_menu_entry() {
  [[ -f "$menu_file" ]] || return 0

  python3 "$SCRIPT_DIR/config/managed-config.py" remove-menu "$menu_file" style.wallpaper-controller
}

set_shortcuts_disabled() {
  mkdir -p -- "$(dirname -- "$disabled_binding_toggle")"
  cat >"$disabled_binding_toggle" <<'EOF'
-- Wallpaper Controller is disabled; prevent its plugin-owned shortcuts running.
hl.unbind("SUPER + ALT + W")
hl.unbind("SUPER + SHIFT + R")
hl.unbind("SUPER + ALT + Q")
EOF
}

reload_hyprland() {
  if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
    hyprctl reload
    hyprctl configerrors
  fi
}

disable_plugin() {
  if [[ ! -e "$plugin_dir" && ! -L "$plugin_dir" ]]; then
    log "Wallpaper Controller is not installed."
    return
  fi

  omarchy plugin disable "$plugin_id" >/dev/null 2>&1 || true
  [[ -x "$plugin_dir/uninstall.sh" ]] && "$plugin_dir/uninstall.sh"
  remove_menu_entry
  set_shortcuts_disabled
  omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  reload_hyprland
  log "Wallpaper Controller is disabled; its menu entry and shortcuts are inactive."
}

remove_plugin() {
  if [[ -e "$plugin_dir" || -L "$plugin_dir" ]]; then
    plugin_checkout_is_current || fail "preserving a foreign, dirty or unpinned plugin; archive/reconcile it before removal"
  fi
  local backup_dir
  local paths=("$config_file" "$HOME/.local/state/omarchy/wallpaper-controller"
    "$HOME/.config/omarchy/backgrounds/wallpaper-controller-transparent.png"
    "$HOME/.config/omarchy/backgrounds/wallpaper-controller-black.png")
  # Capture the original selection/stop state before disable hooks mutate it.
  backup_dir="$(backup_feature_paths wallpaper-controller-remove "$plugin_dir" "${paths[@]}" "$menu_file" "$HOME/.config/omarchy/shell.json")"
  disable_plugin
  rm -rf -- "${paths[@]}"

  if [[ -e "$plugin_dir" || -L "$plugin_dir" ]]; then
    omarchy plugin remove "$plugin_id" --yes
  fi

  log "Removed Wallpaper Controller. Plugin data was archived to: $backup_dir"
}

case "${1:-}" in
  --disable)
    disable_plugin
    exit 0
    ;;
  --remove)
    remove_plugin
    exit 0
    ;;
  "")
    ;;
  *)
    fail "usage: $0 [--disable|--remove]"
    ;;
esac

install_dependency linux-wallpaperengine linux-wallpaperengine-git aur
install_dependency aether aether aur
install_dependency magick imagemagick repo
install_dependency zenity zenity repo

if plugin_checkout_is_current && plugin_is_enabled && [[ -f "$config_file" ]]; then
  log "Wallpaper Controller is already installed."
  exit 0
fi

if ! plugin_checkout_is_current; then
  stage_replacement
fi

seed_configuration
"$plugin_dir/install.sh"

if ! plugin_is_enabled; then
  if ! omarchy plugin enable "$plugin_id"; then
    # The shell can finish registering a just-rescanned plugin after the enable
    # command's RPC timeout. Accept that only after confirming its live state.
    sleep 1
    plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
  fi
fi

rm -f -- "$disabled_binding_toggle"
reload_hyprland
wallpaper-controller restore >/dev/null
log "Installed Wallpaper Controller at $plugin_commit and restored the saved wallpaper settings."
