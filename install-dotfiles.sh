#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DOTFILES_DIR="$(cd -- "$SCRIPT_DIR/../dotfiles" && pwd)"

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

remove_non_symlink_target() {
  local target="$1"

  if [[ -L "$target" ]]; then
    printf 'Already symlinked: %s\n' "$target"
    return
  fi

  if [[ -e "$target" ]]; then
    printf 'Removing non-symlink target before stow: %s\n' "$target"
    rm -rf -- "$target"
  fi
}

if ! command -v stow >/dev/null 2>&1; then
  printf 'stow is not available on PATH.\n' >&2
  exit 1
fi

if [[ ! -d "$DOTFILES_DIR" ]]; then
  printf 'Dotfiles directory not found: %s\n' "$DOTFILES_DIR" >&2
  exit 1
fi

printf '\n==> Stowing dotfiles from %s\n' "$DOTFILES_DIR"
mkdir -p -- "$HOME/.config"

for target in "${stow_targets[@]}"; do
  remove_non_symlink_target "$target"
done

stow --dir "$DOTFILES_DIR" --target "$HOME" "${stow_packages[@]}"
