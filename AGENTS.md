# AGENTS.md

This directory contains idempotent setup scripts for this Omarchy system.

## Rules

- Keep one `install-<software>.sh` script per software.
- Every installer must check whether the software is already present before installing it.
- When software is already present, print an `already installed` message and exit `0`.
- Add every new installer to the explicit `installers=(...)` list in `install-all.sh`.
- Prefer Omarchy commands over raw package manager commands.
- For Omarchy-supported browsers, use `omarchy install browser <name>`.
- For normal Arch packages, use `omarchy pkg add <package>`.
- For AUR-only packages, use `omarchy pkg aur add <package>`.
- Keep shared script helpers in `lib.sh`.
- Keep Hyprland customizations in this directory's `override.conf`.
- Ensure `/home/priyesh/.config/hypr/hyprland.conf` sources this directory's `override.conf` exactly once and at the end.
- For Hyprland window rules or syntax-sensitive settings, verify current Hyprland documentation before editing.

## Omarchy Reference

Relevant Omarchy skill instructions are available at:

`/home/priyesh/.local/share/omarchy/default/omarchy-skill/SKILL.md`

Do not edit files under `/home/priyesh/.local/share/omarchy`; that directory is managed by Omarchy.

