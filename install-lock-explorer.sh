#!/usr/bin/env bash

# Installs Lock Screen Explorer for Omarchy at a pinned commit.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

plugin_id="io.github.sirjul1337.lock-explorer"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-lock-explorer.git"
plugin_revision="v1.7.7 with monitor spanning and power controls"
plugin_commit="b1b010a9113185b215b652c141c4b30168a2836f"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
shell_config="$HOME/.config/omarchy/shell.json"
menu_file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"

require_omarchy

fail() {
  log "Lock Screen Explorer: $*"
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

install_menu_entry() {
  mkdir -p -- "$(dirname -- "$menu_file")"
  if [[ ! -f "$menu_file" ]]; then
    cat >"$menu_file" <<'EOF'
{
  "style.lock-explorer": {"icon": "󰌾", "label": "Lock Screen Explorer", "aliases": ["lockscreen", "lock explorer"], "action": "omarchy-shell shell summon io.github.sirjul1337.lock-explorer"}
}
EOF
    return
  fi

  if grep -q '"style.lock-explorer"' "$menu_file" 2>/dev/null; then
    return
  fi

  MENU_FILE="$menu_file" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["MENU_FILE"])
text = path.read_text()

entry = '  "style.lock-explorer": {"icon": "󰌾", "label": "Lock Screen Explorer", "aliases": ["lockscreen", "lock explorer"], "action": "omarchy-shell shell summon io.github.sirjul1337.lock-explorer"}'

if '"style.lock-explorer"' not in text:
    lines = text.rstrip().splitlines()
    if len(lines) > 1 and lines[-1].strip() == "}":
        lines[-2] = lines[-2].rstrip() + ","
        lines.insert(-1, entry)
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
            if '"style.lock-explorer"' not in line]
if filtered != text.splitlines(keepends=True):
    path.write_text("".join(filtered))
PY
}

managed_config_is_current() {
  jq -e --arg id "$plugin_id" --argjson roles "$monitor_roles" --argjson policy "$monitor_policy" '
    def integer_between($lo; $hi): type == "number" and . >= $lo and . <= $hi and floor == .;
    any(.plugins[]; .id == $id
      and .phasedPower.main == $roles[$policy.lockMain]
      and .phasedPower.sides == [$policy.lockSides[] | $roles[.]]
      and .phasedPower.ddcPowerOffMonitors == [$policy.lockSides[] | $roles[.]]
      and (.phasedPower.mainTimeoutMs | integer_between(1000; 3600000))
      and (.phasedPower.sideTimeoutMs | integer_between(1000; 3600000))
      and (.phasedPower.mainTint | integer_between(0; 100))
      and (.phasedPower.sideTint | integer_between(0; 100))
      and .wallpaperSpanGroups == [[$policy.wallpaperSpan[] | $roles[.]]])' "$shell_config" >/dev/null
}

configure_plugin() {
  managed_config_is_current && return 0
  cp -a -- "$shell_config" "$shell_config.bak-lock-power-$(date +%Y%m%d%H%M%S)"
  SHELL_CONFIG="$shell_config" PLUGIN_ID="$plugin_id" MONITOR_ROLES="$monitor_roles" MONITOR_POLICY="$monitor_policy" python3 - <<'PY'
import json
import os
from pathlib import Path
path = Path(os.environ['SHELL_CONFIG'])
config = json.loads(path.read_text())
entries = config.setdefault('plugins', [])
entry = next((e for e in entries if e.get('id') == os.environ['PLUGIN_ID']), None)
if entry is None:
    entry = {'id': os.environ['PLUGIN_ID']}
    entries.append(entry)
power = entry.setdefault('phasedPower', {})
roles = json.loads(os.environ['MONITOR_ROLES'])
policy = json.loads(os.environ['MONITOR_POLICY'])
power['main'] = roles[policy['lockMain']]
power['sides'] = [roles[r] for r in policy['lockSides']]
power['ddcPowerOffMonitors'] = power['sides']
power.setdefault('mainTimeoutMs', power.get('offMs', 60000))
power.setdefault('sideTimeoutMs', power.get('dimMs', 300000))
power.setdefault('mainTint', 100)
power.setdefault('sideTint', 90)
for key in ('offMs', 'dimMs', 'overlayOpacity'):
    power.pop(key, None)
entry['wallpaperSpanGroups'] = [[roles[r] for r in policy['wallpaperSpan']]]
path.write_text(json.dumps(config, indent=2) + '\n')
PY
  managed_config_is_current || fail "invalid monitor timeout/tint settings; use seconds 1–3600 and tint 0–100% in Lock Screen Explorer"
}

require_unlocked() {
  local status
  status="$(omarchy-shell lock status)" || fail "cannot verify lock state"
  jq -e '.locked == false and .requested == false and .sessionLocked == false' <<<"$status" >/dev/null \
    || fail "unlock the session before changing the lock plugin"
}

restore_power() {
  [[ -f "$plugin_dir/display-power.py" ]] || return 0
  local outputs=()
  mapfile -t outputs < <(jq -r --arg id "$plugin_id" '
    .plugins[] | select(.id == $id) | .phasedPower | [.main, .sides[]?] | .[] | select(type == "string")' "$shell_config")
  python3 "$plugin_dir/display-power.py" wake "${outputs[@]}"
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  omarchy plugin enable "$plugin_id"
  install_menu_entry
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  require_unlocked
  restore_power
  if plugin_is_enabled; then
    omarchy plugin disable "$plugin_id"
  fi
  remove_menu_entry
  log "Lock Screen Explorer is disabled."
}

backup_feature_data() {
  local backup_dir path relative_path
  backup_dir="$HOME/.local/state/arch-setups/backups/lock-explorer-remove-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"
  for path in "$HOME/.config/lock-explorer" "$HOME/.local/state/lock-explorer" "${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/lock-explorer-power"; do
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
  log "Removed Lock Screen Explorer. Configuration and state were backed up to: $backup_dir"
}

case "${1:-}" in
  --disable) disable_plugin; exit 0 ;;
  --remove) remove_plugin; exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

ensure_command git git
ensure_command jq jq
ensure_command python3 python
ensure_command ddcutil ddcutil

monitor_roles="$(python3 "$SCRIPT_DIR/hypr/scripts/monitor-layout.py" --config "$SCRIPT_DIR/monitor-layout.json" resolve)" \
  || fail "cannot resolve configured monitor identities"
monitor_policy="$(cat "$SCRIPT_DIR/monitor-layout.json")"
jq -e --argjson roles "$monitor_roles" '
  [.lockMain, .lockSides[], .wallpaperSpan[]] | all(.[]; $roles[.] != null)' \
  <<<"$monitor_policy" >/dev/null || fail "connect the configured lock and wallpaper displays before installing"

require_unlocked
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

if plugin_is_enabled && [[ "$checkout_changed" == false ]] && managed_config_is_current; then
  log "Lock Screen Explorer is already installed."
  exit 0
fi

# Enabling an existing plugin is idempotent; disabling first discards its
# plugin-entry settings (including the user's lock design and video).
configure_plugin
enable_plugin
# Git checkout hot-reloads several files; drain stale lock IPC handlers once.
require_unlocked
omarchy restart shell
log "Installed and activated Lock Screen Explorer at $plugin_revision ($plugin_commit)."
