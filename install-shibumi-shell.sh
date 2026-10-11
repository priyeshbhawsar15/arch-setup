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
suite_dir="$HOME/.local/share/shibumi-shell/$suite_tag"
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

archive_existing_checkout() {
  [[ -e "$suite_dir" || -L "$suite_dir" ]] || return 0
  local backup_dir
  backup_dir="$HOME/.local/state/arch-setups/backups/shibumi-source-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"
  mv -- "$suite_dir" "$backup_dir/$suite_tag"
  log "Archived the replaced Shibumi checkout to: $backup_dir/$suite_tag"
}

checkout_pinned_suite() {
  local parent stage tag_at_commit
  parent="$(dirname -- "$suite_dir")"
  mkdir -p -- "$parent"
  stage="$(mktemp -d "$parent/.${suite_tag}.install.XXXXXX")"
  cleanup_stage() { rm -rf -- "$stage"; }
  trap cleanup_stage RETURN

  GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$suite_url" "$stage" || fail "could not clone $suite_url"
  git -C "$stage" checkout --quiet --detach "$suite_commit" || fail "could not check out pinned commit $suite_commit"
  git -C "$stage" submodule update --init --recursive
  tag_at_commit="$(git -C "$stage" tag --points-at "$suite_commit" | grep -Fx "$suite_tag" || true)"
  [[ "$tag_at_commit" == "$suite_tag" ]] || fail "pinned commit is not the expected $suite_tag release tag"
  [[ -x "$stage/scripts/shibumi-suite" ]] || fail "pinned release has no Shibumi lifecycle command"
  mv -- "$stage" "$suite_dir"
  trap - RETURN
}

run_suite() {
  "$suite_dir/scripts/shibumi-suite" "$@"
}

backup_shibumi_data() {
  local backup_dir path relative_path
  backup_dir="$HOME/.local/state/arch-setups/backups/shibumi-remove-$(date +%Y%m%d%H%M%S)"
  mkdir -p -- "$backup_dir"
  for path in "$suite_state" "$shell_config" "$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"; do
    [[ -e "$path" || -L "$path" ]] || continue
    relative_path="${path#$HOME/}"
    mkdir -p -- "$backup_dir/$(dirname -- "$relative_path")"
    cp -a -- "$path" "$backup_dir/$relative_path"
  done
  printf '%s\n' "$backup_dir"
}

deploy_overrides() {
  # Enable the suite's supported Bluetooth slot without replacing the layout.
  # GroupSlot's existing monitor filter keeps G15 on the main output (DP-5).
  if [[ -f "$shell_config" ]]; then
    local bluetooth_config
    bluetooth_config="$(mktemp "${shell_config}.bluetooth.XXXXXX")"
    if jq '(.plugins[] | select(.id == "hancore.shibumi.state") | .shibumi.widgets.G15.enabled) = true' \
      "$shell_config" > "$bluetooth_config"; then
      if ! cmp -s "$shell_config" "$bluetooth_config"; then
        cp -a -- "$shell_config" "${shell_config}.bak-bluetooth-$(date +%Y%m%d%H%M%S)"
        chmod --reference="$shell_config" "$bluetooth_config"
        mv -- "$bluetooth_config" "$shell_config"
      else
        rm -f -- "$bluetooth_config"
      fi
    else
      rm -f -- "$bluetooth_config"
      fail "could not enable Shibumi Bluetooth slot"
    fi
  fi
  local base="$HOME/.config/omarchy/plugins/hancore.shibumi.bar"
  if [[ -d "$base" ]]; then
    if [[ -f "$SCRIPT_DIR/shibumi/Bar.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/Bar.qml" "$base/Bar.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/BarPanel.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/BarPanel.qml" "$base/core/BarPanel.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/GroupSlot.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/GroupSlot.qml" "$base/core/GroupSlot.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/BarSection.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/BarSection.qml" "$base/core/BarSection.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/BarSurface.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/BarSurface.qml" "$base/styles/shibumi/BarSurface.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/VisualTokens.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/VisualTokens.qml" "$base/styles/shibumi/VisualTokens.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/RunChrome.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/RunChrome.qml" "$base/styles/shibumi/RunChrome.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/NowPlayingAlbumArt.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/NowPlayingAlbumArt.qml" "$base/styles/shibumi/NowPlayingAlbumArt.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/NowPlayingVisualizer.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/NowPlayingVisualizer.qml" "$base/styles/shibumi/NowPlayingVisualizer.qml"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/NowPlayingExpandedContent.qml" ]]; then
      cp -a -- "$SCRIPT_DIR/shibumi/NowPlayingExpandedContent.qml" "$base/styles/shibumi/NowPlayingExpandedContent.qml"
    fi
    if [[ -d "$SCRIPT_DIR/shibumi/scripts" ]]; then
      mkdir -p -- "$base/scripts"
      cp -a -- "$SCRIPT_DIR/shibumi/scripts/"* "$base/scripts/"
    fi
    if [[ -f "$SCRIPT_DIR/shibumi/Indicators.qml" ]]; then
      mkdir -p "$HOME/.config/omarchy/plugins/priyesh.indicators/indicators"
      cp -a -- "$SCRIPT_DIR/shibumi/Indicators.qml" "$HOME/.config/omarchy/plugins/priyesh.indicators/Indicators.qml"
      if [[ -d "$SCRIPT_DIR/shibumi/indicators" ]]; then
        cp -a -- "$SCRIPT_DIR/shibumi/indicators/"* "$HOME/.config/omarchy/plugins/priyesh.indicators/indicators/"
      fi
      if [[ -f "$SCRIPT_DIR/shibumi/Indicators.manifest.json" ]]; then
        cp -a -- "$SCRIPT_DIR/shibumi/Indicators.manifest.json" "$HOME/.config/omarchy/plugins/priyesh.indicators/manifest.json"
      fi
    fi
    log "Deployed Shibumi side-monitor, visibility, opacity, center-notch, indicator animation, and now-playing bar overrides."
  fi
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
  local backup_dir
  backup_dir="$(backup_shibumi_data)"
  run_suite uninstall --yes
  rm -rf -- "$suite_dir"
  rmdir "$(dirname -- "$suite_dir")" 2>/dev/null || true
  log "Removed Shibumi Shell. Shell configuration and suite state were backed up to: $backup_dir"
}

case "${1:-}" in
  --disable) disable_suite; exit 0 ;;
  --remove) remove_suite; exit 0 ;;
  "") ;;
  *) fail "usage: $0 [--disable|--remove]" ;;
esac

install_runtime_dependencies
ensure_lock_status_service

if [[ -f "$suite_state" ]] && ! suite_state_matches; then
  fail "an existing Shibumi installation has a different lifecycle identity; use its matching upstream checkout to update, repair, or remove it first"
fi

if suite_state_matches; then
  suite_checkout_is_current || fail "Shibumi is installed but the pinned source checkout is missing or modified"
  active_bar="$(jq -r '.bar.id // "omarchy.bar"' "$shell_config")"
  if [[ "$active_bar" == "hancore.shibumi.bar" ]]; then
    deploy_overrides
    log "Shibumi Shell is already installed."
    exit 0
  fi
  run_suite activate --yes
  deploy_overrides
  run_suite status
  log "Re-enabled Shibumi Shell and restored its managed bar."
  exit 0
fi

if ! suite_checkout_is_current; then
  archive_existing_checkout
  checkout_pinned_suite
fi

run_suite install --dry-run
run_suite install --yes
deploy_overrides
run_suite status
log "Installed and activated Shibumi Shell at $suite_tag ($suite_commit)."
