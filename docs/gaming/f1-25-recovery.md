# F1 25: recover the known-working Linux setup

This is a **manual recovery runbook**, not another installer. It records the
working 2026-10-15 Steam/Wayland configuration and the diagnostic addition on
2026-10-16. Reading it or running `install-all.sh` does not apply these F1-specific
changes. The shared [LinUwUx installer](../../gaming/denuvowo/README.md) is a
separate feature; it neither recreates nor replaces this private F1 launch chain.

The recorded user-confirmed result was a visible game menu, HDR, an FPS counter,
and successful switching away and back. A menu/window is not proof of complete
race compatibility or sustained 120 FPS. New game, kernel, GPU-driver or runtime
versions must be validated again.

## 1. Know what must be recovered

The historical paths below are **specific to this machine**, not stable upstream
installation names. In a terminal on the original account:

```sh
R="$HOME/.local/share/f1-25-shaderfix.RfimSS"
S="$R/steam-4k120-hdr.WDi8TG"
```

Keep this shell open for the commands using `R` and `S` below. The launch chain is:

1. Steam's native shortcut or the desktop entry runs
   `~/.local/bin/launch-f1-25-4k`.
2. It locks `S/session.lock` and calls `S/launch-session.sh`.
3. That checks CPU features, runtime hashes, the game file and monitor state;
   reapplies video settings; and arms a bounded one-shot fullscreen helper.
4. `S/watchdog.py` supervises `~/.local/bin/launch-f1-25.sh` using this session's
   prefix/logs and `R/GE-Proton-shaderfix`.
5. The base script runs `S/linuwux-private` → Lutris's bundled `umu-run` →
   `~/games-links/F1-25/F1_25.exe`. The private wrapper preloads
   `S/LinUwUx-v2.so`.

The private runner is based on **GE-Proton11-7**. Only its copied 64-bit
`d3d12core.dll` was replaced. The active prefix is **`S/prefix`**, not
`~/.local/share/wineprefixes/f1-25` or `R/prefix`. Older `play.sh`, multi-instance
experiments and `steam-4k.ZefBvE` are not the final native-Wayland launch path.
The personal gaming profile still contains a historical working-directory
reference to `steam-4k.ZefBvE`; it is not evidence that this is the active prefix.

## 2. Preserve a recovery copy before reinstalling

Close F1 and its launcher normally. Confirm there is no remaining F1 process:

```sh
pgrep -a -x 'F1_25[.]exe'
```

No output means no matching process; do not use a blanket `wineserver -k` or kill
other games. Preserve, privately and off this disk if possible:

- The **whole `R` directory**, including the private Proton, both LinUwUx
  libraries, the active prefix, scripts, tools, reports and rollback copies.
- `~/.local/bin/launch-f1-25-4k`, `~/.local/bin/launch-f1-25.sh`, and
  `~/.local/bin/f1-25-capture-logs`.
- `~/.local/share/applications/f1-25-4k-shaderfix.desktop`.
- `~/.local/share/lutris/runtime/umu/`, the bundled UMU used by this launcher.
- The game-directory symlink and **separate** backups of actual saves/configs.
  Inspect prefix symlinks: an ordinary archive does not follow them to external
  Documents/AppData/save locations.
- A private copy of the working boot entry and monitor configuration for
  reference. Do not blindly replay old EFI hashes, disk UUIDs or connector names.

Example archive command, after choosing a real backup location. It can be large
and contains private prefix/log/shader data; do not commit or publicly upload it.
The game directory is archived as a symlink, **not** a copy of the game files.

```sh
umask 077
ARCHIVE="/path/to/private-backup/f1-25-working-$(date +%Y%m%d-%H%M%S).tar"
tar --acls --xattrs -C "$HOME" -cpf "$ARCHIVE" \
  .local/share/f1-25-shaderfix.RfimSS \
  .local/share/lutris/runtime/umu \
  .local/bin/launch-f1-25-4k \
  .local/bin/launch-f1-25.sh \
  .local/bin/f1-25-capture-logs \
  .local/share/applications/f1-25-4k-shaderfix.desktop \
  games-links/F1-25
(cd -- "$(dirname -- "$ARCHIVE")" && sha256sum -- "${ARCHIVE##*/}" > "${ARCHIVE##*/}.sha256")
```

