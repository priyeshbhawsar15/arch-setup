# Live Lock Wallpapers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render downloaded supported Wallpaper Engine projects live in the lock background through an isolated DMA-BUF worker.

**Architecture:** Lock Explorer retains lock/authentication ownership. Its optional Qt texture bridge consumes bounded GPU buffers over an inherited socketpair from a sandboxed surfaceless EGL engine driver. Existing video playback and fallback backgrounds remain operational.

**Tech Stack:** C++20, EGL/OpenGL/GBM, native fences, Qt6 Quick, QML, Python, bubblewrap, shell.

**Spec:** docs/system-design/live-lock-wallpapers.md

## Global Constraints

- No cached recordings or CPU frame streaming; prove GPU transport before authentication integration.
- Offline, silent worker, no keyboard/mouse/audio-reactivity input; 30 FPS default.
- Three slots per stream, at most two streams/eight consumers; 8192 pixels per dimension, 64 Mi pixels total and 768 MiB buffer budget.
- Worker never owns lock, authentication, monitor power or desktop configuration.
- Preserve independent lock selection, 30-minute rotation, role-based side span, tint/timeouts and DDC off.
- Publish tested plugin/renderer/controller commits before updating setup pins. Preserve unrelated dirty setup work.

## Review Focus

- Malformed or truncated FD-bearing packets must close descriptors and fail without importing memory.
- An unsignaled fence must never block the GUI thread or permit premature buffer reuse.
- Two side surfaces must both release sampled frames before their shared stream reuses a slot.
- Qt ABI/module failure must leave legacy background and authentication loadable.
- Controller/worker/locker death and user stop must preserve desktop enabled/selection intent.

## Task 1: GPU transport proof and bounded protocol

Files in renderer fork: `tools/lock-renderer/CMakeLists.txt`, `Protocol.h`, `Protocol.cpp`, `GpuBuffers.h`, `GpuBuffers.cpp`, `probe-worker.cpp`, `tests/protocol.cpp`, `tests/probe.py`. Bridge worktree: `native/CMakeLists.txt`, `tests/gpu-import.cpp`.

Interfaces: `Packet receivePacket(int socket)`, `void sendPacket(int socket, const Packet&)`; RAII packet owns all received FDs. `GpuBuffers` owns surfaceless EGL context, exportable opaque RGBA buffers and ready/release fences. Qt probe consumes exported descriptor metadata; only test capture may read pixels.

- [ ] Write socketpair tests for valid round trip, unexpected FD counts, truncated ancillary data and overflowing dimensions; tests exercise real sendmsg/recvmsg and assert rejection and stable FD counts.
- [ ] Run `ctest --test-dir build-lock --output-on-failure`; observe rejection tests fail against the initial missing/unsupported implementation.
- [ ] Implement fixed-size LWP1 structures, descriptor RAII, exact packet/FD validation and bounded slot leases.
- [ ] Write GPU integration test launching the worker with a passed socket FD, importing calibration frames in actual Qt EGL context and asserting red/green/blue quadrants and frame progression; report render device, backend, modifier and fence readiness.
- [ ] Implement surfaceless EGL/GBM allocation, DMA-BUF export, native ready fences and release-gated recycling. Run outside real lock with device-matched Qt; stop downstream rollout if this milestone cannot pass.
- [ ] Commit tested transport/probe changes and record evidence in execution ledger.

## Task 2: Real project EGL output

Files in renderer fork: `src/WallpaperEngine/Render/Drivers/LockEGLDriver.{h,cpp}`, output classes beside driver, driver registration, application/argument lock-mode hooks, root CMake integration; reuse Task 1 transport/library.

Interfaces: engine-selected lock output uses inherited socket FD/device path; no regular display connection. `CONFIG`, `VISIBILITY`, `RELEASE`, `STOP` control output; generation-scoped `BUFFER` and `FRAME` publish pixels. Existing destination-framebuffer mechanism binds the active slot before engine rendering.

