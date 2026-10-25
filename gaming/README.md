# Desktop Gaming Mode

Install explicitly with `./install-gaming-mode.sh`, or select `install-gaming-mode.sh`
in the feature profile used by `./install-all.sh`. Dependencies are Steam,
Wallpaper Controller and its Hyprland configuration. The safe base does not
implicitly enable this feature; successful explicit installation records a local choice.
No scheduler, storage, resolution-reduction, global Steam launch options or game files
are modified. This is a companion service, not a shell plugin requiring a separate repo.

## Enter and exit

- Launch a game from Steam (desktop or Big Picture), Lutris, or a Steam-backed Omarchy
  game entry. The service checks runtime signals every second and activates automatically.
  Installing a new game does not require another installer run or launch-option edit.
- Steam's `SteamAppId`/`SteamGameId` process environment markers and Lutris's `GAME_NAME`
  marker identify game processes. Lutris sets its marker in `configure_game()` for all
  supported runners, including native Linux games. A valid `steam_app_ID` window is a
  fallback for games that clear environment markers.
- Big Picture, the Steam client and the Lutris client alone do NOT enable Gaming Mode.
  `gaming-mode big-picture` still opens Big Picture for convenience; selecting a game
  activates mode. No controller settings or Home-button interception are required.
- Mode remains active while any detected game is running, regardless of focus, launch
  path, which client is visible, or whether Big Picture closes. Three consecutive absent
  samples (about three seconds) after the last game exits restore the desktop.
- Known lingering Wine services, Steam/Lutris UI processes, shader-precache workers and
  Wallpaper Engine (Steam app 431960) are ignored so they do not hold the mode on.
- Detection reads only the current user's `/proc` entries, bounded to 256 KiB per
  environment, retaining only game markers/session ID. It neither logs nor persists full
  environments or credentials, and needs no root access, input grants or per-game scripts.
  Explicitly different Hyprland sessions are ignored when the marker is present.

Limitations: launchers/helper processes inheriting game markers can extend mode until they
close. A nonstandard game that clears both markers and its Steam window class cannot be
identified automatically; report that game so an explicit lifetime integration can be added.
If `/proc` environment access is restricted, Lutris detection can be incomplete. This covers
standard Steam/Lutris launches, not arbitrary executables started outside either client.
The optional launcher below also provides a lifetime lease but is NOT needed for detection.
No game list, filesystem scan, log-history guess or Steam VDF rewrite drives activation.

## Selective widget pause

At game entry, Gaming Mode temporarily unloads three reviewed, independent desktop overlays
through supported `omarchy plugin disable` commands: System Metrics, Weather and Immich
Photo Frame. Their QML services/windows are destroyed by the shell, stopping their timers
and refresh processes rather than merely hiding the cards. Quickshell itself, the bar,
notifications, lock/idle services, Home Assistant and unrelated plugins remain enabled.
No plugin source, pin or third-party repository was modified.

Only widgets enabled at entry are recorded in the private recovery journal **before** any
side effects. Exit/service stop reenables those still present/disabled; originally disabled
widgets remain disabled, removed plugins stay removed, and manually resumed widgets need
no change. Existing pin/autohide settings, credentials and widget configuration are not
rewritten. This is an unload/reload, not an exact animation or photo-timestamp resume;
re-enabling may refresh API/cache data. Qt may retain cached graphics allocations.

The optional `pausePlugins` list in `~/.config/omarchy/gaming-mode.json` overrides the default:

```json
"pausePlugins": [
  "priyesh.system-metrics",
  "priyesh.weather-widget",
  "priyesh.immich-photo-frame"
]
```

Use `"pausePlugins": []` to keep all widgets active, or a subset of the reviewed IDs above.
Other IDs, including core/bar/lock services, are rejected before any side effects. Restart
`arch-gaming-mode.service` after configuration changes. Stop Gaming Mode before manually
changing paused plugins' enable/disable lifecycle: a manual disable while already disabled
cannot be distinguished from our temporary disable. The enable flags are temporarily
persisted by Omarchy; a recovery journal restores them after a crash/service restart. If
shell IPC is unavailable, restoration errors retain the journal rather than claiming success.
Do not remove the service/config/state while a recovery journal remains unresolved.

This is a reversible first-stage experiment, not a proven major FPS optimization. The
[controlled pause report](../docs/reports/quickshell-selective-pause-20261025-123909.md)
found modest memory savings but no meaningful graphics-load improvement from these three
widgets; the major remaining rendering load was not identified conclusively.

## Effects and restoration

