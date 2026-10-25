#!/bin/bash
# Reproducible, opt-in desktop gaming mode. No compositor or Steam restart.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"
helper="$HOME/.local/bin/gaming-mode"
unit="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/arch-gaming-mode.service"
config="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/gaming-mode.json"
case "${1:-}" in
  --prepare-benchmark)
    python3 "$SCRIPT_DIR/gaming/prepare-cyberpunk-benchmark.py"
    exit 0 ;;
  --disable|--remove)
    systemctl --user disable --now arch-gaming-mode.service
    # Stop must successfully restore state before removal.
    [[ ! -f "${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/gaming-mode/session.json" ]] || {
      log 'Restoration incomplete; inspect journalctl --user -u arch-gaming-mode before removal.'; exit 1;
    }
    if [[ "$1" == --remove ]]; then
      backup_feature_paths gaming-mode-remove "$helper" "$unit" "$config" \
        "${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/gaming-mode" >/dev/null
      rm -f -- "$helper" "$unit"
      systemctl --user daemon-reload
    fi
    log 'Gaming Mode disabled; configuration preserved.'; exit 0 ;;
  ''|--enable) ;;
  *) log "Usage: $0 [--enable|--disable|--remove|--prepare-benchmark]"; exit 2 ;;
esac
require_omarchy
for dep in python3:python hyprctl:hyprland steam:steam gamescope:gamescope wallpaper-controller:; do
  command="${dep%%:*}"; package="${dep#*:}"
  if ! is_command_available "$command"; then
    [[ -n "$package" ]] || { log 'Install Wallpaper Controller first.'; exit 1; }
    omarchy pkg add "$package"
  fi
done
# Fail closed for foreign destinations, backing up only previously owned helpers.
for target in "$helper" "$unit"; do
  [[ ! -L "$target" ]] || { log "Refusing symlink: $target"; exit 1; }
  if [[ -e "$target" ]] && ! grep -q 'Managed by arch-setups' "$target"; then
    log "Refusing foreign file: $target"; exit 1
  fi
done
changed=false
if [[ ! -e "$config" ]]; then
  mkdir -p -- "$(dirname "$config")"
  python3 - "$config" <<'PY'
import json,os,pathlib,subprocess,sys
instances=json.loads(subprocess.check_output(['hyprctl','instances','-j']))
if len(instances)!=1: raise SystemExit('Run from one active Hyprland session, or create gaming-mode.json with monitor selector.')
os.environ['HYPRLAND_INSTANCE_SIGNATURE']=instances[0]['instance']
monitors=json.loads(subprocess.check_output(['hyprctl','-j','monitors']))
# Seed once from the focused display; never hardcode another host's connector.
m=next((m for m in monitors if m.get('focused')),None)
if not m: raise SystemExit('No focused monitor')
p=pathlib.Path(sys.argv[1]);p.write_text(json.dumps({'monitor':'desc:'+m['description'],'restoreVrr':int(m['vrr']), 'pauseDecorations':True, 'pausePlugins':['priyesh.system-metrics','priyesh.weather-widget','priyesh.immich-photo-frame']},indent=2)+'\n');p.chmod(0o600)
PY
  changed=true
fi
if ! cmp -s "$SCRIPT_DIR/gaming/gaming-mode.py" "$helper" || ! cmp -s "$SCRIPT_DIR/gaming/arch-gaming-mode.service" "$unit"; then
  backup_feature_paths gaming-mode-update "$helper" "$unit" >/dev/null
  # Restore any active mode with the OLD executable before replacing it.
  systemctl --user stop arch-gaming-mode.service 2>/dev/null || true
  [[ ! -f "${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/gaming-mode/session.json" ]] || {
    log 'An active recovery journal remains; refusing update.'; exit 1;
  }
  mkdir -p -- "$(dirname "$helper")" "$(dirname "$unit")"
  install -m 755 "$SCRIPT_DIR/gaming/gaming-mode.py" "$helper"
  install -m 644 "$SCRIPT_DIR/gaming/arch-gaming-mode.service" "$unit"
  changed=true
fi
chmod 755 "$helper"
systemctl --user daemon-reload
systemctl --user enable --now arch-gaming-mode.service
if [[ "$changed" == false ]]; then log 'Gaming Mode already installed.'; else log 'Gaming Mode installed and enabled.'; fi
log 'Steam/Lutris games are detected automatically; Big Picture alone does not enable Gaming Mode. See gaming/README.md.'
