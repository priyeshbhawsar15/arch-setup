#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

installers=(
  install-chrome.sh
  install-brave-origin.sh
  install-zen.sh
  install-stow.sh
  install-hermes-desktop.sh
  install-codex.sh
  install-github-cli.sh
  install-t3code.sh
  install-steam.sh
  install-lutris.sh
  install-sunshine.sh
  install-tailscale.sh
  install-keyd.sh
  install-zsh.sh
  install-hyprland.sh
  install-wallpaper-controller.sh
  install-shibumi-shell.sh
  install-per-monitor-workspaces.sh
  install-hyprmoncfg.sh
  install-lock-explorer.sh
  install-omaland.sh
  install-calendar.sh
  install-omniroute-quota.sh
  install-system-metrics.sh
  install-weather-widget.sh
  install-immich-photo-frame.sh
  install-obsidian-tasks-widget.sh
  install-home-assistant.sh
  install-monitor-layout.sh
)

for installer in "${installers[@]}"; do
  printf '\n==> Running %s\n' "$installer"
  "$SCRIPT_DIR/$installer"
done

printf '\n==> Running install-dotfiles.sh\n'
"$SCRIPT_DIR/install-dotfiles.sh"

printf '\nAll installers completed.\n'
