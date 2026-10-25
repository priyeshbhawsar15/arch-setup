# Opt-in gaming profiles

This directory is a **catalog of launch templates**, not the desired game list. Installing Steam or Lutris does not imply installing these games, importing a library, changing account sessions, forcing 4K/HDR or replacing DLLs.

## Selection and paths

The default `../../gaming/selection.json` selects nothing. Copy `../../profiles/gaming.example.json` to a local file, configure library roots and select only the games you want:

```bash
./install-all.sh --games /path/to/games.local.json --plan
# Or, for a direct read-only game plan:
ARCH_SETUPS_GAMING_PROFILE=/path/to/games.local.json \
  /usr/bin/python3 steam/configure-gaming-profile.py
```

The feature profile must also select Steam/Lutris if you want the entrypoint to install/configure them. No installer formats or mounts drives. `libraries` maps an arbitrary logical name to an absolute path (or `${HOME}/...`); each selected game uses a relative `path`. Changing username/mount location does not require modifying installer code or the catalog. Omitted/disabled games stay unmanaged; an absent game is not excluded from generic Steam import simply because its ID appears in the catalog.

Catalog IDs are each entry's `slug` in `games.json`. Existing numeric shortcut IDs are legacy matching hints, not library roots or the default Wine prefix identity. New prefixes default to `${HOME}/.local/share/wineprefixes/arch-setups/<slug>`; use `prefix` explicitly if an existing prefix/saves should be reused. Review this before migrating a game with existing local saves. A different Steam shortcut ID remains a separate import until deliberately associated; setup does not guess across accounts.

Per-game fields:

- `enabled` (boolean, default true when listed); disabled entries need no library.
- `library` and relative `path` (required for selected games).
- `required` (default false): missing required executable blocks preflight; an absent optional game is deferred and final acceptance reports pending.
- `prefix`: optional absolute Wine-prefix override; `wineVersion`: optional Lutris runner name. Install that Proton/GE-Proton runner separately. Doctor checks availability without choosing a fallback runner.
- `desktop`: override the template's launcher preference. No personal AoE2-account or qBittorrent launchers are generated.
- `hdr` (default false): requests the managed HDR Gamescope wrapper. Requires `resolution: [width, height]`; e.g. `[2560, 1440]`. No universal 4K/120Hz assumption.
- `artwork` (default false): allows missing official artwork downloads from the template URLs.
- `upscaler` (default `none`): explicit compatible template choice, currently `optiscaler-094` or `fsr4vk-043` where supported.
- `allowModReplacement` (default false): separately authorizes adoption/replacement of foreign/modified mod files. Inspect the game's files first; a backup is not evidence that replacement is safe.

Global `exportSteam: true` selects the opposite, Steam-first library/Omarchy launcher workflow; see [Steam-first library](../STEAM-LIBRARY.md). It retains Lutris configurations as the non-Steam launch backend and requires both clients closed. The explicit `./install-lutris.sh --export-steam` option additionally enables artwork enrichment and remembers the preference locally. Do not combine it with `importSteam`; the installer rejects reverse-sync loops. Neither is selected by the empty default.

Global `importSteam: true` opts into generic installed Steam games/shortcuts import; it does not select catalog games. Global `steamHdr: true` opts into broad Steam launch wrapping; it is independent of per-game HDR and requires Steam to be closed for VDF edits. Existing explicit Gamescope settings are user-owned and remain unchanged. The owned HDR helper uses per-game dimensions or the focused output for direct Steam launches.

## Ghost of Tsushima HDR diagnostic

The local OLED reported HDR and Gamescope used `--hdr-enabled`, but Ghost logged only `DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709` and `HDR: No`. A backed-up local diagnostic selects separately installed `GE-Proton11-7-x86_64` and explicitly supplies `PROTON_ENABLE_HDR=1`, `ENABLE_HDR_WSI=1`, `DXVK_HDR=1`, plus 3840×2160 dimensions. Restart and verify the in-game HDR option; this is not yet a confirmed fix. For reproducible opt-in selection use `ghost-of-tsushima` with `wineVersion: "GE-Proton11-7-x86_64"`, `hdr: true`, and `resolution: [3840, 2160]`. Local pre-test YAML is retained alongside the active Lutris configuration as `*.bak-hdr-*`.

## Death Stranding 2 OptiScaler diagnostic

On the current machine, the installed `amd_fidelityfx_upscaler_dx12.dll` reports file version `4.1.1.2740` / product `4.1.1.0`; this identifies the library, not successful FSR4 execution. Bypassing native DXGI/OptiScaler restored the picture. A reversible diagnostic now tests `GE-Proton11-7-x86_64`, `WINEDLLOVERRIDES=dxgi=n,b`, and OptiScaler `[FrameGen]` values `Enabled=false`, `FGInput=nofg`, `FGOutput=nofg`, retaining the INT8 option. It is not yet a verified catalog preset. Local YAML/INI originals are archived under `~/.local/state/arch-setups/backups/ds2-optiscaler-test-*`. Restore them to undo the test; do not infer FSR4 activation from a menu label or loaded DLL alone.

## Death Stranding 2 at 4K

