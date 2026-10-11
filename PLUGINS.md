# Plugins

## Current monitor assignments

DP-6 is now the main OLED; DP-5 and DP-4 are the portrait side displays (this supersedes historical connector references below). The managed Shibumi filters show all top-bar controls/indicators on DP-6 and retain workspaces/center notch on both sides. Obsidian Tasks is on DP-5; Quota, System Metrics, Weather, Immich and Home Assistant remain on DP-4. Wallpaper Controller uses `spanGroups: [["DP-5", "DP-4"]]`, leaving DP-6 as an independent full-screen wallpaper instead of part of a mixed-scale span. Lock Explorer's configured main power target is DP-6 and its dimmed sides are DP-5/DP-4. `install-monitor-layout.sh` idempotently applies this supported configuration after feature installers, with backups and without overwriting personal data, wallpaper selections or stop state. No plugin pins or sources change. Existing feature enable/disable/removal controls remain unchanged. Lock Explorer's source-level video span still uses the old pair; correcting that separate lock-screen feature requires a published plugin update.

## Main-screen Bluetooth bar control

Shibumi's existing `hancore.shibumi.bluetooth` widget is enabled through its supported G15 setting in `shell.json` (`hancore.shibumi.state` → `shibumi.widgets.G15.enabled: true`). It provides the Bluetooth bar control on main output DP-5; the managed GroupSlot filter suppresses G15 on secondary outputs. No new plugin or shortcut is added. Depends on Shibumi and BlueZ. `install-shibumi-shell.sh` reapplies this setting idempotently, backing up changed configuration. To disable it, turn off Bluetooth's bar slot in Shibumi's layout settings; rerunning the installer re-enables the managed preference.

## Desktop widget screen lifecycle

System Metrics, Weather, Immich Photo Frame, Obsidian Tasks, and OmniRoute Quota now own their window instances through Quickshell `Variants`, keyed by the selected screen object. The published pins below include this source fix. The recorded display-sleep cycle removed and re-added DP-4/DP-6; Hyprland sends layer-shell `closed` on output removal, so the previous singleton windows remained closed even after their screen bindings changed. Screen-owned instances destroy the closed window and create a new one on the appropriate live output. The configured target and existing second-screen/first-screen fallback are preserved; zero screens produces no window. Pin, auto-hide, and data stay in the service/state rather than being reset on hotplug. No polling or forced shell restart is used. DP-4 and DP-6 disable/restore tests passed with the same shell PID; physical sleep/wake remains an interactive follow-up. Each plugin repository includes `HOTPLUG-TEST.md` with lifecycle regression steps. Normal enable/disable controls below remain unchanged.

## Wallpaper Controller

- **Plugin ID:** `priyesh.wallpaper-controller`
- **Type:** Original plugin, maintained in its own repository.
- **Original upstream URL:** Not applicable; this is the original plugin repository.
- **Installation source:** `https://github.com/priyeshbhawsar15/omawallpaper-manager.git`
- **Pinned commit:** `68dd1671286ac88b381f1a882fdb20c1415de996`
- **Modifications:** Filters out disabled monitors so single monitor mode targets only active outputs without crashing, tracks active monitor topology in state to automatically re-launch with matched display arguments whenever monitor count changes, regenerates the Aether theme whenever the active wallpaper is restored at plugin startup, uses `hyprctl monitors all -j` and process verification to preserve active live wallpapers across unlocks without screen drops, spans DP-6 and DP-4 using `--scaling fill` without restrictive border clamping, and implements a decoupled 30-minute lock screen video rotation pool combining videos from `~/.config/omarchy/lock-videos/` and Steam Wallpaper Engine (`431960`). Commit `14ef5cbcfbefe6ffee03d3f9e121644e7d716e0d` introduced a scoped bypass for the upstream Linux renderer's broken solid final-composition pass. The maintained list now covers Cloudy Mountain (`3357402729`), GreenForest [4K] (`3062586648`), Blank Stare [4K] (`2897629925`), SandBlack [4k] (`3047405322`), and Sky Line Sakura [4K 244FPS] pt.2 (`3346831410`). Commit `b8a4c13b277366dd82c923bbd839334a585e9c38` additionally restricts Cloudy Mountain to its primary scenic composition, preventing that scene's unsupported media-player overlay from drawing a black thumbnail square. GreenForest. 3 (`3347344353`) disables its optional scene blur and camera-shake effects to preserve a sharp, stable tree image. Lonely Cat (`3299228616`) disables its HDR effect, which otherwise over-brightens output on SDR secondary monitors. Commit `866575e9982a3cf29d49852dcf52930314faa0dc` persists the stop state so automatic rotation and session restore cannot restart Wallpaper Engine. Commit `68dd1671286ac88b381f1a882fdb20c1415de996` keeps that automatic-stop protection while allowing an explicit manual cycle to select the next wallpaper and re-enable the renderer. All other wallpapers retain their normal rendering path.

### Behavior

Wallpaper Controller manages Steam Wallpaper Engine projects and static image wallpapers through an Omarchy overlay and a Style-menu entry. It restores the archived setup:

- The active live wallpaper is `Free Fallen [4k]` (`we:3028787000`).
- The selected rotation list rotates every 30 minutes.
- DP-6 and DP-4 are rendered as one spanning group; other connected displays receive their own background.
- The renderer uses 30 FPS compatibility mode, disabling particles, parallax, and mouse interaction. `renderer.skipSolidFinalFor` is a narrowly scoped compatibility list for scenes whose solid final-composition pass is invalid in `linux-wallpaperengine`; it currently contains Cloudy Mountain, GreenForest [4K], Blank Stare [4K], SandBlack [4k], and Sky Line Sakura [4K 244FPS] pt.2. `renderer.objectOnlyFor` limits Cloudy Mountain to its primary scenic object (`16`) to disable its incompatible media-player overlay. `renderer.propertiesFor` disables the optional blur and camera-shake properties only for GreenForest. 3, and disables HDR only for Lonely Cat.
- Applying, rotating, or restoring the active wallpaper synchronizes the Aether theme and automatically sets Lock Screen Explorer's lock video path if the active wallpaper is a video-based Wallpaper Engine item (`.mp4`/`.webm`), clearing it for scene wallpapers. Stopping Wallpaper Engine records a disabled state: automatic rotation checks and session restore leave it off until a wallpaper is explicitly applied or manually cycled again. The controller owns all `linux-wallpaperengine` processes so another Wallpaper Engine launcher conflicts with it.

