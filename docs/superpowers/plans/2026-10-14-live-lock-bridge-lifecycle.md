# Live Lock Bridge Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development with T3-owned implementation tasks and parent review. Steps use checkbox (`- [ ]`) syntax for tracking. The planner delegates substantial implementation; executors must not delegate further.

**Goal:** Replace the failed mutable-broker bridge with complete session snapshots, immutable worker epochs and render resources that retain their originating epoch.

**Architecture:** A GUI coordinator commits validated topology and device reports. One IPC owner runs each immutable worker attempt; each render arena owns its textures and leases in one window/context. Replacement and shutdown retire these owners asynchronously.

**Tech Stack:** C++20, Qt6 Quick/QML/OpenGL (existing minimum 6.8), EGL/GBM, native fences, existing LWP1 protocol, bubblewrap, CMake/CTest, Node/Python regression tests.

**Spec:** `docs/system-design/live-lock-bridge-lifecycle.md`, together with `docs/system-design/live-lock-wallpapers.md` for unchanged security, behavior and rollout.

## Global Constraints

- The original `live-lock-bridge` unit is stopped. These tasks reconstruct the approved ownership architecture, not a third fix round against that unit. Each new independent deliverable gets an initial task and at most two explicit fix rounds.
- Ownership: `/home/priyesh/Work/.worktrees/lock-live`, baseline `b1b010a9113185b215b652c141c4b30168a2836f`, existing dirty feature code retained for migration. Renderer `/home/priyesh/Work/linux-wallpaperengine-lock` and controller `/home/priyesh/Work/.worktrees/wallpaper-live` are read-only dependencies during these tasks. No plugin source copied into setup.
- Two streams, three slots per stream, eight consumers total across configured streams, 8192 pixels per dimension, 64 Mi pixels across streams and 768 MiB aggregate transport-buffer budget including frozen/retiring arenas. One producing worker; at most prior frozen arena plus candidate/current arena.
- 30 FPS default, allowed 1–60; measured compatible Qt OpenGL/EGL device only. LWP1 masks exclusively, unchanged wire structures, no ordinary wallpaper window, recordings or CPU frame streaming.
- Preserve independent selection/rotation, role topology, desktop user-stop state, auth, tint/timeouts and DDC off/wake. No edits under `/usr/share/omarchy` or `~/.local/share/omarchy`.
- Handshake/buffer phases five seconds each, first visible frame ten seconds, ready/submitted-release fences one second, graceful STOP two seconds plus two seconds terminate/reap, render cleanup acknowledgement five seconds. Incomplete device/registration cohort five seconds. No GUI/render wait or thread join.
- Do not commit, push, publish, activate, restart the installed shell, lock the real session or issue display-power commands during these implementation tasks. Downstream rollout follows the original plan after review and applicable authorization.
- Use current `orchestrator_capabilities` at dispatch; preserve configured provider/model/options exactly. Retain task IDs and collect `task_status`; parent reviews actual shared diff and fresh test output. Do not create bookkeeping ledgers.

## Review Focus

- QML setter/registration order and late window attachment must never create a partial worker configuration (Task 1).
- New sources/retries that repeat initial frame/slot numbers must not reuse prior imports or release endpoints (Tasks 1–2).
- Removing or hiding one side consumer while it holds a sampled lease must not release another surface's GPU work (Tasks 1–2).
- Window/context teardown and failed repaint-fence export must never permit GUI cleanup, stale completion fences or unbounded retired arenas (Tasks 2–3).
- Worker/fence stalls and missing modules must preserve the real fallback/auth UI and remain responsive, rather than passing through test skips or mocks alone (Tasks 2–3).

## Files and shared contracts

Create `native/SessionTypes.h` for values/RAII handles, `native/SessionCoordinator.{h,cpp}` for GUI snapshots/registrations, `native/WorkerSession.{h,cpp}` for immutable IPC epochs, and `native/RenderArena.{h,cpp}` for render-context resources. Reconstruct `native/LiveWallpaperItem.{h,cpp}` around them; retire `FrameBroker.{h,cpp}` once its last production/test dependency migrates. Keep `SandboxLauncher` responsible only for verified launch/reap operations.

The shared header defines these interfaces before dependent implementation:

