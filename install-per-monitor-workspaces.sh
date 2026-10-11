#!/usr/bin/env bash

# Installs the Shibumi-specific fork of Per-monitor Workspaces at one reviewed
# commit. The feature replaces Shibumi's workspace presentation, while its Lua
# actions provide named workspaces scoped to each focused monitor.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="mmsbrggr.per-monitor-workspaces"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-per-monitor-workspaces.git"
plugin_commit="0292ebec608cd7d3907b8f9f9427c252b242edf2"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
shell_config="$HOME/.config/omarchy/shell.json"
toggle_path="$HOME/.local/state/omarchy/toggles/hypr/per-monitor-workspaces.lua"
state_dir="$HOME/.local/state/omarchy"

require_omarchy

fail() {
  log "Per-monitor Workspaces: $*"
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

shibumi_is_active() {
  [[ -f "$shell_config" ]] || return 1
  jq -e '.bar.id == "hancore.shibumi.bar"' "$shell_config" >/dev/null
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

plugin_is_configured() {
  [[ -f "$shell_config" && -f "$toggle_path" ]] || return 1
  jq -e --arg id "$plugin_id" '
    .bar.id == "hancore.shibumi.bar"
    and any(.bar.layout.left[], .bar.layout.center[], .bar.layout.right[];
      type == "object" and .id == $id and .shibumiModule == true and .count == 5)
    and all(.plugins[] | select(type == "object" and .id? == "hancore.shibumi.state");
      (.shibumi.order.left // []) | all(. != ("G:" + $id)))
  ' "$shell_config" >/dev/null
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

write_enabled_toggle() {
  mkdir -p -- "$(dirname -- "$toggle_path")"
  cat > "$toggle_path" <<'EOF'
-- Presence enables Per-monitor Workspaces through managed Hyprland modules.
-- The plugin's named-workspace bindings are loaded from bindings.lua.
EOF
}

remove_restored_stock_workspace_entry() {
  [[ -f "$shell_config" ]] || return 0
  local temporary
  temporary="$(mktemp "${shell_config}.per-monitor-workspaces.XXXXXX")"
  jq '
    def entry_id: if type == "object" then (.id // "" | tostring) else tostring end;
    .bar.layout.left |= map(select(entry_id != "omarchy.workspaces"))
    | .bar.layout.center |= map(select(entry_id != "omarchy.workspaces"))
    | .bar.layout.right |= map(select(entry_id != "omarchy.workspaces"))
  ' "$shell_config" > "$temporary"
  chmod --reference="$shell_config" "$temporary"
  mv -- "$temporary" "$shell_config"
}

remove_native_shibumi_workspace_bar_entry() {
  [[ -f "$shell_config" ]] || return 0
  python3 - <<PY
import json
with open("$shell_config", "r") as f:
    data = json.load(f)

left = data.get("bar", {}).get("layout", {}).get("left", [])
data["bar"]["layout"]["left"] = [e for e in left if (e.get("id") if isinstance(e, dict) else e) != "hancore.shibumi.workspaces"]

for p in data.get("plugins", []):
    if isinstance(p, dict) and p.get("id") == "hancore.shibumi.state":
        shibumi = p.get("shibumi", {})
        order = shibumi.get("order", {})
        roles = shibumi.get("v1SlotRoles", {})
        left_order = order.get("left", [])
        if left_order:
            left_order = [g for g in left_order if g != "G:mmsbrggr.per-monitor-workspaces"]
            if "G2" in left_order:
                left_order.remove("G2")
            g1_idx = left_order.index("G1") if "G1" in left_order else -1
            left_order.insert(g1_idx + 1 if g1_idx >= 0 else 0, "G2")
            order["left"] = left_order
            roles["left"] = ["base"] * len(left_order)

with open("$shell_config", "w") as f:
    json.dump(data, f, indent=2)
PY
}

restore_native_shibumi_workspace_bar_entry() {
  [[ -f "$shell_config" ]] || return 0
  python3 - <<PY
import json
with open("$shell_config", "r") as f:
    data = json.load(f)

left = data.get("bar", {}).get("layout", {}).get("left", [])
if not any((e.get("id") if isinstance(e, dict) else e) == "hancore.shibumi.workspaces" for e in left):
    idx = -1
    for i, e in enumerate(left):
        if (e.get("id") if isinstance(e, dict) else e) == "hancore.shibumi.control-center":
            idx = i
            break
    left.insert(idx + 1 if idx >= 0 else 0, {"id": "hancore.shibumi.workspaces"})
    data["bar"]["layout"]["left"] = left

with open("$shell_config", "w") as f:
    json.dump(data, f, indent=2)
PY
}

reload_hyprland() {
  if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
    hyprctl reload
    hyprctl configerrors
  fi
}

enable_plugin() {
  shibumi_is_active || fail "Shibumi must be the active bar before enabling this Shibumi-only widget"
  [[ -d "$HOME/.config/omarchy/plugins/hancore.shibumi.state/lib/presentation" ]] \
    || fail "Shibumi's required presentation library is unavailable"

  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  omarchy bar set "$plugin_id" shibumiModule true --json
  omarchy bar set "$plugin_id" count 5 --json
  omarchy bar move "$plugin_id" --section left --before hancore.shibumi.status
  remove_native_shibumi_workspace_bar_entry
  write_enabled_toggle
  reload_hyprland

  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
  plugin_is_configured || fail "Shibumi did not retain the managed workspace widget configuration"
}

disable_plugin() {
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  # Restore Shibumi's native workspace bar entry and clean up temporary stock entries
  restore_native_shibumi_workspace_bar_entry
  remove_restored_stock_workspace_entry
  rm -f -- "$toggle_path"
  reload_hyprland
  log "Per-monitor Workspaces is disabled; Shibumi's native workspace widget and Omarchy's numeric workspace rules are restored."
}

backup_feature_data() {
  local backup_dir path relative_path
  backup_dir="$HOME/.local/state/arch-setups/backups/per-monitor-workspaces-remove-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"
  for path in \
    "$toggle_path" \
    "$state_dir/$plugin_id.lua" \
    "$state_dir/$plugin_id.layouts.lua" \
    "$state_dir/$plugin_id.offer-dismissed"; do
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
  rm -f -- \
    "$state_dir/$plugin_id.lua" \
    "$state_dir/$plugin_id.layouts.lua" \
    "$state_dir/$plugin_id.offer-dismissed"
  log "Removed Per-monitor Workspaces. Plugin state was backed up to: $backup_dir"
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

if plugin_is_enabled && plugin_is_configured && [[ "$checkout_changed" == false ]]; then
  log "Per-monitor Workspaces is already installed."
  exit 0
fi

if plugin_is_enabled; then
  omarchy plugin disable "$plugin_id"
  remove_restored_stock_workspace_entry
fi

enable_plugin
if [[ "$checkout_changed" == true ]]; then
  # Omarchy rescans the plugin catalog, but a running QML Loader may retain a
  # component from the preceding reviewed revision. Restart only on a changed
  # pin so the active Shibumi bar instantiates the new source deterministically.
  omarchy restart shell
fi
log "Installed and activated Per-monitor Workspaces at $plugin_commit."
