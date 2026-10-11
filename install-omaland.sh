#!/usr/bin/env bash

# Installs Omaland (Hyprland Visual Look & Feel Editor) for Omarchy at a pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="bobbynicholas.omaland"
plugin_url="https://github.com/bobby-nicholas/omaland.git"
plugin_commit="ec232b6aa2e31b2f089ad89b653cd706989865b9"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"

menu_file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
desktop_file="$HOME/.local/share/applications/omaland.desktop"

require_omarchy

fail() {
  log "Omaland: $*"
  exit 1
}

ensure_command() {
  local command="$1" package="$2"
  if command -v "$command" >/dev/null 2>&1; then
    return
  fi
  log "Installing required command '$command'..."
  omarchy pkg add "$package"
}

plugin_checkout_is_current() {
  [[ -d "$plugin_dir/.git" ]] || return 1
  [[ "$(git -C "$plugin_dir" remote get-url origin 2>/dev/null || true)" == "$plugin_url" ]] || return 1
  [[ "$(git -C "$plugin_dir" rev-parse HEAD 2>/dev/null || true)" == "$plugin_commit" ]] || return 1
  git -C "$plugin_dir" diff --quiet || return 1
  git -C "$plugin_dir" diff --cached --quiet || return 1
  [[ -z "$(git -C "$plugin_dir" status --porcelain --untracked-files=all)" ]] || return 1
}

plugin_is_enabled() {
  omarchy plugin list --json | jq -e --arg id "$plugin_id" \
    'any(.[]; .id == $id and .enabled)' >/dev/null
}

wait_for_plugin_discovery() {
  local attempt
  for (( attempt = 0; attempt < 40; attempt++ )); do
    if omarchy plugin list --json | jq -e --arg id "$plugin_id" \
      'any(.[]; .id == $id)' >/dev/null; then
      return
    fi
    sleep 0.05
  done
  fail "Omarchy did not discover $plugin_id after a plugin rescan"
}

checkout_pinned_plugin() {
  local parent stage
  parent="$(dirname -- "$plugin_dir")"
  mkdir -p -- "$parent"
  stage="$(mktemp -d "$parent/.${plugin_id}.install.XXXXXX")"
  cleanup_stage() { rm -rf -- "$stage"; }
  trap cleanup_stage RETURN

  GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$plugin_url" "$stage" \
    || fail "could not clone $plugin_url"
  git -C "$stage" checkout --quiet --detach "$plugin_commit" \
    || fail "could not check out pinned commit $plugin_commit"
  git -C "$stage" submodule update --init --recursive
  omarchy plugin validate "$stage" \
    || fail "the pinned plugin checkout did not pass Omarchy validation"
  mv -- "$stage" "$plugin_dir"
  trap - RETURN
}

