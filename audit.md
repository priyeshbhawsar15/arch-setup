# Project audit: arch-setups

Reviewed 12 October 2026, repository commit `93f63ed`, installed Omarchy `4.0.4-1`.

**Archived review:** This report was restored from the original review in the chat after its temporary file disappeared. Findings describe the state reviewed at commit `93f63ed`; subsequent repository and desktop changes have not been re-audited here.

**Assessment:** The repository has a sensible foundation, but its “one command restores my setup” goal is only partially achieved. There are confirmed data-loss paths, fresh-install blockers, incomplete plugin disable/removal behavior, and differences between the running desktop and the committed configuration. Repair these before trusting an unattended rebuild. A wholesale rewrite is unnecessary.

This was a read-only review of the repository, relevant installed plugin sources at the pinned revisions, packaged command implementations, and selected live status. Reproductions used temporary fixtures and mocks. No installers, plugin lifecycle mutations, display reloads, package installations, or device-changing Home Assistant actions were run against the real desktop. No credential values are included.

**What is implemented well**

- All 30 installers are registered in the entrypoint, including the separately invoked dotfiles installer. Every one of the 36 shell files is named in `SCRIPTS.md`.
- The explicit installer ordering and stop-on-failure behavior are easy to follow. [install-all.sh](/home/priyesh/Work/arch-setups/install-all.sh:7) is a good orchestration starting point.
- The setup keeps Zsh/Neovim and other tool configuration in the separate dotfiles repository, rather than duplicating those configurations.
- Most plugin installations pin exact commits, verify the origin and revision, validate manifests, and refuse to overwrite dirty Git checkouts.
- All 12 installer plugin pins found by the audit are recorded in `PLUGINS.md` and match the installed HEAD revisions. Eleven of those installed worktrees are clean; hyprmoncfg has a pre-existing modified `BarWidget.qml`.
- Ordinary application installers mostly use the appropriate Omarchy package/browser routes. Current package metadata supports the Hermes, Sunshine, and T3 package routes.
- Most original widget QML uses dynamic `Color`/`Style` tokens. The inspected desktop widgets implement Bottom/Overlay pinning, persistent settings, edge masks, reveal handles, and the specified collapse timing.
- The Home Assistant installer has stronger lifecycle handling than many peers: a pinned runtime dependency, protected local credentials, seed-only configuration, transport shutdown, and a clean-checkout guard. These source-level protections are good; no fresh-machine or physical-device acceptance claim is made here.
- The existing 18 repository tests pass, and the source syntax checks pass. These tests provide useful coverage for CLI wrappers and selected Steam configuration behavior.

Priority definitions: **P1** means a rebuild blocker, destructive configuration change, or broken application launch; **P2** means a broken feature/lifecycle or material reproducibility gap.

**P1 findings to repair first**

1. **Dotfiles deployment can erase working configuration before discovering a Stow conflict.**

   [install-dotfiles.sh](/home/priyesh/Work/arch-setups/install-dotfiles.sh:30) removes existing non-symlink Neovim, Starship, tmux, and Zsh targets with `rm -rf`, then runs Stow at line 53. A temporary fixture with valid dotfiles packages and an unrelated `.zprofile` conflict made Stow fail after all four original targets had disappeared. No backups were created.

   Move existing targets into a unique backup directory, validate the package set and conflicts, then deploy with restoration on failure. Check for the sibling dotfiles checkout before the application installers start. Existing symlinks should also be verified to point to the intended repository.

   [install-hyprland.sh](/home/priyesh/Work/arch-setups/install-hyprland.sh:99) has a related P2 problem: it backs up legacy `.conf` files, but overwrites changed personal Lua modules/helpers and SDDM configuration without backing up those destinations.