The saved configuration seed is `omarchy/wallpaper-controller.json`. It is copied to `~/.config/omarchy/wallpaper-controller.json` only when absent, then becomes plugin state so interactive changes and rotation progress are preserved. It retains an archived static-image entry at `/home/priyesh/Downloads/PXL_20250811_062224647.jpg`; that source file is currently absent, so the inactive entry appears as missing but does not affect the restored live wallpaper.

### Dependencies and shortcuts

The installer uses Omarchy to install missing `linux-wallpaperengine-git`, `aether`, `imagemagick`, and `zenity`. Steam is installed by `install-steam.sh`; log in and download the required Wallpaper Engine Workshop subscriptions before expecting live entries to work on a new machine.

- `Super+Alt+W` opens Wallpaper Controller.
- `Super+Shift+R` advances to the next configured wallpaper. If Wallpaper Engine was stopped, this explicit action re-enables it and starts the selected wallpaper.
- `Super+Alt+Q` stops Wallpaper Engine persistently; it remains off across automatic rotation checks and shell/session restoration until a wallpaper is explicitly selected or manually cycled.
- The plugin also adds **Style → Wallpaper Controller** to the Omarchy menu.

### Install, disable, remove, and update

- **Install or re-enable:** `./install-wallpaper-controller.sh` — installs the exact pinned commit, seeds missing configuration, enables the plugin, restores the active wallpaper and matching Aether theme only when Wallpaper Engine is enabled in its saved state, and re-enables its shortcuts.
- **Disable:** `./install-wallpaper-controller.sh --disable` — disables the Omarchy plugin, stops its renderer/helper, removes its menu entry, and writes a Quattro toggle that unbinds all three plugin shortcuts. Do not use `omarchy plugin disable` alone, because it does not clean the helper, menu entry, or Hyprland shortcuts.
- **Remove:** `./install-wallpaper-controller.sh --remove` — runs the disable flow, removes the plugin, and archives its configuration, state, and generated transparent background under `~/.local/state/arch-setups/backups/wallpaper-controller-remove-<timestamp>/`.
- **Update:** Do not run `omarchy plugin update priyesh.wallpaper-controller`; it would move to an unpinned branch tip. Request plugin maintenance instead: review and test a candidate commit in the original repository, then update `plugin_commit` in `install-wallpaper-controller.sh` and this document together.

## Shibumi Shell

- **Suite ID:** `hancore.shibumi`; the selectable bar is `hancore.shibumi.bar`.
- **Type:** Unmodified community plugin suite. It contains 24 interdependent Omarchy plugin roots and must be installed and managed only through its suite lifecycle command.
- **Original upstream and installation source:** `https://github.com/HANCORE-linux/Shibumi-Shell.git`
- **Pinned release:** `v0.1.1-beta.14.1` at `7a6c853b1947d303bad9a5b640c224c01b669106`.
- **Local modifications:** None. The pinned upstream source is cloned to `~/.local/share/shibumi-shell/v0.1.1-beta.14.1/`; plugin source is not copied into this setup repository. Managed Shibumi bar overrides are stored in `shibumi/` and deployed by `install-shibumi-shell.sh`. `BarSurface.qml` clusters all top bar elements (workspaces, volume, control center, middle notch, indicators, and tools) together in the horizontal center of the screen flanked closely beside the middle notch, leaving the outer edges open. `GroupSlot.qml` and `BarSection.qml` display the workspace widget and center notch section on every monitor while keeping heavy system trays and Omarchy indicators (Stay Awake / Caffeine, Night Light, Voxtype Dictation, Do Not Disturb, Reminders, Screen Recording) focused on the primary monitor (`DP-5`). `BarPanel.qml` provides the auto-hide reveal strip without consuming clicks once the bar is shown; it yields below the surface after reveal so hover over the center notch opens the media control centre normally and keeps the entire bar exposed while the pointer remains within that media area. `VisualTokens.qml` sets the top-bar and panel background to 100% solid opacity without transparency or frost blur. `RunChrome.qml` renders the V1 center group as a centered, compact 300px-max screen-edge Apple-style notch: a broad top transitions through an organic S-curve shoulder into a subtly inward-tapering body with rounded lower corners, while preserving the floating left and right islands. `NowPlayingAlbumArt.qml`, `NowPlayingVisualizer.qml`, and `NowPlayingExpandedContent.qml` implement a Dynamic-Island-style now-playing widget over `omarchy.media`'s MPRIS state directly inside the V1 center notch: a rounded album-art thumbnail flanks the clock on the left and a 4-bar decorative visualizer flanks it on the right (both hidden with no active track), and hovering either reveals an expanded card with larger art, title/artist, a scrub bar, and previous/play-pause/next transport controls, closing on a debounce delay after the pointer leaves the card. The stock `hancore.shibumi.media` bar widget is disabled in favor of this notch-integrated presentation.

### Behavior and compatibility

The default Shibumi lifecycle activates its V1/V2 full-bar host, installs its complete plugin suite transactionally, and replaces the active Omarchy bar/layout with Shibumi’s managed layout. It records the prior bar for suite-managed return to stock Omarchy. The suite owns its 24 plugin directories, the `hancore.shibumi.state` entry in `~/.config/omarchy/shell.json`, and `~/.local/state/shibumi/` transaction and recovery state. It also adds reversible Omarchy menu routing for its theme and wallpaper pickers. It does not add Hyprland keyboard shortcuts.

