#!/bin/bash
# Managed by arch-setups/install-sunshine.sh
# Listen on LAN and Tailscale, including interfaces which appear after startup.
set -euo pipefail
bind_address=0.0.0.0
case "${1:-}" in
  --print-address) printf '%s\n' "$bind_address"; exit 0 ;;
  '') ;;
  *) echo "Usage: $0 [--print-address]" >&2; exit 2 ;;
esac
# The packaged web UI needs exact trusted origins for browser POST requests.
# Discover current addresses best-effort; never block startup on an interface.
origins="$(ip -o -4 address show up 2>/dev/null | awk '{split($4, a, "/"); printf "%shttps://%s:47990", sep, a[1]; sep=","}' || true)"
args=("bind_address=$bind_address" 'upnp=disabled' 'address_family=ipv4' 'port=47989')
[[ -z "$origins" ]] || args+=("csrf_allowed_origins=$origins")
exec /usr/bin/sunshine "${args[@]}"