```cpp
using EpochId = std::uint64_t;
using RegistrationToken = std::uint64_t;
using ConsumerKey = std::string;
enum class SampleState { Unsampled, Sampled };
struct StreamConfig { std::uint32_t id, width, height, consumers; };
struct ConsumerConfig { ConsumerKey key; std::uint32_t stream, id; };
struct DeviceReport {
    std::string renderNode;
    std::uint32_t major, minor;
    std::uint64_t contextSerial;
    bool openGlEgl;
};
struct SessionConfig {
    std::uint64_t revision;
    std::string sourceId, sourcePath;
    int fps;
    std::vector<StreamConfig> streams;
    std::vector<ConsumerConfig> consumers;
};
class WorkerSession;
struct FrameRef {
    std::shared_ptr<WorkerSession> epoch;
    std::uint32_t stream, slot;
    std::uint64_t sequence;
};
// SessionCoordinator: GUI thread only
void stageDesired(SessionConfig config);
RegistrationToken registerConsumer(ConsumerKey key, DeviceReport device);
void setVisible(RegistrationToken token, bool visible);
void detachConsumer(RegistrationToken token);
// WorkerSession: methods enqueue; its IPC thread owns mutable transport state
WorkerSession(EpochId id, SessionConfig config);
void release(FrameRef frame, ConsumerKey key, SampleState sampled, lockframe::Fd fence);
void requestStop();
```

Declarations above are member signatures in their named classes, not free-function implementations. Configuration and device reports are copied across threads; no QObject/window/GL pointer crosses into IPC. `FrameRef` is never synthesized from the coordinator's current session. Reaping ownership outlives consumer references and completes away from GUI/render threads; the public destructor cannot synchronously join there.

### Task 1: Immutable epoch runtime and complete configuration barrier

**Work unit:** `live-lock-epoch-runtime` (initial reconstruction task).

**Create:** `native/SessionTypes.h`, `native/SessionCoordinator.{h,cpp}`, `native/WorkerSession.{h,cpp}`, `native/tests/session-runtime-tests.cpp`, `native/tests/SessionHarness.{h,cpp}`.
**Modify:** `native/CMakeLists.txt`, `native/SandboxLauncher.{h,cpp}` only for asynchronous IPC-owned stop/reap, `README.md` runtime contract documentation. Existing item stays on legacy broker until Task 2.

**Consumes:** actual renderer `Protocol.h/.cpp`, fixed mask contract, existing bubblewrap launcher. **Produces:** compiled shared contracts above and a CTest target `session-runtime-tests`. Test harness owns a private socketpair/mock child, captures real Configure/Release packets, and exposes `stage`, `attach`, `advance`, `spawnCount`, `wireConfig`, `epochId`, `retry`, `hide`, `detach`, `guiHeartbeatMaxGapMs`, and `pendingObligations` methods; it must never invoke installed desktop commands.

- [ ] Add the harness, CMake test target and RED contract cases, including this complete-barrier test. Define `fullTopology()` as stream 0/consumer main and stream 1/two side consumers; `measuredDevice()` reports the same fixture device for all three.

```cpp
SessionHarness h;
h.stage(fullTopology());
h.attach("main", measuredDevice());
h.advance(1);
CHECK(h.spawnCount() == 0);
h.attach("side-left", measuredDevice());
h.advance(1);
CHECK(h.spawnCount() == 0);
h.attach("side-right", measuredDevice());
h.advance(1);
CHECK(h.spawnCount() == 1);
CHECK(h.wireConfig().count == 2);
CHECK(h.wireConfig().streams[1].consumers == 3);
auto oldEpoch = h.epochId();
h.retry();
CHECK(h.epochId() != oldEpoch);
```

