# Steam-first library and Omarchy launchers

Steam provides the game-library frontend; the Lutris application is also available in the
Omarchy launcher. Lutris remains installed as the launch backend for
its non-Steam games, preserving each live YAML configuration: prefix, Wine/GE-Proton,
arguments, environment, working directory, Gamescope/HDR wrapper and mods. This is not a
conversion of Wine prefixes to Steam prefixes or an uninstall of Lutris.

## Install, preview and reproduce

Prerequisites: native Steam and Lutris with their libraries configured, Lutris's Python
modules/PyYAML (included with Lutris), and an existing logged-in Steam userdata directory.
No API token is required. Do not run while games, Steam or Lutris are open.

```
# Read-only preview, automatically selecting the active account:
/usr/bin/python3 steam/export-lutris-steam.py
# Explicit account selection is a Steam userdata directory ID, not a username:
/usr/bin/python3 steam/export-lutris-steam.py --account 123456789
# Close Steam and Lutris, then apply and remember this preference:
./install-lutris.sh --export-steam
# Reconcile app visibility and AoE launcher duplicates only (Steam may stay open):
/usr/bin/python3 steam/export-lutris-steam.py --apply --launchers-only
```

The explicit installer option exports all installed source entries, adds available artwork,
and records `~/.config/omarchy/steam-library.json`. Subsequent `install-lutris.sh` calls
(including the single `install-all.sh` entrypoint) reconcile after selected source profiles
are configured. They require Steam/Lutris to be closed when this preference is enabled.
The normal safe base remains unmodified unless export is selected or remembered.

For a fresh installation select `install-steam.sh` and `install-lutris.sh`, configure/restore
the source Lutris library and Steam account, and set `"exportSteam": true` in the external
gaming selection passed with `./install-all.sh --games /path/to/games.json`. Use the explicit
export command above to additionally request artwork and remember the local preference.
Account IDs, local game paths, database contents, saves and personal preferences are not
committed. Export cannot fabricate missing games/prefixes/runners from an empty system.

`importSteam` and `exportSteam` are opposite workflows; do not enable both. The installer
also refuses a reverse import when the remembered Steam-first preference is enabled, before
it can overwrite the Lutris source configuration with the new Linux launcher target.

## What changes

- Existing non-Steam shortcut IDs are preserved, including signed/unsigned ID handling.
  Match by the source legacy shortcut ID, exact executable, or Lutris URI; ambiguous
  duplicates and new-ID collisions are refused. New entries use deterministic IDs.
- Non-Steam targets become `/usr/bin/lutris lutris:rungameid/ID`, the native Lutris export
  convention. Existing shortcut tags/playtime/unknown fields are preserved; readable
  titles and a `Lutris backend` tag are added. Forced Steam Proton overrides for these
  IDs alone are removed: running the Linux Lutris executable inside Proton is incorrect.
- Steam-native source entries stay native Steam apps and do not become Lutris shortcuts.
- Names, icons, portrait covers, horizontal artwork, heroes and logos are populated where
  available. Existing custom Steam artwork is never replaced. Local Lutris art is preferred,
  with maintained catalog URLs and public Steam CDN artwork as optional fallback. Sources
  are allowlisted and downloaded content is bounded/validated as JPEG or PNG. Artwork
  copies have SHA256 records under the private state directory.
- Steam does not support official store descriptions, achievements, DLC entitlements or
  ownership metadata on arbitrary non-Steam shortcuts. Artwork does NOT turn a shortcut
  into an owned Steam copy; official IDs are used only for public artwork lookup.
- `~/.local/share/applications/steam-library-*.desktop` entries launch through Steam.
  Non-Steam URIs use the full 64-bit game ID, not just the 32-bit shortcut ID.
- Existing recognized `lutris-*.desktop` game entries are hidden, not destroyed. The
  tracked `steam/launcher-policy.json` keeps the main Lutris app visible. Its file-handler
  entry retains `NoDisplay=true` so it does not create a second Lutris application icon.
  Package-managed desktop files are untouched; later exports preserve this visibility.
- The same policy archives recognized `aoe2-*.desktop` account-switching shortcuts only
  when a standard AoE launcher exists. It hides additional direct native Steam entries
  for app 813780 when the managed canonical entry is valid, leaving one visible AoE entry.
  Unknown custom commands, account data and the account-switching helper are preserved.
  The policy runs during exports and via `--apply --launchers-only`; that restricted action
  edits no Steam VDF/library files and does not require closing either client.
