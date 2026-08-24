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
- Keep Quattro Hyprland customizations in this directory's `hypr/` Lua modules.
- Deploy the managed Hyprland configuration with `install-hyprland.sh`; add it to `install-all.sh`.
- Keep the Quattro `~/.config/hypr/hyprland.lua` entrypoint package-managed and put personal settings only in `monitors.lua`, `input.lua`, `bindings.lua`, `looknfeel.lua`, and `autostart.lua`.
- Store stateful Hyprland toggles as `*.lua` files in `~/.local/state/omarchy/toggles/hypr/`; Quattro does not load `*.conf` toggles.
- For Hyprland window rules or syntax-sensitive settings, verify current Hyprland documentation before editing.

## Omarchy Reference

Relevant Omarchy skill instructions are available at:

`/usr/share/omarchy/default/agents/skills/omarchy/SKILL.md`

Do not edit files under `/home/priyesh/.local/share/omarchy`; that directory is managed by Omarchy.