- [ ] Run `cmake -S native -B build-native -DLOCKFRAME_SOURCE=/home/priyesh/Work/linux-wallpaperengine-lock/tools/lock-renderer`, build `session-runtime-tests`, then `ctest --test-dir build-native -R '^session-runtime-tests$' --output-on-failure`. Record failures against missing runtime behavior, not merely a missing executable.
- [ ] Implement staged snapshots and registrations using stored tokens; validate exact consumer-mask membership, dimensions, budgets and measured device identity before committing. Capture CONFIG while permuting all attach orders; include masks 1/2/4/128, side-only stream 1, conflicting revisions, device mismatch and rejection of nine consumers across two streams. No even-mask count conversion.
- [ ] Implement immutable per-attempt buffers/endpoints, RAII descriptors and slot/frame obligation tracking; fresh ID on retry, fixed wire generation in every release, stale messages closed, duplicate records removed on completion. Test old-session release after new session uses the same slot/sequence; only the old socket may receive it. Exercise queue overflow and unknown slot/consumer rejection.
- [ ] Implement per-consumer visibility OR, hidden-clock freeze and no-launch all-covered state. Detach updates membership and returns unsampled obligations only for work never delivered/sampled. Test hiding either side in both orders and removing the final consumer with a running child.
- [ ] Implement nonblocking GUI stop and IPC-thread deadlines/reaping. Dup and poll submitted release fences without blocking, retain their endpoint, fail on deadline rather than force reuse. Inject stalled handshake/buffers/ready/release fences and child exit; assert heartbeat gaps below 250 ms, one-second fence expiry, process exit within four seconds of stop, at most 64 queued packets and at most 48 outstanding obligations.
- [ ] Run the runtime tests plus existing `bridge-tests`, Node and Python lock regressions; capture exact output, FD baselines and diff. Leave tested changes uncommitted for parent review. Reject this task before Task 2 if contracts or failure bounds disagree with the spec.

### Task 2: Reconstruct item ownership and prove actual GPU transitions

**Work unit:** `live-lock-item-ownership` (initial reconstruction task), depends on accepted Task 1.

**Create:** `native/RenderArena.{h,cpp}`, `native/tests/item-gpu-tests.cpp`, `native/tests/ItemGpuHarness.{h,cpp}`.
**Modify:** `native/LiveWallpaperItem.{h,cpp}`, `LiveWallpaper.qml`, `WallpaperSpan.js`, `LockHost.qml`, `Service.qml` only topology/session-token facade bindings, `native/CMakeLists.txt`, `native/tests/bridge-tests.cpp`, `tests/wallpaper-span.test.cjs`, `README.md`.
**Remove:** `native/FrameBroker.{h,cpp}` after migrating all uses to accepted runtime; no parallel production ownership models.

**Consumes:** Task 1 types, coordinator/epoch API, renderer GPU buffers and existing span geometry. **Produces:** production `LiveWallpaperItem` wired to shared session snapshots; `item-gpu-tests` CTest target. Harness creates actual attached QQuickWindows, imports via the production item, captures test-only pixels, provides fixture sources A/B with distinct calibrated colors but identical initial slot/frame numbers, and collects release packets by epoch. Required harness API: `showThreeConsumers`, `select`, `waitReady`, `redraw`, `detachSide`, `reparent`, `invalidateSceneGraph`, `injectFenceExportFailure`, `pixelAt`, `releaseEpochs`, `fdCount`, `importCount`, `shutdown`, `sourceA`, `sourceB`, `sourceAColor`, `sourceBColor`, `currentEpoch`, `oldFrameReleasesOnlyTarget`.

- [ ] Add GPU-item RED tests against current item. Keep capability setup separate from assertions; unsupported device/backend or a skipped GPU path is a nonzero acceptance result. This assertion must inspect the production item, not the existing standalone importer:

```cpp
ItemGpuHarness h;
h.showThreeConsumers();
h.select(h.sourceA());
CHECK(h.waitReady(10000));
auto a = h.currentEpoch();
CHECK(h.pixelAt("main", 16, 16) == h.sourceAColor());
h.select(h.sourceB());
CHECK(h.waitReady(10000));
CHECK(h.currentEpoch() != a);
CHECK(h.pixelAt("main", 16, 16) == h.sourceBColor());
CHECK(h.oldFrameReleasesOnlyTarget(a));
```