- Existing matching Omarchy gamepad-wheel Steam actions are corrected to full game IDs;
  unrelated menu entries, colors and settings remain intact. The wheel is not filled with
  every game; all exported games appear in the normal applications launcher.
- Nothing adds a second Gamescope layer. Steam starts Lutris natively; the game uses its
  existing Lutris wrapper. Do not force a Steam compatibility tool on these shortcuts.

`steam/metadata-policy.json` records reproducible visual exclusions and explicit removals.
Sims 4 (`ts4_x64exe`) and KS retain their original source titles, empty shortcut icons and
no generated backend tag; artwork enrichment is skipped. Previously generated artwork is
backed up/removed only if its ownership hash still matches; user-modified art is preserved.
HS2 is explicitly removed from Steam and its managed launcher, including when a restored
Lutris database still says installed. Reinstalling HS2 requires deliberately clearing that
removal policy. These visual changes do not revert the remaining games' launch integration.
`--no-artwork-downloads` applies the policy without fetching new artwork for other games.

An unavailable source executable is otherwise reported but its library entry is retained. Correct the
source configuration or reconnect the game drive; the exporter will not guess a different
executable, remove saves or download games. Games without available artwork remain usable
with generic icons; missing public hero/logo artwork is nonfatal and explicitly reported.
Launching through Steam does not guarantee overlay/controller compatibility in every game.

## Backups, disabling and recovery

Every changed existing file is privately backed up under
`~/.local/state/arch-setups/steam-library/backup-*`, preserving absolute paths below that
folder. `changes.jsonl` records changed/new destinations. Configuration edits are atomic,
but the whole migration is NOT a global transaction; inspect the backup if a later step
fails. Close Steam/Lutris before any restoration. Never blindly overwrite a newer Steam
configuration: it may contain later library changes or login/session updates.

To stop future reconciliation set `enabled` to false in `steam-library.json` and disable
`exportSteam` in your selected gaming input. This does not destructively undo launchers or
shortcuts. To undo the migration, deliberately restore the affected shortcut/config/menu
and desktop files from the first relevant backup, and remove only newly created paths
listed in its manifest after checking they have not since changed. Retain the backup and
original prefixes. Lutris is now visible by policy; set `showLutris` in `launcher-policy.json`
if changing that preference intentionally. Account-launcher retirement and native-ID
deduplication are separately configurable there. Never delete package-managed files
under `/usr/share/applications`.

## Recorded acceptance

Initial migration retained 11 non-Steam IDs and added 3 missing entries. After the requested
follow-up, HS2 was removed from Steam/the launcher and its source database installed flag
was set to 0 after a SQLite backup (remaining YAML/prefix files retained). There are now
13 non-Steam shortcuts targeting existing Lutris configurations plus 4 native Steam entries;
the normal launcher exposes 17 Steam-backed entries. Sims 4 and KS visual metadata were
restored to the original `TS4_x64.exe` and `KS` titles with empty icons/tags and no generated
artwork, while keeping their working backend targets. Following the launcher-policy update,
Gio reports one visible Lutris application, no old Lutris game entries, and one standard AoE
entry. Both account-specific AoE launchers were backed up/removed and the extra native
Steam-generated desktop entry was hidden; no Steam library entry or login account was removed.
All source Lutris YAML hashes were unchanged. Selected shortcuts have no forced Proton
mapping. Steam was gracefully closed and reopened with `-silent` after applying.

The initial 42 artwork files were reduced to 38 after backing up/removing the 4 generated
Sims 4 assets. Metadata enrichment is intentionally excluded for Sims 4/KS/HS2. Missing
optional art elsewhere: Epic hero/logo, Death Stranding 2 hero/logo, Halo logo and F1 logo.
These are reported limitations, not verified successful launches. The other Steam account was not modified.

Twelve migration/launcher fixtures, eleven selection tests and five feature-profile tests passed.
The broader Steam suite encountered five failures in the existing reverse-import/profile
integration tests due to this machine's Gtk/Gdk 3-versus-4 namespace conflict. Running the
unchanged HEAD reverse-import script reproduced the same error; this export path does not
use that GUI-dependent importer. That separate compatibility issue remains unresolved.

Fixtures cover stable IDs, metadata preservation, missing-entry idempotence, duplicate
refusal, scoped compatibility changes, correct launch URIs, hidden desktop entries, private
backups, unchanged source YAML and isolation of another Steam account. Actual game launch,
controller, overlay, HDR and performance remain hardware acceptance tests.
