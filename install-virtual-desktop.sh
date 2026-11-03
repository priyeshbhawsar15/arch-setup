#!/bin/bash
# Independent optional virtual monitor and Sunshine host, not a second package.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
export PYTHONDONTWRITEBYTECODE=1
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
unit=arch-sunshine-virtual.service
case "${1:-}" in
  --status)
    systemctl --user status "$unit" --no-pager
    exit 0 ;;
  --disable)
    disable_user_unit "$unit"
    # Stop jobs can succeed despite an ExecStopPost failure; verify cleanup.
    export HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE:-$(systemctl --user show-environment | sed -n 's/^HYPRLAND_INSTANCE_SIGNATURE=//p')}"
    [[ ! -f "$HOME/.local/lib/arch-setups/sunshine-virtual.py" ]] || python3 "$HOME/.local/lib/arch-setups/sunshine-virtual.py" cleanup
    run_privileged /usr/bin/bash "$SCRIPT_DIR/sunshine/virtual-firewall.sh" disable
    remember_feature_choice "$0" false
    log 'Virtual Desktop stopped; owned output removed. Pairing data retained.'
    exit 0 ;;
  ''|--enable) ;;
  *) log "Usage: $0 [--enable|--disable|--status]" >&2; exit 2 ;;
esac
(( EUID != 0 )) || { log 'Run as the desktop user.' >&2; exit 1; }
for executable in sunshine hyprctl python3; do
  command -v "$executable" >/dev/null || { log "Missing $executable; install Sunshine and start Hyprland first." >&2; exit 1; }
done
log 'Sunshine is already installed; configuring its independent virtual profile.'
[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || {
  export HYPRLAND_INSTANCE_SIGNATURE="$(systemctl --user show-environment | sed -n 's/^HYPRLAND_INSTANCE_SIGNATURE=//p')"
}
[[ -n "$HYPRLAND_INSTANCE_SIGNATURE" ]] || { log 'A running Hyprland session is required.' >&2; exit 1; }
helper="$HOME/.local/lib/arch-setups/sunshine-virtual.py"
unit_path="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$unit"
for path in "$helper" "$unit_path"; do
  if [[ -e "$path" || -L "$path" ]]; then
    [[ ! -L "$path" ]] && grep -Fq '# Managed by arch-setups/install-virtual-desktop.sh' "$path" || {
      log "Refusing foreign virtual-host file: $path" >&2; exit 1;
    }
  fi
done
changed="$(python3 "$SCRIPT_DIR/sunshine/virtual-desktop.py" configure --json | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["changed"]).lower())')"
if ! cmp -s "$SCRIPT_DIR/sunshine/virtual-desktop.py" "$helper" || ! cmp -s "$SCRIPT_DIR/sunshine/$unit" "$unit_path"; then
  backup_feature_paths sunshine-virtual-service "$helper" "$unit_path" >/dev/null
  install -Dm 755 "$SCRIPT_DIR/sunshine/virtual-desktop.py" "$helper"
  install -Dm 644 "$SCRIPT_DIR/sunshine/$unit" "$unit_path"
  changed=true
fi
# The ports belong only to this instance; LAN-private and tailnet sources only.
run_privileged /usr/bin/bash "$SCRIPT_DIR/sunshine/virtual-firewall.sh" enable
systemctl --user daemon-reload
systemctl --user enable "$unit"
if [[ "$changed" == true ]]; then
  systemctl --user restart "$unit"
else
  log 'Virtual desktop is already installed; ensuring its service is running.'
  systemctl --user start "$unit"
fi
remember_feature_choice "$0" true
log 'Virtual host enabled: add <LAN-IP>:48989 or <Tailscale-IP>:48989 in Moonlight.'
log 'Independent admin page: https://localhost:48990 (existing admin login seeded once).'
