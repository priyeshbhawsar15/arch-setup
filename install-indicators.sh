#!/usr/bin/env bash
# Install the independently managed personal indicator clone at an exact pin.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"

plugin_id="priyesh.indicators"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-indicators.git"
plugin_commit="f159ed5d870c7b402a4885ad1c72236620819e0f"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
shell_config="$HOME/.config/omarchy/shell.json"
layout_state="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/indicators-layout.json"

require_omarchy

configure_layout() {
  python3 "$SCRIPT_DIR/indicators/layout.py" "$1" "$shell_config" "$layout_state"
}

plugin_is_enabled() {
  omarchy plugin list --json | jq -e --arg id "$plugin_id" 'any(.[]; .id == $id and .enabled)' >/dev/null
}

disable_plugin() {
  configure_layout disable
  if plugin_is_enabled; then omarchy plugin disable "$plugin_id"; fi
  omarchy-shell shell rescanPlugins >/dev/null
  log "Personal indicators are disabled; unrelated bar settings were preserved."
}

case "${1:-}" in
  --disable) disable_plugin; exit 0 ;;
  --remove)
    backup="$(backup_feature_paths indicators-remove "$layout_state" "$shell_config" "$plugin_dir")"
    disable_plugin
    if [[ -e "$plugin_dir" ]]; then omarchy plugin remove "$plugin_id" --yes; fi
    log "Removed personal indicators. Backup: $backup"
    exit 0 ;;
  "") ;;
  *) log "Usage: $0 [--disable|--remove]"; exit 1 ;;
esac

[[ "$plugin_commit" =~ ^[0-9a-f]{40}$ ]] || {
  log "The reviewed private indicators revision must be published and pinned before installation."
  exit 1
}
for dependency in git jq python3; do
  if ! command -v "$dependency" >/dev/null; then
    package="$dependency"
    [[ "$dependency" == python3 ]] && package=python
    omarchy pkg add "$package"
  fi
done
[[ -f "$shell_config" ]] || { log "An existing Omarchy desktop configuration is required."; exit 1; }

checkout_current=false
if managed_plugin_checkout_current "$plugin_dir" "$plugin_url" "$plugin_commit"; then checkout_current=true; fi
if [[ "$checkout_current" == false && -e "$plugin_dir" && ! -d "$plugin_dir/.git" ]]; then
  # The historical copied clone has no revision identity. Preserve it in full
  # and let the staged helper install at the original path, with rollback.
  original="$plugin_dir"
  legacy="$(backup_feature_paths indicators-legacy "$plugin_dir")"
  temporary="$(mktemp -d "$(dirname -- "$plugin_dir")/.indicators-legacy.XXXXXX")"
  rmdir -- "$temporary"
  mv -- "$plugin_dir" "$temporary"
  if ! install_pinned_plugin "$plugin_dir" "$plugin_url" "$plugin_commit" "$plugin_id"; then
    mv -- "$temporary" "$plugin_dir"
    exit 1
  fi
  rm -rf -- "$temporary"
  log "Archived the historical indicators clone: $legacy"
else
  install_pinned_plugin "$plugin_dir" "$plugin_url" "$plugin_commit" "$plugin_id"
fi
configure_layout enable
omarchy-shell shell rescanPlugins >/dev/null
for ((attempt=0; attempt<40; attempt++)); do
  if plugin_is_enabled; then
    if [[ "$checkout_current" == true ]]; then log "Personal indicators are already installed.";
    else log "Installed and enabled personal indicators at $plugin_commit."; fi
    exit 0
  fi
  sleep 0.05
done
log "Omarchy did not discover the configured personal indicators."
exit 1
