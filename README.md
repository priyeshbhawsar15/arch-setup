# Reproducible Omarchy setup

Install a **selected** setup, not every historical customization from another machine. The default is a safe application profile: no selected games, experimental DLLs, private widgets, fixed monitor topology, system-wide key remap or account enrollment.

## Start here

```bash
./install-all.sh --plan
./install-all.sh
```

Run as your normal desktop user, not root. Supported baseline: Omarchy 4.0.4+ with Bash, Python 3, Git, coreutils, diffutils/cmp, util-linux/flock and mise. Missing applications use Omarchy package/browser commands. Pins freeze plugin source, not the rolling Arch package universe; new platform versions still need compatibility testing.

The first command validates inputs and shows the selected/skipped installers and game changes **without writing state, downloading, or running installers**. Apply runs read-only preflight first, stops on an installer failure, and finishes with readiness checks. Exit 1 means an error; exit 2 means pending external integration/game prerequisites at final acceptance. Neither is success.

A new ISO may have no online package indexes. Before any installers run, setup then requests confirmation for Omarchy's initial snapshot/keyring/**full system-package upgrade**/migration stages. For explicitly approved automation use `--approve-system-update`; this is not a database-only partial upgrade. Existing indexed systems are not automatically updated. Setup never chooses a reboot: exit **3** means reboot/log in and rerun; an interrupted initial update is remembered and must finish before applications are installed.

See [SCRIPTS.md](SCRIPTS.md) for every script, prerequisites and system changes, and [PLUGINS.md](PLUGINS.md) for plugin sources, exact pins, behavior, conflicts and lifecycle controls.

## Choose your setup

- `features.json`: safe default selection.
- `profiles/personal.json`: fuller personal desktop/apps, but still **no games selected**.
- `monitor-layout.json`: existing three-display desktop preset, with modes/scale/HDR/workspaces now in policy data.
- `profiles/laptop.json`: portable primary-display policy, no side displays/HDR/spanning.
- `gaming/selection.json`: empty default game selection.
- `profiles/gaming.example.json`: example library mapping plus one explicitly selected game. `/mnt/games` is only an example you must replace, not a required mount.

Custom feature profile:

```json
{
  "schemaVersion": 1,
  "enabledInstallers": ["install-stow.sh", "install-steam.sh", "install-lutris.sh"],
  "disabledInstallers": []
}
```

Use registered `install-*.sh` names from `config/features.json`, including required installers in an explicit `enabledInstallers` list. Missing explicit dependencies, unknown keys/names and malformed local state are errors. Remembering a disabled dependency skips its dependents with a reason; the runner does not secretly enable it. `config/plugin-sources.json` records exact source locks; run `python3 config/check-source-contracts.py` manually to check agreement with the installer declarations.

```bash
./install-all.sh --profile /path/to/selected-features.json --plan
./install-all.sh --profile personal --host profiles/laptop.json \
  --dotfiles-dir /path/to/dotfiles --games /path/to/games.local.json \
  --settings /path/to/settings.local.json --plan
# Remove --plan only after reviewing the result and satisfying preflight.
```

Selecting the entire personal profile requires its documented private sources, configured executor, dotfiles and desktop prerequisites; the safe profile deliberately does not. `--planner-config FILE` (or `T3_PLANNER_EXECUTOR_SEED_CONFIG`) selects your own workflow provider/model seed instead of the personal `t3/planner-executor.json`; existing explicit runtime values remain preserved. Preflight checks the chosen executor, not a universal Pi assumption. Provider/model authentication and actual task dispatch still need acceptance. You can start with a smaller selection instead.

### Remembered enable/disable choices

Successful explicit plugin install/re-enable, `--disable`, or `--remove` commands persist booleans in `${XDG_STATE_HOME:-~/.local/state}/arch-setups/features.json`. Failed commands do not change the preference. Automatic setup does not replace those choices. Remembered choices override profiles; use `--ignore-local-choices` when you deliberately want only a profile's selection.

```bash
./install-weather-widget.sh --disable
./doctor.sh --export-profile > /path/to/rebuild-features.json
```

