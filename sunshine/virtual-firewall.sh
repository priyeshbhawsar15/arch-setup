#!/bin/bash
# Managed by arch-setups/install-virtual-desktop.sh
# Privileged, scoped UFW integration. Does not enable the firewall or use UPnP.
set -euo pipefail
(( EUID == 0 )) || { echo 'System authentication is required.' >&2; exit 1; }
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mode="${1:-}"
[[ "$mode" == enable || "$mode" == disable ]] || { echo 'Expected enable or disable.' >&2; exit 2; }
command -v ufw >/dev/null || exit 0
profile=/etc/ufw/applications.d/arch-sunshine-virtual
if [[ -e "$profile" || -L "$profile" ]]; then
  [[ ! -L "$profile" ]] && grep -Fq '# Managed by arch-setups/install-virtual-desktop.sh' "$profile" || {
    echo 'Refusing foreign UFW application profile.' >&2; exit 1;
  }
fi
if [[ "$mode" == enable ]]; then
  if ! cmp -s "$SCRIPT_DIR/virtual-ufw.profile" "$profile"; then
    if [[ -e "$profile" ]]; then
      install -d -m 700 /var/lib/arch-setups/backups
      backup="$(mktemp -d /var/lib/arch-setups/backups/sunshine-virtual-ufw-XXXXXX)"
      cp -a -- "$profile" "$backup/"
    fi
    install -Dm 644 "$SCRIPT_DIR/virtual-ufw.profile" "$profile"
  fi
  ufw app update ArchSunshineVirtual
  action=(allow)
else
  [[ -f "$profile" ]] || exit 0
  action=(--force delete allow)
fi
for source in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
  ufw "${action[@]}" from "$source" to any app ArchSunshineVirtual comment arch-setups-virtual-lan
done
ufw "${action[@]}" in on tailscale0 to any app ArchSunshineVirtual comment arch-setups-virtual-tailnet
