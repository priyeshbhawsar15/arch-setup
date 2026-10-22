#!/bin/bash
set -euo pipefail
# Plans/diagnostics import local helpers: do not create source-tree cache files.
export PYTHONDONTWRITEBYTECODE=1
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Explicit order remains reviewable. config/features.json declares dependencies;
# tests check that every registered installer occurs here, exactly once.
installers=(
  install-chrome.sh
  install-brave-origin.sh
  install-zen.sh
  install-stow.sh
  install-hermes-desktop.sh
  install-codex.sh
  install-github-cli.sh
  install-t3code.sh
  install-t3-planner-executor.sh
  install-steam.sh
  install-lutris.sh
  install-linuwux.sh
  install-sunshine.sh
  install-tailscale.sh
  install-keyd.sh
  install-zsh.sh
  install-hyprland.sh
  install-wallpaper-controller.sh
  install-shibumi-shell.sh
  install-indicators.sh
  install-per-monitor-workspaces.sh
  install-hyprmoncfg.sh
  install-lock-explorer.sh
  install-omaland.sh
  install-calendar.sh
  install-omniroute-quota.sh
  install-system-metrics.sh
  install-weather-widget.sh
  install-immich-photo-frame.sh
  install-obsidian-tasks-widget.sh
  install-home-assistant.sh
  install-monitor-layout.sh
  install-dotfiles.sh
)

plan_only=false
approve_system_update=false
export ARCH_SETUPS_PROFILE="${ARCH_SETUPS_PROFILE:-$SCRIPT_DIR/features.json}"
while (($#)); do
  case "$1" in
    --plan) plan_only=true; shift ;;
    --approve-system-update) approve_system_update=true; shift ;;
    --profile|--host|--games|--settings|--planner-config|--dotfiles-dir)
      (($# >= 2)) || { log "Missing value for $1" >&2; exit 2; }
      case "$1" in
        --profile)
          case "$2" in
            safe) ARCH_SETUPS_PROFILE="$SCRIPT_DIR/features.json" ;;
            personal) ARCH_SETUPS_PROFILE="$SCRIPT_DIR/profiles/personal.json" ;;
            *) ARCH_SETUPS_PROFILE="$2" ;;
          esac ;;
        --host) export ARCH_SETUPS_MONITOR_LAYOUT="$2" ;;
        --games) export ARCH_SETUPS_GAMING_PROFILE="$2" ;;
        --settings) export ARCH_SETUPS_SETTINGS="$2" ;;
        --planner-config) export T3_PLANNER_EXECUTOR_SEED_CONFIG="$2" ;;
        --dotfiles-dir) export ARCH_SETUPS_DOTFILES_DIR="$2" ;;
      esac
      shift 2 ;;
    --ignore-local-choices) export ARCH_SETUPS_IGNORE_LOCAL=1; shift ;;
    --help)
      log "Usage: $0 [--plan] [--profile safe|personal|FILE] [--host FILE] [--games FILE] [--settings FILE] [--planner-config FILE] [--dotfiles-dir DIR] [--ignore-local-choices] [--approve-system-update]"
      exit 0 ;;
    *) log "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

python3 "$SCRIPT_DIR/config/feature-profile.py" plan
selected="$(python3 "$SCRIPT_DIR/config/feature-profile.py" list)"
# Validate external profiles even for --plan, without connecting or mutating.
python3 "$SCRIPT_DIR/config/setup-inputs.py" plan
if [[ "$plan_only" == true ]]; then
  [[ -z "$selected" ]] || python3 "$SCRIPT_DIR/config/package-bootstrap.py" status
  log "Read-only plan. Games and experimental graphics mods are opt-in; no installer was run."
  exit 0
fi
((EUID != 0)) || { log "Run as the normal desktop user, not root." >&2; exit 1; }
"$SCRIPT_DIR/preflight.sh"

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups"
mkdir -p -m 700 -- "$state_dir"
exec 9>"$state_dir/install.lock"
chmod 600 "$state_dir/install.lock"
flock -n 9 || { log "Another setup run holds the install lock." >&2; exit 1; }
if [[ -n "$selected" ]]; then
  package_status="$(python3 "$SCRIPT_DIR/config/package-bootstrap.py" status --json)"
  if ! python3 -c 'import json,sys; s=json.loads(sys.argv[1]); sys.exit(0 if s["ready"] and not s["pending"] else 1)' "$package_status"; then
    bootstrap_args=()
    [[ "$approve_system_update" == false ]] || bootstrap_args+=(--approved)
    python3 "$SCRIPT_DIR/config/package-bootstrap.py" prepare "${bootstrap_args[@]}"
    # The initial platform update may change APIs, tools and desktop readiness.
    "$SCRIPT_DIR/preflight.sh"
  fi
fi
export ARCH_SETUPS_AUTOMATED=1
completed=0 skipped=0
for installer in "${installers[@]}"; do
  if ! grep -Fxq -- "$installer" <<<"$selected"; then
    log "==> Skipping $installer (disabled or dependency disabled)"
    skipped=$((skipped + 1))
    continue
  fi
  printf '\n==> Running %s\n' "$installer"
  if "$SCRIPT_DIR/$installer"; then
    completed=$((completed + 1))
  else
    status=$?
    log "FAILED: $installer (exit $status). Completed: $completed; skipped: $skipped. Fix the reported prerequisite and rerun; dependents were not run." >&2
    exit "$status"
  fi
done
printf '\nApplied %s installers; skipped %s. Checking selected feature readiness...\n' "$completed" "$skipped"
"$SCRIPT_DIR/doctor.sh" --acceptance
log "All selected features passed setup acceptance. Account pairing and runtime compatibility still require the documented manual checks."
