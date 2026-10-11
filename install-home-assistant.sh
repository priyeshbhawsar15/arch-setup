#!/usr/bin/env bash
# Install the original private Home Assistant widget at a reviewed published pin.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
require_omarchy
plugin_id="priyesh.home-assistant"
plugin_url="https://github.com/priyeshbhawsar15/omarchy-home-assistant.git"
plugin_commit="1fe269a3fdff3a7c8f920c0403f069449745069b"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
venv="$HOME/.local/share/omarchy-home-assistant/venv"
config="$HOME/.config/omarchy/home-assistant.json"
fail() { log "Home Assistant: $*"; exit 1; }
for cmd in git jq python3; do command -v "$cmd" >/dev/null || fail "required command missing: $cmd"; done
enabled() { omarchy plugin list --json | jq -e --arg id "$plugin_id" 'any(.[]; .id == $id and .enabled)' >/dev/null; }
clean_checkout() {
  [[ -d "$plugin_dir/.git" ]] || fail "existing path is not a managed Git checkout"
  [[ "$(git -C "$plugin_dir" remote get-url origin)" == "$plugin_url" ]] || fail "unexpected plugin origin"
  [[ -z "$(git -C "$plugin_dir" status --porcelain --untracked-files=all)" ]] || fail "plugin has local changes; refusing to overwrite"
}
disable() {
  if enabled; then
    omarchy-shell -q "$plugin_id" shutdown
    omarchy plugin disable "$plugin_id"
  fi
  if [[ -x "$venv/bin/python" && -f "$plugin_dir/backend.py" ]] && grep -q '^def stop_transport' "$plugin_dir/backend.py"; then
    "$venv/bin/python" "$plugin_dir/backend.py" stop
  fi
  log "Home Assistant widget disabled."
}
case "${1:-}" in
  --disable) disable; exit 0 ;;
  --remove)
    clean_checkout
    backup="$HOME/.local/state/arch-setups/backups/home-assistant-remove-$(date +%Y%m%d%H%M%S)"
    mkdir -p -m 700 -- "$backup"
    for path in "$config" "$HOME/.local/state/omarchy/home-assistant"; do
      if [[ -e "$path" ]]; then cp -a -- "$path" "$backup/"; fi
    done
    disable
    omarchy plugin remove "$plugin_id" --yes
    log "Removed widget; backup: $backup. Existing HA token and shared venv retained."
    exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac
runtime_current() {
  [[ -x "$venv/bin/python" ]] && "$venv/bin/python" -c 'import websocket; assert websocket.__version__ == "1.8.0"' >/dev/null 2>&1
}
changed=false
if [[ -e "$plugin_dir" || -L "$plugin_dir" ]]; then
  clean_checkout
  if [[ "$(git -C "$plugin_dir" rev-parse HEAD)" != "$plugin_commit" ]]; then
    git -C "$plugin_dir" fetch --quiet origin
    git -C "$plugin_dir" cat-file -e "$plugin_commit^{commit}"
    disable
    git -C "$plugin_dir" checkout --quiet --detach "$plugin_commit"
    changed=true
  fi
else
  mkdir -p -- "$(dirname -- "$plugin_dir")"
  stage="$(mktemp -d "$(dirname -- "$plugin_dir")/.home-assistant-install.XXXXXX")"
  trap 'rm -rf -- "$stage"' EXIT
  GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$plugin_url" "$stage" || fail "private repository requires GitHub authentication"
  git -C "$stage" checkout --quiet --detach "$plugin_commit"
  omarchy plugin validate "$stage"
  mv -- "$stage" "$plugin_dir"
  trap - EXIT
  changed=true
fi
omarchy plugin validate "$plugin_dir"
if runtime_current && [[ -f "$config" ]] && enabled && [[ "$changed" == false ]]; then
  log "Home Assistant widget is already installed."
  exit 0
fi
if ! runtime_current; then
  python3 -m venv "$venv"
  "$venv/bin/pip" install --disable-pip-version-check 'websocket-client==1.8.0'
fi
"$venv/bin/python" "$plugin_dir/backend.py" seed
omarchy-shell shell rescanPlugins >/dev/null
for ((attempt=0; attempt<40; attempt++)); do
  if omarchy plugin list --json | jq -e --arg id "$plugin_id" 'any(.[]; .id == $id)' >/dev/null; then break; fi
  sleep 0.05
done
omarchy plugin enable "$plugin_id"
if [[ "$changed" == true ]]; then omarchy restart shell; fi
enabled || fail "plugin did not enable"
log "Installed Home Assistant widget at $plugin_commit."
log "Configure HA token (0600) and entity mappings locally; credentials are never deployed by this repository."
