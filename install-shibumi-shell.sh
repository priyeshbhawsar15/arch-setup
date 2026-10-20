#!/usr/bin/env bash

# Shibumi Shell is a 24-plugin suite, not a repository that can be passed to
# `omarchy plugin add`. Its upstream lifecycle command installs the complete
# validated payload transactionally.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

suite_url="https://github.com/HANCORE-linux/Shibumi-Shell.git"
suite_tag="v0.1.1-beta.14.1"
suite_commit="7a6c853b1947d303bad9a5b640c224c01b669106"
suite_dir="$HOME/.local/share/shibumi-shell/$suite_commit"
suite_state="$HOME/.local/state/shibumi/install.json"
shell_config="$HOME/.config/omarchy/shell.json"

runtime_packages=(
  git python jq curl networkmanager power-profiles-daemon upower xdg-utils
  libnotify wl-clipboard ttf-material-symbols-variable
  ttf-jetbrains-mono-nerd-basic noto-fonts-cjk adwaita-fonts
)

require_omarchy

fail() {
  log "Shibumi Shell: $*"
  exit 1
}

suite_checkout_is_current() {
  [[ -d "$suite_dir/.git" ]] || return 1
  [[ "$(git -C "$suite_dir" remote get-url origin 2>/dev/null || true)" == "$suite_url" ]] || return 1
  [[ "$(git -C "$suite_dir" rev-parse HEAD 2>/dev/null || true)" == "$suite_commit" ]] || return 1
  git -C "$suite_dir" diff --quiet || return 1
  git -C "$suite_dir" diff --cached --quiet || return 1
  [[ -z "$(git -C "$suite_dir" status --porcelain --untracked-files=all)" ]] || return 1
}

suite_state_matches() {
  [[ -f "$suite_state" ]] || return 1
  jq -e --arg commit "$suite_commit" --arg source "$suite_dir" \
    '.suiteId == "hancore.shibumi" and .installOrigin == "checkout" and .sourceRevision == $commit and .sourceRoot == $source' \
    "$suite_state" >/dev/null
}

