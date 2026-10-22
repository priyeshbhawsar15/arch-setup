#!/usr/bin/env bash

# Installs tmn73.calendar (Calendar Bar Widget) for Omarchy at a pinned commit,
# placing it in the center slot of the top bar replacing the stock clock.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"

plugin_id="tmn73.calendar"
plugin_url="https://github.com/tmn73/omarchy-calendar.git"
plugin_commit="08f5c01fb3b40322787ebfa9805429baa19beb5f"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
shell_config="$HOME/.config/omarchy/shell.json"

bar_role="calendar"
bar_state_file="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/tmn73.calendar/bar-layout.json"

require_omarchy

fail() {
  log "Calendar: $*"
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
  managed_plugin_checkout_current "$plugin_dir" "$plugin_url" "$plugin_commit"
}

plugin_is_enabled() {
  omarchy plugin list --json | jq -e --arg id "$plugin_id" \
    'any(.[]; .id == $id and .enabled)' >/dev/null
}

layout_has_calendar_in_center() {
  [[ -f "$shell_config" ]] || return 1
  jq -e --arg id "$plugin_id" \
    '.bar.layout.center | any(.[]; (if type == "object" then .id else . end) == $id)' "$shell_config" >/dev/null && manage_bar_layout check
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
  install_pinned_plugin "$plugin_dir" "$plugin_url" "$plugin_commit" "$plugin_id"
}

update_pinned_plugin() {
  checkout_pinned_plugin
}

sync_state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/$plugin_id"
sync_units_state="$sync_state_dir/sync-units.json"

manage_sync_units() {
  python3 - "$plugin_dir" "$HOME/.config/systemd/user" "$sync_units_state" "$1" <<'PY'
import hashlib, json, os, pathlib, shutil, sys, tempfile, time
plugin, destination, record = map(pathlib.Path, sys.argv[1:4])
action = sys.argv[4]
names = ('omarchy-calendar-sync.service', 'omarchy-calendar-sync.timer')
owned = json.loads(record.read_text()) if record.exists() else {}
if action == 'adopt' and not all((plugin / 'sync/systemd' / name).exists() for name in names): raise SystemExit(1)
expected = {name: (plugin / 'sync/systemd' / name).read_bytes() for name in names} if action in ('install', 'check', 'adopt') else {}
def digest(content): return hashlib.sha256(content).hexdigest()
if action == 'adopt':
    if not all((destination / name).exists() and (destination / name).read_bytes() == content for name, content in expected.items()): raise SystemExit(1)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({name: digest(content) for name, content in expected.items()}) + '\n')
    record.chmod(0o600)
    raise SystemExit(0)
if action == 'owned':
    raise SystemExit(0 if owned and all((destination / name).exists() and digest((destination / name).read_bytes()) == known_hash for name, known_hash in owned.items()) else 1)
if action == 'check':
    raise SystemExit(0 if all((destination / name).exists() and (destination / name).read_bytes() == content
        and owned.get(name) == digest(content) for name, content in expected.items()) else 1)
changed = False
if action == 'install':
    # Check both files before changing either; custom user units remain untouched.
    for name, content in expected.items():
        path = destination / name
        if path.exists() and path.read_bytes() != content and owned.get(name) != digest(path.read_bytes()):
            raise SystemExit('Preserving custom calendar sync unit: ' + str(path))
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        path = destination / name
        if path.exists() and path.read_bytes() == content: continue
        if path.exists():
            backup = record.parent / ('sync-unit-backup-' + str(time.time_ns()))
            backup.mkdir(parents=True); shutil.copy2(path, backup / name)
        fd, temporary = tempfile.mkstemp(dir=destination)
        try:
            with os.fdopen(fd, 'wb') as f: f.write(content); f.flush(); os.fsync(f.fileno())
            os.chmod(temporary, 0o644); os.replace(temporary, path)
        finally: pathlib.Path(temporary).unlink(missing_ok=True)
        changed = True
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({name: digest(content) for name, content in expected.items()}) + '\n')
    record.chmod(0o600)
elif action == 'remove':
    for name, known_hash in owned.items():
        path = destination / name
        if path.exists() and digest(path.read_bytes()) == known_hash:
            path.unlink(); changed = True
        elif path.exists():
            print('Preserving edited calendar sync unit: ' + str(path), file=sys.stderr)
    record.unlink(missing_ok=True)
else: raise SystemExit('Unknown sync unit operation')
print('changed' if changed else 'current')
PY
}