Check every listed path exists first; stop if `tar` reports a failure. Keep the
archive and its checksum together, and archive any remaining public build source
and build instructions separately rather than relying on `/tmp` surviving.

**Recovery limitation:** this repo preserves the public-source shader patch and
its source pins below, but does not contain the private optimized LinUwUx source,
its compiled library, the private Proton bundle, prefix or helper scripts. A
clone of this repository alone cannot reproduce the complete historical setup.
The fastest reliable recovery is the verified private backup. This runbook does
not claim a clean-room, bit-for-bit rebuild of the optimized runtime.

## 3. Restore files and basic dependencies

1. Restore onto the same account/home path when possible. Extract a trusted
   archive into a private **staging directory**, not straight over a live setup:

   ```sh
   (cd -- "$(dirname -- "$ARCHIVE")" && sha256sum -c -- "${ARCHIVE##*/}.sha256")
   ```

   Only after checksum verification succeeds, extract:

   ```sh
   RESTORE="$(mktemp -d "$HOME/f1-25-restore.XXXXXX")"
   tar --acls --xattrs -xpf "$ARCHIVE" -C "$RESTORE"
   ```

   Confirm the checksum entry names the archive actually being extracted. Review
   staged contents, preserve any current prefix/saves and wrappers as a separate
   dated backup, then copy the reviewed files back to their original paths as
   the normal user. Do not merge an unknown broken prefix into the good one or
   restore private files as root-owned. Preserve executable bits and symlinks.
2. Supply your own game installation. The final link resolved to
   `/run/media/priyesh/F1F5227BC4FE0E49/Games/F1 25`, not the original repack path.
   Mount/verify the actual installation and confirm `F1_25.exe` exists before
   restoring or repointing `~/games-links/F1-25`. Back up an existing link/path;
   do not replace a real directory or reinstall over saves just to fix a link.
3. Ensure the host has Steam, Lutris/bundled UMU, Vulkan support, MangoHud,
   Python 3, `flock`, `notify-send`, `hyprctl` and a working systemd user session.
   Missing normal packages can be installed with Omarchy's package commands.
   The recorded UMU path is
   `~/.local/share/lutris/runtime/umu/umu-run`; verify it is executable.
   The shared installer uses system `umu-run`, which is not automatically a
   replacement for this hard-coded path.
4. If the username, home directory, mount or monitor connector changed, inspect
   the restored scripts and desktop entry for old absolute paths. Update only
   reviewed paths in a backed-up candidate copy. Review prefix `dosdevices` and
   save/config links too; changing the outer wrapper alone is not relocation.

## 4. Use the correct CPU/boot configuration

The recorded runtime requires **UMIP absent** and **`cpuid_fault` present** in the
running kernel's CPU flags. Check the actual boot, not merely an old config file:

```sh
cat /proc/cmdline
grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(umip|cpuid_fault)$'
```

The machine had a separate Limine entry named **F1 25 - UMIP disabled (testing)**,
with `clearcpuid=514` appended to its normal kernel arguments. Select that entry
when intentionally testing this runtime. Preserve an ordinary protected boot.