Do **not** run `omarchy plugin add`, `omarchy plugin update`, `omarchy plugin disable`, or `omarchy plugin remove` against individual Shibumi directories. Use the suite lifecycle only; individual changes can break its verified ownership, recovery, and inter-plugin dependencies.

Upstream validates this prerelease on Omarchy 4.0.3 and explicitly has not completed multi-output acceptance. This system runs Omarchy 4.0.4-1 and uses multiple outputs, so installation remains outside upstream’s validated compatibility boundary. The initial preflight refusal was caused by this system’s disabled `omarchy.lock` service, not an API difference: Shibumi needs its lock-status IPC to prove the session is safe to mutate. The service is now enabled. Do not manually edit Shibumi state, lifecycle journals, or managed plugin files.

### Dependencies and lifecycle

`install-shibumi-shell.sh` installs missing source-workflow runtime packages through Omarchy: Git, Python, jq, curl, NetworkManager, power-profiles-daemon, upower, xdg-utils, libnotify, wl-clipboard, and the required Material Symbols, JetBrains Mono Nerd, Noto CJK, and Adwaita fonts. Optional Shibumi integrations, such as CAVA, GPU telemetry, video thumbnails, and btop, are not installed automatically. The managed `priyesh.indicators` override keeps inactive indicators hidden at rest, animates them open on hover, keeps the expanded pill open while the pointer crosses either active or inactive indicators, and collapses it only after the pointer leaves the complete indicator area.

- **Install or re-enable:** `./install-shibumi-shell.sh` — enables Omarchy’s required built-in `omarchy.lock` service when necessary, verifies its status endpoint, runs upstream’s source dry-run, then installs and activates the 24-plugin suite. It must run in an active, unlocked Omarchy desktop session; the suite safely drains and restarts the shell.
- **Disable:** `./install-shibumi-shell.sh --disable` — runs upstream `deactivate`, restores the stock Omarchy bar, and retains the suite payload and settings for later reactivation. Shibumi owns no Hyprland shortcuts.
- **Remove:** `./install-shibumi-shell.sh --remove` — backs up Shibumi state plus the shell/menu configuration to `~/.local/state/arch-setups/backups/shibumi-remove-<timestamp>/`, then runs upstream’s transactional uninstall and removes the pinned checkout.
- **Update:** Do not update from upstream `main`. Request maintenance: review a compatible tagged release, test the suite lifecycle and this host, then update the pinned tag/commit and this documentation together. The upstream release must explicitly support the installed Omarchy version before this pin is advanced.

## Per-monitor Workspaces for Shibumi

- **Plugin ID:** `mmsbrggr.per-monitor-workspaces`
- **Type:** Customized community plugin. It remains a separate public fork so Shibumi-specific QML changes do not modify either upstream project.
- **Original upstream URL:** `https://github.com/mmsbrggr/omarchy-per-monitor-workspaces`
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-per-monitor-workspaces.git`
- **Pinned commit:** `0292ebec608cd7d3907b8f9f9427c252b242edf2` (`v1.2.0-shibumi.5`)
- **Local modifications:** The fork preserves upstream MIT attribution, named-workspace protocol, Hyprland Lua actions, hotplug adoption, and mouse behavior. It replaces only `Workspaces.qml` with a Shibumi-native workspace pill: matching Shibumi’s presentation tokens, marker geometry, color treatment, hover feedback, tooltips, and standard QML wheel handling. It also consumes Shibumi State’s public, variant-scoped G2 appearance settings, so the existing Control Center **Bars → Workspaces** visual controls affect this provider. It requires Shibumi’s State presentation library and is not intended for the stock Omarchy bar.

### Behavior and keyboard controls

Hyprland itself has global workspaces; the plugin implements independent per-monitor slots as named workspaces keyed to each output’s display description. `Super+1` through `Super+5` therefore always selects the corresponding slot on the focused monitor. The default count is five slots per monitor. The bar on each output displays only that output’s slots, plus a Shibumi-styled display marker for a disconnected output’s temporarily parked workspace.

Shibumi Control Center → **Bars** → **Workspaces** controls this provider’s active-profile appearance (fill color, content tone, opacity) and marker preferences (**Marker Style** and **Visible Workspaces** mode). The five-slot count remains a local widget setting because it is also projected into Hyprland’s binding actions. The native `hancore.shibumi.workspaces` plugin must remain enabled as the default-bundle G2 service and safe fallback; it is visually displaced by this provider, not disabled.

The feature-specific keymap is activated by the managed toggle at `~/.local/state/omarchy/toggles/hypr/per-monitor-workspaces.lua`, which `hypr/bindings.lua` reads before loading the plugin’s `hypr/init.lua`. While active it replaces Omarchy’s global workspace bindings:

- `Super+1…5`, `Super+Shift+1…5`, and `Super+Shift+Alt+1…5` select or move windows within the focused monitor’s slots.
- `Super+Tab`, `Super+Shift+Tab`, and `Super+scroll` cycle the focused monitor’s slots; `Super+Ctrl+Tab` returns to its previous workspace.
- `Super+L` toggles the named workspace’s dwindle/scrolling layout.
- Directional `Super+Ctrl+Alt`, `Super+Ctrl+Shift`, `Super+Shift+Alt`, and `Super+Ctrl+Alt+Shift` arrow bindings focus a monitor, move a window, move the current workspace’s windows, or swap workspace contents.

`hypr/monitors.lua` keeps the existing numeric workspace rules only while this feature is disabled. Enabling it removes those static assignments at the next Hyprland reload; existing numeric workspaces remain accessible as parked workspaces until their windows are moved or closed.

### Dependencies, conflicts, and lifecycle

This feature requires the active `hancore.shibumi.bar`, its `hancore.shibumi.state` presentation library, and its enabled native `hancore.shibumi.workspaces` default-bundle service. It replaces Shibumi’s workspace presentation without disabling that service; do not separately enable the stock `omarchy.workspaces`, Screens workspace spreading, or another per-monitor workspace manager. The fork is pinned because marketplace installation clones mutable upstream HEAD; the marketplace’s latest upstream source was not snapshot-verified when this fork was made.

- **Install or re-enable:** `./install-per-monitor-workspaces.sh` — validates and installs the pinned fork, configures it as Shibumi’s workspace provider, enables the Lua toggle, and reloads Hyprland. It requires an active Shibumi desktop session.
- **Disable:** `./install-per-monitor-workspaces.sh --disable` — disables the widget, removes the temporary stock-workspace restoration, removes the Lua toggle, and reloads Hyprland so Shibumi’s native workspace widget and numeric workspace rules return.
- **Remove:** `./install-per-monitor-workspaces.sh --remove` — archives the plugin’s count, layout, and toggle state under `~/.local/state/arch-setups/backups/per-monitor-workspaces-remove-<timestamp>/`, then disables and removes the pinned checkout.
- **Update:** Do not use `omarchy plugin update`; it follows a branch tip. Request maintenance instead: merge or rebase a reviewed upstream change into the fork, test bar rendering, named-workspace keybindings, unplug/replug behavior, and the enable/disable lifecycle, publish the change, then update this pin and both documentation files together.

## hyprmoncfg: Multi-Monitor Manager for Omarchy

- **Plugin ID:** `crmne.hyprmoncfg`
- **Type:** Unmodified community plugin.
- **Original upstream URL:** `https://github.com/crmne/omarchy-hyprmoncfg.git`
- **Installation source:** `https://github.com/crmne/omarchy-hyprmoncfg.git`
- **Pinned release:** `v2.3.5` at `cf05a04a50339510cd1f9d547fb5f80556ae6599`
- **Local modifications:** None.