calendar_auth_ready() {
  # Auth status is a local credential/scope check; do not run the interactive
  # Google Cloud/OAuth setup or fetch calendar events from this installer.
  python3 - <<'PY'
import json, os, pathlib, re, shutil, subprocess
config_path = pathlib.Path.home() / '.config/omarchy/calendar-sync.json'
if not config_path.exists(): raise SystemExit(1)
try:
    config = json.loads(config_path.read_text())
    if not isinstance(config, dict): raise ValueError('expected object')
except (OSError, ValueError):
    print('Calendar sync configuration is invalid; repair calendar-sync.json before enabling sync.', file=__import__('sys').stderr)
    raise SystemExit(1)
profile = pathlib.Path(config.get('profile') or str(pathlib.Path.home() / '.config/gws-omarchy-calendar')).expanduser()
binary = str(config.get('gwsPath') or 'gws')
if not pathlib.Path(binary).is_absolute(): binary = shutil.which(binary) or ''
if not binary: raise SystemExit(1)
env = dict(os.environ, GOOGLE_WORKSPACE_CLI_CONFIG_DIR=str(profile))
try:
    version = subprocess.run([binary, '--version'], env=env, capture_output=True, text=True, timeout=5)
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', version.stdout)
    if not match or tuple(map(int, match.groups())) < (0, 13, 2): raise SystemExit(1)
    status = subprocess.run([binary, 'auth', 'status'], env=env, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, timeout=10)
    auth = json.loads(status.stdout)
except (OSError, ValueError, subprocess.TimeoutExpired): raise SystemExit(1)
raise SystemExit(0 if status.returncode == 0 and 'https://www.googleapis.com/auth/calendar.readonly' in auth.get('scopes', []) else 1)
PY
}

calendar_sync_is_current() {
  manage_sync_units check || return 1
  if calendar_auth_ready; then
    systemctl --user is-enabled --quiet omarchy-calendar-sync.timer && \
      systemctl --user is-active --quiet omarchy-calendar-sync.timer
  else
    ! systemctl --user is-enabled --quiet omarchy-calendar-sync.timer && \
      ! systemctl --user is-active --quiet omarchy-calendar-sync.timer
  fi
}

stop_calendar_sync() {
  # Adopt exact units created by the upstream OAuth setup on older installs.
  if [[ ! -f "$sync_units_state" ]]; then manage_sync_units adopt >/dev/null || true; fi
  if [[ -f "$sync_units_state" ]] && manage_sync_units owned; then
    systemctl --user disable --now omarchy-calendar-sync.timer
    systemctl --user stop omarchy-calendar-sync.service
  fi
}

configure_calendar_sync() {
  local result
  result="$(manage_sync_units install)" || fail "calendar sync unit deployment failed"
  if [[ "$result" == changed ]]; then systemctl --user daemon-reload; fi
  if calendar_auth_ready; then
    systemctl --user enable --now omarchy-calendar-sync.timer
  else
    stop_calendar_sync
    log "Calendar OAuth setup is still required. Run $plugin_dir/sync/setup in a terminal with gws and gcloud, then rerun this installer."
  fi
  calendar_sync_is_current || fail "calendar sync timer did not retain its configured state"
}

# Keep the reversible layout change separate from Omarchy's plugin registry.
# Restore before disabling a cloned widget so the registry cannot replace an
# unrelated stock workspace entry with a manufactured fallback.
manage_bar_layout() {
  python3 "$SCRIPT_DIR/config/bar-layout.py" "$shell_config" "$bar_state_file" \
    "$plugin_id" "$bar_role" "$1"
}

enable_plugin() {
  omarchy-shell shell rescanPlugins >/dev/null
  wait_for_plugin_discovery
  configure_calendar_sync
  manage_bar_layout enable
  omarchy plugin enable "$plugin_id"
  omarchy-shell shell rescanPlugins >/dev/null
  plugin_is_enabled || fail "Omarchy did not enable $plugin_id"
}

disable_plugin() {
  local was_enabled=false
  if plugin_is_enabled; then was_enabled=true; fi
  stop_calendar_sync
  manage_bar_layout disable
  if [[ "$was_enabled" == true ]]; then
    omarchy plugin disable "$plugin_id"
  fi
  omarchy-shell shell rescanPlugins >/dev/null
  log "Calendar bar widget is disabled."
}

backup_feature_data() {
  backup_feature_paths calendar-remove "$HOME/.config/omarchy/calendar-sync.json" \
    "$HOME/.local/state/omarchy/calendar-events.json" "$shell_config" "$sync_state_dir" \
    "$HOME/.config/systemd/user/omarchy-calendar-sync.service" \
    "$HOME/.config/systemd/user/omarchy-calendar-sync.timer"
}

remove_plugin() {
  plugin_checkout_is_current || fail "the managed pinned checkout is unavailable or modified"
  local backup_dir
  backup_dir="$(backup_feature_data)"
  disable_plugin
  manage_sync_units remove >/dev/null
  systemctl --user daemon-reload
  omarchy plugin remove "$plugin_id" --yes
  log "Removed Calendar bar widget. Configuration and state were backed up to: $backup_dir"
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

if plugin_is_enabled && layout_has_calendar_in_center && calendar_sync_is_current && [[ "$checkout_changed" == false ]]; then
  log "Calendar is already installed."
  exit 0
fi


enable_plugin
log "Installed and activated Calendar bar widget at $plugin_commit."
