# Fresh-install reliability and architecture audit

Reviewed revision: `1c5c975`. This is an analysis, not an implementation change. References below are relative to the repository root; line numbers refer to that revision.

## Verdict

**The repository is not currently a reliable one-command rebuild for a brand-new Omarchy installation.** It has useful building blocks, but mixes a general installer, a snapshot of one desktop's preferences, migration scripts, and incomplete integrations. Several failures are deterministic, not merely hypothetical portability concerns.

Keep the Bash entrypoint, per-software installers, Python configuration helpers, separate dotfiles repository, and pinned plugin repositories. A wholesale rewrite is unnecessary. The missing architectural layer is a validated **desired configuration** that separates reusable feature implementations from user choices, host hardware, credentials, and mutable application state.

A realistic success contract is: **given a supported Omarchy version, a selected profile, and explicitly supplied external prerequisites, every selected feature is verified operational; everything else is clearly skipped, blocked, or awaiting authentication.** Installing packages and exiting zero is not sufficient.

## Scope and verification

- Inspected the entrypoint, shared helpers, application/plugin installers, monitor deployment and runtime helpers, gaming configuration/synchronization, feature-state and diagnostic tools, relevant tests, and documentation.
- Checked the exact public Shibumi and Omaland pins remotely, rather than assuming their current upstream branches have the same APIs.
- Ran all five Python test suites with `/usr/bin/python3`: **161 discovered, 134 passed, 27 skipped, zero failures**.
  - `tests`: 99 discovered, 27 skipped.
  - `steam`: 23 passed.
  - `github`: 12 passed.
  - `t3`: 5 passed.
  - `gaming/denuvowo`: 22 passed.
- All repository `.sh` files passed `bash -n`. ShellCheck was unavailable.
- Additional temporary, isolated probes reproduced ignored feature selections, wrong Lutris paths, unwanted launchers with an empty game selection, missing backup helpers, unsafe menu removal, and the lock-state diagnostic gap.
- Test/probe logs for this review are in `/tmp/arch-setups-review-tests.sb3vke/`; these are temporary, not a durable project dependency.
- No installers ran against the live desktop. No packages, plugins, accounts, mounts, or desktop configuration were changed. Some existing monitor tests leaked fixture backups into the inherited host `XDG_STATE_HOME`; those exact test-created directories were removed afterward.
- This was **not** a clean-VM acceptance test. Private plugin implementations and their authenticated services were not exhaustively audited. Native live-wallpaper work already documented as unaccepted is not treated as a deployed feature.

## Findings

### 1. P1 — Shibumi's pinned source cannot satisfy its installer

**Evidence:** `install-shibumi-shell.sh:12–15,87–88,147–148,165,173–174`.

The installer pins upstream `7a6c853b1947d303bad9a5b640c224c01b669106`, requires `install --help` to advertise `--user-layout`, and passes that option to installation/activation. The exact upstream CLI has no such option. Its installer will stop with “the reviewed custom fork must be published and pinned before installation,” including on a fresh machine with all other prerequisites satisfied. Existing installations also hit the unconditional capability gate.

