#!/bin/bash
# Room ambilight: HyperHDR captures the main OLED through PipeWire and drives three
# WLED controllers (monitor, window, bed). See ambilight/README.md.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"

# Official release package, pinned to the version validated on this desktop.
package_name="HyperHDR"
package_version="22.0.0beta2-1"
package_url="https://github.com/awawa-dev/HyperHDR/releases/download/v22.0.0.0beta2/HyperHDR-22.0.0beta2-1-x86_64.pkg.tar.zst"
package_sha256="6815643c5de17419ad4dc0c022f1798e154a4d94cd2754914c61415bf1200109"

config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
helper="$HOME/.local/bin/ambilight"
unit_dir="$config_home/systemd/user"
units=(hyperhdr.service ambilight-watch.service)
layout="$HOME/.config/ambilight/layout.json"
state="${XDG_STATE_HOME:-$HOME/.local/state}/ambilight"
database="$HOME/.config/HyperHDR/db/hyperhdr.db"

as_root() {
  if (( EUID == 0 )); then
    "$@"
  elif [[ -t 0 ]]; then
    sudo "$@"
  else
    pkexec "$@"
  fi
}

case "${1:-}" in
  --disable|--remove)
    # Stopping HyperHDR hands every WLED back to its own preset (restoreOriginalState).
    systemctl --user disable --now ambilight-watch.service hyperhdr.service 2>/dev/null || true
    if [[ "$1" == --remove ]]; then
      backup="$(backup_feature_paths hyperhdr-remove "$helper" "${units[@]/#/$unit_dir/}" "$layout" "$state" "$(dirname -- "$database")")"
      rm -f -- "$helper" "${units[@]/#/$unit_dir/}"
      systemctl --user daemon-reload
      log "Ambilight helper and services removed (backup: $backup). The HyperHDR package, its database and layout.json are kept."
    else
      log 'Ambilight disabled; HyperHDR stopped and the WLEDs returned to their own presets.'
    fi
    exit 0 ;;
  ''|--enable) ;;
  *) log "Usage: $0 [--enable|--disable|--remove]"; exit 2 ;;
esac

require_omarchy
for dep in python3:python hyprctl:hyprland sqlite3:sqlite curl:curl; do
  is_command_available "${dep%%:*}" || omarchy pkg add "${dep#*:}"
done

changed=false

# 1. Package: install the pinned release when missing; never silently replace another version.
installed_version="$(pacman -Q "$package_name" 2>/dev/null | awk '{print $2}' || true)"
if [[ -z "$installed_version" ]]; then
  download="$(mktemp -d)"
  trap 'rm -rf -- "$download"' EXIT
  file="$download/$(basename -- "$package_url")"
  curl -fsSL --retry 3 -o "$file" "$package_url"
  printf '%s  %s\n' "$package_sha256" "$file" | sha256sum -c --quiet - || { log 'HyperHDR package checksum mismatch; refusing to install.'; exit 1; }
  as_root pacman -U --noconfirm --needed "$file"
  changed=true
elif [[ "$installed_version" != "$package_version" ]]; then
  log "HyperHDR $installed_version is installed (pinned $package_version); keeping the installed version."
fi

# 2. Helper and user units: refuse foreign files, back up owned ones before updating.
targets=("$helper" "${units[@]/#/$unit_dir/}")
sources=("$SCRIPT_DIR/ambilight/ambilight.py" "${units[@]/#/$SCRIPT_DIR/ambilight/}")
for target in "${targets[@]}"; do
  [[ ! -L "$target" ]] || { log "Refusing symlink: $target"; exit 1; }
  if [[ -e "$target" ]] && ! grep -q 'Managed by arch-setups' "$target"; then
    log "Refusing foreign file: $target"; exit 1
  fi
done
deploy=false
for i in "${!targets[@]}"; do
  cmp -s "${sources[$i]}" "${targets[$i]}" || deploy=true
done
if [[ "$deploy" == true ]]; then
  backup_feature_paths hyperhdr-update "${targets[@]}" >/dev/null
  mkdir -p -- "$(dirname -- "$helper")" "$unit_dir"
  install -m 755 "$SCRIPT_DIR/ambilight/ambilight.py" "$helper"
  for unit in "${units[@]}"; do install -m 644 "$SCRIPT_DIR/ambilight/$unit" "$unit_dir/$unit"; done
  systemctl --user daemon-reload
  changed=true
fi
chmod 755 "$helper"

# 3. Layout (LED counts, directions, WLED hosts): seeded once, then owned by the user.
if [[ ! -e "$layout" ]]; then
  mkdir -p -- "$(dirname -- "$layout")"
  install -m 644 "$SCRIPT_DIR/ambilight/layout.json" "$layout"
  changed=true
fi

# 4. HyperHDR database: let HyperHDR create it once, then reconcile only the settings
#    the helper owns (instances, WLED devices, LED layouts, smoothing, capture source).
if [[ ! -e "$database" ]]; then
  systemctl --user start hyperhdr.service
  for _ in $(seq 1 60); do [[ -s "$database" ]] && break; sleep 1; done
  sleep 3
  systemctl --user stop hyperhdr.service
  [[ -s "$database" ]] || { log "HyperHDR did not create $database"; exit 1; }
fi
if ! "$helper" verify-db >/dev/null; then
  backup_feature_paths hyperhdr-database "$(dirname -- "$database")" >/dev/null
  systemctl --user stop ambilight-watch.service hyperhdr.service 2>/dev/null || true
  # A hyperhdr started outside systemd (launcher/tray) would keep the old database open.
  pkill -x hyperhdr 2>/dev/null && sleep 2 || true
  "$helper" setup-db
  changed=true
fi

# 5. Services: HyperHDR (capture -> WLED) and the automatic movie/game/work profile.
for unit in "${units[@]}"; do
  if ! systemctl --user is-enabled --quiet "$unit" || ! systemctl --user is-active --quiet "$unit"; then
    systemctl --user enable --now "$unit"
    changed=true
  fi
done
if [[ "$deploy" == true ]]; then systemctl --user restart ambilight-watch.service; fi

# 6. WLED power limits are device settings; an unreachable controller is reported, not fatal.
if ! "$helper" wled-limits --check >/dev/null 2>&1; then
  "$helper" wled-limits || log 'Some WLED controllers were unreachable; rerun this installer when they are online.'
fi

if [[ "$changed" == false ]]; then log 'HyperHDR ambilight already installed.'; else log 'HyperHDR ambilight installed and enabled.'; fi
if ! sqlite3 -readonly "$database" "select 1 from auth where length(portal_token) > 0" 2>/dev/null | grep -q 1; then
  log 'Pending: pick the main monitor in the screen-share dialog HyperHDR opens; the choice is remembered.'
fi
log 'Keys: Super+Alt+A toggles spatial/average mapping, Super+Ctrl+Alt+A cycles profiles. See ambilight/README.md.'
