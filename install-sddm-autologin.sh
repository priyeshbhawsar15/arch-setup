#!/bin/bash
# Optional automatic login plus native Omarchy startup locking.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
export PYTHONDONTWRITEBYTECODE=1
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
unit=arch-sddm-autolock.service
configure_sddm() {
  local status=0
  python3 "$SCRIPT_DIR/sddm/configure-autologin.py" "$1" --user "$(id -un)" --check || status=$?
  if (( status == 0 )); then
    log 'SDDM autologin configuration is already installed.'
  elif (( status == 1 )); then
    run_privileged /usr/bin/python3 "$SCRIPT_DIR/sddm/configure-autologin.py" "$1" --user "$(id -un)"
  else
    return "$status"
  fi
}
case "${1:-}" in
  --status)
    python3 "$SCRIPT_DIR/sddm/configure-autologin.py" status
    printf 'Startup lock unit: '
    systemctl --user is-enabled "$unit" || true
    exit 0 ;;
  --disable)
    configure_sddm disable
    disable_user_unit "$unit"
    remember_feature_choice "$0" false
    log 'Automatic SDDM login and its startup lock are disabled. Normal locking is unchanged.'
    exit 0 ;;
  ''|--enable) ;;
  *) log "Usage: $0 [--enable|--disable|--status]" >&2; exit 2 ;;
esac
(( EUID != 0 )) || { log 'Run as the normal desktop user.' >&2; exit 1; }
command -v sddm >/dev/null || { log 'SDDM must already be installed.' >&2; exit 1; }
log 'SDDM is already installed; checking automatic-login configuration.'
for command in omarchy-shell uwsm python3; do
  command -v "$command" >/dev/null || { log "Missing prerequisite: $command" >&2; exit 1; }
done
[[ -f /usr/share/wayland-sessions/hyprland-uwsm.desktop ]] || { log 'The Hyprland UWSM session is required.' >&2; exit 1; }
# Do not enable passwordless login if the current native lock cannot authenticate.
lock_status="$(OMARCHY_PATH=/usr/share/omarchy omarchy-shell lock status)"
python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1]).get("passwordPam") is True else 1)' "$lock_status" || {
  log 'The Omarchy password lock must be available before enabling autologin.' >&2; exit 1;
}
helper="$HOME/.local/lib/arch-setups/sddm-autolock.py"
unit_path="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$unit"
for target in "$helper" "$unit_path"; do
  if [[ -e "$target" || -L "$target" ]]; then
    [[ ! -L "$target" ]] && grep -Fq '# Managed by arch-setups/install-sddm-autologin.sh' "$target" || {
      log "Refusing foreign startup lock file: $target" >&2; exit 1;
    }
  fi
done
if ! cmp -s "$SCRIPT_DIR/sddm/lock-after-login.py" "$helper" || ! cmp -s "$SCRIPT_DIR/sddm/$unit" "$unit_path"; then
  backup_feature_paths sddm-autolock "$helper" "$unit_path" >/dev/null
  install -Dm 755 "$SCRIPT_DIR/sddm/lock-after-login.py" "$helper"
  install -Dm 644 "$SCRIPT_DIR/sddm/$unit" "$unit_path"
fi
systemctl --user daemon-reload
# Install the guard before enabling SDDM autologin. Do not start it in this
# already-running session: it is for the next graphical-session activation.
guard_was_enabled=false
if systemctl --user is-enabled --quiet "$unit"; then guard_was_enabled=true; fi
systemctl --user enable "$unit"
if ! configure_sddm enable; then
  # Without autologin a new guard would lock every password login. Keep an older
  # guard: autologin may still be active, and it must stay protected.
  [[ "$guard_was_enabled" == true ]] || systemctl --user disable "$unit"
  log 'SDDM autologin was not enabled.' >&2
  exit 1
fi
remember_feature_choice "$0" true
log 'Automatic SDDM login with immediate Omarchy startup locking is enabled for the next boot.'
log 'SDDM was not restarted; the current session was not locked or logged out.'