### Behavior and controls

Provides automatic multi-monitor profile layout switching on hotplug, lid open/close, and suspend events. Includes a spatial display editor with per-output scale, brightness, HDR, ICC color management, mirroring, rotation, and workspace planner. Matches monitors by make, model, and serial rather than connector port.

- **Install or re-enable:** `./install-hyprmoncfg.sh` — validates and installs the pinned `v2.3.5` checkout and enables the plugin in Omarchy shell.
- **Disable:** `./install-hyprmoncfg.sh --disable` — disables the plugin in Omarchy shell.
- **Remove:** `./install-hyprmoncfg.sh --remove` — archives configuration and state under `~/.local/state/arch-setups/backups/hyprmoncfg-remove-<timestamp>/`, then disables and removes the plugin.

## Lock Screen Explorer

- **Plugin ID:** `io.github.sirjul1337.lock-explorer`
- **Type:** Customized community plugin fork.
- **Original upstream URL:** `https://github.com/SirJul1337/omarchy-lock-explorer.git`
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-lock-explorer.git`
- **Pinned commit:** `7f0da0169e41615493834e39d9c84c889b3ac30e` (persistent brightness-recovery fork, based on v1.7.7).
- **Local modifications:** The fork adds native QtMultimedia video wallpaper playback to `designs/Wallpaper.qml` and `designs/VideoWallpaper.qml` so all built-in designs play active video wallpapers seamlessly, spans video wallpaper playback across secondary monitors (`DP-6` and `DP-4`) using `VideoOutput.PreserveAspectCrop` container mapping to maintain original aspect ratios without stretching, automatically restores live desktop wallpaper on session unlock via `wallpaper-controller restore`, adds opt-in per-output locked idle power management with compositor activity detection instead of QML pointer-change wakeups, enables crisp video playback on side monitors (`designs/Companion.qml`), and optimizes Explorer grid preview performance by decoding video only for the currently selected card while unselected cards display static background thumbnails.

### Behavior and controls

Provides custom lock screen designs, a preview/picker overlay to switch between lock screens, and a designer overlay to build custom lock screens. Accessible from Omarchy Menu (**Style › Lock Screen Explorer**).

Managed `phasedPower` on the plugin entry in `~/.config/omarchy/shell.json`: main `DP-5` powers off after **60 seconds**; sides `DP-4`/`DP-6` remain powered and reach hardware minimum brightness (DDC VCP 10 = 0) after **300 seconds total**, indefinitely. Both side lock surfaces also receive a **50%-opaque black attenuation overlay** (`overlayOpacity: 0.5`) above all content, without intercepting input; it disappears immediately on activity/unlock and never covers DP-5. This is literal optical black, not a decorative theme color; existing Aether-themed content remains unchanged underneath. Brightness writes are checked with VCP 10 readback. Pre-dim values are saved atomically/fsynced in `${XDG_STATE_HOME:-~/.local/state}/omarchy/lock-explorer-power/`, surviving logout/reboot; legacy runtime data is migrated when available. Once startup confirms the compositor session is unlocked, saved brightness is restored automatically with up to five bounded attempts; failed restores retain saved values. This fixes brightness remaining at 0 on the unlocked desktop after a reboot erased the former runtime-only restore state. Connector-matched buses reported as invalid by `ddcutil detect` are tested for actual brightness access before being discarded; a failure on one side does not skip the other and is logged. Compositor input activity restores all displays and their original side brightness, then restarts both deadlines; unlocking restores them too. Geometry changes/PAM retries do not wake monitors. Requires Python 3, ddcutil, I2C permissions and DDC-capable sides; monitor buses are discovered by connector, not pinned bus numbers. Conflicts with other display-power daemons. No new shortcut. Legacy `blankMs`/`keepDisplayOn` do not apply in this mode. Unlock before installation, disable/removal or shell restart; installer checks this and restores saved brightness before disable. Remove `phasedPower` while unlocked to revert to legacy behavior. Verification: **both DP-4 and DP-6 read back brightness 0** in a live hardware roundtrip and then returned to their original 100. Unit tests (12 Python + 17 JS, including fresh-process restoration and runtime-state migration), QML syntax checks, facade validation and manifest validation passed; physical full-duration lock/overlay/wake/suspend/hotplug acceptance remains pending.

- **Install or re-enable:** `./install-lock-explorer.sh` — validates and installs the pinned checkout, enables the plugin in Omarchy shell, and registers its menu shortcut.
- **Disable:** `./install-lock-explorer.sh --disable` — disables the plugin in Omarchy shell and removes its menu shortcut.
- **Remove:** `./install-lock-explorer.sh --remove` — archives configuration and state under `~/.local/state/arch-setups/backups/lock-explorer-remove-<timestamp>/`, then disables and removes the plugin.

## Omaland (Hyprland Visual Look & Feel Editor)

- **Plugin ID:** `bobbynicholas.omaland`
- **Type:** Unmodified community plugin.
- **Original upstream URL:** `https://github.com/bobby-nicholas/omaland.git`
- **Installation source:** `https://github.com/bobby-nicholas/omaland.git`
- **Pinned commit:** `ec232b6aa2e31b2f089ad89b653cd706989865b9`
- **Local modifications:** None.

