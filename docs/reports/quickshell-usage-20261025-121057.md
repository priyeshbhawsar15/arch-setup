# Quickshell resource-use report

## Conclusion

The existing Gaming Mode does not materially reduce Quickshell CPU usage or memory residency. During this unlocked, non-game test, the shell still performed substantial AMD graphics-engine work. A selective pause of nonessential widget animation/polling is worth testing, but freezing the whole shell is not recommended and was not tested. No FPS improvement can be inferred from these measurements.

## Valid measurement

- Host: Intel i3-12100, 8 logical CPUs; Radeon RX 6800, 16 GiB VRAM; Intel UHD 730 also present. Main display previously configured at native 4K/120Hz with two secondary displays.
- Process: Quickshell PID 1014425, stable throughout the run.
- Local time: 25 October 2026, sample phases from 12:11:03 to approximately 12:13:28 IST (UTC+05:30).
- Design: desktop → existing Gaming Mode → desktop → existing Gaming Mode. Four 30-second phases, six-second settling periods, approximately 1 Hz sampling. Sixty intervals per condition, about 60.01 seconds each.
- Gaming Mode was activated by a harmless process carrying Lutris's standard `GAME_NAME` marker. No actual game or additional Gamescope instance ran. Quickshell was never paused or stopped.
- All 32 sampled lock/screensaver checks were clear. Checks occurred at phase boundaries and approximately every five seconds, not continuously. The user's stay-awake preference was already enabled; the sampler did not change locking settings.
- Wallpaper/Gaming Mode state was restored afterward.

The earlier run with uncertain lock state and the aborted run against a restarted PID are excluded. A process restart also changed the shell's state, so the difference from those earlier numbers must not be attributed solely to unlocking.

## Results

All CPU percentages below use the standard Linux convention: **100% equals one logical CPU**, not the whole processor. GPU percentages are derived per-client engine time divided by elapsed time; they are not FPS loss or percentages of VRAM.

### Quickshell CPU

- Desktop: mean **10.63% of one core**, 1-second p95 12.00%, maximum 14.00%.
- Gaming Mode: mean **10.58% of one core**, p95 14.00%, maximum 14.04%.
- Mean difference: **−0.05 percentage points**, effectively unchanged in these short samples.
- Gaming Mode mean is approximately **1.32% of the eight-logical-CPU total**. This normalization is not a measure of gaming throughput or bottleneck severity.

### Shell process-tree CPU

Includes Quickshell, observed live descendants and CPU charged for reaped descendants:

- Desktop: mean **18.40% of one core**, p95 29.00%, maximum 30.01%.
- Gaming Mode: mean **18.56% of one core**, p95 30.00%, maximum 36.00%.
- Independently launched services and orphaned processes are not necessarily included. Process-tree sampling is approximate because processes can exit between reads.

Across the approximately 115-second span between the first and last phase-start snapshots, Quickshell accumulated about **7.90% of one core in reaped-child CPU**. Stable long-lived children contributed little: the Home Assistant Python daemon averaged about 0.03% of one core in that span; three voxtype followers, two clipboard watchers and inotifywait registered no own-CPU tick increase between those endpoints. This points toward short-lived child workloads as an investigation target, but does not identify which plugin launches them. Do not blame the duplicate voxtype followers for CPU cost based on this sample.

### Quickshell AMD graphics-engine activity

- Desktop: mean **14.45%**, p95 16.29%, maximum 17.01%.
- Gaming Mode: mean **18.83%**, p95 20.90%, maximum 20.99%.
- Individual phase means: desktop 14.63%, Gaming Mode 17.92%, desktop 14.27%, Gaming Mode 19.74%.
- Compute-engine activity was small: mean 0.018% desktop and 0.009% Gaming Mode. Intel engine counters showed no measurable increase in this run.

The higher graphics-engine occupancy in Gaming Mode is an observation, not proof of a VRR regression or a specific widget fault. Frame scheduling, animations, changing content and the live desktop can affect it. Widgets were not isolated individually.

Whole-AMD-GPU sampled busy readings averaged 19.30% desktop and 17.47% Gaming Mode. Those instantaneous system-wide readings use a different accounting/window from cumulative per-client engine counters; they cannot be subtracted from or directly equated to the shell's engine percentages. Other applications also contribute.

### Memory

- Quickshell mean resident RAM (RSS): **921 MiB desktop / 919 MiB Gaming Mode**.
- Proportional set size (PSS), sampled only at boundaries: **794 MiB initially / 799 MiB finally**.
- AMD resident VRAM charged to Quickshell's deduplicated DRM clients: mean **929 MiB in both conditions**; peak approximately **1,073 MiB**.
- Approximately **375 MiB of the VRAM accounting is shared**. The remainder is roughly 554 MiB, but this is not a promise of memory reclaimable by stopping the shell.
- These RAM and VRAM metrics are distinct; do not add them together as system RAM usage.

Pausing process execution does not release its RAM or GPU allocations. Reducing VRAM residency would require unloading/releasing specific widget resources or stopping relevant components, not simply stopping timers or applying SIGSTOP.

## Recommended next experiment

1. Add a game-aware pause signal to nonessential widgets, keeping locking, notifications and shell controls responsive.
2. First investigate continuous animation/rendering and short-lived subprocess polling. Batch repeated collection or reduce polling during games where appropriate.
3. Pause one feature at a time and repeat the same unlocked measurement; hiding a widget alone may leave timers or collectors running.
4. If memory is a goal, separately test unloading scene/resources. A polling pause alone is unlikely to reclaim the allocations above.
5. Finally benchmark a real fullscreen game, using the same scene/settings and frame-time logging, comparing current mode with selective widget pausing.

This report is an unlocked desktop resource baseline, not a fullscreen game benchmark, causal widget profile, or measured before/after Quickshell-pause result. Fullscreen occlusion, game contention, user interaction and animation state can change the workload. GPU clocks/power states were not controlled, so idle engine occupancy is not a percentage of full-speed GPU throughput. Two rounds per condition are not enough for robust statistical or performance-gain claims.

Follow-up: the [controlled selective-pause trial](quickshell-selective-pause-20261025-123909.md) found modest memory savings but no meaningful graphics-load improvement from pausing System Metrics, Weather and Immich.

## Accounting and reproducibility

CPU: deltas from `/proc/PID/stat`, using the host's clock-tick rate and elapsed monotonic time. RSS: resident pages from the same source. PSS: `/proc/PID/smaps_rollup`. GPU: `/proc/PID/fdinfo`; repeated descriptors for the same DRM PCI device/client ID are counted once. Engine deltas are aggregated per device/engine. AMD global busy: `/sys/class/drm/card2/device/gpu_busy_percent`. Lock/screensaver state: Omarchy shell's read-only IPC.

Data: [raw samples and validity checks](quickshell-usage-20261025-121057.json). Each condition has 60 one-second intervals; p95 values use the nearest-rank method. Reported means are arithmetic means; interval lengths stayed close to one second.
