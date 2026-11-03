#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
unit=app-dev.lizardbyte.app.Sunshine.service
case "${1:-}" in
  --disable)
    # The virtual host depends on Sunshine and install-all.sh skips it once this
    # is off, so stop it and close its firewall rules here.
    if systemctl --user cat arch-sunshine-virtual.service >/dev/null 2>&1; then
      "$SCRIPT_DIR/install-virtual-desktop.sh" --disable
    fi
    disable_user_unit "$unit"
    remember_feature_choice "$0" false
    exit 0 ;;
  --enable) systemctl --user enable --now "$unit"; remember_feature_choice "$0" true; exit 0 ;;
  --repair-pairing|--reset-pairing)
    # The running daemon owns this JSON; stop it before making an offline repair.
    was_active=false
    if systemctl --user is-active --quiet "$unit"; then was_active=true; fi
    systemctl --user stop "$unit"
    restore_service() { [[ "$was_active" == false ]] || systemctl --user start "$unit"; }
    trap restore_service EXIT
    if [[ "$1" == --reset-pairing ]]; then
      python3 "$SCRIPT_DIR/sunshine/reset-pairing.py"
    else
      python3 "$SCRIPT_DIR/sunshine/repair-pairing.py"
    fi
    exit 0 ;;
  '') ;;
  *) log "Usage: $0 [--enable|--disable|--repair-pairing|--reset-pairing]" >&2; exit 2 ;;
esac
if is_command_available sunshine || pacman -Q sunshine >/dev/null 2>&1; then
  log 'Sunshine is already installed; checking managed configuration.'
else
  require_omarchy
  omarchy pkg add sunshine
fi
# Mesa VAAPI is required on AMD hosts, harmless on other GPUs.
if ! pacman -Q libva-mesa-driver >/dev/null 2>&1; then
  require_omarchy
  omarchy pkg add libva-mesa-driver
fi
config_file="${XDG_CONFIG_HOME:-$HOME/.config}/sunshine/sunshine.conf"
config_before="$(sha256sum "$config_file" 2>/dev/null || true)"
python3 "$SCRIPT_DIR/sunshine/configure.py"
changed=false
[[ "$(sha256sum "$config_file" 2>/dev/null || true)" == "$config_before" ]] || changed=true
bin_dir="${HOME}/.local/bin"
drop_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$unit.d"
mkdir -p -- "$bin_dir" "$drop_dir"
for item in "$bin_dir/sunshine-host" "$drop_dir/arch-setups-network.conf" "$bin_dir/sunshine-tailscale" "$drop_dir/arch-setups-tailscale.conf"; do
  if [[ -e "$item" || -L "$item" ]]; then
    [[ ! -L "$item" ]] && grep -qE 'arch-setups|Resolve the local tailnet address' "$item" || {
      log "Refusing foreign managed path: $item" >&2; exit 1;
    }
  fi
done
if ! cmp -s "$SCRIPT_DIR/sunshine/start.sh" "$bin_dir/sunshine-host" || ! cmp -s "$SCRIPT_DIR/sunshine/network.conf" "$drop_dir/arch-setups-network.conf" || [[ -e "$bin_dir/sunshine-tailscale" || -e "$drop_dir/arch-setups-tailscale.conf" ]]; then
  backup_feature_paths sunshine-service "$bin_dir/sunshine-host" "$drop_dir/arch-setups-network.conf" "$bin_dir/sunshine-tailscale" "$drop_dir/arch-setups-tailscale.conf" >/dev/null
  install -m 755 "$SCRIPT_DIR/sunshine/start.sh" "$bin_dir/sunshine-host"
  install -m 644 "$SCRIPT_DIR/sunshine/network.conf" "$drop_dir/arch-setups-network.conf"
  rm -f -- "$bin_dir/sunshine-tailscale" "$drop_dir/arch-setups-tailscale.conf"
  changed=true
fi
systemctl --user daemon-reload
systemctl --user enable "$unit"
# Apply changed security settings to a running host, but never drop a live
# stream when a rerun has nothing to change.
if [[ "$changed" == true ]]; then
  systemctl --user restart "$unit"
else
  log 'Sunshine configuration is already installed; ensuring its service is running.'
  systemctl --user start "$unit"
fi
remember_feature_choice "$0" true
log 'Sunshine configured for LAN and Tailscale access, independent of interface startup order.'
log 'Use the LAN IP locally or the Tailscale IP remotely in Moonlight; administration is available at https://localhost:47990.'
log 'Verify capture, audio and input from your client. No router forwarding is needed.'
if [[ "$(bash "$SCRIPT_DIR/sunshine/start.sh" --print-admin-access)" == pc ]]; then
  log "No admin login yet: create one on this PC at https://localhost:47990, then run: systemctl --user restart $unit"
  log 'Until then the admin page only opens on this PC.'
fi