`~/.config/omarchy/gaming-mode.json` selects the monitor by connector or `desc:...`.
Installation seeds it once from the focused display. `restoreVrr` is the normal desktop
VRR policy (0=off, 1=always, 2=fullscreen); the seed uses current active VRR as 0/1,
so set this explicitly if your normal policy is conditional. During Gaming Mode it is 1.
The display must support Adaptive Sync and have it enabled in its OSD. OLED VRR can
flicker. Software cannot guarantee actual panel operation; inspect `hyprctl monitors -j`.

Quattro monitor calls replace complete rules. The service carries forward live resolution,
refresh, position, scale, transform, 8/10-bit format, color preset and SDR luminance settings,
and restores only VRR on exit. Other monitors are not changed. This targets Omarchy's
preset-based monitor configuration; custom ICC profiles, mirrored outputs and manual HDR
metadata overrides are not supported by this snapshot mechanism. Do not enable it for
such configurations without extending and testing the preservation contract first.

Wallpaper Controller's supported `stop` blocks automatic rotation/recovery. The service
records the active selection before stopping and uses `apply ID` on exit only if the
selection is still unchanged and disabled. Already stopped/no-selection wallpapers stay
stopped. This restarts rather than resumes the animation timestamp and may refresh Aether.
A manual wallpaper selection during gaming relinquishes restoration ownership and can
restart wallpapers; avoid changing wallpapers while testing performance. A manual Stop
while already stopped is indistinguishable from Gaming Mode's stop.

A private recovery journal lives under `~/.local/state/omarchy/gaming-mode/`. It is written
before side effects; graceful service stop restores settings. Restart recovers the journal
before detecting running games again. If restoration fails it is retained and errors go to
the journal. A disconnected gaming monitor may require reconnecting before cleanup.
There is no change to the package-managed Hyprland entrypoint or persisted monitor files.

## Gamescope (per-game opt-in)

The desktop service cannot move an already-running Steam process into Gamescope. It does
not restart Steam or rewrite your library. For an ordinary Steam game, set Launch Options:

```
gaming-mode run -- %command%
```

For explicit HDR:

```
gaming-mode run --hdr -- %command%
```

Both use native main-monitor render/output dimensions and refresh, not a 1440p upscale.
The main monitor is focused before launch. HDR remains opt-in; no FPS cap, frame generation,
forced tearing or GameMode/scheduler tuning is added. Nested Gamescope uses the Wayland
backend; host Hyprland controls panel VRR. This is NOT a standalone Gamescope login session
and doesn't remove desktop compositor overhead. Compare against unwrapped launching.
Steam's overlay preload is removed for Gamescope; unrelated preloads are preserved.

Do not stack this with `steam-gamescope-hdr` or another Gamescope wrapper. Existing games
using that HDR helper can retain it: runtime game detection still enables desktop mode.
For Lutris use the command prefix `gaming-mode run --` only where no other wrapper is set.
Native Wayland game compatibility, HDR output, Steam overlay and controller/mouse capture
must be verified per game; remove the launch option if a game misbehaves.

## Controls, updates and removal

- `gaming-mode status`
- `systemctl --user status arch-gaming-mode.service`
- `journalctl --user -u arch-gaming-mode.service -n 50`
- `./install-gaming-mode.sh --disable` (restores desktop; records disabled choice)
- `./install-gaming-mode.sh --enable`
- `./install-gaming-mode.sh --remove` (backs up managed paths, removes helper/unit,
  preserves configuration/state; remove any per-game launch options first)
- Update by rerunning the installer from an updated setup checkout. Unchanged installs
  report `already installed`; changed owned files are backed up before deployment.

## Verification

Run `python3 -m unittest discover -s gaming -p 'test_gaming_mode.py'` for fixture tests.
On hardware verify: actual Steam/Lutris game launch and closure from each entry point,
Big Picture alone remaining inactive, overlapping games, client crash with a game still
running, service stop/restart, already-stopped wallpaper, and unchanged 4K/120Hz,
scaling, HDR and secondary monitors before/during/after. Inspect frame times separately;
installation is not evidence of better performance. Do not claim controller/HDR or a
particular game's lifecycle acceptance based on fixtures alone.

### Local acceptance recorded during implementation

- Initial mode used Big Picture detection; that trigger has now been replaced by runtime
  game detection. The original live test verified wallpaper/VRR restoration with unchanged
  3840×2160 at 119.999Hz, scale 1.5, HDR and secondary displays. Service stop during an
  installer update also restored state. This is historical display-lifecycle evidence, not
  acceptance of the replacement detector on every actual game.
- Twenty-one Gaming Mode fixtures pass, covering widget ownership/restoration, partial
  pause failure, rejected essential IDs, plugin-catalog semantics, Steam/Lutris markers, arbitrary newly
  installed game IDs/names, Big Picture not triggering, multiple games, ignored background
  processes, other users/sessions, transient `/proc` entries, environment privacy, and
  existing recovery behavior.