Verified source: [pinned Shibumi CLI](https://github.com/HANCORE-linux/Shibumi-Shell/blob/7a6c853b1947d303bad9a5b640c224c01b669106/scripts/shibumi_suite/cli.py), parser around lines 1392–1457.

**Fix:** Either use supported behavior at the upstream pin, or finish, test, and publish the required fork and then pin that source. Do not merely remove the safety check while retaining unsupported arguments. Validate install, activate, deactivate, repair, and uninstall against the actual selected release.

### 2. P1 — Omaland is also pinned to a source that fails its activation gate

**Evidence:** `install-omaland.sh:11–13,174–175`.

The installer requires `.archSetups.personalModule == "hypr/looknfeel.lua"`. The exact pinned upstream manifest has no `archSetups` field. Installation checks out the plugin, then exits nonzero before activation. This is a second independent blocker later in `install-all.sh`, not a consequence of the Shibumi failure.

Verified source: [pinned Omaland manifest](https://github.com/bobby-nicholas/omaland/blob/ec232b6aa2e31b2f089ad89b653cd706989865b9/manifest.json).

**Fix:** Decide whether the upstream implementation already meets the required personal-module behavior. If so, validate its actual supported contract; otherwise publish and pin the reviewed fork. Test the real manifest contract in CI.

### 3. P1 — Feature selection is mostly disconnected from execution

**Evidence:** `install-all.sh:7–49`; `features.json`; `config/feature-profile.py`; `lib.sh:157–166`.

`install-all.sh` does not read the feature profile, call preflight/doctor, or set the advertised automated-run flag. Almost all plugin installers neither consult nor remember feature choices. T3 Planner-Executor is the notable exception. Thus disabling or removing a widget normally does not prevent the next full run from enabling/reinstalling it.

**Reproduction:** Copy the real entrypoint into a temporary directory, replace installers with logging stubs, and declare all listed installers disabled. It still invokes **all 31 listed installers plus dotfiles**, then reports completion. Neither diagnostic stub runs.

**Fix:** Resolve and validate feature selection centrally before execution. Have all lifecycle commands update the same desired-state model. Distinguish invalid profile data from a deliberately disabled feature; do not interpret every nonzero query result as “disabled.” Honor dependencies and explicit disabled choices consistently. Preserve the explicit ordered installer list as required by this repository's guidelines, and test its agreement with the feature registry.

### 4. P1 — The personal gaming profile ignores Lutris's configured directories

**Evidence:** `steam/configure-gaming-profile.py:223–245`; compare `steam/sync-lutris-steam.py:37–40,237`.

The profile hardcodes both the database and YAML under `~/.local/share/lutris`. Lutris uses its configured `GAME_CONFIG_DIR` and `DB_PATH`; the generic sync already uses these APIs. **Correction found during implementation:** newer Lutris versions default `CONFIG_DIR` to `DATA_DIR` when the legacy config directory is absent. Thus the original location works on some new installations; it is incorrect to claim that all fresh installs read YAML from `.config/lutris/games`.

**Affected cases:** an existing legacy `.config/lutris`, non-default XDG directories, or a configured database override. A synthetic test confirmed the hardcoded destination, but did not alone prove which directory a given Lutris version uses. Tests must exercise the actual Lutris API in both layouts. In affected cases the database can claim installation while launch configuration is missing or stale.

**Fix:** Resolve data, configuration, database, and artwork locations through Lutris's settings, with explicit test overrides. Migrate only positively identified misplaced managed files, with backups and conflict handling. Test by loading the installed result through Lutris's real configuration API, not just checking a synthetic database row.

### 5. P1 — Required bootstrap dependencies are missing or discovered too late

**Evidence:** `install-all.sh:16,45–46`; `install-t3-planner-executor.sh:11,139–158,197`; `install-dotfiles.sh:6,26–38`; `lib.sh:176–182`; `config/doctor.py:31–70`.

- T3 Planner-Executor defaults to Pi, checks for it, and aborts if it is absent. There is no Pi installer in the entrypoint. A fresh supported machine without that extra CLI stops here, before gaming and desktop deployment.
- The default planner repository uses private SSH access. Installing `gh` does not establish SSH keys, host trust, or access to that repository. Other private plugins use HTTPS and have their own Git credential requirements.
- Dotfiles must already exist at exactly `../dotfiles`. Setup neither obtains them nor accepts a location override, and discovers their absence only after the preceding installation work. `doctor --dotfiles` can check an alternative location that `install-dotfiles.sh` still cannot use.
- Mise must already be available for the Codex/GitHub helper. If this is guaranteed by the supported Omarchy baseline, declare and validate that baseline rather than relying on an implicit assumption.

**Fix:** Run a dependency-aware preflight first. Provision authorized tool dependencies or report a blocking requirement before mutation. Support an explicit dotfiles source/path and revision without duplicating its contents. Check actual Git access using each source's intended transport; a successful `gh auth status` is not proof of private SSH/HTTPS clone access. Keep secrets out of Git and provide a resumable authentication step.

### 6. P1 — Game data in a separate JSON file is not yet configurable game selection

**Evidence:** `steam/profile/games.json:78–79,385–427,451–464`; `steam/configure-gaming-profile.py:23,26–34,285–305,313–320`; `steam/sync-lutris-steam.py:209–215`.

The concern about game drives is correct:

- Paths contain `/run/media/priyesh/...`, a specific volume identifier, specific installation folders, and historical shortcut/prefix IDs.
- The CLI always loads the repository's one `games.json`; it has no profile selection, library-root mapping, or selected-game list.
- Presence of an executable is treated as permission to manage that game. Mounting a drive with an old game therefore opts it into configuration changes.
- The generic sync excludes every listed managed/retired shortcut even when the personal profile subsequently skips it because its path is missing. An otherwise valid Steam shortcut can disappear from the import result.
- Retirement of particular games and desktop launchers is unconditional personal migration policy, not a generic Lutris installation concern.
- AoE2 account names and launcher creation remain hardcoded in Python. The qBittorrent Web launcher points to a personal domain and is also created independently of game selection.

**Reproduction:** A completely empty `games` list still creates `aoe2-pbtroopers.desktop`, `aoe2-the-gremlin15.desktop`, and `qBittorrent.desktop`.

**Fix:** Separate a reusable game catalog from an explicit selection and host library mapping. Resolve paths from configured roots, not the current username or incidental automount naming. Only exclude imports that a selected, successfully resolved profile actually owns. Move retirements into explicit versioned migrations and account/webapp launchers into independently selected features. Missing selected games should have a defined required/optional status, not silently change ownership.

### 7. P1 — Monitor policy centralizes identities but still requires one three-monitor setup

**Evidence:** `monitor-layout.json`; `hypr/scripts/monitor-layout.py:15–40,150–155`; `hypr/monitors.lua:4–23`; `install-lock-explorer.sh:260–265`; `install-system-metrics.sh:102–103`.

Moving connector identities into a central policy is good. However, validation requires `main`, `side_left`, and `side_right`, nonempty span/side lists, and exactly two window-span outputs. Modes, positions, rotations, scale, and HDR assumptions remain hardcoded in Lua. Merely changing descriptions is not enough to describe a different machine.

Lock Explorer requires all configured lock/span outputs connected. System Metrics refuses installation without its configured display. A laptop or a machine with only the main display therefore cannot complete the default setup. The core Lua fallback and final monitor installer's graceful skipping do not prevent those earlier failures.

**Fix:** Make topology, modes, HDR, scale, and orientation host-profile data. Support one monitor and optional roles. Make spanning a feature requiring two resolved outputs, not a universal schema constraint. Define per-widget fallback behavior: primary monitor, deferred activation, or intentionally strict required output. Resolve targets before enabling widgets rather than repairing them only at the end.

### 8. P2 — Gaming installation implicitly opts into intrusive graphics changes

**Evidence:** `install-lutris.sh:23–29`; `steam/configure-gaming-profile.py:164–186,282–283`; `steam/gamescope-hdr:10–26`; `steam/configure-gamescope-hdr.py:205–228`.

Installing Lutris automatically runs `--apply --upscalers`, downloads third-party DLLs, and replaces files such as `dxgi.dll` in selected game directories. Backups and checksums are valuable, but do not establish user intent or ownership of an existing graphics mod. Steam installation also rewrites launch options broadly to use 4K/HDR Gamescope, even on different displays/GPUs, and changes existing Gamescope resolution/filter choices.

**Fix:** Separate package installation, library import, per-game configuration, and experimental mod deployment. Make upscalers and HDR explicit per-game/profile opt-ins with a preview of files and launch options to change. Detect foreign mod files and require an adoption decision. Store ownership/hash records for safe rollback. Use configured or supported display dimensions, not a universal 3840×2160 target. Do not imply checksums guarantee runtime compatibility or online-game safety.

### 9. P2 — “Installed” does not mean the external integrations work

**Evidence:** `install-immich-photo-frame.sh:61–76`; `install-omniroute-quota.sh:61–80`; `install-obsidian-tasks-widget.sh:61–75`; `install-home-assistant.sh:74–90`; `install-calendar.sh:181–190`; `install-tailscale.sh`; `install-sunshine.sh`; `omarchy/wallpaper-controller.json`.

Fresh setup enables integrations with blank credentials, example/personal endpoints, a fixed Obsidian vault, or unavailable content. Wallpaper settings include a large preselected Workshop collection and an unavailable personal photo; setup does not supply those assets. Tailscale's daemon running does not mean the device is enrolled. Sunshine package installation does not configure and verify streaming.

These manual authorization/data requirements are legitimate and often documented. The gap is that the orchestrator has no machine-readable readiness model and ends with an undifferentiated completion message.

**Fix:** Support local non-secret settings plus references to securely supplied credentials. Validate selected service URLs, required files, and authorization without printing credentials. Report `ready`, `pending-auth`, `missing-data`, `deferred`, or `failed` separately. Do not auto-enable network access or invent credentials. A selected required integration that is not operational must prevent an “everything ready” result.

### 10. P2 — Several lifecycle paths call an undefined backup helper

**Evidence:** `install-shibumi-shell.sh:104`; `install-omaland.sh:89`; `install-indicators.sh:34,62`; compare `lib.sh:29`.

These paths invoke `backup_paths`, but the shared helper is named `backup_feature_paths`. No definition of `backup_paths` exists in the repository. Shibumi repair/removal, replacement of an existing managed Omaland desktop file, and indicator removal/migration will hit `command not found` when reached.

**Fix:** Standardize the helper name and test the actual lifecycle branches. An undefined function check alone is insufficient; assert that backup contents and restoration paths are correct.

### 11. P2 — Wallpaper menu removal can corrupt unrelated menu configuration

**Evidence:** `install-wallpaper-controller.sh:108–121`.

The removal helper deletes every line containing `"style.wallpaper-controller"`. For a valid multiline JSONC object it removes only the property header, leaving the property's contents and closing delimiter behind. It can also remove an unrelated comment containing the same text.

**Reproduction:** Calling the extracted function on a temporary valid multiline menu exits zero but leaves invalid JSON.

**Fix:** Use the existing structured JSONC helper in `config/managed-config.py` to remove the owned key, preserve comments/siblings, validate the result, and back it up. Add multiline and commented-menu lifecycle tests.

### 12. P2 — Wallpaper updates disable/archive the working plugin before validating the replacement

**Evidence:** `install-wallpaper-controller.sh:63–95,206–208`.

When the checkout is not current, setup first disables and moves the existing plugin away, then clones/checks out/validates the replacement. A network/authentication/pin/validation failure leaves the feature absent or disabled. There is a backup, but no automatic restoration. This diverges from the safer staging approach already present in `lib.sh`.

**Fix:** Stage and validate first, then replace under a bounded transaction with rollback. Keep the old checkout until activation and health checks succeed. Do not equate “backup exists” with failure-safe deployment. Test download failure, invalid manifest, activation failure, and interruption with an existing healthy plugin.

### 13. P2 — Diagnostics can miss unsafe or incomplete states

**Evidence:** `config/doctor.py:50–70,84–110,134–135`; `install-lock-explorer.sh:193–197`.

Preflight tests the lock response only against literal `locked`/`true`, whereas the setup's other lock checks expect a JSON object. A response containing `{"locked":true}` is not rejected; a failed lock query is also not a blocking result. The private-auth list omits Planner-Executor but includes Indicators, which is not in the entrypoint. Checking GitHub CLI login does not establish source access.

The normal doctor identifies plugins by regexes in scripts, skips nonstandard pins/suite layouts, treats missing requested plugins as warnings, and checks permissions rather than actual credential/readiness state. It can report `ok` without the selected environment being operational. Re-running Home Assistant is also not guaranteed to repair permissions: its already-installed early return checks runtime/file existence/enabled state, not permissions.

**Fix:** Consume a typed feature registry, check source access by transport, parse the supported lock API and fail closed on unknown/failed responses before mutations, and distinguish installation integrity from operational readiness. Keep optional diagnostics informational, but make missing required features fail acceptance. Do not use a minimum Omarchy version alone as proof that a pinned plugin is compatible with every later release.

### 14. P2 — File ownership and multi-file failure recovery are inconsistent

**Evidence:** `install-hyprland.sh:79–132`; `config/shibumi-settings.py:23–29`; `hypr/scripts/monitor-layout.py:222–257`; `steam/configure-gamescope-hdr.py:119–122,170–172`; `install-lock-explorer.sh:161–190`.

Some operations carefully preserve unknown settings and write atomically; others overwrite whole managed personal modules, write live configuration in place, or read/modify shared `shell.json` without a common lock. A GUI edit or concurrent installer can be lost. A crash between database, YAML, and launcher changes can leave a partially applied gaming profile. Syntax validation occurs after some live Hyprland changes without automatic rollback.

There is also an ownership ambiguity: Omaland edits `looknfeel.lua`, while the Hyprland installer treats the repository copy as authoritative and replaces a changed file on rerun. Widget/UI preferences preserved locally are generally not exported into a rebuild profile. A backup helps recovery but does not make those preferences reproducible.

**Fix:** For every field/file, declare `managed`, `seed-only`, or `user-owned`. Use one lock and atomic write path for shared configuration, with conflict checks and per-feature rollback. Keep backups private. Provide an export path for approved user-owned preferences, excluding secrets and ephemeral state. Batch shell restarts where safe, and verify activation after restart.

### 15. P2 — Documentation describes behavior the entrypoint does not deploy

**Evidence:** `SCRIPTS.md:40`; `PLUGINS.md:65,77`; `install-shibumi-shell.sh:107–111`; `install-indicators.sh:9`; `install-all.sh`.

Documentation says the custom Shibumi QML overrides in `shibumi/` are deployed, but the current installer only calls `config/shibumi-settings.py`; it no longer copies those overrides. Therefore the bespoke notch/media/bar behavior is not reproducibly installed from those files. Reintroducing unmanaged copies would conflict with the suite's payload integrity checks and the repository's separate-source rule.

Indicators has `PENDING_APPROVED_PUBLICATION`, is omitted from the entrypoint, and cannot install at its placeholder pin. Yet related documentation still describes the override as part of the setup. This should be treated as an incomplete integration, not a supported reproducible feature.

**Fix:** Publish authorized custom behavior in its owning plugin/fork, pin it, and validate the resulting UI lifecycle. Mark unreleased integrations explicitly unavailable until then. Generate or check source URL/pin/registration documentation against the feature registry. Keep design/review artifacts clearly separate from deployed source.

### 16. P2 — The current tests do not establish the fresh-install contract

**Evidence:** `tests/test_t3_planner_executor.py:66–68`; `steam/test_gaming_profile.py:69–106`; `tests/test_monitor_layout.py:168–190,211–227`; absence of a tracked CI workflow.

The 27 skipped tests require a sibling Planner-Executor source repository or an environment override. On a clean checkout, the suite can be green while skipping that entire install/lifecycle integration class. Other tests assert the existing fixed 13-game manifest, not user-selectable behavior. The gaming fixture did not detect the wrong YAML destination because it never asked Lutris to read it.

The extra entrypoint probe exposed a gap not covered by existing tests. Public source capability mismatches also escaped the current fixture-based checks. Several in-process monitor tests patch `Path.home()` but inherit host XDG state, causing test artifacts outside the temporary home.

**Fix:** Add clean-checkout CI, isolate HOME and all XDG paths, make essential integration skips visible/failing in release acceptance, and test contracts against real pinned dependencies. Use sanitized in-repo fixtures for core tests; fetch authorized private pinned sources only in a separate integration job. Test both clean install and second-run convergence. A green unit suite is necessary, not sufficient.

## Recommended configuration architecture

Keep it deliberately small. One feature registry and a validated profile resolver are enough; there is no need to introduce a large configuration-management framework just to fix these issues.

### Separate four kinds of information

1. **Implementation and compatibility:** installer path, dependencies, supported platform/API capabilities, plugin source URL, exact revision, health check, lifecycle hooks. Maintain original plugin code in its separate repository as required.
2. **Desired user choices:** selected applications/plugins/games, keyboard preferences, enabled behaviors, optional account/webapp launchers. Keep a named personal preset if useful; do not make it the only supported setup.
3. **Host bindings:** display identities and modes, library roots/mount locations, GPU/HDR policy, local vault locations. Resolve these from a selected host profile or an explicit first-run configuration step.
4. **Runtime/private state:** credentials, Steam login sessions, cached artwork, wallpaper shuffle progress, process IDs. Do not confuse these with portable configuration or commit them into profiles.

A reasonable precedence is base defaults → named user profile → host profile → explicit command-line choices, with a deliberate policy for remembered local choices. Validate unknown keys, dependency conflicts, unsafe paths, missing references, and schema versions before executing installers. Do not silently “repair” an invalid profile into a different selection.

### Gaming example — a proposal, not implemented functionality

A game catalog can describe relative executable paths, store IDs, and supported launch templates. The host mapping and selected games should be separate:

```json
{
  "schemaVersion": 1,
  "features": {
    "steam": true,
    "lutris": true,
    "gamingProfiles": true,
    "experimentalUpscalers": false
  },
  "libraries": {
    "primary": { "path": "/mnt/games", "required": false }
  },
  "games": {
    "cyberpunk-2077": {
      "enabled": true,
      "library": "primary",
      "relativePath": "Cyberpunk 2077",
      "hdr": false,
      "upscaler": "none"
    }
  }
}
```

`/mnt/games` is an example host-supplied value, not a new hardcoded default. Omitted games should remain unmanaged. If a library is absent, report which selected games are deferred or blocked. Offer discovery to propose a selection, not to modify every discovered installation. If drive mounting is desired, make it separately authorized and use stable filesystem identity with validation; never format or mount arbitrary devices implicitly.

Also resolve required Proton/GE-Proton runners before declaring games ready. The current general LinUwUx runtime does not provision every per-game Proton version or private launcher referenced by the personal catalog.

### Entrypoint stages

1. **Load and validate:** resolve selected features, inputs, source pins, and dependency order; refuse root execution unless intentionally supported.
2. **Plan:** show packages, managed paths, migrations, service changes, optional downloads, missing mounts/data, and credential requirements without making changes.
3. **Bootstrap/preflight:** verify the supported base, unlocked session where required, privileges, tool dependencies, source access, and dotfiles. Finish interactive authorization before destructive work.
4. **Apply:** use staged per-feature transactions and owned-path backups. Avoid leaving a working plugin removed if a replacement download fails. Record outcomes and prerequisite failures.
5. **Verify:** check deployed bytes/configuration, services, commands, valid Hyprland configuration, plugins, and selected service connectivity/readiness. Finish with an actionable summary and a meaningful exit status.

A proposed interface could be `./install-all.sh --profile personal --host laptop --plan`, followed by an explicit apply. This interface does not exist today. Do not implement arbitrary continue-on-error; independent optional features may be deferred, but failed dependencies must block their dependents.

### Version and lifecycle policy

- Pin plugin/custom runtime sources and keep the same lock data in installers, docs, and tests.
- For rolling Arch packages, state a tested compatibility baseline and capability checks; do not promise bit-identical rebuilds without package snapshots.
- Codex/GitHub wrappers currently perform `mise use -g` during ordinary execution (`t3/codex`, `github/gh`). Separate normal command execution from explicit version installation/update, or clearly retain that behavior as a selected policy. Runtime commands should not unexpectedly need network access or mutate tool selection.
- An existing executable or `.desktop` file alone does not prove a healthy installation. Check the managed executable and selected configuration where it matters.
- Support install/check/enable/disable/remove consistently. Disabled features must stay disabled across a full run; dependent features must not reintroduce their behavior.
- Respect the distinction between software already present and configuration already current. The project guidance should explicitly allow reconciliation without reinstalling the package.

## Suggested implementation order

### Phase 1 — Restore correctness before generalization

1. Correct the Shibumi/Omaland source-capability mismatches; leave publication-blocked integrations explicitly unavailable.
2. Wire profile selection and diagnostics into the entrypoint, with early checks for Pi, Git access, and dotfiles.
3. Correct Lutris paths and add a regression that reads the resulting configuration through Lutris.
4. Fix undefined backup helpers and wallpaper JSONC removal.
5. Stage wallpaper updates before disabling/replacing the working installation.

### Phase 2 — Make rebuilds portable and intentional

6. Introduce validated user/host profiles with safe defaults and an example personal preset.
7. Separate gaming package installation, library discovery/import, selected profiles, launchers, migrations, and optional upscalers.
8. Support single-monitor/laptop setups and explicitly optional display-dependent features.
9. Add secret references, external-data checks, and honest pending-auth/readiness outcomes.

### Phase 3 — Prove and maintain the contract

10. Standardize configuration ownership, locking, atomic writes, rollback, and export of portable preferences.
11. Add clean-checkout CI and contract tests against exact pinned sources; remove mandatory integration-test skips from acceptance.
12. Run a disposable Omarchy VM acceptance matrix and then document the supported baseline.

## Minimum acceptance matrix

- Fresh supported Omarchy, default/safe profile, no private credentials, no game drive, one display.
- Personal profile with explicit private Git access, configured services, separate dotfiles, and selected games.
- A different username, HOME path with spaces, and non-default XDG directories where supported.
- Disabled features remain absent/inactive after install-all; dependency conflicts fail before mutation.
- Empty game selection produces no personal launchers, imports, retirements, or DLL writes.
- Missing selected game/library/runner gives the declared deferred/blocking outcome; no mutation of unselected games.
- Unavailable private repository, interrupted download, missing pin, and invalid manifest preserve the prior working installation.
- Second run makes no unintended changes; manually edited/user-owned settings survive.
- Enabled → disabled → enabled → removed lifecycle preserves unrelated settings and leaves no owned shortcuts/helpers behind.
- Locked or unavailable desktop session is rejected before shell/lock mutations.
- Malformed JSON/JSONC, concurrent config edit, and symlink conflicts fail without corrupting the original.
- Login/reboot verifies the actual desktop, services, plugin behavior, keyboard shortcuts, and selected application launch configuration.

## What is already good

- Explicit installation ordering and per-software scripts are understandable and easy to debug.
- Omarchy package/browser commands are generally used instead of bypassing the platform.
- Pinned plugin commits, hashes for downloaded gaming assets, and separate plugin repositories are the right foundation.
- Shared staging helpers refuse foreign/dirty checkouts; several configuration helpers use backups, atomic replacement, and conflict checks.
- Dotfiles remains separate and its installer contains meaningful backup/rollback logic.
- The central monitor identity resolver is a real improvement over connector-number-only configuration.
- The tests already cover useful idempotency, preservation, and lifecycle cases. Extend them to verify user-visible contracts rather than replacing them.

**Bottom line:** repair the proven blockers first, then separate portable intent from machine-specific bindings. The repository should rebuild a selected setup, not replay every historical customization from the current machine.
