# Quickshell media-playback comparison

## Result

With Gaming Mode active, Quickshell CPU/graphics activity fell sharply when the authorized Chromium media pause took effect, then returned when playback resumed:

- Playing before: shell CPU **10.50% of one logical CPU**, AMD gfx-engine occupancy **18.98%**.
- Paused: shell CPU **0.70%**, AMD gfx-engine occupancy **0.04%**.
- Playing afterward: shell CPU **10.43%**, AMD gfx-engine occupancy **19.23%**.

This strongly links the remaining Quickshell workload to media-playing UI state in this trial. The installed Shibumi bar has continuously looping decorative visualizer animations while MPRIS reports playing. That is a strong candidate, but pausing media affects more than one media-related property and GPU power state, so the exact contribution of that component still needs a targeted animation-only patch/test. These are idle engine-time percentages, not FPS losses or full-speed GPU throughput measurements.

## Method and validity

- User explicitly authorized a short media pause/resume test. Chromium initially reported Playing; the test called Pause, then Play. No seek, Stop, source edits or permanent media settings were applied.
- Three 30-second phases in playing/paused/playing order, approximately 1 Hz, six-second settling periods. Playback was paused for approximately 36 seconds including settling.
- Existing Gaming Mode remained active throughout the sampled phases, with its configured widget pause, wallpaper stop and VRR behavior. No game was launched and no actual frame times were collected.
- Quickshell PID 1014425 stayed stable. All 25 sampled lock/screensaver checks were clear; each phase also checked the expected playback status.
- Final playback status was **Playing**. Gaming Mode stopped afterward and the original wallpaper-enabled state was restored.
- This was a short, single-session comparison. Media content, GPU clocks, compositing and workload were not controlled as a formal game benchmark would require. No browser titles or media URLs were recorded.

## Implication

The three initial desktop widgets were not the main measured graphics source. A targeted gaming-aware pause of the bar's **decorative visualizer only** is the next justified experiment, preserving audio playback, track controls, notifications and locking.

That requires a source-code change to the existing separately maintained Shibumi fork, not a copied modification in this setup repository. Publishing authorization and a tested reachable commit are required before updating the setup's pin. Actual Cyberpunk 2077 frame-time comparison remains pending; preparing logging must avoid injecting MangoHud into Gamescope itself or adding another Gamescope layer.

[Raw samples and checks](quickshell-media-test-20261025-130012.json).