update_pinned_plugin() {
  [[ -d "$plugin_dir/.git" ]] || fail "the existing plugin is not a Git checkout"
  [[ "$(git -C "$plugin_dir" remote get-url origin 2>/dev/null || true)" == "$plugin_url" ]] \
    || fail "the existing plugin checkout is not managed by this installer"
  git -C "$plugin_dir" diff --quiet \
    || fail "the existing plugin checkout has uncommitted changes"
  git -C "$plugin_dir" diff --cached --quiet \
    || fail "the existing plugin checkout has staged changes"
  [[ -z "$(git -C "$plugin_dir" status --porcelain --untracked-files=all)" ]] \
    || fail "the existing plugin checkout has untracked files"

  git -C "$plugin_dir" fetch --quiet --tags origin \
    || fail "could not fetch the reviewed pinned revision"
  git -C "$plugin_dir" checkout --quiet --detach "$plugin_commit" \
    || fail "could not check out pinned commit $plugin_commit"
  git -C "$plugin_dir" submodule update --init --recursive
  omarchy plugin validate "$plugin_dir" \
    || fail "the updated pinned checkout did not pass Omarchy validation"
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  install_desktop_entry
  install_menu_entry
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

install_desktop_entry() {
  mkdir -p -- "$(dirname -- "$desktop_file")"
  sed "s|@ICON@|$plugin_dir/icon.png|" "$plugin_dir/omaland.desktop" > "$desktop_file"
  chmod +x "$desktop_file"
  update-desktop-database "$(dirname -- "$desktop_file")" >/dev/null 2>&1 || true
}

remove_desktop_entry() {
  if [[ -f "$desktop_file" ]]; then
    rm -f -- "$desktop_file"
    update-desktop-database "$(dirname -- "$desktop_file")" >/dev/null 2>&1 || true
  fi
}

install_menu_entry() {
  mkdir -p -- "$(dirname -- "$menu_file")"
  if [[ ! -f "$menu_file" ]]; then
    cat >"$menu_file" <<'EOF'
{
  "style.hyprland": {"icon": "󰸌", "label": "Hyprland", "aliases": ["hyprland", "looknfeel"]},
  "style.hyprland.omaland": {"icon": "󰸌", "label": "Omaland Visual Editor", "aliases": ["omaland"], "action": "omarchy-shell shell toggle bobbynicholas.omaland"},
  "style.hyprland.edit": {"icon": "󰏫", "label": "Edit Config", "action": "omarchy-launch-config-editor \"$HOME/.config/hypr/looknfeel.lua\""}
}
EOF
    return
  fi

  if grep -q '"style.hyprland.omaland"' "$menu_file" 2>/dev/null; then
    return
  fi

  MENU_FILE="$menu_file" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["MENU_FILE"])
text = path.read_text()

entries = '''
  "style.hyprland": {"icon": "󰸌", "label": "Hyprland", "aliases": ["hyprland", "looknfeel"]},
  "style.hyprland.omaland": {"icon": "󰸌", "label": "Omaland Visual Editor", "aliases": ["omaland"], "action": "omarchy-shell shell toggle bobbynicholas.omaland"},
  "style.hyprland.edit": {"icon": "󰏫", "label": "Edit Config", "action": "omarchy-launch-config-editor \\"$HOME/.config/hypr/looknfeel.lua\\"}'''

if '"style.hyprland.omaland"' not in text:
    lines = text.rstrip().splitlines()
    if len(lines) > 1 and lines[-1].strip() == "}":
        lines[-2] = lines[-2].rstrip() + ","
        lines.insert(-1, entries)
        path.write_text("\n".join(lines) + "\n")
PY
}

remove_menu_entry() {
  [[ -f "$menu_file" ]] || return 0
  MENU_FILE="$menu_file" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["MENU_FILE"])
text = path.read_text()
filtered = [line for line in text.splitlines(keepends=True)
            if '"style.hyprland' not in line]
if filtered != text.splitlines(keepends=True):
    path.write_text("".join(filtered))
PY
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  remove_desktop_entry
  remove_menu_entry
  log "Omaland is disabled."
}

backup_feature_data() {
  local backup_dir path relative_path
  backup_dir="$HOME/.local/state/arch-setups/backups/omaland-remove-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"
  for path in "$HOME/.config/omaland" "$HOME/.local/state/omaland"; do
    [[ -e "$path" || -L "$path" ]] || continue
    relative_path="${path#$HOME/}"
    mkdir -p -- "$backup_dir/$(dirname -- "$relative_path")"
    cp -a -- "$path" "$backup_dir/$relative_path"
  done
  printf '%s\n' "$backup_dir"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  omarchy plugin remove "$plugin_id" --yes
  log "Removed Omaland. Configuration and state were backed up to: $backup_dir"
}

case "${1:-}" in
  --disable) disable_plugin; exit 0 ;;
  --remove) remove_plugin; exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

ensure_command git git
ensure_command jq jq

checkout_changed=false
if [[ -e "$plugin_dir" || -L "$plugin_dir" ]]; then
  if ! plugin_checkout_is_current; then
    update_pinned_plugin
    checkout_changed=true
  fi
else
  checkout_pinned_plugin
  checkout_changed=true
fi

if plugin_is_enabled && [[ "$checkout_changed" == false ]]; then
  log "Omaland is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
fi

enable_plugin
log "Installed and activated Omaland at $plugin_commit."
