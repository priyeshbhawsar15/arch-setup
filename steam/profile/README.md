# Personal gaming profile

`../configure-gaming-profile.py` is the declarative restore step invoked by
`install-lutris.sh` (already registered in `install-all.sh`). Generic Steam sync
skips this profile's shortcut IDs, so it cannot turn direct Proton entries back
into Steam launchers or overwrite their DLL overrides.

## Restore / inspect

Close Lutris and all affected games before applying. The Steam installer also
requires Steam closed before its separate VDF configuration step.

```bash
# Read-only availability report: no downloads, writes, or game launches.
/usr/bin/python3 steam/configure-gaming-profile.py

# Restore launchers/settings only; no third-party DLL downloads.
/usr/bin/python3 steam/configure-gaming-profile.py --apply

# Full profile, including pinned experimental upscalers (install-lutris default).
/usr/bin/python3 steam/configure-gaming-profile.py --apply --upscalers

# Full machine entrypoint:
./install-all.sh
```

Dependencies: Lutris, Arch system Python/PyYAML/Pillow, desktop-file-utils and
7zip. `install-lutris.sh` ensures Lutris/7zip; the Lutris package supplies its
Python dependencies. Steam/Gamescope and `steam-gamescope-hdr` are managed by
`install-steam.sh` earlier in the entrypoint.

## Managed state

- `games.json` records thirteen local games, direct `wine`/`linux` runners,
  executable/working-directory paths, separate or reused Proton prefixes,
  environment variables, Gamescope/HDR wrappers, titles and existing release
  years. `${HOME}` expands for the installing user. External mount paths remain
  explicit: edit this file if disks move. Recorded `games-links` symlinks are
  restored only when their targets exist; conflicting local paths are preserved.
  Missing executables are reported and skipped, never replaced with broken launchers.
- Ten Lutris desktop entries (the remaining games other than Sims/HS2/KS) use
  IDs resolved from the destination database, not this machine's numeric IDs.
- Sims keeps `TS4_x64.exe` and gets no new desktop entry/artwork. HS2/KS retain
  their short names, no artwork/extra metadata, separate GE-Proton prefixes,
  `winhttp=n,b`, and 3840x2160 fullscreen in launch arguments and UTF-16-safe
  `UserData/setup.xml` edits.
- Existing official artwork is preserved. Missing artwork is fetched from the
  recorded official Steam image URLs; outages are reported, not fatal. Only
  title/year/artwork are managed, not descriptions, achievements or save data.
- AoE II launchers are `pbtrooper15 — Age of Empires II` and
  `The_Gremlin15 — Age of Empires II`. Their helper requires Steam to remember
  both accounts locally. It asks before gracefully restarting Steam to switch,
  waits for shutdown and backs up account-selection files privately. It never
  stores passwords in this repository, never imports sessions and never
  switches accounts as part of installing. Steam Guard may still be required.
- An existing `qBittorrent.desktop` is renamed to `qBittorrent Web`; its browser,
  URL and icon stay untouched. When absent, the recorded Omarchy webapp entry is
  restored; a generic browser icon is used if its original icon is unavailable.
- FC26/FC27 IDs are excluded from generic import, their Lutris rows retired and
  their three known desktop entries archived. This installer **never deletes
  game folders, prefixes, saves, or Steam shortcuts**. The original user-approved
  deletion was a one-time operation, not an action to replay on every install.

## Upscalers and provenance

Binaries are not committed. Explicit `--upscalers`/`install-lutris.sh` downloads
these exact GitHub assets into `~/.cache/arch-setups/gaming`, verifies SHA256
against `games.json`, then extracts without running upstream installers:

- OptiScaler v0.9.4, asset `Optiscaler_0.9.4-final.20260718._MM.7z`:
  https://github.com/optiscaler/OptiScaler/releases/tag/v0.9.4
- FSR4VK v0.4.3, asset `fsr4vk-v0.4.3.zip`:
  https://github.com/dvj5411/fsr4vk/releases/tag/v0.4.3
- FSR4VK's base dependency package, OptiScaler nightly-20261020, asset
  `OptiScaler_v10.0.0-pre1_20261020.7z`:
  https://github.com/optiscaler/OptiScaler-nightly/releases/tag/nightly-20261020

The INI templates are upstream configuration, not plugin source forks:
`OptiScaler-0.9.4.ini` comes from the v0.9.4 archive; the FSR4VK template is
from `dvj5411/OptiScaler` commit
`613492a8909929dfd618b03df08e47b07055c0b0`.
Upstream licensing/attribution: OptiScaler is GPL-3.0; FSR4VK's mixed licensing
is documented in its repository and release `LICENSES` directory. Downloaded
packages retain their upstream license files in the archive/cache.

- Halo, Cyberpunk 2077, Ghost of Tsushima and Death Stranding 2: upstream
  v0.9.4 FSR 4.1.1 INT8 workaround, native `dxgi` override.
- RDR2: FSR4VK custom host and Vulkan INT8 provider, existing native overrides
  preserved, Vulkan FSR inputs enabled. Keep Vulkan selected in-game; choose
  FSR 3.X / FSR 4.1.1 VK INT8 in the overlay.
- Defaults: Backspace overlay, explicit overlay enable, high-quality fonts off,
  watermark/logging on. Existing `OptiScaler.ini` files are **not overwritten**:
  tuning saved from the in-game menu remains user-owned. To reseed defaults,
  close the game and move its INI aside, then rerun with `--upscalers`.
- Existing Gamescope/HDR wrappers remain enabled. If an overlay fails, test
  without Gamescope; its menu visibility is not proof of FSR4 execution.
- These are unsupported experiments on RDNA2. Halo was user-confirmed working;
  installation of the other games is not a claim of runtime validation. Enable
  an in-game upscaler and verify the FSR4-i8/provider indication rather than an
  internal FSR3 fallback. Frame generation is not newly enabled by this setup.
- Offline/single-player only where DLL injection is permitted. Do not use these
  mods with anti-cheat-protected online play.

## Prerequisites this repo cannot recreate

Supply legally obtained game installations and their expected mounts,
Steam-owned Proton Experimental/Proton 10, and GE-Proton11-7-x86_64 separately.
The installer does not copy commercial game files, distribution-specific game
patches, Steam tokens, prefixes, saves, or NVIDIA model DLLs into Git.

F1's existing custom `~/.local/bin/launch-f1-25-4k` and its shader-fix/private
runtime are external prerequisites, not something this conversation added or
an OptiScaler target. The profile restores its Lutris entry/artwork only when
that launcher exists. Rebuilding that runtime needs its original source and
provenance; this profile deliberately does not vendor its private binaries.

## Backups, updates and checks

Changed files/database rows are backed up under
`~/.local/state/arch-setups/backups/gaming-<timestamp>/`; existing modes and
unmanaged YAML/environment settings are preserved. Unchanged reruns do not
rewrite files. Backups of an already-modded installation reflect that state,
not pristine game files. Keep the original one-time test backups under
`~/.local/share/lutris-backups/` and the existing `restore-*-upscaler` helpers
if you need to undo the original manual installations. No installer is run on
the live machine merely by editing this repository.

To update, explicitly change the version, asset URL and verified SHA256
together, review upstream compatibility, and test offline before changing the
profile. Never substitute a `latest` URL or disable checksum verification.

```bash
/usr/bin/python3 -m unittest discover -s steam -p 'test_*.py'
bash -n install-lutris.sh
```