- [ ] Add integration cases rendering representative scene projects and offline White Tree web at main/side aspect ratios; compare deterministic first-frame landmarks and animated progression.
- [ ] Verify they cannot run with the existing ordinary-display driver in the display-less test sandbox.
- [ ] Implement no-input/no-audio lock-mode driver, bounded pools, frozen clock while inactive, output orientation and per-project overrides. Keep CEF subprocesses within the outer sandbox and remove unnecessary relaxed security switches in lock mode.
- [ ] Run transport tests and project smoke tests; inspect frame/FD/memory behavior on visibility, source exit and hotplug-sized configuration changes.
- [ ] Commit engine backend with build and usage documentation.

## Task 3: Optional native Qt background bridge

Files in lock fork: `native/LiveWallpaperItem.{h,cpp}`, `native/FrameBroker.{h,cpp}`, `native/SandboxLauncher.{h,cpp}`, `native/CMakeLists.txt`, `LiveWallpaper.qml`, `designs/Wallpaper.qml`, `LockHost.qml`, `Service.qml`, tests.

Interfaces: QML item properties `sourcePath`, `streamId`, `consumerId`, `frameVisible`, `fps`, `status`; shared broker per source generation. QML typed source setter accepts validated JSON metadata. Native module is imported only by optional asynchronously loaded LiveWallpaper.qml.

- [ ] Test renderer crash, missing module, ready-fence timeout, two-window releases and generation replacement in standalone Qt scenegraph harness.
- [ ] Implement non-GUI IPC broker, render-thread import/destruction and per-consumer release fences. Spawn worker using private socketpair through restrictive bubblewrap mounts/namespaces with no session sockets/network/audio.
- [ ] Integrate optional background Loader and existing span geometry; preserve trusted auth overlay and video path. Map tint/power visibility without resetting timers or waking monitors.
- [ ] Run existing lock fork suites plus new Qt/sandbox tests, including unavailable native module and malformed IPC.
- [ ] Commit native/QML integration; keep installed lock code unchanged until tested and session unlocked.

## Task 4: Typed rotation and reversible desktop lease

Files in wallpaper-manager: `bin/wallpaper-controller`, focused `tests/test_lock_sources.py`, `tests/test_lock_lease.py`, plugin service/timer hooks and documentation where needed.

Interfaces: version-2 lock-video.json typed source with stable ID and legacy activeVideo compatibility; controller acquire/release runtime lease keyed by owner PID/start time; typed source apply calls Lock Explorer public API.

- [ ] Write tests using temporary HOME and real fixture project metadata: exact legacy selection/time migration, missing/symlink-escaped assets, bounded failed candidates, shuffle preservation, user stop while leased, controller restart and owner death.
- [ ] Run tests to observe absent typed-source/lease behavior, then implement discovery/migration and idempotent lifecycle. Lease suspends without changing persistent enabled flag; restore current desired selection on release only when user enabled.
- [ ] Run the complete wallpaper-manager suite and source/controller integration with standalone lock API harness.
- [ ] Commit controller and plugin hooks with matching source schema.

## Task 5: Reproducible installation and actual lock validation

Files in setup: `install-lock-renderer.sh`, `install-lock-explorer.sh`, `install-wallpaper-manager.sh`, `install-all.sh`, `PLUGINS.md`, `SCRIPTS.md`; use actual existing installer names discovered in this repository and preserve current managed role topology.

- [ ] Add staged-install fixtures proving failure leaves old artifacts intact, exact manifest matches print already installed, and Qt version changes rebuild optional native module.
- [ ] Add feature-owned builds/artifacts, explicit installer registration, exact source pins, manifest/rollback, enable/disable/removal documentation. Native artifacts installed before live feature enabled.
- [ ] Test in nested compositor first: renderer failure and locker failure must never release lock. Run user-present actual lock tests only after unlocked installation; validate side cropping, deadlines/tint, DDC off/wake and responsive password input.
- [ ] Perform fresh whole-branch review, fix meaningful findings with regression tests, run required suites/builds and publish authorized feature branches/commits.
- [ ] Verify published hashes can be fetched, update setup pins/docs, install on unlocked session, rerun installers for idempotence and preserve unrelated dirty work.

## Execution record

Run implementation inline following the user's explicit instruction to proceed. Record tests, commits and any architecture changes in `/home/priyesh/Work/.worktrees/live-lock-ledger.md`. Worktrees: lock-live, wallpaper-live; renderer fork checkout linux-wallpaperengine-lock on feat/lock-dmabuf. No unrelated setup edits are part of feature commits.