- [ ] Replace launch-on-setter logic: expose atomic `sessionConfig` plus consumer key/session token, stage from `componentComplete`, report devices from render callbacks, and post immutable registration changes to the GUI. Add full topology helper tests including actual scale/transform inputs; never substitute connector constants or guessed dimensions. Store the old token/window before setter/reparent changes.
- [ ] Implement arenas keyed by epoch/context serial. Leases retain original `WorkerSession`; displayed fences refresh on every draw. Detach QSG nodes before destruction, destroy imports on owning render threads, and close pending unsampled descriptors through their original endpoint. Connect only the current window and ignore stale context/registration callbacks.
- [ ] Implement frozen-prior/candidate replacement: asynchronously reap old producer before candidate launch, retain old imported backing memory, and require first-import acknowledgements from every visible consumer before posting one promotion serial to all their arenas. Retire prior arenas after swap acknowledgements; test that one slow side keeps the prior span displayed. Account both arenas against the budget. Coalesce subsequent selections; never allocate a third arena while retirement is pending. On missing cleanup acknowledgement after five seconds, disable live rendering for the session and bound quarantine until context teardown.
- [ ] Exercise unrelated repaints, two side-window release fences, side removal while sampled, reparenting, invalidation, failed import and failed fence export specifically after a repaint. Verify failure retires the epoch, the last valid/legacy background remains usable and sampled work is never falsely released without a fence.
- [ ] Build and run `ctest --test-dir build-native -R '^(session-runtime-tests|item-gpu-tests)$' --output-on-failure` in an explicitly discovered active Wayland session with the test-only OpenGL backend setting. Record actual Qt/DRM identities; do not permanently change shell environment/backend. Run the whole legacy lock suite. Leave diff and results for parent review; no actual lock test or installed plugin mutation.

### Task 3: Integration, failure soak and downstream rollout gate

**Work unit:** `live-lock-lifecycle-acceptance` (initial validation/integration task), depends on accepted Tasks 1–2.

**Create:** `native/tests/lifecycle-soak.cpp`, `tests/live-loader-harness.qml`, `tests/live-loader.test.cjs`, `TESTING.md` if absent.
**Modify:** `native/CMakeLists.txt`, `designs/Wallpaper.qml`, `LiveWallpaper.qml`, `Service.qml` optional Loader/fallback/capability status only, `native/tests/ItemGpuHarness.{h,cpp}`, `README.md` acceptance/runbook. Setup pins/installers and authentication remain out of scope.

**Consumes:** accepted production item and runtime. **Produces:** reproducible `lifecycle-soak` and real QML Loader harness tests, measured readiness for the original rollout stage, not an installation claim.

- [ ] Add a QML fixture that loads the actual `designs/Wallpaper.qml` and optional `LiveWallpaper.qml` with a minimal shell/theme fixture; remove the module from its import path and assert the real fallback stays instantiated. Repeat with renderer failure and the module present. A fabricated Loader with only a Rectangle is insufficient.
- [ ] Wire truthful measured capabilities, session-token separation and lifecycle shutdown; enable/disable and preview-to-lock transitions cannot leak a worker or desktop lease. Keep source-failure positional ID/token contract. Mock controller transport in fixtures so no real desktop commands execute.
- [ ] Add a 100-transition soak using the accepted GPU harness; alternate source A/B, two-stream/side-only topology, consumer detach/recreate and hide/show. Warm up once, then after each fully retired cycle assert FD count does not exceed warm baseline by more than four test-harness FDs, imported resources return to baseline, outstanding/queue bounds hold, and quarantined arenas never accumulate. Record memory high-water marks against the 768 MiB transport budget.
- [ ] Inject stalled fences, worker crash/hang and context cleanup that never acknowledges. Assert GUI heartbeat gaps below 250 ms, bounded process cleanup and fallback; verify tint/deadline fixture values are unchanged. Soak GPU skips or fallback-only runs fail acceptance.
- [ ] Run `ctest --test-dir build-native --output-on-failure`, `node --test tests/*.test.cjs`, `python3 -m unittest discover -s tests -v`, and unchanged renderer/controller suites in isolated fixtures. Record failures honestly; inspect the entire feature diff and prove no auth/monitor-power changes. Leave changes uncommitted and stopped on any unresolved safety blocker.
- [ ] Parent reviews fresh outputs and shared code before returning to original plan Task 5. The remaining gates are nested-compositor fail-closed lock behavior, staged install/rollback/Qt ABI checks, authorized publication of fetchable exact hashes, setup pins/documentation and unlocked installation, then user-present lock/wake acceptance. Do not infer those gates passed from this task's tests.

## Execution handoff

The user approved the revised written specification and this plan and explicitly authorized implementation on 14 October 2026. Use the preserved planner/executor delegation method; no extra execution-method choice or confirmation is needed between tasks. Each dispatch carries the original spec/plan, current accepted contracts, exact owning paths and acceptance checks. A fix dispatch retains its unit ID, original brief, prior findings/responses and unresolved objections; no third fix round is allowed.
