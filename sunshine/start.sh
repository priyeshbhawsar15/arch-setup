#!/bin/bash
# Managed by arch-setups/install-sunshine.sh
# Listen on LAN and Tailscale, including interfaces which appear after startup.
set -euo pipefail
bind_address=0.0.0.0
# Whoever opens a host with no admin login can create one and approve their own
# pairing, so keep the page on this PC until a login exists. An unreadable state
# file counts as no login.
state="${XDG_CONFIG_HOME:-$HOME/.config}/sunshine/sunshine_state.json"
admin_access=pc
if python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if all(d.get(k) for k in ("username","password","salt")) else 1)' "$state" 2>/dev/null; then
  admin_access=lan
fi
case "${1:-}" in
  --print-address) printf '%s\n' "$bind_address"; exit 0 ;;
  --print-admin-access) printf '%s\n' "$admin_access"; exit 0 ;;
  '') ;;
  *) echo "Usage: $0 [--print-address|--print-admin-access]" >&2; exit 2 ;;
esac
# The packaged web UI needs exact trusted origins for browser POST requests.
# Discover current addresses best-effort; never block startup on an interface.
origins="$(ip -o -4 address show up 2>/dev/null | awk '{split($4, a, "/"); printf "%shttps://%s:47990", sep, a[1]; sep=","}' || true)"
args=("bind_address=$bind_address" 'upnp=disabled' 'address_family=ipv4' 'port=47989' "origin_web_ui_allowed=$admin_access")
[[ -z "$origins" ]] || args+=("csrf_allowed_origins=$origins")
# Connector names change when monitors are switched or replugged, so find the
# streamed monitor by its EDID identity; otherwise keep the configured output.
stream_display="$HOME/.local/lib/arch-setups/sunshine-stream-display.py"
if [[ -f "$stream_display" ]] && output="$(python3 "$stream_display" output-name --record 2>/dev/null)"; then
  args+=("output_name=$output")
fi
exec /usr/bin/sunshine "${args[@]}"