### Behavior and controls

Provides a graphical panel for editing Hyprland's visual look and feel (gaps, borders, animations, blur, rounding) with live visual previews. Writes a managed block into `~/.config/hypr/looknfeel.lua`.

- **Open Omaland:** Search `Omaland` in Omarchy Menu, or run `omarchy-shell shell toggle bobbynicholas.omaland` from the terminal.
- **Install or re-enable:** `./install-omaland.sh` — validates and installs the pinned checkout and enables the plugin in Omarchy shell.
- **Disable:** `./install-omaland.sh --disable` — disables the plugin in Omarchy shell.
- **Remove:** `./install-omaland.sh --remove` — archives configuration and state under `~/.local/state/arch-setups/backups/omaland-remove-<timestamp>/`, then disables and removes the plugin.

## Calendar Bar Widget

- **Plugin ID:** `tmn73.calendar`
- **Type:** Unmodified community plugin.
- **Original upstream URL:** `https://github.com/tmn73/omarchy-calendar.git`
- **Installation source:** `https://github.com/tmn73/omarchy-calendar.git`
- **Pinned commit:** `08f5c01fb3b40322787ebfa9805429baa19beb5f` (`v0.2.1`)
- **Local modifications:** None.

### Behavior and controls

Provides a Google Calendar integration and clock/date bar widget in the center slot of the top bar. Shows your date/time, next meeting at a glance, and one-click Google Calendar meeting joining.

- **Install or re-enable:** `./install-calendar.sh` — validates and installs the pinned checkout, enables the plugin in Omarchy shell, and configures it in the top bar center slot.
- **Disable:** `./install-calendar.sh --disable` — disables the plugin in Omarchy shell and restores the stock Shibumi center clock.
- **Remove:** `./install-calendar.sh --remove` — archives configuration and state under `~/.local/state/arch-setups/backups/calendar-remove-<timestamp>/`, then disables and removes the plugin.

## OmniRoute Quota Monitor

- **Plugin ID:** `priyesh.omniroute-quota`
- **Type:** Original plugin, maintained in its own repository.
- **Original upstream URL:** Not applicable; this is the original plugin repository.
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-omniroute-quota.git`
- **Pinned commit:** `b2e3be74e29d9d94e97be9db3d0242641d5b2348`
- **Local modifications:** None. The plugin repository maintains the official Provider Limits API parser and edge-docked collapse fix.

### Behavior and controls

Provides a live AI provider quota and connection health desktop HUD on portrait display `DP-4`. It joins active connections from OmniRoute's `/api/providers` endpoint with official quota observations from `/api/usage/provider-limits`. Startup and manual refresh perform a live upstream quota sync; 30-second background reads reuse OmniRoute's provider-limit cache without repeatedly hitting provider APIs. The HUD displays Copilot premium-interaction capacity, Codex 5-hour and weekly capacity, and the active Antigravity Pro account's Gemini capacity with reset intervals. Missing telemetry is explicitly shown as unavailable instead of being inferred as 100% from the absence of a cooldown.

- **Configuration:** `~/.config/omarchy/omniroute-quota.json` (endpoint, token, refresh interval, position, dimensions). Fresh installs seed an empty token; configure credentials locally before using the HUD. Existing configuration is preserved; credentials are not stored in this repository.
- **CLI helper:** `omniroute-quota {refresh|status|config}`.
- **Controls:** Pin overlays the card above apps; Auto-Hide slides it into the right display edge, leaving the same 14px hover target and 6×80px accent handle as the task widget. Both preferences persist in `~/.local/state/omarchy/omniroute-quota/settings.json`.
- **Toggle visibility:** `omarchy-shell shell toggle priyesh.omniroute-quota`.
- **Install or re-enable:** `./install-omniroute-quota.sh` — installs the pinned checkout, seeds default settings, and enables the plugin in Omarchy shell.
- **Disable:** `./install-omniroute-quota.sh --disable` — disables the plugin and hides the HUD.
- **Remove:** `./install-omniroute-quota.sh --remove` — archives configuration and state under `~/.local/state/arch-setups/backups/omniroute-quota-remove-<timestamp>/`, then disables and removes the plugin.

## System Metrics HUD

- **Plugin ID:** `priyesh.system-metrics`
- **Type:** Original plugin, maintained in its own repository.
- **Original upstream URL:** Not applicable; this is the original plugin repository.
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-system-metrics.git`
- **Pinned commit:** `0a2fd78d7f5b0571f90e3cc2c1fa8869c75aad76`
- **Local modifications:** None. The edge-docked collapse fix is maintained in the plugin repository.

### Behavior and controls