If the testing entry was lost after reinstall/kernel update, recreate an
**optional** entry using the currently valid normal entry and the distribution's
current bootloader procedure. Preserve its current disk/encryption/resume
arguments and valid EFI/UKI path/integrity metadata. Do not copy an obsolete
machine-specific EFI hash or replace the default entry. Consult the
[upstream CPU/kernel guidance](https://github.com/brcly/linuwux-runtime#cpu-and-kernel-prerequisites)
and [kernel parameter reference](https://docs.kernel.org/admin-guide/kernel-parameters.html).

Disabling UMIP weakens user-mode instruction protection; `clearcpuid` is a kernel
debugging aid and taints the kernel. This is system-wide for that boot, not a
per-game environment variable. Remove it/use the normal entry and reboot to
undo. If `cpuid_fault` is missing, stop: disabling UMIP does not create CPUID
faulting support. Reassess host/upstream support rather than installing an
unverified module or pretending the preflight succeeded.

## 5. Verify the private runtime before launching

Check the preserved artifacts against the recorded SHA256 values:

```sh
(
  cd "$R" || exit 1
  sha256sum -c <<'HASHES'
983419885ec83c51465d2e2638f69dea91fb8cd0e39a052479102f982f1fdb54  GE-Proton-shaderfix/files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll
1f34629bf1c1cd752d3d0e2f7d31da118ec19a23ec54e32b9027fb62e22d7bf1  steam-4k120-hdr.WDi8TG/LinUwUx-v2.so
f8a00b29416b1b683479befdf2fb9e019e9d85850c104a31782320e4f389e924  steam-4k120-hdr.WDi8TG/LinUwUx.so
HASHES
)
```

A mismatch is a reason to stop and identify which version is present, not to
remove the hash guard. Newer upstream releases have not thereby been validated
as identical to these artifacts. Copying the generic shared runtime over the
private one does not recreate this profile.

The v2 runtime batched Wine export-name reads through `process_vm_readv`, retained
bounded scalar fallback, and passed 48 recorded native tests. The observed
visible-window startup comparison improved from roughly 279 seconds to 4 seconds;
this is not a race FPS benchmark or a guarantee on a new machine. The older
`LinUwUx.so` remains a slower recorded-working fallback. To try it, use a separate
candidate launch chain and deliberately change both its selected library and
matching expected hash; do not rename a different binary to pass an old guard.
Rebuilding v2 requires its original archived source/toolchain, not just this
summary of its algorithm.

## 6. Restore the F1-only graphics and launch configuration

The active saved XML is:

```text
S/prefix/drive_c/users/steamuser/Documents/My Games/F1 25/hardwaresettings/hardware_settings_config.xml
```

Here `S` means the directory defined above, not a literal Windows path. The
preserved `S/configure-video.py` backs up the XML and reapplies this profile:

- `graphics_card/resolution`: width `3840`, height `2160`, `displayMode="2"`
  (**Windowed (Fullscreen)/borderless**), limiter enabled and value `120`.
- `resolution/hdr`: mode `1`; saved output-monitor index `1`; window position
  `0,0`; automatic aspect ratio. Verify the output index if the monitor layout
  changes; a stale Gamescope comment in the script is not the current renderer.
- Dynamic resolution disabled; DLSS/FSR3/XeSS disabled; frame generation and
  multi-frame generation disabled. Native 4K, not an upscaling preset.

Exclusive fullscreen (`displayMode="1"`) caused focus-loss minimization. The
successful fix was borderless mode, plus `S/ensure-fullscreen.py` targeting only
this prefix's game/launcher ancestry while exactly one F1 process exists. Its
13-minute service ceiling bounds **the helper**, not the game session. Do not
replace it with a global window rule or give the game a diagnostic timeout.

The final session sets native Wine Wayland and HDR:

```text
PROTON_ENABLE_WAYLAND=1
PROTON_USE_WAYLAND=1
PROTON_ENABLE_HDR=1
DXVK_HDR=1
PROTON_WAYLAND_MONITOR=DP-6
WAYLANDDRV_PRIMARY_MONITOR=DP-6
LINUWUX_SYSCALL_HACK=0
USE_GAMESCOPE=0
```

The recorded output was **4K/120 Hz HDR on DP-6**. `launch-session.sh` checks the
physical output but does not reconfigure it. Connector names are machine-specific;
if they change, review the preflight, monitor-selection variables and fullscreen
helper together. The current repo's monitor policy is documented in
[`SCRIPTS.md`](../../SCRIPTS.md), but first verify the real connected output.

MangoHud uses **`S/MangoHud.conf`**, with only the top-left FPS counter and
**Right Shift+F12** toggle. The session uses private Mesa/VKD3D cache directories,
disables bulk shader dumping and Steam Fossilize capture, and disables core dumps.
The recorded controller flags were `PROTON_NO_STEAMINPUT=1` and
`SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1`; these are per-session, not a global
controller fix. Do not copy later FC26/FC27 60 FPS/VSync changes into F1: its
recorded limiter remained 120 FPS.

## 7. Restore the shortcut and check without launching

For Steam, add the existing native Linux script as a non-Steam shortcut:

- Target: `~/.local/bin/launch-f1-25-4k` (use the actual absolute home path).
- Start in: the absolute `S` path above; no extra launch options.
- Name: **F1 25 - 4K (Shader Fix)**.
- Do **not** force a Steam compatibility tool: the script/UMU chooses the private
  Proton itself. The verified setup used Steam's overlay disabled and MangoHud
  instead. Prefer the Steam UI; do not edit its VDF database while it is running.

The saved desktop entry has the same target and start directory. The existing
Lutris profile registration is a shortcut to that script, not an instruction to
run the Windows executable with a different Wine runner.

Once CPU, files and monitor state are correct:

```sh
"$HOME/.local/bin/launch-f1-25-4k" --check
```

The preserved check path performs preflight and exits **before** XML changes,
helpers, the watchdog or game startup. It still requires an active Hyprland
session. A failed check is not fixed by bypassing it. After it passes, explicitly
launch once through Steam or the desktop entry. Confirm the menu, intended
monitor/HDR, FPS counter and Alt-Tab return, then test an offline race. Record
actual FPS/frame pacing rather than assuming the 120 FPS cap is achieved.

## 8. Recover the shader correction if the private DLL was lost

Prefer restoring the verified private Proton copy. The public-source fallback is
an **advanced rebuild procedure**, not an automatic install or a promise of a
byte-identical DLL from a different compiler toolchain.

Recorded source provenance:

- VKD3D-Proton 3.1.0 base:
  [`af89350cc2eacd9da2293fbae96bd9ab4987c9bb`](https://github.com/HansKristian-Work/vkd3d-proton/tree/af89350cc2eacd9da2293fbae96bd9ab4987c9bb).
- Its original DXIL-SPIRV was 2.73.0 at
  `bed30ff2115d845fb6bf8752bcbe1c681efb0e01`.
- Replacement DXIL-SPIRV 2.75.0:
  [`8434b0639fb2a48ce13aac08a420ecce5d23df0e`](https://github.com/HansKristian-Work/dxil-spirv/tree/8434b0639fb2a48ce13aac08a420ecce5d23df0e),
  **plus** [`phi-backedge.patch`](f1-25/phi-backedge.patch).
- Patch/source license and attribution:
  [`LICENSE.dxil-spirv`](f1-25/LICENSE.dxil-spirv).

Unmodified 2.75.0 fixed a duplicated loop merge target but still emitted one PHI
with six inputs for seven predecessors. The local patch includes the resolvable
back-edge input and rejects an intermediate frontier whose back-edge value
cannot be resolved. It does not invent a general cyclic SSA solution.

Build prerequisites include Git, C/C++ tools, CMake/Ninja, Meson, the MinGW-w64
cross compiler/tools, glslang/Vulkan headers and a suitable `widl`/Wine development
setup. Consult the pinned upstream build instructions for the complete toolchain.
Install missing build tools deliberately using the distribution's package
workflow; do not replace the working runtime just to experiment.

In a **new scratch workspace**, with `SETUP_REPO` set to this checkout:

```sh
# Review/set both paths. Do not run inside the private working runtime.
SETUP_REPO="$HOME/Work/arch-setups"
WORK="$(mktemp -d "$HOME/f1-25-source.XXXXXX")"
PATCH="$SETUP_REPO/docs/gaming/f1-25/phi-backedge.patch"

(
  set -e
  git clone https://github.com/HansKristian-Work/vkd3d-proton.git "$WORK/vkd3d-proton"
  git -C "$WORK/vkd3d-proton" checkout --detach af89350cc2eacd9da2293fbae96bd9ab4987c9bb
  git -C "$WORK/vkd3d-proton" submodule update --init --recursive
  DXIL="$WORK/vkd3d-proton/subprojects/dxil-spirv"
  git -C "$DXIL" checkout --detach 8434b0639fb2a48ce13aac08a420ecce5d23df0e
  git -C "$DXIL" submodule update --init --recursive
  git -C "$DXIL" apply --check "$PATCH"
  git -C "$DXIL" apply "$PATCH"
  sha256sum "$DXIL/cfg_structurizer.cpp"
)
```

Stop on any failed command. The resulting source hash must be:

```text
90a34e107e2c7bc7ae903e44acb89144dd2c69af88bcb9c683744f69b1a52e87
```

For native compiler diagnosis, the recorded CMake settings included
`-DCMAKE_BUILD_TYPE=RelWithDebInfo -DDXIL_SPIRV_CLI=ON`; the CLI target is
`dxil-spirv`. This native Linux converter is **not** the PE DLL used by the game.
To produce the 64-bit Windows DLL, use VKD3D's pinned cross-build procedure:

```sh
(
  set -e
  cd "$WORK/vkd3d-proton"
  meson setup --cross-file build-win64.txt --buildtype release build.64
  ninja -C build.64
  find build.64 -type f -name d3d12core.dll
)
```

If the toolchain needs extra configuration, resolve it using the
[pinned upstream build instructions](https://github.com/HansKristian-Work/vkd3d-proton/blob/af89350cc2eacd9da2293fbae96bd9ab4987c9bb/README.md#building-vkd3d-proton).
Do not substitute a native `libvkd3d-proton.so` for `d3d12core.dll`.

Clone an official GE-Proton11-7 runner into a **new, dedicated candidate** and
replace only its
`files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll` with the rebuilt PE DLL.
The official archive version/digest is recorded in
[`assets.json`](../../gaming/denuvowo/assets.json). Do not alter Steam's shared
runner, the shared installer's runner or the preserved known-good copy. Use a
separate candidate prefix/launcher and record the rebuilt DLL's hash. A different
build may have a different binary hash; validate it before deliberately updating
its candidate hash checks. Proton normally propagates the DLL into its prefix;
verify the loaded/prefix copy rather than assuming a disk replacement was used.

Historical validation passed all 2,357 captured DXIL inputs with no structural
validity regressions; the formerly failing in-game output also passed
`spirv-val --target-env vulkan1.3 --scalar-block-layout`. Those private shader
inputs are **not in Git**. If privately retained, use them for regression checks;
never claim the old corpus was rerun when it was unavailable. Validation proves
SPIR-V structure, not full shader semantic equivalence or gameplay correctness.
Do not upload game shaders, cores, saves or prefix data to document a rebuild.

## 9. Diagnose regressions without destroying the working profile

- **CPU preflight fails:** check this boot's `umip`/`cpuid_fault`, not just the
  presence of the optional entry on disk.
- **Executable unavailable:** inspect the mounted game disk and symlink target;
  do not install another repack over the existing directory as a first step.
- **Runtime hash mismatch or compute-pipeline/shader exception:** verify the
  selected private runner and actual `d3d12core.dll`. A shared Proton update or
  stale prefix is not evidence the patch stopped working.
- **Long startup, high kernel CPU, little game-file I/O:** compare the selected
  runtime against the v2 hash; the old export-reading path explained the recorded
  delay. Do not fix it by disabling the CPU handling indiscriminately.
- **Window disappears on Alt-Tab:** check minimization/borderless settings before
  calling it a crash or spawning duplicate instances.
- **Black lines visible physically but absent in screenshots:** these also
  affected other applications and were resolved by replacing the DisplayPort
  cable at 120 Hz HDR. No permanent 60 Hz workaround or shader change fixed them.
- **Already-running notification:** inspect the existing F1 session and lock
  owner; do not delete an active lock or kill unrelated Wine games.

The restored launcher writes per-session logs under `S/logs`. Its passive
watchdog stores bounded private snapshots under `S/diagnostics/watchdog`. While
an affected session is still open, request a snapshot with:

```sh
"$HOME/.local/bin/f1-25-capture-logs"
```

This does not restart or pause the game and is not a full debugger backtrace.
The watchdog never kills/restarts a game merely because it looks stuck. Historical
eight-minute diagnostic services timed out deliberately; the final game launcher
has no such game timeout. Review logs locally and redact sensitive data before
sharing any excerpt.

For rollback, close only the candidate session, restore its backed-up scripts,
XML and matching runtime as one set, and select the normal protected boot when
finished. Never clear the whole prefix or delete saves just to reset a cache.

## References and validation boundaries

Local recovery evidence, if preserved, lives at `R/fix-report.md`,
`S/README.md` and `S/verified-result.json`. The older shader report predates the
later working Steam/borderless setup; do not treat its old default-launcher
statement as the final launch configuration.

This documentation change checked the source patch against the exact pinned
upstream `cfg_structurizer.cpp` and confirmed the resulting source hash above.
It did **not** rebuild Proton, modify the bootloader/display, apply recovery
commands to the live installation, or launch a game. Private runtime recovery
and a new game's actual behavior must still be verified on the target machine.
