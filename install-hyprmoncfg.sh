#!/usr/bin/env bash

# Installs hyprmoncfg: Multi-Monitor Manager for Omarchy at a pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="crmne.hyprmoncfg"
plugin_url="https://github.com/crmne/omarchy-hyprmoncfg.git"
plugin_tag="v2.3.5"
plugin_commit="cf05a04a50339510cd1f9d547fb5f80556ae6599"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
shell_config="$HOME/.config/omarchy/shell.json"

require_omarchy

fail() {
  log "hyprmoncfg: $*"
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

disable_inbuilt_monitor_manager() {
  [[ -f "$shell_config" ]] || return 0
  python3 - <<PY
import json
with open("$shell_config", "r") as f:
    data = json.load(f)

right = data.get("bar", {}).get("layout", {}).get("right", [])
right = [e for e in right if (e.get("id") if isinstance(e, dict) else e) not in ["hancore.shibumi.brightness", "crmne.hyprmoncfg"]]
right.append({"id": "crmne.hyprmoncfg"})
data["bar"]["layout"]["right"] = right

for p in data.get("plugins", []):
    if isinstance(p, dict) and p.get("id") == "hancore.shibumi.state":
        shibumi = p.get("shibumi", {})
        widgets = shibumi.get("widgets", {})
        if "G13" not in widgets:
            widgets["G13"] = {}
        widgets["G13"]["enabled"] = False

with open("$shell_config", "w") as f:
    json.dump(data, f, indent=2)
PY
}

restore_inbuilt_monitor_manager() {
  [[ -f "$shell_config" ]] || return 0
  python3 - <<PY
import json
with open("$shell_config", "r") as f:
    data = json.load(f)

for p in data.get("plugins", []):
    if isinstance(p, dict) and p.get("id") == "hancore.shibumi.state":
        shibumi = p.get("shibumi", {})
        widgets = shibumi.get("widgets", {})
        if "G13" in widgets:
            widgets["G13"]["enabled"] = True

right = data.get("bar", {}).get("layout", {}).get("right", [])
if not any((e.get("id") if isinstance(e, dict) else e) == "hancore.shibumi.brightness" for e in right):
    idx = -1
    for i, e in enumerate(right):
        if (e.get("id") if isinstance(e, dict) else e) in ["crmne.hyprmoncfg", "hancore.shibumi.bluetooth"]:
            idx = i
            break
    if idx >= 0:
        right.insert(idx, {"id": "hancore.shibumi.brightness"})
    else:
        right.append({"id": "hancore.shibumi.brightness"})
    data["bar"]["layout"]["right"] = right

with open("$shell_config", "w") as f:
    json.dump(data, f, indent=2)
PY
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  disable_inbuilt_monitor_manager
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  restore_inbuilt_monitor_manager
  log "hyprmoncfg is disabled."
}

backup_feature_data() {
  local backup_dir path relative_path
  backup_dir="$HOME/.local/state/arch-setups/backups/hyprmoncfg-remove-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"
  for path in "$HOME/.config/hyprmoncfg" "$HOME/.local/state/hyprmoncfg"; do
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
  log "Removed hyprmoncfg. Configuration and state were backed up to: $backup_dir"
}

case "${1:-}" in
  --disable) disable_plugin; exit 0 ;;
  --remove) remove_plugin; exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

ensure_command git git
ensure_command jq jq
ensure_command hyprmoncfg hyprmoncfg

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
  log "hyprmoncfg is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
fi

enable_plugin
log "Installed and activated hyprmoncfg at $plugin_tag ($plugin_commit)."