Provides a real-time hardware telemetry HUD on portrait monitor `DP-4` (positioned directly below the OmniRoute Quota HUD). Displays:

- **Circular Progress Rings**: Side-by-side circular donut meters for System RAM (Cyan) and GPU VRAM (Purple), showing used/total GB and percentage occupied.
- **Real-time CPU Metrics & Graph**: CPU utilization percentage, CPU temperature in °C, and a 20-point rolling area graph (Emerald).
- **Real-time GPU Metrics & Graph**: AMD GPU utilization percentage, GPU temperature in °C, and a 20-point rolling area graph (Amber).
- **Real-time Network Throughput & Graph**: Download/Upload speeds in KB/s / MB/s and network traffic activity graph (Sky Blue).

- **CLI helper:** `system-metrics-collector {once|daemon}`.
- **Controls:** Pin overlays the card above apps; Auto-Hide slides it into the right display edge with the shared vertical accent handle. Both preferences persist in `~/.local/state/omarchy/system-metrics/settings.json`.
- **Toggle visibility:** `omarchy-shell shell toggle priyesh.system-metrics`.
- **Install or re-enable:** `./install-system-metrics.sh` — installs the pinned checkout and enables the plugin in Omarchy shell.
- **Disable:** `./install-system-metrics.sh --disable` — disables the plugin and hides the HUD.
- **Remove:** `./install-system-metrics.sh --remove` — archives configuration and state under `~/.local/state/arch-setups/backups/system-metrics-remove-<timestamp>/`, then disables and removes the plugin.

## Weather Widget

- **Plugin ID:** `priyesh.weather-widget`
- **Type:** Original plugin, maintained in its own repository.
- **Original upstream URL:** Not applicable; this is the original plugin repository.
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-weather-widget.git`
- **Pinned commit:** `e9c0d99ffa587452ba4597160a28f1fdc9d8b00c`
- **Local modifications:** None.

### Behavior and controls

Provides a desktop weather card widget on portrait monitor `DP-4` (positioned directly below the System Metrics HUD). Displays:

- **Large Weather Outline Icon**: Dynamic high-contrast weather condition icon (cloud with rain drops, sun rays, fog, snow, thunderstorm).
- **Thermometer Gauge**: Custom QML canvas glass thermometer showing an inner mercury fill height proportional to temperature with right-side tick marks.
- **Temperature & Location Subtitle**: Large bold temperature readout (`23°`), location name, condition text, and humidity percentage.
- **3-Hour Forecast Row**: 3 columns displaying upcoming 3-hour forecast intervals (`+3h`, `+6h`, `+9h`), mini weather condition icons, and forecast temperatures.

- **Configuration:** `~/.config/omarchy/weather-widget.json`. Respects Omarchy's location settings in `~/.local/state/omarchy/settings/weather.json` or auto-detects city coordinates via Open-Meteo API.
- **CLI helper:** `weather-widget {refresh|status|config}`.
- **Controls:** Header Auto-Hide (`󰘖` / `󱊒`) and Pin (`󰐃` / `󰤱`) buttons slide the card into the right edge or move it above applications; settings persist in `~/.local/state/omarchy/weather-widget/settings.json`. The collapsed card leaves the same edge target and vertical accent handle as the task widget.
- **Toggle visibility:** `omarchy-shell shell toggle priyesh.weather-widget`.
- **Install or re-enable:** `./install-weather-widget.sh` — installs the pinned checkout and enables the plugin in Omarchy shell.
- **Disable:** `./install-weather-widget.sh --disable` — disables the plugin and hides the HUD.
- **Remove:** `./install-weather-widget.sh --remove` — archives configuration and state under `~/.local/state/arch-setups/backups/weather-widget-remove-<timestamp>/`, then disables and removes the plugin.

## Immich Photo Frame

- **Plugin ID:** `priyesh.immich-photo-frame`
- **Type:** Original private plugin, maintained in its own repository.
- **Original upstream URL:** Not applicable; this is the original plugin repository.
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-immich-photo-frame.git` (private)
- **Pinned commit:** `6221323be37f96bd17b18f0875bb062f9fbe66d3`
- **Local modifications:** None.

### Behavior and controls

Provides a desktop-only Polaroid-style photo frame on `DP-4`, modeled after the supplied framed-photo reference. The photo fills a cropped image well inside a lightly tilted paper frame, has a theme-aware paper/tape/shadow treatment, and keeps the decorative layer behind application windows. Its caption prints the capture date followed by the photo's saved city, region, and country.

- **Source:** Follows every page of the configured Immich metadata-search API and selects uniformly from all non-archived images, rather than sampling only the API's first result page or favoring geotagged photos. A persistent shuffle-cycle history guarantees every currently available image is selected once in random order before any repeats; a new cycle cannot immediately repeat the current image. It downloads only the selected asset's preview thumbnail and never stores the API key, originals, or library metadata in this repository.
- **Rotation:** Selects a photo at shell startup, then hourly. Click the frame to select another photo from the same no-repeat random cycle immediately.
- **Configuration:** `~/.config/omarchy/immich-photo-frame.json`, mode `0600`. It contains the Immich base URL, API key, and target output. The source key is local-only and is backed up only as part of this feature's explicit removal archive.
- **Cached state:** `~/.local/state/omarchy/immich-photo-frame/` holds the current preview, minimal display state, and `selection-history.json` containing only asset IDs used by the no-repeat cycle, all with mode `0600`.
- **CLI helper:** `immich-photo-frame {refresh|status}`.
- **Controls:** Click the photo or run `immich-photo-frame refresh` to fetch a new image. Buttons in its top-right photo corner enable Auto-Hide (`󰘖` / `󱊒`) and Pin (`󰐃` / `󰤱`). Collapsing slides the frame into the left edge, leaving a rounded, theme-aware edge rail and the shared vertical accent handle; the frame stays revealed while the pointer is over any part of it, including the photo and controls, and collapses after the pointer leaves. Preferences persist in `~/.local/state/omarchy/immich-photo-frame/settings.json`. Disable or re-enable with its installer.
- **Install or re-enable:** `./install-immich-photo-frame.sh` installs the exact pinned private checkout and enables the widget.
- **Disable:** `./install-immich-photo-frame.sh --disable` disables only the frame.
- **Remove:** `./install-immich-photo-frame.sh --remove` archives the local configuration and cache under `~/.local/state/arch-setups/backups/immich-photo-frame-remove-<timestamp>/`, then disables and removes the plugin.

