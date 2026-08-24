#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

installers=(
  install-chrome.sh
  install-brave-origin.sh
  install-zen.sh
  install-stow.sh
  install-steam.sh
  install-sunshine.sh
  install-tailscale.sh
  install-keyd.sh
  install-zsh.sh
  install-hyprland.sh
  install-wallpaper-controller.sh
  install-per-monitor-bar.sh
)

for installer in "${installers[@]}"; do
  printf '\n==> Running %s\n' "$installer"
  "$SCRIPT_DIR/$installer"
done

printf '\n==> Running install-dotfiles.sh\n'
"$SCRIPT_DIR/install-dotfiles.sh"

printf '\nAll installers completed.\n'
