#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

lutris_installed=false
if is_command_available lutris || pacman -Q lutris >/dev/null 2>&1; then
  lutris_installed=true
  log "Lutris is already installed."
else
  require_omarchy
  log "Installing Lutris with Omarchy..."
  omarchy pkg add lutris
fi

# Package installation is independent of library import and game-file changes.
# Only an explicit selection can request imports, profiles or experimental DLLs.
selection="$(python3 "$SCRIPT_DIR/config/setup-inputs.py" gaming | python3 -c 'import json,sys; p=json.load(sys.stdin); print(json.dumps(dict(games=len(p["games"]), importSteam=p["importSteam"], upscalers=any(g.get("upscaler") for g in p["games"]))))')"
if [[ "$(python3 -c 'import json,sys; p=json.loads(sys.argv[1]); print(p["games"] == 0 and not p["importSteam"])' "$selection")" == True ]]; then
  log "Lutris is installed; no library import or game modifications selected."
  exit 0
fi
if [[ "$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["importSteam"])' "$selection")" == True ]]; then
  /usr/bin/python3 "$SCRIPT_DIR/steam/sync-lutris-steam.py"
elif [[ "$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["games"])' "$selection")" != 0 ]]; then
  /usr/bin/python3 "$SCRIPT_DIR/steam/sync-lutris-steam.py" --initialize-only
fi
if [[ "$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["upscalers"])' "$selection")" == True ]] && ! is_command_available 7z; then
  require_omarchy
  omarchy pkg add 7zip
fi
/usr/bin/python3 "$SCRIPT_DIR/steam/configure-gaming-profile.py" --apply --upscalers

if [[ "$lutris_installed" == false ]]; then
  log "Lutris installed and game library synchronized."
fi