- Live replacement-detector checks used harmless `sleep` processes carrying standard Steam
  and Lutris markers (not actual games). An arbitrary Steam marker activated mode with no
  Big Picture or game window. An overlapping Lutris marker retained mode after the first
  process exited. Last-process exit restored the original wallpaper and VRR; 4K/120Hz,
  HDR, scaling, positions and secondary displays remained unchanged. These checks verify
  runtime wiring/restoration, not every game's marker behavior or game performance.
- Native-resolution Wayland-nested Gamescope ran `vkcube --wsi xcb` on RADV RX 6800,
  both with Big Picture and through the game-lifetime launcher without Big Picture.
  Gamescope exited successfully. This is a Vulkan smoke test, not a game benchmark
  or an HDR-content/physical-controller acceptance result.
- Repeated unchanged installation reported `Gaming Mode already installed`.
- Still pending: actual games' controller/cursor/overlay behavior, HDR content,
  unplug/replug lifecycle, forced service-crash recovery, and measured frame-time
  improvements. Controller Guide-button handling is Steam's normal behavior and is
  independent of runtime Gaming Mode detection.

- Live selective-pause checks verified automatic unloading of the three widget surfaces,
  preservation of every unrelated plugin enable flag and Quickshell PID, and restoration
  of the original plugin flags/settings/wallpaper/display layout. All 43 lock/screensaver
  checks were clear during the six-condition experiment. This remains a no-game resource
  test, not a frame-time acceptance test.

## Gaming-aware decorative media animation

The pinned Shibumi fork consumes the version-1 Gaming Mode journal using one shared,
event-driven watcher. Only the decorative media bars stop; playback and controls are
not paused. Set `"pauseDecorations": false` in `~/.config/omarchy/gaming-mode.json`
and restart the service to opt out. This is independent of `pausePlugins`.
Missing/malformed/unsupported/foreign-session hints leave normal animation enabled.
The hint is a presentation signal, not a command to suspend Quickshell.

When G9 is visually hidden, the center notch still requires an explicit hidden
`hancore.shibumi.media` service entry. `config/shibumi-settings.py` reconciles this
without placing a second media widget in the bar; `--media-backend-only` repairs
that demand without applying monitor/presentation preferences.

The [live controlled validation](../docs/reports/quickshell-visualizer-validation-20261025-173529.md)
used a user-approved silent MPRIS fixture: shell CPU was about 8.97% of one logical
core with the loop running versus 0.47% paused; AMD graphics-engine occupancy was
about 17.50% versus 0.01%. Reenabling reproduced the workload. All 25 display checks
were unlocked, and desktop/plugin state restored. This proves lower rendering
overhead in that desktop scene, not real-audio acceptance, reclaimed VRAM or higher
game FPS. An actual Halo session also activated the observer automatically and its
exit cleared the pause. Historical full host-qualification gates remain blocked;
see the report for the exact scope and excluded initial run.

## Cyberpunk benchmark preparation (not activation)

Run `./install-gaming-mode.sh --prepare-benchmark` to generate a private, idempotent
logging profile and proposed child-only prefix under
`~/.local/state/arch-setups/benchmarks/cyberpunk/` (honors `XDG_STATE_HOME`).
This does not launch a game, restart Gaming Mode, edit Lutris/Steam launch settings,
or change graphics settings. The profile keeps the HUD hidden, disables uploads,
adds no FPS limiter, and requests per-frame CSV logging (`log_interval=0`).
**Left Shift + F2** toggles logging once the profile is actually activated.

Activation remains a deliberate next step with games/Lutris closed: privately back
up the exact Cyberpunk YAML, preserve its existing Gamescope options, and enable
MangoHud only in Gamescope's child. Never wrap the compositor or add a second
Gamescope. Audit inherited MangoHud settings first and retain any intentional FPS
limiter identically in both conditions. Restore the original YAML after testing.
Use identical graphics settings, a warm shader cache and repeated alternating
built-in benchmark runs; exclude loading/menu frames. A prepared profile is not
proof of successful layer injection or recorded game frame times.

## Quickshell resource baseline

The [unlocked resource report](../docs/reports/quickshell-usage-20261025-121057.md)
compares the existing desktop and Gaming Mode without a real game or pausing Quickshell.
All 32 sampled lock/screensaver checks were clear. The shell's CPU and memory use were
essentially unchanged; significant graphics-engine activity remained. This supports a
selective widget-pause experiment, not a claim of measured FPS gains. Raw samples and
methodology accompany the report; earlier uncertain-lock/aborted runs are excluded.