An exported feature profile contains no credentials. A disabled feature is skipped on future full runs; **editing a selection does not uninstall already-installed software**. Use the plugin's lifecycle control to stop existing behavior. Install/re-enable most plugins with their no-argument installer; T3 Planner-Executor additionally provides `--enable`.

## Game drives and graphics are explicit inputs

Configure `libraries` and `games` in your own selection; no particular username, volume label, drive UUID or game set is required. No drives are formatted or mounted automatically. The catalog contains launch templates, not a mandatory installation list.

```json
{
  "schemaVersion": 1,
  "libraries": {"primary": "/your/game/library"},
  "games": {
    "cyberpunk-2077": {
      "library": "primary",
      "path": "Cyberpunk 2077",
      "required": false,
      "hdr": false,
      "upscaler": "none"
    }
  },
  "importSteam": false,
  "steamHdr": false
}
```

Omitted/disabled games remain unmanaged. Without a selected/remembered Steam-first export, an empty selection creates no personal launchers, game links, retirements or DLL modifications. Optional `exportSteam: true` (or `./install-lutris.sh --export-steam`) makes Steam the frontend while retaining Lutris configurations as the backend; see [Steam-first library](steam/STEAM-LIBRARY.md). Do not combine it with the reverse `importSteam` workflow. `importSteam` separately opts into generic library import; `steamHdr` opts into broad Steam launch wrapping. Per-game HDR needs an explicit `resolution`; artwork and upscalers require explicit per-game selection. Existing foreign mods require a separate adoption decision. HDR opt-out removes still-owned launch settings; omitting a game stops management rather than automatically uninstalling its prior mods, prefixes or saved games. See [gaming configuration](steam/profile/README.md).

## Dotfiles and authorization

The separate dotfiles repository remains authoritative for Neovim, Starship, tmux and Zsh. Select `install-dotfiles.sh` with its Stow/Zsh dependencies and supply `--dotfiles-dir`; preflight checks all four packages before any installer runs. This repository does not duplicate those configurations or guess a private clone URL.

For private sources, authenticate and configure the actual Git transport before apply. For HTTPS, use an authorized `gh auth login` and `gh auth setup-git`; a successful CLI login alone does not configure SSH. SSH sources require keys, repository access and verified host trust. Source checks are bounded/noninteractive; exact clean local pinned sources can be reconciled offline.

Credentials, OAuth, game files, Workshop downloads, vaults, runner binaries and service pairing are external prerequisites. Never put tokens into a tracked profile. `--settings` accepts local secret-file references for supported widgets; those files must be user-only (0600), and generated runtime config remains private. See `profiles/settings.example.json`. Existing entity mappings and unrelated config are preserved. Local configuration presence is not proof that a remote service works; perform the documented connectivity/pairing acceptance.

## Verification and recovery

```bash
./preflight.sh
./doctor.sh --json
/usr/bin/python3 tests/run.py --require-system-tests
python3 config/check-source-contracts.py
```

Test dependencies: Python/PyYAML/Pillow, Git, Node.js, jq, Lua, Lutris/system GI, Bash and coreutils. GitHub Actions setup jobs have been removed; install these dependencies and run the checks manually as an unprivileged user. Private workflow integration is explicit:

```bash
/usr/bin/python3 tests/run.py --require-system-tests --require-integration \
  --integration-source /path/to/clean/pinned/t3-planner-executor
```

The source must match the exact registry pin and be clean. Missing sources cannot silently count as passing release integration. The default runner clearly reports that private integration was not selected.

Backups live under `${XDG_STATE_HOME:-~/.local/state}/arch-setups/backups/` unless a feature explicitly documents another private archive. Wallpaper replacement is staged and rolls back on activation failure. JSONC menu removal is structural, not line deletion. Other features retain per-feature recovery boundaries; this is **not** a global system transaction or automatic package rollback.

The safe application profile passed [real Omarchy 4.0.6 VM installation, password login, reboot and repeat-run checks](docs/reviews/vm-acceptance.md). The personal/custom-plugin profile, physical multi-monitor/DPMS/lock behavior, authenticated integrations and real games/HDR still need acceptance. See [the implementation follow-up](docs/reviews/implementation-status.md) for the full evidence and limits; the original [audit](docs/reviews/fresh-install-audit.md) is historical, not a description of the fixed tree.
