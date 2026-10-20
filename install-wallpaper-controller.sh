#!/usr/bin/env bash

# Installs the Wallpaper Controller at an audited commit. `omarchy plugin add`
# clones a branch tip, so it cannot satisfy this setup's pinned-revision rule.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

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
  [[ -d "$plugin_dir/.git" ]] || return 1

  local installed_remote installed_commit
  installed_remote="$(git -C "$plugin_dir" remote get-url origin 2>/dev/null || true)"
  installed_commit="$(git -C "$plugin_dir" rev-parse HEAD 2>/dev/null || true)"

  [[ "$installed_remote" == "$plugin_url" || "$installed_remote" == "$plugin_ssh_url" ]] || return 1
  [[ "$installed_commit" == "$plugin_commit" ]] || return 1
  git -C "$plugin_dir" diff --quiet || return 1
  git -C "$plugin_dir" diff --cached --quiet || return 1
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

backup_existing_plugin() {
  [[ -e "$plugin_dir" || -L "$plugin_dir" ]] || return 0

  local backup_dir
  backup_dir="$HOME/.local/state/arch-setups/backups/wallpaper-controller-plugin-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"

  omarchy plugin disable "$plugin_id" >/dev/null 2>&1 || true
  mv -- "$plugin_dir" "$backup_dir/plugin"
  omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  log "Archived the replaced Wallpaper Controller plugin to: $backup_dir/plugin"
}

install_pinned_plugin() {
  local plugins_dir stage staged_id
  plugins_dir="$(dirname -- "$plugin_dir")"
  mkdir -p -- "$plugins_dir"
  stage="$(mktemp -d "$plugins_dir/.${plugin_id}.install.XXXXXX")"

  cleanup_stage() { rm -rf -- "$stage"; }
  trap cleanup_stage RETURN

  GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$plugin_url" "$stage" || fail "could not clone $plugin_url"
  git -C "$stage" checkout --quiet --detach "$plugin_commit" || fail "could not check out pinned commit $plugin_commit"
  git -C "$stage" submodule update --init --recursive
  omarchy plugin validate "$stage" || fail "pinned plugin failed Omarchy validation"

  staged_id="$(jq -r '.id // empty' "$stage/manifest.json")"
  [[ "$staged_id" == "$plugin_id" ]] || fail "pinned plugin manifest has unexpected id: $staged_id"

  mv -- "$stage" "$plugin_dir"
  trap - RETURN
  omarchy-shell shell rescanPlugins >/dev/null
}

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

  MENU_FILE="$menu_file" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["MENU_FILE"])
text = path.read_text()
filtered = [line for line in text.splitlines(keepends=True)
            if '"style.wallpaper-controller"' not in line]
if filtered != text.splitlines(keepends=True):
    path.write_text("".join(filtered))
PY
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
  disable_plugin

  local backup_dir path relative_path
  backup_dir="$HOME/.local/state/arch-setups/backups/wallpaper-controller-remove-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"

  for path in "$config_file" "$HOME/.local/state/omarchy/wallpaper-controller" \
    "$HOME/.config/omarchy/backgrounds/wallpaper-controller-transparent.png" \
    "$HOME/.config/omarchy/backgrounds/wallpaper-controller-black.png"; do
    if [[ -e "$path" || -L "$path" ]]; then
      relative_path="${path#$HOME/}"
      mkdir -p -- "$backup_dir/$(dirname -- "$relative_path")"
      mv -- "$path" "$backup_dir/$relative_path"
    fi
  done

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
  backup_existing_plugin
  install_pinned_plugin
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