## Obsidian Tasks Widget

- **Plugin ID:** `priyesh.obsidian-tasks`
- **Type:** Original private plugin, maintained in its own repository.
- **Original upstream URL:** Not applicable; this is the original plugin repository.
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-obsidian-tasks.git` (private)
- **Pinned commit:** `c930f029ee43043163de2946b7c780c8f995353f`
- **Local modifications:** None.

### Behavior and controls

Provides a scrollable desktop list of the active tasks represented by `00 Home/Tasks.md`, placed at the left edge of `DP-6` with its expanded card inset from that edge. Clicking its heading or any displayed task opens that dashboard in the Obsidian desktop application.

- **Category Filters:** Interactive pill tabs allow filtering open tasks by **All**, **Homelab**, **Projects**, **Personal**, and **Work**, each showing real-time task counts.
- **On-Top Pin Control (`󰐃` / `󰤱`):** Switches the widget to `WlrLayer.Overlay` to stay visible above open applications.
- **Auto-Hide Control (`󰘖` / `󱊒`):** When enabled, automatically slides into the left screen edge with smooth easing when unhovered, leaving a vertical reveal handle; hovering the handle or card slides it back in.
- **Task scope:** Mirrors the dashboard's global `#tasks` filter: unchecked task lines whose first token is `#tasks`, from active Personal, Projects, Homelab, and Work notes. It excludes `00 Home`, `90 Archive`, and `_System` templates, reads each source task once rather than duplicate query output, and sorts overdue/due tasks before the remaining category/task order.
- **Refresh:** Reads the vault at plugin startup and every minute; `obsidian-tasks-widget refresh` runs a manual refresh.
- **Configuration:** `~/.config/omarchy/obsidian-tasks.json` holds the vault path/name, dashboard path, and target output (default `DP-6`).
- **Cached state:** `~/.local/state/omarchy/obsidian-tasks/state.json` contains display tasks and `settings.json` saves pin/auto-hide preferences.
- **Install or re-enable:** `./install-obsidian-tasks-widget.sh` installs the exact pinned private checkout and enables the widget.
- **Disable:** `./install-obsidian-tasks-widget.sh --disable` disables only the widget.
- **Remove:** `./install-obsidian-tasks-widget.sh --remove` archives the local configuration and state under `~/.local/state/arch-setups/backups/obsidian-tasks-remove-<timestamp>/`, then disables and removes the plugin.

## Bar Visibility Mode Controls

Top bar visibility is toggled by `Super+Shift+Space` (via `~/.config/hypr/scripts/bar-visibility-mode-toggle.sh`). It cycles through 3 modes:

1. **Always show**: The bar is pinned and reserves screen space.
2. **Auto-hide**: The bar hides when not hovered and reveals smoothly when the mouse touches the top 6px edge.
3. **Disabled**: The bar is completely hidden.

Shibumi Bar monitors `~/.local/state/omarchy/toggles/` (`bar-autohide` and `bar-off`) and reacts dynamically to mode changes.

## Home Assistant Environment and Lighting

- **Plugin ID:** `priyesh.home-assistant`; original private plugin in its own repository.
- **Original upstream:** Not applicable; original implementation.
- **Installation source:** `https://github.com/priyeshbhawsar15/omarchy-home-assistant.git` (private).
- **Pinned commit:** `1fe269a3fdff3a7c8f920c0403f069449745069b`.
- **Modifications:** None outside the maintained original source repository.

A desktop-only control card on **DP-4**, directly below Weather at the right edge, emphasizes room temperature and humidity in two aligned, equally prominent 30px readouts. It matches Weather/System Metrics: 390px card width, shared font hierarchy, 85%-alpha Aether background, 30%-alpha accent outline, `Style.space(16)` rounding/padding, and 28px Auto-Hide then Pin header controls. The full controls are always present when revealed in a fixed-height, bounded scrollable card (up to 650px); there is no compact-to-expanded resize or slide animation. The cleaned-up AC keeps a compact 164px 270° setpoint dial and ± buttons, with Mode/Fan/Preset fields aligned alongside it and equal-width Vertical/Horizontal Swing fields below. The redundant AC current-temperature block is removed. Every climate/WLED dropdown and popup uses the same font, 34px height, padding, 8px corners and theme-bound selected/focus/hover states. Room switches occupy an aligned 2×2 grid and all four are visible without scrolling at this DP-4 geometry; lower WLED controls remain scrollable. Dial drag commits on release and ±/arrow keys step within the entity's actual limits. Hover/focus or click instantly reveals Panasonic AC power, temperature and supported climate options; outdoor HA weather; Tube, Top 1, Top 2 and Fan switches; Mood Lighting and Focus Mode scenes; Monitor/Bed/Window WLED brightness, named color presets/hue and actual effect-list selection. Escape dismisses details. No bar entry, new global shortcut or smart-home automation is created. The existing HA Quick entry is absent from the current bar; unrelated bar layout is preserved.

**Removed controls:** Good Night and Leave Home have been removed from default and current local configuration, and are filtered from legacy scene mappings. Mood Lighting and Focus Mode remain. **Intentional limitation:** Monitor (`light.window`) is unavailable in HA; no direct WLED bypass is used. Repair its HA integration separately; no substitute device actions are invented.

