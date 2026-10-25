# Selective Quickshell widget-pause experiment

## Outcome

Automatic widget unload/restoration works, but these three widgets are **not a demonstrated solution to the remaining graphics load**. Pausing all three reduced mean Quickshell RSS by about 57 MiB and charged resident VRAM by about 33 MiB in this trial. CPU differences were small; graphics-engine occupancy did not improve. No actual game or frame-time benchmark was run, so no FPS/stutter improvement is established.

## Implemented behavior

The Gaming Mode service temporarily disables enabled System Metrics, Weather and Immich Photo Frame plugins through supported Omarchy controls. Disabling destroys their QML service/window instances instead of merely hiding them. A private recovery journal records the original enabled IDs before changes. Game exit, service stop or recovery restores the originally enabled widgets; already-disabled/missing plugins stay disabled/missing. Core/bar/lock IDs cannot be selected. No plugin source or pins were changed.

Bar, notifications, lock/idle, Home Assistant and unrelated plugins remain enabled. Configuration, credentials, pin/autohide preferences and game launch options are untouched. Set `"pausePlugins": []` in `~/.config/omarchy/gaming-mode.json` and restart the service to opt out, or select a subset of the three reviewed IDs. Avoid manually changing paused plugins' lifecycle during gaming: a second disable while already disabled cannot be distinguished from the temporary disable.

## Controlled design

- Host: i3-12100 (8 logical CPUs), RX 6800, native 4K/120Hz main display plus two secondary displays.
- Quickshell PID 1014425 remained the same. Sample window: 25 October 2026, 12:39:19 to approximately 12:42:25 IST.
- All six conditions kept Gaming Mode active: wallpaper stopped and main-monitor VRR enabled. Thus the comparison changes widget state, not wallpaper/VRR.
- Controls with all widgets enabled bracketed three individual pauses and a combined pause. Controls and combined pause used 30 seconds; individual conditions used 20 seconds. Approximately 1 Hz sampling, six-second settling periods: 150 total intervals.
- All 43 sampled lock/screensaver checks were clear. The user's existing stay-awake setting was not changed. No game was launched and media playback was not paused.
- The service automatically unloaded the three widgets at entry. Their enable flags were false and their layer surfaces disappeared. For the control conditions the test temporarily resumed them, retaining the journal so the service could restore the original state on exit.

## Measurements

CPU percentages use 100% = one logical CPU, not the whole processor. GPU percentages are graphics-engine nanosecond deltas divided by elapsed time, not lost FPS or full-speed GPU throughput. GPU clocks/power states were not controlled.

### Matched control vs all three paused

Controls combine 60 intervals; the combined-pause condition has 30:

- Main Quickshell CPU: **10.83% → 10.26% of one core** (−0.57 percentage points). Individual control means were 10.53% and 11.13%; these short samples do not establish statistical significance.
- Shell plus observed/reaped child CPU: **24.08% → 22.36% of one core** (−1.72 percentage points). Independently launched/orphaned services may not be represented.
- AMD graphics-engine occupancy: **18.30% → 19.28%** (+0.99 percentage points). There is no measured graphics improvement.
- Resident RAM/RSS: **1,006 → 948 MiB** (approximately −57 MiB).
- Charged resident AMD VRAM: **1,045 → 1,012 MiB** (approximately −33 MiB). Accounting includes shared buffers, so this is not a wholly private/reclaimable allocation estimate.

### Individual condition means

- Control before, 30 seconds: shell CPU 10.53%; AMD gfx 18.32%.
- System Metrics paused, 20 seconds: shell CPU 10.90%; AMD gfx 20.58%.
- Weather paused, 20 seconds: shell CPU 10.80%; AMD gfx 17.20%.
- Immich paused, 20 seconds: shell CPU 12.05%; AMD gfx 16.96%.
- All three paused, 30 seconds: shell CPU 10.26%; AMD gfx 19.28%.
- Control after, 30 seconds: shell CPU 11.13%; AMD gfx 18.27%.

These are short, single-pass, non-randomized conditions. Recreating widgets can refresh data and warm caches. Animation, media content, compositing and GPU clock state were not held perfectly constant. Do not rank widgets or claim additive GPU savings from this trial.

## Lifecycle and safety checks

Passed on this host:

- Automatic pause journal contained exactly the three reviewed widgets.
- Paused widget surfaces disappeared; no whole-Quickshell restart occurred.
- Every unrelated plugin enable flag remained unchanged.
- Original plugin enable flags were restored after the marker process exited.
- Widget configuration/settings hashes were unchanged, including pin/autohide configuration.
- Wallpaper, display layout, resolution, refresh, HDR and scaling were restored/preserved.
- No lock/screensaver appeared at the 43 sampled checks. Lock IPC stayed responsive; an actual authentication or notification-delivery test was not performed.

Unit coverage additionally checks already-disabled widgets, partial-pause rollback, recovery-journal retention on restoration failure, manually resumed/removed widgets, rejection of essential IDs and the plugin catalog's bar-only `active` flag. There are 21 passing Gaming Mode fixtures. This does not simulate every possible power-loss/uninstall race.

## Remaining investigation

After the trial, Chromium reported MPRIS `PlaybackStatus=Playing`. The installed Shibumi bar's `NowPlayingVisualizer.qml` contains continuously looping height animations while media is playing. This is a plausible candidate for remaining shell animation work, not a confirmed attribution or proof that media state was constant throughout the trial. Reactor mode was separately observed as 0, with its backend unloaded.

A controlled media pause/resume test would require permission because it interrupts playback. A permanent gaming-aware visualizer change should pause only decorative rendering, not audio or media controls, and would need to follow the separate Shibumi repository/pinned-source maintenance workflow. No such plugin-source modification was made here.

Next, run an actual affected game's fixed scene/built-in benchmark with frame-time logging, comparing the same settings with widgets enabled and selectively unloaded. A native desktop resource test cannot establish whether gameplay frame drops improve.

## Data and method

[Raw samples, lock observations and restoration checks](quickshell-selective-pause-20261025-123909.json). CPU/RSS use `/proc/PID/stat`; PSS uses `smaps_rollup`; per-process GPU/memory use deduplicated `/proc/PID/fdinfo` DRM client counters. Mean values are arithmetic means of approximately one-second intervals. No credentials, browser titles or media URLs were recorded.
