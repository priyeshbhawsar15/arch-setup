#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DOTFILES_DIR="${ARCH_SETUPS_DOTFILES_DIR:-$SCRIPT_DIR/../dotfiles}"

stow_packages=(
  nvim
  starship
  tmux
  zsh
)

stow_targets=(
  "$HOME/.config/nvim"
  "$HOME/.config/starship.toml"
  "$HOME/.config/tmux"
  "$HOME/.zshrc"
)

if ! command -v stow >/dev/null 2>&1; then
  printf 'stow is not available on PATH.\n' >&2
  exit 1
fi

if [[ ! -d "$DOTFILES_DIR" ]]; then
  printf 'Dotfiles directory not found: %s\n' "$DOTFILES_DIR" >&2
  exit 1
fi
DOTFILES_DIR="$(cd -- "$DOTFILES_DIR" && pwd)"

for package in "${stow_packages[@]}"; do
  if [[ ! -d "$DOTFILES_DIR/$package" ]]; then
    printf 'Dotfiles package not found: %s\n' "$DOTFILES_DIR/$package" >&2
    exit 1
  fi
done

backup_dir=""
saved_targets=()
created_paths=()
committed=false

# On conflicts, failed Stow operations, or interruption, remove only links
# created by this run and empty directories before restoring staged originals.
rollback() {
  local status="$?" target relative resolved index
  trap - EXIT INT TERM
  set +e
  if [[ "$committed" == false ]]; then
    for ((index=${#created_paths[@]}-1; index>=0; index--)); do
      target="${created_paths[index]}"
      if [[ -L "$target" ]]; then
        resolved="$(readlink -m -- "$target")"
        [[ "$resolved" == "$DOTFILES_DIR/"* ]] && rm -- "$target"
      elif [[ -d "$target" ]]; then
        rmdir -- "$target" 2>/dev/null
      fi
    done
    for relative in "${saved_targets[@]}"; do
      target="$HOME/$relative"
      if [[ -e "$target" || -L "$target" ]]; then
        printf 'Cannot restore changed target %s; original remains in %s\n' "$target" "$backup_dir/$relative" >&2
      else
        mkdir -p -- "$(dirname -- "$target")"
        mv -- "$backup_dir/$relative" "$target"
      fi
    done
  fi
  exit "$status"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

directory_can_be_stowed() {
  local source_dir="$1" target_dir="$2" source_path target_path
  while IFS= read -r -d '' source_path; do
    target_path="$target_dir/${source_path#"$source_dir/"}"
    [[ -e "$target_path" || -L "$target_path" ]] || continue
    if [[ -d "$source_path" && ! -L "$source_path" ]]; then
      [[ -d "$target_path" ]] || return 1
    else
      [[ -L "$target_path" && "$(readlink -m -- "$target_path")" == "$(readlink -m -- "$source_path")" ]] || return 1
    fi
  done < <(find "$source_dir" -mindepth 1 -print0)
}

printf '\n==> Stowing dotfiles from %s\n' "$DOTFILES_DIR"

for index in "${!stow_targets[@]}"; do
  target="${stow_targets[index]}"
  relative="${target#"$HOME/"}"
  source_target="$DOTFILES_DIR/${stow_packages[index]}/$relative"
  # Keep already managed directory trees (and unrelated extra files) in place.
  if [[ -d "$target" && ! -L "$target" && -d "$source_target" ]] &&
    directory_can_be_stowed "$source_target" "$target"; then
    continue
  fi
  if [[ -e "$target" && ! -L "$target" ]]; then
    if [[ -z "$backup_dir" ]]; then
      backup_parent="${XDG_STATE_HOME:-$HOME/.local/state}/arch-setups/backups"
      mkdir -p -- "$backup_parent"
      backup_dir="$(mktemp -d "$backup_parent/dotfiles-$(date +%Y%m%dT%H%M%S)-XXXXXX")"
    fi
    mkdir -p -- "$(dirname -- "$backup_dir/$relative")"
    mv -- "$target" "$backup_dir/$relative"
    saved_targets+=("$relative")
  fi
done

# Enumerate only paths owned by the four Stow packages, never unrelated HOME
# data. --no-folding makes rollback independent of Stow's directory folding.
for package in "${stow_packages[@]}"; do
  while IFS= read -r -d '' source_path; do
    relative="${source_path#"$DOTFILES_DIR/$package/"}"
    target="$HOME/$relative"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      created_paths+=("$target")
    fi
  done < <(find "$DOTFILES_DIR/$package" -mindepth 1 -print0)
done

stow --simulate --no-folding --dir "$DOTFILES_DIR" --target "$HOME" "${stow_packages[@]}"
stow --no-folding --dir "$DOTFILES_DIR" --target "$HOME" "${stow_packages[@]}"
committed=true
if [[ -n "$backup_dir" ]]; then
  printf 'Backed up previous dotfiles to %s\n' "$backup_dir"
elif ((${#created_paths[@]} == 0)); then
  printf 'Dotfiles are already installed.\n'
fi
