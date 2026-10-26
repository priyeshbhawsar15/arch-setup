# Gaming-aware visualizer: live controlled validation

## Result

The decorative media loop is a substantial Quickshell workload in this desktop scene. Pausing it removed most of the shell's measured CPU and AMD graphics-engine activity; reenabling it reproduced the workload. This establishes a rendering-overhead reduction, **not an FPS improvement**.

- Running before: shell CPU **8.96% of one logical core**; shell plus observed/reaped child CPU **14.76% of one core**; AMD graphics-engine occupancy **17.81%**.
- Paused: shell CPU **0.47% of one core**; shell/tree CPU **6.30%**; AMD graphics-engine occupancy **0.01%**.
- Running after: shell CPU **8.97% of one core**; shell/tree CPU **14.73%**; AMD graphics-engine occupancy **17.19%**.

The average running control is about 8.97% CPU and 17.50% graphics-engine occupancy. CPU percentages are not percentages of the whole eight-logical-CPU machine. Engine occupancy is per-client DRM accounting, not an interchangeable whole-GPU busy percentage or a prediction of game performance. Idle-scene GPU clocks/work differ from gaming conditions.

Memory does not support a reclamation claim: RSS drifted 1149 → 1146 → 1130 MiB and charged AMD VRAM 653 → 644 → 622 MiB across the three phases, continuing down after animation resumed. This is animation gating, not shell suspension or unloading its buffers.

## Method and validity

- Published fork commit: `19ee5f70cf3763be9c0dcbc663c459bd4118841a`, branch `gaming/visualizer-pause-20261025` in `priyeshbhawsar15/Shibumi-Shell`.
- One unchanged production Quickshell PID **1196211**. Three connected displays retained their configuration; no game ran during this comparison.
- Gaming Mode and its selected widget pause remained active throughout. A harmless owned `GAME_NAME` marker held the session. Only the version-1 journal's `pauseDecorations` hint alternated false/true/false, acknowledged by the bar IPC.
- Three alternating 30-second phases, six-second settles, 90 approximately-one-second samples, **25 clear lock/screensaver checks**.
- User-approved temporary, **silent metadata-only MPRIS fixture**, advertising Playing. It exercises the real native media proxy and live bar renderer but produces no sound. No real-player playback controls were called. **This is not a real-audio playback acceptance test.**
- The fixture and owned marker were removed. Gaming Mode ended; wallpaper and original plugin flags restored; the bar watcher returned to `watching=true, paused=false`.

An earlier run, `quickshell-visualizer-validation-20261025-171936.json`, is explicitly excluded from fix acceptance: both its controls and paused phase were idle because the hidden G9 widget had no explicit suite media-service demand. That run exposed a configuration regression; it is not evidence of a successful optimization.

## Configuration correction and deployment

The newer fork routes the center media notch through `hancore.shibumi.media`. Hiding G9 removes its implicit service demand, so personal configuration must retain `{"id":"hancore.shibumi.media"}` in the shell's service entries. `config/shibumi-settings.py` now reconciles that idempotently without adding another visible widget. Its `--media-backend-only` repair preserves existing presentation and layout.

The supported suite transaction installed all 24 roots from the exact published commit, preserving the bar object, plugin enable flags and display configuration. A private predeployment backup is retained under `~/.local/state/arch-setups/backups/shibumi-gaming-visualizer-predeploy-20261025T140016-KX9RZv/`. An actual Halo launch was detected automatically; the new watcher consumed the pause signal and subsequently cleared after the game ended. Current host diagnostics found three bar panels, 27 ready loader items and no enabled active slots without items.

## Evidence and limits

Passed: 291 fork source/lifecycle tests; actual offscreen animation/file lifecycle fixture; vendoring and AUR scaffold checks; 22 producer tests; four benchmark-preparation tests; six personal media-backend configuration tests. The 39 directly relevant setup tests passed, along with shell/systemd validation and source-contract/diff checks. The expanded setup runner now includes Gaming Mode tests; its full 233-test run retains five pre-existing Lutris Gtk/Gdk namespace failures, not an all-green result. No upstream tag, merge, binary package or AUR release was created.

Full historical compatibility gates remain blocked by the installed Omarchy 4.0.6 versus the pinned 4.0.3 host boundary and absent historical checkouts. Scoped live observations are not a replacement for that release qualification. Actual game controller/HDR content acceptance and controlled game frame-time comparison remain pending.

Cyberpunk logging is prepared but not activated. No graphics settings, game prefix, mods, existing Gamescope options, Steam shortcut or Lutris launch configuration changed for that preparation. Run `./install-gaming-mode.sh --prepare-benchmark` to reproduce the private logging profile.

Raw data: [quickshell-visualizer-validation-20261025-173529.json](quickshell-visualizer-validation-20261025-173529.json). [Visual report](quickshell-visualizer-validation-20261025-173529.html).