- **Configuration:** `~/.config/omarchy/home-assistant.json`, seeded only if absent, holds HTTPS URL, token-file path, output/top margin and entity mappings. `targetScreen: "DP-4"`, `topMargin: null` computes placement from Weather's managed top (`Style.space(900)`), 165px height and `Style.space(14)` gap; a numeric margin remains an explicit override. The existing local configuration was backed up before moving it from DP-6. Re-enable after changing mappings. Personal configuration is local-only.
- **Credentials:** existing `~/.config/omarchy/hass/token`, mode `0600`. Python reads it without putting the token into QML, process arguments, logs or cached state. HTTPS certificates are verified and redirects rejected. The token is never published or removed by this installer.
- **Transport:** REST states and domain/service calls plus authenticated WebSocket state-change events with reconnect. Stale/offline readings remain labelled disconnected and controls disabled. Actions are not replayed after connection loss. Only configured entities and supported values can be submitted.
- **Controls:** persistent Pin (`󰐃` / `󰤱`) selects Overlay versus default Bottom; Auto-Hide (`󰘖` / `󱊒`) defaults on and is enabled for this deployment; it hides/reveals the full card instantly at the right edge using the 14px mask, 6×80px accent handle and 700ms departure delay. The standard slide/fade animation is deliberately omitted per this user's explicit request. Preferences and selected telemetry reside in `~/.local/state/omarchy/home-assistant/` (user-only files). Aether tokens theme the controls dynamically. Screen-keyed Variants show nothing when DP-4 is absent, rather than falling back onto excluded outputs.
- **Dashboard:** launches the existing `~/.local/share/applications/Home Assistant.desktop` through `gio launch`; that webapp must exist on a fresh machine.
- **Dependencies:** Omarchy/Quickshell, Python 3 with venv/pip, Git, jq, gio, private GitHub repository access and a dedicated HA long-lived token. A user-local venv pins `websocket-client==1.8.0`; no system package or HA configuration is modified. Other room-control software can independently change devices, so readings remain authoritative from HA.
- **Install/re-enable:** `./install-home-assistant.sh`; registered in `install-all.sh`. Changed pins restart the shell once to avoid cached QML. Matching current installations print `already installed` and exit 0.
- **Disable:** `./install-home-assistant.sh --disable`; stops transport and removes only this widget's windows. The installer additionally uses a transport PID/source record and verifies `/proc` command identity before signalling it, preventing a stale reload generation from retaining the HA reader; unrelated processes are never targeted.
- **Remove:** `./install-home-assistant.sh --remove`; archives config/state under `~/.local/state/arch-setups/backups/home-assistant-remove-<timestamp>/`, then removes the clean managed checkout. Preserves the pre-existing HA token and user-local runtime. No shortcuts/menu entries require cleanup.
- **Update:** review/test in the separate original repository, publish authorized changes, then advance the installer pin and both documentation entries together. Do not use branch-tip `omarchy plugin update`.

**Verification:** 11 backend tests (including preset/horizontal swing validation, removed scene defaults and an unrelated-process stop guard), manifest validation, live read-only REST/WebSocket connection, rendered compact thermostat/dropdowns, dynamic theme binding, Pin layer switch and disable/re-enable process/window cleanup passed. `/tmp/ha-clean-final.png` confirms both large room readings, no duplicate current-temperature block, aligned dropdown columns and all four switches visible without scrolling; no widget runtime errors were observed. HA remains at y=1231 beneath Weather's y=1215 bottom (16px gap), matching its 409px window width including inset. The prior right-edge reveal test passed; this revision retains that mask/handle while removing all expansion/slide animations and retaining the full card height. Pin was reset to Bottom and Auto-Hide left enabled. Physical device actions, full keyboard navigation, hotplug/sleep and fresh-machine launcher/authentication remain manual acceptance items; see the plugin's `TESTING.md`. No device-changing service calls were issued during verification.

## Removed integrations

The `per-monitor-bar` plugin remains removed. Its installer, source checkout, visibility-mode shortcut, and local state were archived during the plugin reset. Omarchy's default `Super+Shift+Space` bar toggle remains in use.

## Adding future plugins

Plugins can implement an original requested feature or come from a community repository supplied by the user. Keep each feature independently toggleable. Original plugins live in separate repositories; community plugins use upstream directly unless source modifications require a separate fork. Prefer supported configuration over code changes.

The agent handles repository/fork creation and maintenance when requested and authorized; the user need not create each repository manually. GitHub CLI/API authentication is required for repository and fork creation; SSH alone covers Git operations. Confirm any unclear account, repository name, visibility, or publishing authorization first.

For each plugin:

1. Review its source, installation hooks, dependencies, and compatibility before execution.
2. Record the original upstream URL (if applicable), installation source URL, exact pinned commit, and any modifications here. Keep source in upstream, a dedicated fork, or the original plugin's own repository—not copied into this setup repository. Preserve licenses and attribution. Use submodules only if explicitly requested.
3. Add an idempotent installer to `install-all.sh`, using supported Omarchy commands where available, and document it in `SCRIPTS.md`. Install the pinned commit, not the latest branch tip. Check both revision and managed configuration before treating an existing installation as current.
4. Record its purpose, behavior, dependencies, conflicts, configuration, keyboard shortcuts, and installation/update/removal procedure here.
5. Document and test independent enable/disable behavior, including cleanup of plugin-owned shortcuts and menu entries. Standard shell plugins use `omarchy plugin enable <id>`, `omarchy plugin disable <id>`, and `omarchy plugin remove <id>`; document any additional steps required by that plugin.
6. For updates, integrate upstream changes into the fork if needed, resolve conflicts, and test before publishing authorized changes and advancing this repository's pin. Keep installed configuration and both documentation files synchronized. Offer useful fixes upstream with user authorization, and consider dropping a fork once upstream provides the needed behavior.

Maintenance happens on request. Automatic monitoring or scheduled updates require separately configured and authorized automation.
