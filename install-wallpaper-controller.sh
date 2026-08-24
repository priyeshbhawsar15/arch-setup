#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

require_omarchy

plugin_id="priyesh.wallpaper-controller"
plugin_url="https://github.com/priyeshbhawsar15/omawallpaper-manager.git"
target_dir="$HOME/.config/omarchy/plugins/$plugin_id"
first_migration=true
grep -q '"migratedLegacy": true' "$HOME/.config/omarchy/wallpaper-controller.json" 2>/dev/null && first_migration=false

install_dependency() {
  local command_name="$1"
  local package_name="$2"
  local package_kind="$3"
  if command -v "$command_name" >/dev/null 2>&1; then
    return
  fi
  log "Installing $package_name..."
  if [[ "$package_kind" == "aur" ]]; then
    omarchy pkg aur add "$package_name"
  else
    omarchy pkg add "$package_name"
  fi
}

install_dependency linux-wallpaperengine linux-wallpaperengine-git aur
install_dependency aether aether aur
install_dependency magick imagemagick repo
install_dependency zenity zenity repo

is_current_git_plugin=false
if [[ -d "$target_dir/.git" ]]; then
  installed_remote="$(git -C "$target_dir" remote get-url origin 2>/dev/null || true)"
  if [[ "$installed_remote" == "$plugin_url" || "$installed_remote" == "git@github.com:priyeshbhawsar15/omawallpaper-manager.git" ]]; then
    is_current_git_plugin=true
  fi
fi

if [[ "$is_current_git_plugin" == true ]]; then
  "$target_dir/install.sh"
  log "Wallpaper Controller is already installed. Update it with: omarchy plugin update $plugin_id"
  exit 0
fi

# `plugin remove` backs up a manually copied plugin directory. It deliberately
# leaves the controller's config and rendered-wallpaper state untouched.
if [[ -e "$target_dir" ]]; then
  log "Migrating the existing local Wallpaper Controller plugin..."
  omarchy plugin remove "$plugin_id" --yes
fi

omarchy plugin add "$plugin_url" --enable --yes
[[ -x "$target_dir/install.sh" ]] || chmod +x "$target_dir/install.sh"
"$target_dir/install.sh"

if [[ "$first_migration" == false ]]; then
  wallpaper-controller restore >/dev/null
  log "Installed Wallpaper Controller from its Omarchy plugin repository."
  exit 0
fi

# Import the valid part of the former playlist before retiring the legacy
# service. A missing Steam subscription is never made the active wallpaper.
legacy_was_enabled=false
if systemctl --user is-enabled --quiet wallpaper-engine.service 2>/dev/null; then
  legacy_was_enabled=true
fi
systemctl --user stop wallpaper-engine.service wallpaper-engine-rotate.timer >/dev/null 2>&1 || true
pkill -f 'linux-wallpaperengine.*--layer background' >/dev/null 2>&1 || true
wallpaper-controller migrate-legacy >/dev/null
if ! wallpaper-controller restore >/dev/null; then
  if [[ "$legacy_was_enabled" == true ]]; then
    systemctl --user start wallpaper-engine.service >/dev/null 2>&1 || true
  fi
  log "Wallpaper Controller was installed, but no valid wallpaper could be restored; legacy services were left untouched."
  exit 1
fi

legacy_root="$HOME/.local/state/omarchy/wallpaper-controller/legacy-wallpaper-engine-$(date +%Y%m%d%H%M%S)"
mkdir -p "$legacy_root/bin" "$legacy_root/systemd"
systemctl --user disable --now wallpaper-engine.service wallpaper-engine-rotate.timer >/dev/null 2>&1 || true
for unit in "$HOME/.config/systemd/user/wallpaper-engine.service" "$HOME/.config/systemd/user/wallpaper-engine-rotate.service" "$HOME/.config/systemd/user/wallpaper-engine-rotate.timer"; do
  [[ -e "$unit" ]] && mv "$unit" "$legacy_root/systemd/"
done
for helper in wallpaper-engine-start wallpaper-engine-rotate wallpaper-engine-toggle wallpaper-engine-refresh-list wallpaper-engine-list; do
  [[ -e "$HOME/.local/bin/$helper" ]] && mv "$HOME/.local/bin/$helper" "$legacy_root/bin/"
done
[[ -d "$HOME/.config/wallpaper-engine" ]] && mv "$HOME/.config/wallpaper-engine" "$legacy_root/config"
systemctl --user daemon-reload
log "Installed Wallpaper Controller. Open it with Super+Alt+W."