2. **Shibumi modifications invalidate the suite’s installation identity and prevent normal lifecycle operations.**

   [install-shibumi-shell.sh](/home/priyesh/Work/arch-setups/install-shibumi-shell.sh:139) replaces transaction-managed QML after upstream installation. Its subsequent status call at line 247 fails because the payload no longer matches the recorded identity. The installed suite’s read-only status command exits 1. Direct preflight identified `hancore.shibumi.bar` as the mismatch; the computed payload digest differs from the recorded digest.

   A fresh run performs these same overwrites before its final status call, so the entrypoint stops there. Activate, deactivate, and uninstall also use the admission checks. The “already installed” path skips status and conceals the damaged lifecycle. The identity check is visible in the [pinned upstream admission code](https://github.com/HANCORE-linux/Shibumi-Shell/blob/7a6c853b1947d303bad9a5b640c224c01b669106/scripts/shibumi_suite/admission.py).

   Maintain the customized source in a separate fork/custom suite and install its reviewed payload through the supported lifecycle. Do not merely remove the status check or rewrite the recorded hashes. Preserve the current customization during migration, then test fresh install, repeat install, status, disable, re-enable, and removal.

   This also resolves a repository-policy violation: [PLUGINS.md](/home/priyesh/Work/arch-setups/PLUGINS.md:55) describes Shibumi as unmodified with no copied source, while `shibumi/` actually maintains thousands of lines of source overrides.

3. **The hyprmoncfg dependency uses the wrong package source.**

   [install-hyprmoncfg.sh](/home/priyesh/Work/arch-setups/install-hyprmoncfg.sh:202) requests `hyprmoncfg` through `omarchy pkg add`, which routes to the regular pacman repositories. Read-only `pacman -Si hyprmoncfg` returned “package not found”; a mocked missing-command installation reproduced failure at this call.

   Use `omarchy pkg aur add hyprmoncfg-bin` for a missing binary, retaining an already installed supported variant. This matches the [official installation guide](https://hyprmoncfg.dev/getting-started/) and the pinned plugin’s README. Also reproduce daemon activation: this installer never enables/starts `hyprmoncfgd`, although automatic hotplug/lid layout switching depends on it.

4. **Omaland’s menu insertion writes invalid JSON, and removal can delete unrelated entries.**

   The existing-menu branch in [install-omaland.sh](/home/priyesh/Work/arch-setups/install-omaland.sh:149) omits the outer closing quote of an action string. Running the actual function against a valid temporary menu exited 0 but left JSON that failed parsing. Wallpaper Controller and Lock Explorer normally create the menu before Omaland, making this a relevant installation path.

   Its [removal logic](/home/priyesh/Work/arch-setups/install-omaland.sh:168) deletes every line containing `"style.hyprland`. A separate fixture confirmed that an unrelated `style.hyprland.custom` entry was deleted. Line-based deletion can also damage formatted object structure.

   Replace these edits with an owned-key merge/removal helper that supports the menu’s JSONC format, preserves other entries, validates the generated document, and replaces it atomically after backup.

5. **Lutris synchronization overwrites user settings and assumes an initialized user database.**

   [sync-lutris-steam.py](/home/priyesh/Work/arch-setups/steam/sync-lutris-steam.py:139) builds a partial game configuration and writes it over an existing YAML file at lines 151–154. A temporary existing-game fixture lost a custom working directory, gamemode preference, environment variable, and Steam runner settings. There is no backup or merge.

   [install-lutris.sh](/home/priyesh/Work/arch-setups/install-lutris.sh:19) also invokes this synchronizer before initializing Lutris’s directories/schema. With one installed Steam-game fixture and fresh user-data directories, installed Lutris 0.5.22-2 raised “unable to open database file”; after creating its directory, it raised “no such table: service_games.” An empty new Steam library does not trigger this path.

   Initialize the application’s user state through supported Lutris functionality, merge only managed fields, back up changed YAML, and avoid database/file writes while Lutris is actively using them. Cover both a blank machine and a populated library in tests.

6. **Steam launch-option rewriting breaks common existing options.**

   [configure-gamescope-hdr.py](/home/priyesh/Work/arch-setups/steam/configure-gamescope-hdr.py:204) turns argument-only `-novid -dx11` into `-novid -dx11 steam-gamescope-hdr %command%`, placing arguments before the executable. Preserve such arguments after the wrapped command.

   The [VDF regex](/home/priyesh/Work/arch-setups/steam/configure-gamescope-hdr.py:218) cannot parse escaped quotes. A quoted-value fixture produced duplicate `LaunchOptions` entries and a default-only replacement. Use a VDF-aware parser and correct escaping, or leave unsupported input unchanged with an actionable message.

   The [installed-game scan](/home/priyesh/Work/arch-setups/steam/configure-gamescope-hdr.py:166) also ignores secondary Steam libraries. A fixture referenced through `libraryfolders.vdf` produced no discovered games. Enumerate all available library locations.

**P2 lifecycle and reproducibility findings**

7. **Weather updates abort on an undefined variable.**

   [install-weather-widget.sh](/home/priyesh/Work/arch-setups/install-weather-widget.sh:91) uses `$stage` inside the existing-checkout update function, where only `$plugin_dir` is available. A mocked update reproduced exit 1 with `stage: unbound variable`. The error occurs after checkout, so a failed update can already have changed the installed revision.

   Correct the directory reference, preserve submodule failures, and validate updates before replacing a working deployment. Share the repeated checkout/update logic through `lib.sh` so this copy/paste defect cannot recur independently across installers.

8. **Disabling hyprmoncfg does not stop display management.**

   [install-hyprmoncfg.sh](/home/priyesh/Work/arch-setups/install-hyprmoncfg.sh:163) disables the shell UI and restores a bar widget, but never calls `hyprmoncfg unmanage`. The current daemon is enabled and active. The [official panel guide](https://hyprmoncfg.dev/omarchy/) explains that management-off returns display configuration ownership.

   Back up management state and use the supported management-off lifecycle when disabling/removing this feature. Re-enabling should restore management intentionally, without losing saved profiles.

9. **Feature disable flows can change unrelated bar layout.**

   [install-per-monitor-workspaces.sh](/home/priyesh/Work/arch-setups/install-per-monitor-workspaces.sh:217) restores Shibumi’s workspace widget and removes the stock widget regardless of which bar is active. An isolated stock-bar fixture confirmed that disabling an absent feature replaced `omarchy.workspaces` with `hancore.shibumi.workspaces`.

   [install-hyprmoncfg.sh](/home/priyesh/Work/arch-setups/install-hyprmoncfg.sh:123) similarly inserted Shibumi’s brightness widget into a stock-bar fixture.

   [install-calendar.sh](/home/priyesh/Work/arch-setups/install-calendar.sh:113) replaces the whole center section on enable; [its disable path](/home/priyesh/Work/arch-setups/install-calendar.sh:130) always restores Shibumi’s center, discarding other center widgets and assuming Shibumi still exists.

   Store the previous owned slot/settings, verify that the feature still owns them, and restore only those changes. Gate Shibumi-specific operations on the active bar and installed dependencies.

10. **The current display setup is not fully reproduced by the repository.**

    The live [Hyprland entrypoint](/home/priyesh/.config/hypr/hyprland.lua:31) includes an additional generated monitor block and then loads the generated monitor rules again at line 40. This integration is absent from the setup repository and conflicts with its package-managed-entrypoint rule.

    The generated configuration specifies 60 Hz and SDR brightness 1.75 for the main display; the [managed module](/home/priyesh/Work/arch-setups/hypr/monitors.lua:10) specifies 120 Hz and 1.0. Read-only live monitor output confirmed the generated settings are active. Generated numeric workspace assignments also remain present while the per-monitor named-workspace feature suppresses those assignments in the managed module.

    Choose one owner for monitor rules, reproduce its supported service/profile integration, and resolve load-order conflicts through personal modules. The duplicate generated include follows the single-monitor override; its live effect on toggling was not exercised.

11. **The window-span shortcut is incompatible with the committed layout.**

    [window-span-dp6-dp4-toggle.sh](/home/priyesh/Work/arch-setups/hypr/scripts/window-span-dp6-dp4-toggle.sh:125) requires DP-6 and DP-4 to be adjacent with equal logical heights. The current and committed arrangement puts DP-5 between them, and gives DP-6 height 1440 while DP-4 has height 1920.

    A geometry fixture exited 1 before any dispatch. The [shortcut](/home/priyesh/Work/arch-setups/hypr/bindings.lua:37) remains installed. Redesign the requested span for the current arrangement or remove the obsolete helper/shortcut and corresponding documentation.

12. **The custom indicators are not independently reproducible or lifecycle-managed.**

    [install-shibumi-shell.sh](/home/priyesh/Work/arch-setups/install-shibumi-shell.sh:175) copies `priyesh.indicators`, but no installer enables/configures it in a fresh shell layout or removes it. The running machine contains a manually existing bar entry. Upstream suite removal handles its own `hancore.shibumi.*` inventory, so this custom plugin remains outside that cleanup.

    The copied plugin also changes its [IPC target](/home/priyesh/Work/arch-setups/shibumi/Indicators.qml:169), while the packaged reminder command refreshes `omarchy.indicators`. The reminder component lacks polling, so its count can remain stale. Its [clone metadata](/home/priyesh/Work/arch-setups/shibumi/Indicators.manifest.json:7) places `clonedFrom` at the root instead of the current `.omarchy.clonedFrom` location.

    Give this original customization its own repository, pin, installer, layout integration, documentation, and removal behavior. Preserve supported built-in IPC/clone metadata where the feature depends on them.

13. **Calendar restoration omits its sync infrastructure and actual backup paths.**

    The pinned calendar widget requires separate Google synchronization setup; installing the widget alone yields a clock and an empty calendar. The installer does not reproduce its timer/service setup or describe the required `gws`/`gcloud` OAuth preparation.

    [disable/remove](/home/priyesh/Work/arch-setups/install-calendar.sh:147) does not stop an existing sync timer. Removing the source can leave units referring to a deleted checkout. Its [backup list](/home/priyesh/Work/arch-setups/install-calendar.sh:160) misses the actual `calendar-events.json` state file, `calendar-sync.json` config, and bar presentation settings.

    Reproduce non-secret infrastructure, document the account-authentication step, manage the timer lifecycle, and back up actual paths. Do not publish OAuth credentials.

14. **The pinned Weather widget displays fabricated readings on failure and selects past forecast hours.**

    In the separate pinned plugin source, [weather-widget](/home/priyesh/.config/omarchy/plugins/priyesh.weather-widget/bin/weather-widget:155) handles an API error by producing 27°, 80% humidity, rain, and three invented forecasts. [WeatherCard.qml](/home/priyesh/.config/omarchy/plugins/priyesh.weather-widget/WeatherCard.qml:17) displays these fields without checking error status.

    A mocked offline request reproduced those values. Preserve the last valid readings with an explicit stale timestamp, or display unavailable state.

    Its [forecast indexing](/home/priyesh/.config/omarchy/plugins/priyesh.weather-widget/bin/weather-widget:123) falls back to midnight whenever the current timestamp does not exactly match an hourly timestamp. A 14:15 fixture produced 03h/06h/09h forecasts; a 14:00 fixture correctly produced 17h/20h/23h. [Open-Meteo’s documentation](https://open-meteo.com/en/docs) confirms current conditions use 15-minute timestamps. Select the appropriate hour by time comparison rather than exact string membership.

    Implement these changes in the dedicated Weather plugin repository, test and publish the reviewed change, then update the setup pin and both documentation entries.

15. **OmniRoute’s configured token file is readable by other local users.**

    [install-omniroute-quota.sh](/home/priyesh/Work/arch-setups/install-omniroute-quota.sh:97) creates the config without restricting its mode. The current config is mode `0644` and contains a configured token; only the presence of a token was checked, never its value printed.

    Enforce `0600` on both seeded and existing credential-bearing configs, and use private backup directories. The Immich installer already follows the tighter config-file pattern.

16. **“Already installed” often checks presence instead of the complete managed state.**

    The Metrics and Quota installers skip their install hooks once the checkout matches and the plugin is enabled, so a missing helper link is not repaired. Wallpaper Controller’s [fast path](/home/priyesh/Work/arch-setups/install-wallpaper-controller.sh:200) likewise ignores missing helper/menu/toggle artifacts.

    [install-steam.sh](/home/priyesh/Work/arch-setups/install-steam.sh:30) only repairs wrapper permissions when contents differ; a matching mode-0644 fixture stayed nonexecutable while installation succeeded.

    [install-tailscale.sh](/home/priyesh/Work/arch-setups/install-tailscale.sh:8) exits on package presence and does not repair a disabled service. [install-keyd.sh](/home/priyesh/Work/arch-setups/install-keyd.sh:17) replaces configuration and enables an already running service without reloading it.

    Separate package-presence checks from integration reconciliation. Check managed contents, executable modes, symlink destinations, services, settings, and layout/shortcut artifacts before declaring the feature current.

17. **Omaland can modify the protected Hyprland entrypoint.**

    The matching pinned plugin targets [hyprland.lua](/home/priyesh/.config/omarchy/plugins/bobbynicholas.omaland/Panel.qml:30) and writes it for its full-opacity rule at [line 249](/home/priyesh/.config/omarchy/plugins/bobbynicholas.omaland/Panel.qml:249). The setup documentation describes only `looknfeel.lua`, and its backup list misses the real Hyprland destinations.

    Prefer a supported output-path setting; otherwise maintain a dedicated fork that writes personal rules into the allowed module. Verify that editor apply/reset leaves the package-managed entrypoint unchanged.

**Recommended improvement sequence**

1. **Protect existing data:** repair dotfiles/Lutris destructive paths, add backups for changed personal configuration, repair exact menu-key ownership, and enforce credential permissions.
2. **Make a fresh install finish:** correct the hyprmoncfg package/service route, install a lifecycle-compatible Shibumi fork, initialize Lutris user state, and fix Omaland serialization.
3. **Make feature lifecycle reliable:** test every plugin with install → repeat → disable → repeat disable → re-enable → remove. Verify owned processes, timers, shortcuts, menu entries, and layout restoration.
4. **Reconcile desktop ownership:** unify monitor policy, remove unmanaged entrypoint changes through supported integration, and reproduce indicators/calendar infrastructure.
5. **Reduce maintenance duplication:** keep thin per-feature installers, move shared Git checkout/validation/backups/config-edit functions into `lib.sh`, and retain feature-specific hooks.
6. **Add a preflight and read-only doctor:** check unlocked desktop/session availability, supported Omarchy/Quickshell versions, dotfiles packages, private-repository access, needed external assets, and credential-file presence without printing secrets. A doctor should explain each mismatch between declared and deployed state.
7. **Record intended feature state:** keep a simple desired enabled/disabled profile so a rebuild reproduces the chosen setup. Current no-argument installers explicitly re-enable features; this is documented behavior, but `install-all.sh` does not preserve an independently chosen disabled state.
8. **Consolidate configuration:** define main/left/right display identities in one place. The standalone Lock Explorer installer still restores old connector assignments that the final monitor-layout installer corrects. Hardcoded account paths and output names are acceptable personal defaults, but should derive from explicit configuration where practical.
9. **Improve documentation accuracy:** correct the “unmodified Shibumi” claim, stale monitor mappings, indicators ownership, calendar requirements/backups, Omaland write locations, and stale verification prose referencing `/tmp` screenshots. Put repeatable acceptance procedures alongside the relevant plugin sources.
10. **Add targeted automated coverage:** prioritize meaningful temporary-environment tests for data preservation, fresh state, interrupted updates, JSONC merging, and lifecycle isolation. Add a CI check for installer registration, shell-file documentation coverage, and consistency between pins and docs. ShellCheck is a useful addition; it was unavailable during this audit.

Exact application versions are a policy choice: package/AUR installers and unversioned mise tools currently restore selected applications rather than identical historical builds. Document the supported base versions and make tool upgrades intentional if stronger reproducibility is desired. A full Arch snapshot mechanism is unnecessary unless identical historical environments are a real requirement.

**Verification evidence and limits**

These results are from the original audit, not new verification of the current working tree.

- `bash -n`: all 36 shell files passed.
- Python compile checks: all seven repository Python files passed.
- `luac -p`: all five managed Lua modules passed.
- Existing tests: GitHub 9/9, T3 5/5, Steam 4/4; 18/18 total.
- Read-only `hyprctl -i 0 configerrors`: empty, as reported by the monitor audit. This means the configuration running at the time parsed; it does not prove fresh deployment or behavior.
- All eight installed `priyesh.*` manifests inspected with the Omarchy validator passed. Manifest validation does not validate runtime behavior.
- Selected pinned installed source and dependency implementation checks; documented Git revision checks and safe status/service queries.
- Temporary reproductions confirmed the destructive dotfiles and Lutris cases, Lutris fresh-database errors, Steam option/parser/library issues, stock-bar disable side effects, span geometry rejection, Omaland menu errors, Weather update failure, and inaccurate Weather output.
- The original audit left the repository unchanged. No physical lock/wake, widget visual, theme-change, hotplug/suspend, GPU/HDR game launch, authenticated calendar, or complete fresh-machine end-to-end acceptance run was performed.
- Source links and line numbers refer to the files reviewed; later changes can move lines or resolve findings.

The next implementation batch should focus on data preservation and rebuild blockers, with regression coverage. Preserve the existing modular design while making the install and lifecycle contracts verifiable.

