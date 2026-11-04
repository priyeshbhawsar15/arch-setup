#!/bin/bash
# Fluentbird: unmodified upstream Thunderbird userChrome theme at an exact pinned
# commit. An application theme, not an Omarchy shell plugin: no fork, no copied
# source. See PLUGINS.md for the lifecycle and thunderbird/fluentbird.py for how
# the theme is deployed into the Thunderbird profile.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
feature_lifecycle "$0" "$@"

theme_url="https://github.com/Deathbyteacup/fluentbird.git"
theme_commit="aec46b35aebde03c0da5575fa54692c3eac09585"
# Mirror/test hooks: honored only when explicitly exported, never by default.
source_url="${FLUENTBIRD_SOURCE_URL:-$theme_url}"
source_commit="${FLUENTBIRD_SOURCE_PIN:-$theme_commit}"
checkout="${XDG_DATA_HOME:-$HOME/.local/share}/arch-setups/fluentbird"
helper="$SCRIPT_DIR/thunderbird/fluentbird.py"

# Run the helper, mapping its documented exit codes (10 current, 11 no profile).
run_helper() {
  helper_status=0
  python3 "$helper" "$@" || helper_status=$?
}

case "${1:-}" in
  --status)
    exec python3 "$helper" status --revision "$source_commit" ;;
  --disable|--remove)
    run_helper remove
    case "$helper_status" in
      0) log "Fluentbird removed from the Thunderbird profile; restart Thunderbird to drop the theme." ;;
      10|11) log "Fluentbird is not applied to a Thunderbird profile; nothing to remove." ;;
      *) exit "$helper_status" ;;
    esac
    if [[ "$1" == --remove && -d "$checkout" ]]; then
      # The checkout is reproducible upstream source, so only a clean managed one is deleted.
      managed_git_checkout_current "$checkout" "$source_url" "$(git -C "$checkout" rev-parse HEAD)" || {
        log "Keeping $checkout: not a clean checkout of $source_url."; exit 0; }
      rm -rf -- "$checkout"
    fi
    exit 0 ;;
  ''|--enable) ;;
  *) log "Usage: $0 [--enable|--disable|--remove|--status]"; exit 2 ;;
esac

for tool in git python3; do
  is_command_available "$tool" || { log "$tool is required to install Fluentbird."; exit 1; }
done
is_command_available thunderbird || { log "Thunderbird is not installed; run ./install-thunderbird.sh first."; exit 1; }

install_pinned_git_checkout "$checkout" "$source_url" "$source_commit" fluentbird
run_helper apply --source "$checkout" --revision "$source_commit"
case "$helper_status" in
  0) log "Fluentbird installed (commit ${source_commit:0:12}). Restart Thunderbird to apply it." ;;
  10) log "Fluentbird is already installed (commit ${source_commit:0:12})." ;;
  11) log "Thunderbird has no profile yet. Start Thunderbird once, then rerun ./install-fluentbird.sh." ;;
  *) exit "$helper_status" ;;
esac
# Surface advisory problems (for example a non-System Thunderbird theme) without failing setup.
python3 "$helper" status --revision "$source_commit" | grep '^Warning:' || true