install_runtime_dependencies() {
  local package
  local missing=()
  for package in "${runtime_packages[@]}"; do
    pacman -Q "$package" >/dev/null 2>&1 || missing+=("$package")
  done
  if ((${#missing[@]} == 0)); then
    log "Shibumi Shell runtime dependencies are already installed."
    return
  fi
  log "Installing Shibumi Shell runtime dependencies..."
  omarchy pkg add "${missing[@]}"
}

ensure_lock_status_service() {
  if ! omarchy plugin list --json | jq -e \
    'any(.[]; (.id == "omarchy.lock" or .clonedFrom == "omarchy.lock" or .id == "io.github.sirjul1337.lock-explorer") and .enabled)' >/dev/null; then
    log "Enabling Omarchy's lock service required by Shibumi's safety preflight..."
    omarchy plugin enable omarchy.lock
  fi

  local status
  status="$(omarchy-shell lock status 2>/dev/null)" || fail "Omarchy lock-status IPC is unavailable"
  jq -e '(.locked | type == "boolean") and (.requested | type == "boolean") and (.pending | type == "boolean") and (.sessionLocked | type == "boolean") and (.secure | type == "boolean")' \
    <<<"$status" >/dev/null || fail "Omarchy lock-status IPC returned an invalid response"
}

checkout_pinned_suite() (
  set -euo pipefail
  local parent stage
  [[ ! -e "$suite_dir" && ! -L "$suite_dir" ]] || fail "preserving a foreign or modified source checkout at $suite_dir"
  parent="$(dirname -- "$suite_dir")"
  mkdir -p -- "$parent"
  stage="$(mktemp -d "$parent/.shibumi.install.XXXXXX")"
  trap 'rm -rf -- "$stage"' EXIT
  GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$suite_url" "$stage"
  git -C "$stage" checkout --quiet --detach "$suite_commit"
  git -C "$stage" submodule update --init --recursive
  [[ -x "$stage/scripts/shibumi-suite" ]] || fail "pinned source has no lifecycle command"
  "$stage/scripts/shibumi-suite" install --help | grep -q -- --user-layout \
    || fail "the reviewed custom fork must be published and pinned before installation"
  mv -- "$stage" "$suite_dir"
  trap - EXIT
)

run_suite() {
  "$suite_dir/scripts/shibumi-suite" "$@"
}

backup_shibumi_data() {
  local plugin
  local paths=("$(dirname -- "$suite_state")" "$shell_config" "$HOME/.config/omarchy/extensions/omarchy-menu.jsonc")
  while IFS= read -r plugin; do
    [[ "$plugin" =~ ^hancore\.shibumi\.[a-z0-9-]+$ ]] || fail "unsafe suite plugin identity in install state"
    paths+=("$HOME/.config/omarchy/plugins/$plugin")
  done < <(jq -r '.plugins[]' "$suite_state")
  backup_paths shibumi-lifecycle "${paths[@]}"
}

deploy_overrides() {
  # Configuration is supported by the pinned fork. Never rewrite the managed
  # payload: upstream admission verifies each plugin's exact transaction digest.
  python3 "$SCRIPT_DIR/config/shibumi-settings.py" "$shell_config" "$SCRIPT_DIR/monitor-layout.json"
}

disable_suite() {
  suite_checkout_is_current || fail "the pinned Shibumi checkout is unavailable or modified; do not use a different lifecycle version"
  suite_state_matches || fail "Shibumi is not managed by the pinned source checkout"
  run_suite deactivate --yes
  # Upstream status deliberately reports configuration drift while an installed
  # suite is inactive, so its nonzero result is expected after deactivation.
  run_suite status || true
  log "Shibumi Shell is disabled; the stock Omarchy bar is active and Shibumi data is retained."
}

remove_suite() {
  suite_checkout_is_current || fail "the pinned Shibumi checkout is unavailable or modified; do not use a different lifecycle version"
  suite_state_matches || fail "Shibumi is not managed by the pinned source checkout"
  run_suite uninstall --dry-run
  local backup_dir
  backup_dir="$(backup_shibumi_data)"
  run_suite uninstall --yes
  rm -rf -- "$suite_dir"
  rmdir "$(dirname -- "$suite_dir")" 2>/dev/null || true
  log "Removed Shibumi Shell. Shell configuration and suite state were backed up to: $backup_dir"
}

case "${1:-}" in
  --disable|--remove|"") mode="${1:-}" ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

if [[ -n "$mode" && ! -f "$suite_state" ]]; then
  log "Shibumi Shell is not installed."
  exit 0
fi
install_runtime_dependencies
ensure_lock_status_service
if ! suite_checkout_is_current; then checkout_pinned_suite; fi
run_suite install --help | grep -q -- --user-layout \
  || fail "the reviewed custom fork must be published and pinned before installation"

if [[ -f "$suite_state" ]]; then
  active_bar="$(jq -r '.bar.id // "omarchy.bar"' "$shell_config")"
  if ! suite_state_matches || { [[ "$active_bar" == hancore.shibumi.bar ]] && ! run_suite status >/dev/null; }; then
    # Repair admits only explicit predecessor identities and archives/replaces
    # dirty payload through the suite transaction; never rewrite marker hashes.
    run_suite repair --dry-run --keep-layout
    backup_dir="$(backup_shibumi_data)"
    run_suite repair --yes --keep-layout
    log "Migrated/repaired admitted Shibumi payload. Original data backup: $backup_dir"
  fi
  case "$mode" in
    --disable) disable_suite; exit 0 ;;
    --remove) remove_suite; exit 0 ;;
  esac
  if [[ "$active_bar" != hancore.shibumi.bar ]]; then
    run_suite activate --yes --user-layout
  fi
  deploy_overrides
  run_suite status
  log "Shibumi Shell is already installed and its managed configuration is current."
  exit 0
fi

run_suite install --dry-run --user-layout
run_suite install --yes --user-layout
deploy_overrides
run_suite status
log "Installed and activated Shibumi Shell at $suite_tag ($suite_commit)."
