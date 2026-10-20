# Shared DenuvOwO launch support

`../../install-linuwux.sh`, also registered in `install-all.sh`, installs shared
LinUwUx + GE-Proton/UMU launch support for selected DenuvOwO games. This is not
an individual game's graphics profile or a guarantee that every title works.

## Installation and provenance

Run as your normal desktop user:

```sh
./install-linuwux.sh
```

The installer requires x86-64 Arch/Omarchy, Bash and Python 3.12+. It installs
`umu-launcher` through `omarchy pkg add` only if `umu-run` is missing. UMU uses
the distribution package version and dependencies. This does not require Lutris;
its private bundled UMU is not overwritten. Package installation can request
administrator authentication; runtime files are installed without root.

`assets.json` pins official release downloads and their GitHub-published SHA256:

- **LinUwUx v26.09.28.4**, upstream
  <https://github.com/brcly/linuwux-runtime/tree/v26.09.28.4> (AGPL-3.0).
- **GE-Proton11-7, x86-64**, upstream
  <https://github.com/GloriousEggroll/proton-ge-custom/releases/tag/GE-Proton11-7>.
  Its archive retains the upstream license files.

Downloads are checksum-verified before use. The LinUwUx file must be an x86-64
ELF shared object. Proton extraction uses Python's safe data filter and checks
the archive layout and runner files. No runtime binaries or game files are
committed. No remote installer is piped into a shell. Initial setup downloads a
large Proton archive; matching reruns make no network requests or file rewrites
and print `already installed`.

Installed paths:

- `~/.local/bin/linuwux`: reusable command-prefix wrapper.
- `~/.local/bin/launch-denuvowo`: generic per-game launcher.
- `~/.local/share/linuwux/LinUwUx.so`: shared upstream runtime.
- `~/.local/share/arch-setups/denuvowo/GE-Proton11-7-x86_64/`: dedicated runner,
  separate from Steam's installed tools.
- `~/.local/share/arch-setups/denuvowo/runtime.json`: local install metadata.

Changed existing wrapper/library files are backed up with permissions preserved
under `~/.local/state/arch-setups/backups/linuwux-<timestamp>/`. Managed symlinks
and unknown existing Proton directories are refused rather than overwritten.
The shared `linuwux` wrapper/library may be replaced on installation; close
launchers/games first and review backups if you previously customized them.
The installer does not run any game or initialize any Wine prefix.

## Use with any selected game

Give every game its own stable ID. Paths with spaces are supported for games;
`HOME` must contain no whitespace or colons because of `LD_PRELOAD` syntax.

```sh
~/.local/bin/launch-denuvowo my-game "/path/to/My Game/Game.exe"
# Optional arguments are passed as separate, unchanged arguments:
~/.local/bin/launch-denuvowo another-game "/path/to/Other.exe" -windowed
```

The launcher uses `~/.local/share/wineprefixes/denuvowo/<game-id>/`, ignoring any
inherited `WINEPREFIX`. Reusing an ID deliberately reuses that prefix, so never
share an ID between different games. Existing prefixes elsewhere are untouched.
The working directory is the executable's directory. Steam's application IDs
are removed only from this child's environment so external UMU owns its launch.
UMU's default `GAMEID=umu-default` avoids selecting another title's fixes; set
`DENUWOWO_GAMEID=umu-<supported-id>` explicitly for an appropriate UMU database
entry if needed. An explicit absolute `PROTONPATH` can select another runner;
otherwise the pinned dedicated runner is used.

For a non-Steam shortcut, use `~/.local/bin/launch-denuvowo` as the target and
`my-game "/path/to/Game.exe"` as its arguments. Do **not** force a Steam Proton
compatibility tool on that native launcher: UMU selects Proton internally. This
setup does not create or edit Steam shortcuts automatically.

For an existing Steam Windows game, the standalone command prefix is:

```text
/home/USERNAME/.local/bin/linuwux %command%
```

Select the desired Proton tool in Steam as usual. The prefix wrapper also works
in Lutris's **System options → Command prefix**. It preserves unrelated
`LD_PRELOAD` entries, avoids adding LinUwUx twice, and removes inherited Steam
overlay preload entries only when wrapping Gamescope, matching upstream guidance.

Extra compatibility flags remain per-title opt-ins; none are enabled globally.
Host CPU/kernel compatibility remains subject to the upstream runtime's support.
This installer changes **no kernel, bootloader, monitor, HDR, resolution, FPS,
VSync, fullscreen, controller, shader-cache, overlay, game-file or save settings**.
It adds no game-specific launcher, watchdog or automatic service.

## Updates and removal

To update, review upstream releases, change the exact version/URL/digest in
`assets.json`, and rerun the installer. There is no `latest` resolution or silent
background updater. Existing managed Proton versions and prefixes are retained.

To stop using this setup, remove its command prefix from affected launchers,
remove `install-linuwux.sh` from the `install-all.sh` list, and delete the two
installed wrappers and the dedicated runner directory when no game uses them.
Restore the prior shared wrapper/library from the backup if one existed; do not
remove a shared library another launcher still uses. Prefixes and backups are
never automatically removed; retain or archive them to preserve saves. Leave the
system UMU package installed if other applications use it.

## Offline validation

```sh
python3 -m unittest discover -s gaming/denuvowo -p 'test_*.py'
bash -n install-linuwux.sh gaming/denuvowo/linuwux
```

Tests use temporary homes, small generated archives, mocked downloads and fake
UMU commands. They do not install packages, download Proton, touch live games,
change boot settings or launch a real Windows game.
