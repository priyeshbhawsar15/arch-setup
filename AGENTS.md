# AGENTS.md

## Project Purpose

This project maintains my personal Omarchy setup so that running a single entrypoint, `./install-all.sh`, restores my applications, configuration files, custom keyboard shortcuts, and desktop behavior on a fresh Omarchy installation.

I will describe features or plugins and how I want them to behave. Implement that behavior reproducibly in this repository and maintain it across fresh installs, rather than making undocumented changes only to the current machine.

This repository must be used together with my separate dotfiles repository, which provides configurations for tools such as Zsh and Neovim. Keep that integration part of the single-script setup; do not duplicate configuration owned by the dotfiles repository here.

## Features and Plugins

- Omarchy plugins are one supported way to implement custom behavior.
- Keep each plugin-based feature in its own plugin so it can be enabled or disabled independently.
- Keep feature-specific configuration and keyboard shortcuts with the feature where supported, and document any dependencies or conflicts.
- Disabling a plugin must disable its behavior and shortcuts without breaking unrelated features.
- Keep plugin installation and configuration reproducible through the single-script setup.
- Support both locally implemented features and community-made plugins supplied by the user. For a supplied plugin, review its source, dependencies, and installation hooks before installing or enabling it; do not install unrelated plugins automatically.
- Add an idempotent installer and register it in `install-all.sh` so a fresh install reproduces the plugin and its configuration. Document installation, updates, enable/disable controls, and removal in `PLUGINS.md`, and its installer in `SCRIPTS.md`.
- Keep Omarchy's built-in plugins package-managed. Removing custom plugins must also remove their installer registrations, shortcuts, and menu/config references, while preserving unrelated settings and backing up local data.

## Plugin Repository and Maintenance Workflow

- **Unmodified community plugins:** install directly from upstream at an exact pinned commit; do not create unnecessary forks.
- **Customized community plugins:** prefer supported configuration first. When source-code changes are needed, maintain them in a separate fork of that plugin, preserving its license and attribution.
- **Original plugins:** maintain each plugin in its own separate Git repository.
- Keep installers, personal configuration, shortcuts, source URLs, pinned commits, and documentation in this setup repository. Do not duplicate plugin source here or maintain parallel copied and forked versions. Git submodules are optional only when explicitly requested.
- The agent should handle creating the required repositories or forks, implementing and testing changes, publishing authorized changes, and integrating them here; the user should not have to create every repository manually. Verify GitHub CLI/API authentication first: SSH enables Git operations but does not by itself authorize API operations such as fork creation. Ask for missing authentication or unclear account, repository name, visibility, or publishing authorization before proceeding.
- Record each plugin's original upstream URL, installation source URL (fork or original repository), exact commit, and any local modifications in `PLUGINS.md`. Install that commit, not the latest branch tip; an existing installation is current only if its revision and managed configuration match.
- For updates, fetch upstream changes, merge or rebase them into the fork as appropriate, resolve conflicts, and test the requested behavior and enable/disable lifecycle. Publish authorized changes before updating this repository's pin so fresh installs can fetch it. Update `PLUGINS.md` and any affected `SCRIPTS.md` entries in the same change.
- Offer generally useful fixes upstream with user authorization. Once upstream includes a modification, consider returning to a pinned upstream version instead of retaining an unnecessary fork.
- Perform maintenance when requested; do not silently update pins or claim ongoing monitoring. Scheduled maintenance requires separately configured and authorized automation.

## Required Documentation

Maintain these two repository-root Markdown files in addition to `AGENTS.md`:

- `SCRIPTS.md`: Document every `.sh` file, including installers, the entrypoint, and shared helpers. Explain what each does, why it exists, its prerequisites, and any configuration or system changes it makes.
- `PLUGINS.md`: Document every plugin, the feature and behavior it provides, its configuration and keyboard shortcuts, dependencies or conflicts, and how to enable or disable it.

Whenever adding, changing, or removing a feature or behavior, update the relevant entries in these files in the same change. Update both when a change affects both scripts and plugins. Create either file if missing when working on the corresponding functionality; documentation is part of completing the change.

## Installer and Configuration Rules

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

## UI, Widgets, and Theming Guidelines

- **Desktop Widget Layering and Pinning**: Any desktop HUD, telemetry dashboard, or background monitor widget defaults to `WlrLayershell.layer: WlrLayer.Bottom` (with `exclusionMode: ExclusionMode.Ignore`) so desktop widgets live on the desktop layer behind active application windows. Every desktop widget must provide an on-top Pin toggle button (`󰐃` / `󰤱`) to switch `WlrLayershell.layer` to `WlrLayer.Overlay` when pinned, persisting the preference in `~/.local/state/omarchy/<widget-name>/settings.json`.
- **Desktop Widget Collapsing and Auto-Hide**: Every desktop widget must provide an Auto-Hide toggle button (`󰘖` / `󱊒`), persisting the preference in `settings.json`. When auto-hide is enabled and unhovered, the widget collapses smoothly into its configured docking monitor edge (left or right, according to the feature).
- **Standardized Collapsed Look and Feel**:
  - Docking window margins must be flush to the screen edge (`margins { right: 0 }` for right-docked widgets, `margins { left: 0 }` for left-docked widgets) with an `implicitWidth` accommodating the card width plus horizontal inset.
  - Quickshell `mask: Region` restricts the interactive region to the reveal strip when collapsed so mouse interactions elsewhere pass through to the underlying desktop.
  - An edge-spanning `MouseArea` sensor along the docking edge triggers expansion on hover with an auto-hide delay timer (`700ms`).
  - Card horizontal slide animations use standardized cubic easing (`duration: 320; easing.type: Easing.OutCubic`).
  - A standardized vertical grab handle pill (`width: 6, height: 80, radius: 3, color: themeAccent, opacity: isRevealed ? 0 : 0.85`) is positioned against the monitor edge in the collapsed state and fades out smoothly when expanded.
- **Aether Dynamic Theming Compliance**: All widgets, panels, HUDs, and UI components must strictly consume dynamic Aether theme tokens through `qs.Commons` `Color.*` (`Color.accent`, `Color.background`, `Color.foreground`, `Color.muted`, `Color.urgent`, etc.) and `Style.*` rather than hardcoding static hex colors. When themes or wallpapers change, all UI elements must update seamlessly with Aether's extracted palette.

## Omarchy Reference

Relevant Omarchy skill instructions are available at:

`/usr/share/omarchy/default/agents/skills/omarchy/SKILL.md`

Do not edit files under `/home/priyesh/.local/share/omarchy`; that directory is managed by Omarchy.