`profiles/gaming.example.json` includes an opt-in `death-stranding-2` example with `hdr: true` and `resolution: [3840, 2160]`. Set its library/path to the installed game and use that selection with `install-lutris.sh`. This supplies `ARCH_SETUPS_GAME_WIDTH=3840` and `ARCH_SETUPS_GAME_HEIGHT=2160` to the Gamescope HDR wrapper, independently of desktop scaling. Select 3840×2160 in the game's display menu as well; this does not force its internal rendering scale. Restart the game after changing launch settings. Omit this example entry if unwanted; the default selection remains empty.

## Halo capture and engine settings

Halo's catalog runner is `GE-Proton11-7-x86_64` (install separately; `wineVersion` can override it). The observed Experimental session could not load its GStreamer libav plugin because `libavfilter.so.7` was missing, coinciding with black prerecorded cutscenes. GE bundles FFmpeg libraries; playback still needs in-game verification after restarting. The existing prefix/saves are retained; no codec packs or registry edits are applied. Set `wineVersion` back to `Proton - Experimental` to undo the runner choice.

The incoming Halo profile is retained as an opt-in: selecting `halo-campaign-evolved` with `hdr: true` and `resolution: [3840, 2160]` requests its original 4K/HDR preset. Other resolutions work too. The Gamescope helper honors `HALO_GAMESCOPE_CAPTURE=1` for relative cursor capture (use `0` in its launch environment to disable); Halo uses XWayland inside Gamescope, without another host `confine_pointer` rule. Mouse recovery after wallpaper changes remains unverified.

An explicit Halo `resolution` also manages dimensions and borderless mode in the existing prefix's `drive_c/users/steamuser/AppData/Local/Meteorite/Saved/Config/Windows/GameUserSettings.ini`. Only `hdr: true` requests `bUseHDRDisplayOutput=True` and Proton HDR. Selecting Halo alone does not alter that INI or enable HDR. Launch once if the INI is absent, then rerun; malformed/ambiguous sections and symlinked files are refused. Encoding, line endings and unrelated settings are preserved. Restart the game and verify actual HDR/input behavior on hardware. To undo engine preferences already applied, restore the private original backup; removing HDR from the selection removes still-owned launcher/env settings, not arbitrary engine preferences.

## Apply and recovery

```bash
ARCH_SETUPS_GAMING_PROFILE=/path/to/games.local.json ./install-lutris.sh
# Manual lower-level apply (Lutris database must already be initialized):
/usr/bin/python3 steam/configure-gaming-profile.py --profile /path/to/games.local.json --apply
# Add --upscalers only to apply the mods already explicitly selected in that file.
```

Close Lutris and affected games first. The installer uses Arch's `/usr/bin/python3` for system Lutris/GI/YAML modules. Actual Lutris settings determine the database and config directory: both legacy `.config/lutris` and newer `.local/share/lutris` layouts, XDG locations and configured database overrides are supported. A positively selected misplaced historical YAML is archived only after a correct configuration is written. Existing unrelated YAML settings are merged/preserved; unknown configpath traversal is refused. Private ownership snapshots in the selected state home's `arch-setups/games/` track the managed fields. Opting out of HDR removes still-owned launcher/environment values rather than leaving them stuck through merging; intervening user changes to removed fields are preserved.

No games, saved games, Steam login tokens, account credentials or private runtime binaries are stored here. No game/account is retired merely by installing Lutris. Existing personal launchers previously created are left alone rather than removed without explicit ownership/adoption.

Modified files and database originals are backed up under `~/.local/state/arch-setups/backups/gaming-*` (using the selected state home for normal deployment). Files are atomically replaced, but the database, launchers and game directory are **not one global transaction**. Review the backup if a multi-file operation fails. Upscaler ownership hashes are private under `~/.local/state/arch-setups/mods/`; preserve those when rebuilding if you want managed-update recognition. Upscaler tuning INI files remain user-owned after initial creation; explicitly selected Halo engine-display fields are managed while configured. Omitting a game or choosing `upscaler: "none"` does not automatically uninstall previously deployed DLLs or undo engine settings; review and restore the recorded backups deliberately. Never delete foreign mods, prefixes or saves as an implicit side effect of deselection.

## Third-party assets and boundaries

`games.json` records exact versioned URLs and SHA256 values for the OptiScaler/FSR4VK assets; the checked-in INIs are templates. No mutable latest URL is used. The checks establish artifact identity, not compatibility, legitimacy of a game installation, anti-cheat safety or online-game support. These are explicit offline/single-player experiments. Foreign mods are refused by default, and existing user tuning is not blindly replaced. A direct manual `--apply` without `--upscalers` avoids DLL downloads.

The F1 template references an explicitly supplied external launcher directory; it does not fabricate the private optimized runtime. The [F1 recovery runbook](../../docs/gaming/f1-25-recovery.md) remains manual reference material. Shared LinUwUx support is independent: see [DenuvOwO runtime](../../gaming/denuvowo/README.md).

Tests include empty selection/no side effects, library paths with spaces, unavailable-game import ownership, explicit HDR/mod choices, foreign-mod refusal, dynamic desktop IDs, checksum failure, idempotency, and loading generated configuration through Lutris in both directory layouts. Run `/usr/bin/python3 tests/run.py` from the repository root. Launching real games and validating HDR/Proton/upscalers on hardware remain user acceptance, not unit-test claims.
