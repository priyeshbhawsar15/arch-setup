# Fresh-install readiness review

Reviewed repository commit `1c5c975`. This is a new review, not an endorsement of the older `audit.md` (which explicitly describes an earlier commit).

## Verdict

**Good foundations, but not currently reliable as a fresh-install restoration system.** The code mixes reusable installation logic, one machine's desired configuration, local migration operations, and optional integrations. These need clearer boundaries, not a wholesale rewrite.

Two default installers have demonstrably incompatible source pins. The entrypoint bypasses the preflight and most feature-selection infrastructure. Gaming and monitor handling still assume the original machine. Successful package installation also does not establish that all configured features are usable.

This review made no desktop, package, plugin, account, drive, or credential changes. Only this report was added. Source inspection focused on orchestration, shared helpers, gaming, monitor deployment, plugin lifecycle, configuration and test coverage; it is not a claim that every QML/C++ implementation or private plugin was exhaustively reviewed. Public pinned Shibumi CLI and Omaland manifest were fetched read-only to verify compatibility. No clean Omarchy VM acceptance test was performed.

## What is already good

- Small per-software installers, explicit ordering and fail-fast shell settings are understandable.
- Dotfiles remain in their own repository, rather than being duplicated here.
- Shared pinned-checkout helpers validate identity and refuse unknown/dirty checkouts. Staging before replacement is a sound pattern.
- The dotfiles installer now backs up existing targets and attempts rollback; the destructive implementation in the archived audit is no longer current.
- Structured menu/layout helpers, monitor identity resolution, service reconciliation, credential modes and lifecycle tests improve substantially on ad hoc shell edits.
- Gaming assets have hashes, and game configuration changes generally create backups.
- Existing tests cover useful failure cases, rather than only happy paths.

## Highest-priority confirmed findings

### 1. Shibumi's configured pin cannot satisfy its installer

**Priority: P1 — default rebuild blocker.**

Evidence: `install-shibumi-shell.sh:12-14`, `:87-88`, `:147-148`, `:154-174`.

The installer points at upstream `HANCORE-linux/Shibumi-Shell`, commit `7a6c853b1947d303bad9a5b640c224c01b669106`, but requires `install --help` to advertise `--user-layout`. The CLI source at that exact upstream revision does not contain that option. The script also expects a custom repair workflow. It explicitly exits with “the reviewed custom fork must be published and pinned before installation.”

This is not merely an upstream-version risk: the default recipe is internally incompatible. On a fresh run, the guard fails before committing the staged suite checkout, stopping `install-all.sh` and preventing all later installers and dotfiles deployment.

**Fix:** publish the reviewed customization in its own fork, verify its lifecycle against the supported Omarchy version, then change source URL and exact commit together. Alternatively, use an actually supported upstream configuration workflow and remove unsupported assumptions. Do not bypass the safety guard. Update `PLUGINS.md`/`SCRIPTS.md`, which still describe the old upstream installation and copied overrides.

### 2. Omaland also requires a fork that is not the configured source

**Priority: P1 — another default rebuild blocker.**

Evidence: `install-omaland.sh:11-13`, `:174-175`.

The script installs upstream commit `ec232b6aa2e31b2f089ad89b653cd706989865b9`, then requires manifest field `.archSetups.personalModule == "hypr/looknfeel.lua"`. The manifest fetched at that exact revision has no `archSetups` field. Therefore activation fails even if Shibumi is repaired or skipped.

**Fix:** publish and pin the reviewed personal-module fork, or implement the behavior using an upstream-supported capability. Add a test that checks the real pinned manifest contract, not just a synthetic fixture.

### 3. Feature selection exists but the entrypoint does not enforce it

**Priority: P1 — unwanted installation and disabled-feature resurrection.**

Evidence: `install-all.sh:7-47`, `config/feature-profile.py`, `lib.sh:170-179`; repository-wide search finds `feature_is_enabled`/`remember_feature_choice` used by the T3 planner installer, not the other feature installers.

`install-all.sh` executes every listed installer without checking `features.json` or the local feature-choice file. It also does not set `ARCH_SETUPS_AUTOMATED=1`. Most `--disable`/`--remove` paths do not persist a feature choice, and subsequent default invocations enable plugins again.

A temporary fixture using the actual entrypoint and inert installer stubs confirmed that declaring Steam and Shibumi disabled still invokes both. All 32 installer invocations ran.

**Fix:** filter the execution plan centrally through validated feature preferences, resolve dependencies before mutation, pass automated context, and have every lifecycle operation record explicit choices. Define what skipping an installed feature means: preserve it or actively disable it, rather than silently mixing the two behaviors. Add entrypoint-level tests.

### 4. Preflight and final verification are not connected to the one-command setup

**Priority: P1 — avoidable partial setup and misleading completion.**

Evidence: `preflight.sh`, `doctor.sh`, `config/doctor.py`, versus `install-all.sh:41-49`.

The entrypoint does not call either checker. Missing dotfiles are discovered only at the very end. Missing Git authentication, an unsupported Omarchy environment, unavailable shell IPC or disconnected required monitors can be discovered after many unrelated changes. There is no root-user rejection, despite the documented requirement to run as the normal user.

The final “All installers completed” means only that commands returned zero; no integrated readiness assessment runs.

**Fix:** first validate the selected plan and prerequisites, then apply it, then run postconditions. Bootstrap prerequisites needed by preflight in a separate minimal phase; do not make a first install impossible by requiring already-installed tooling. Reject root invocation. Make the sibling dotfiles location configurable and validate it before package/config changes.

### 5. Several lifecycle branches call a nonexistent backup function

**Priority: P2 — broken update/removal paths.**

Evidence: `install-shibumi-shell.sh:104`, `install-omaland.sh:89`, `install-indicators.sh:34,62`, `lib.sh`.

These call `backup_paths`, but the shared library defines `backup_feature_paths`, not `backup_paths`. No repository definition of the former exists. Sourcing `lib.sh` and querying the command confirms it is absent.

Consequences include Shibumi removal/repair failing when they reach backup, Omaland managed desktop-entry replacement failing, and Indicators lifecycle failure if that feature becomes installable.

**Fix:** use the supported helper consistently, audit its argument/return contract, and test each branch through the real script. Shell syntax checks cannot catch this.

## Gaming: configuration, safety and restoration gaps

### 6. The game profile is data-driven but not user-selectable

**Priority: P1/P2 — core portability and user-choice gap.**

Evidence: `install-lutris.sh:19-29`; `steam/configure-gaming-profile.py:315-323`; `steam/profile/games.json:78-79,385-427,452-463`.

The installer unconditionally runs the bundled personal profile with `--apply --upscalers`. The CLI has no profile-path, selected-games, root-mapping or disabled-games option. Only `${HOME}` is expanded. Absolute `/run/media/priyesh/...` paths and a specific volume identifier remain embedded.

Important distinction: the code does **not** download/install all thirteen commercial games. Missing executables are skipped. Nevertheless, whenever those paths exist it configures those titles and selected DLL modifications automatically, with no per-title opt-in.

Even when every game is missing, it still deploys two personal AoE account launchers, changes/seeds qBittorrent Web, and processes retired entries. Thus “missing games are skipped” is not equivalent to opting out of the personal gaming profile.

**Fix:** separate Lutris package installation, generic Steam import, optional personal game registration, optional account launchers, and experimental modifications. Provide a configurable profile path, game selection and named library roots. Keep the current list as an optional personal preset, not mandatory behavior. Default third-party DLL injection to explicit opt-in.

### 7. Generic Steam import excludes games merely because they appear in the bundled preset

**Priority: P2 — existing games can disappear from the intended import path.**

Evidence: `steam/sync-lutris-steam.py:207-215`.

The generic importer derives excluded shortcut IDs from the entire bundled profile and retirement list, not from the user's selected/enabled and successfully applicable games. A shortcut can therefore be excluded from generic import while the personal importer skips it because its old hardcoded executable path is absent.

**Fix:** compute ownership from the resolved selected profile. Exclude only entries that the personal importer actually owns; keep retirement migrations explicit and scoped to previously owned records.

### 8. Display/rendering preferences are imposed globally on games

**Priority: P2 — likely wrong on different hardware and sometimes on the same hardware.**

Evidence: `steam/gamescope-hdr:18-21`, `steam/configure-gamescope-hdr.py:205-229`, `steam/profile/games.json`, `install-steam.sh:49-52`.

The wrapper assumes a 3840×2160 game/output surface and HDR. Existing Gamescope commands are normalized toward the same size. Some personal games additionally force 120 Hz, 4K game arguments or XML settings. Steam UI scale is also a fixed personal value.

These are personal performance/display policies, not prerequisites for Steam. They may be inappropriate on a laptop, SDR monitor, different GPU, lower-powered machine, or a game with special compatibility needs. This review does not claim every such machine fails; the missing capability/choice boundary is confirmed.

**Fix:** make HDR, nested resolution, output resolution, refresh rate and UI scale profile settings with per-game overrides. Use native/automatic defaults when unspecified, and preserve user launch policy unless ownership is explicit.

### 9. Configured games are not guaranteed to have usable runtimes

**Priority: P2 — installation can report success while launches fail.**

Evidence: `steam/profile/games.json` runner versions; `steam/configure-gaming-profile.py:235-283`; `steam/profile/README.md:107`.

The profile checks executable availability, but does not establish that the configured Proton/GE-Proton runner, prefix or private F1 runtime exists and is usable. The README explicitly requires several runtimes separately. Installing LinUwUx's dedicated shared runner is not proof that Lutris's separate named runner lookup is satisfied.

**Fix:** validate runtime resolution per selected title. Install supported redistributable prerequisites reproducibly where feasible; otherwise mark the title `pending runtime` rather than ready. Keep private/nonredistributable assets external and give precise recovery instructions.

### 10. Gaming apply is not a multi-resource transaction

**Priority: P2 — recoverable but inconsistent partial state.**

Evidence: `steam/configure-gaming-profile.py:211-308`.

It creates symlinks, writes YAML, commits database updates, downloads artwork, changes game XML and installs DLLs incrementally. A later download/hash/extraction/write failure leaves earlier changes applied. Backups help manual recovery but do not provide coordinated rollback. Each run also reapplies managed launch/env fields; backing up is not the same as preserving user-edited policy.

**Fix:** plan and validate all selected changes first, stage downloads before modifying game folders, use per-game ownership state and backup manifests, then commit per-game changes with recovery. Provide a dry-run through `install-all.sh`, not only the low-level profile tool.

## Other machine-specific assumptions

### 11. Monitor identity is centralized, but monitor topology and modes are not truly portable

**Priority: P2 — a single-monitor rebuild is not a supported configuration shape.**

Evidence: `monitor-layout.json`; `hypr/scripts/monitor-layout.py:16-38,158-162`; `hypr/monitors.lua:4-23`; `install-system-metrics.sh:99-101`.

The policy requires `main`, `side_left`, `side_right`, exactly two window-span roles and nonempty side/span lists. It cannot naturally describe a laptop with one output or no spanning feature. The Lua template still fixes modes, refresh, rotation, coordinates, scale, HDR, bit depth and `GDK_SCALE=2` outside the central JSON.

Stable descriptions are a genuine improvement over connector numbers, but changing three descriptions is insufficient to adapt the configuration to different hardware. System Metrics explicitly refuses installation if its selected display is absent, which can block the rest of setup.

**Fix:** represent arbitrary monitor roles with optional feature targets; put geometry/modes/scaling/HDR in the machine profile. Make spanning and side widgets optional. Resolve missing targets to an explicit fallback or a visible pending state; never silently disable the only available output.

### 12. Service endpoints, paths and accounts are personal application data

**Priority: P2 — features install but cannot work on a clean machine without undeclared data.**

Examples:

- `install-obsidian-tasks-widget.sh:69`: `/home/priyesh/Documents/Obsidian/pb`.
- `install-omniroute-quota.sh:69`: personal home-server URL, with empty token.
- `steam/profile/qBittorrent.desktop:5`: personal homelab URL.
- `steam/profile/launch-aoe2-account:12`: two fixed Steam accounts.
- `omarchy/wallpaper-controller.json:74`: an absolute personal Downloads image path.
- Seed/widget configurations retain connector defaults such as `DP-4`/`DP-5`; the later monitor installer repairs some but not every startup path.

Secrets should absolutely remain outside Git. The gap is that feature selection, required local data and readiness are not modeled together.

**Fix:** separate a portable personal profile from a machine-local overlay and a private secret/data restoration source. Validate selected vaults, endpoint configuration, remembered accounts and wallpaper assets. Report `installed / configured / ready / pending external input` separately. Avoid emitting dead personal launchers when their feature is unselected.

### 13. Git authentication and external dotfiles are insufficiently reproducible

**Priority: P2 — fresh machines depend on unverified external state.**

Evidence: private repository URLs across installers, `install-t3-planner-executor.sh`, `config/doctor.py:61-70`, `install-dotfiles.sh:6`.

Private plugins use HTTPS while the planner source uses SSH. `gh auth status` alone does not establish HTTPS Git credential-helper wiring, SSH key access or authorization to each selected repository. The doctor private-feature list also omits the planner source. Dotfiles are assumed to exist at a sibling path, with no recorded revision/compatibility identity.

**Fix:** preflight actual read access to selected sources using their exact transports, never logging credentials. Support an explicit dotfiles path/URL and reviewed revision or record the resolved revision in an install manifest. Treat login/authorization as a documented bootstrap prerequisite, not something SSH or package presence magically satisfies.

## Reliability, lifecycle and verification

### 14. Installer ownership and rollback conventions are inconsistent

**Priority: P2 — failures are handled differently depending on the feature.**

Evidence: compare shared `install_pinned_plugin` in `lib.sh` with the custom implementation and replacement flow in `install-wallpaper-controller.sh`, and the in-place update in `install-home-assistant.sh:51-58`.

Wallpaper Controller shadows the library function with its own implementation and archives the existing plugin before installing the replacement. If replacement download/validation fails, the original is no longer active at its expected path. Its current-check ignores untracked files, unlike the shared helper. Home Assistant updates the live checkout before all runtime/config postconditions succeed. These are weaker guarantees than the staged shared pattern.

Wallpaper Controller also still removes menu entries by filtering lines (`install-wallpaper-controller.sh:109-124`), whereas Omaland has moved to a structured JSONC helper. Multiline entries or compact JSON can be damaged by line deletion.

**Fix:** converge on one staged-checkout and owned-config lifecycle, with feature-specific hooks but common backup, identity, rollback and JSONC handling. Do not hide unexpected lifecycle failures behind `|| true` and then announce success.

### 15. Doctor is not yet a reliable acceptance gate

**Priority: P2 — false confidence or incorrect preflight results.**

Evidence: `config/doctor.py:57-70,90-113,134-135`.

The lock check only rejects plain `locked`/`true` output and does not validate the structured lock-status fields that the Shibumi installer itself uses. Its GitHub check is not a repository access test. Installed plugin revision/origin/cleanliness does not prove credentials, target assets, transports or application behavior work. Home Assistant's installer also returns early when revision/runtime/config existence match without repairing token permissions or validating readiness.

**Fix:** define structured postconditions per feature, validate the actual supported IPC response, and distinguish pending optional data from mandatory failures. Doctor should consume the same selected plan/manifest as installation, rather than infer the architecture from shell regexes.

### 16. Tests pass, but do not establish the advertised one-command contract

**Priority: P2 — important integration defects evade current coverage.**

Executed:

- `python3 -m unittest discover -s tests -v`: 99 discovered, 72 passed, **27 skipped**.
- `python3 -m unittest discover -s steam -p 'test_*.py'`: 23 passed.
- Same discovery for `github`: 12 passed; `t3`: 5 passed; `gaming/denuvowo`: 22 passed.
- Total across these suites: **134 passed, 27 skipped, 0 failed**.
- `bash -n` on repository `.sh` files: passed.

All 27 skips are the planner/executor suite because its sibling portable package source is absent. The tests for feature preferences and preflight mostly exercise helpers; they do not prove that `install-all.sh` actually calls them. Synthetic plugin fixtures do not validate real upstream pins, explaining why the incompatible Shibumi/Omaland contracts pass unnoticed.

**Fix:** add orchestration tests with disabled selections and failed preflight; test real pinned source contracts; make required integration-test dependencies explicit in CI rather than silently green-by-skip. Add a disposable supported-Omarchy VM acceptance run: blank home, apply, rerun, reboot/login, validate, disable/re-enable/remove, interrupted install, missing monitor, offline rerun and selected-game paths containing spaces. Run ShellCheck in addition to syntax checks.

### 17. The repository contains transitional/unavailable feature artifacts

**Priority: P2/P3 — unclear source of truth and incomplete future installation.**

Evidence: `install-indicators.sh:9`, `install-all.sh`; `shibumi/*.qml`, `native/*.cpp`; archived `audit.md` and current script descriptions.

Indicators has placeholder pin `PENDING_APPROVED_PUBLICATION` and is not registered in `install-all.sh`. It is not a current default blocker, but it cannot count as a reproducible installed feature. Copied Shibumi/native implementation files coexist with an installer intended to rely on a separately published customization, making it unclear which source actually builds the desktop. Documentation still describes behaviors already replaced in code (including destructive dotfiles deployment).

**Fix:** explicitly label pending features, never advertise them as ready, publish authorized source changes before pinning, and remove stale parallel copies only after confirming the fork owns them. Update both required documentation files alongside implementation fixes. Maintain one current readiness report and label historical reports as historical.

## Recommended architecture

Keep Bash and the per-software installer structure. Add a small validated configuration/planning layer rather than introducing a general-purpose automation framework.

### Configuration boundaries

1. **Feature catalog / lock manifest:** installer identity, dependencies, source URL, exact commit, required capabilities, supported Omarchy baseline and postconditions. One source used by installer, doctor and documentation checks.
2. **Portable personal profile:** selected applications/plugins/games, desired behavior, service URLs and account labels. No passwords/tokens.
3. **Machine overlay:** monitor inventory/topology, scale/HDR policy, named game-library paths and hardware-specific settings. No mandatory three-monitor shape.
4. **Private local inputs:** tokens, OAuth, vaults, Workshop content, game files/prefixes and private runtimes. Restore from an explicitly configured private source or report pending; never put these into Git.

Configuration files are allowed to contain personal values. The important rule is that reusable implementation must not require editing source to change those values, and optional personal presets must not be mandatory.

### Execution contract

`resolve selected profile → validate dependencies/source access/inputs → show plan → install prerequisites → stage changes → apply owned configuration → activate in an unlocked session → verify → summarize ready/pending/failed`

- Preserve current fail-fast behavior for mandatory failures, but print the failed step and a rerun/recovery command.
- Optional unavailable features should be explicitly skipped/pending according to profile policy, not silently treated as working.
- Provide `--plan`, `--profile`, and a feature subset. Resume can initially mean safe idempotent rerun; a complex checkpoint system is unnecessary until needed.
- Add a setup-level lock to prevent two concurrent mutation runs.
- Record what configuration/revisions were actually applied, without recording secrets.
- Separate package presence from configuration convergence. Exiting as soon as a package exists must not skip repairing managed services/configuration.
- Back up before mutation, maintain ownership metadata, validate before activation, and make rollback actionable. Do not promise transactional rollback of package-manager operations.

### Gaming contract

- `install-lutris.sh` ensures Lutris works without requiring any particular game.
- Optional game registration accepts an explicit selected list and profile path.
- Library roots map logical names to paths; do not infer a drive by a casual label and mount arbitrary disks. Existing paths can be user-supplied, with optional UUID-based resolution/validation when requested. Never format or repartition drives as part of ordinary setup.
- Each selected title has a relative executable path, optional runtime, optional launch policy and explicit mod opt-ins.
- Imports exclude only owned selected entries; retirement is a separate owned migration.
- Missing games/runtimes are visible pending prerequisites, not fabricated launch readiness.

## Suggested repair order

1. Fix/publish Shibumi and Omaland source pins and undefined backup calls.
2. Wire selected-feature planning, preflight and postflight into the entrypoint; test that failures happen before mutation.
3. Split generic gaming setup from personal title/account/mod policies and introduce root/game selection.
4. Make monitor topology, rendering policy and external integration inputs machine-configurable.
5. Unify remaining checkout/menu/backup lifecycle implementations and update documentation.
6. Add real-pin contract checks and disposable fresh-install acceptance testing before declaring the one-command goal met.

**Bottom line:** retain the existing modular structure, but make the desired state explicit and validated. The repository currently restores portions of the original desktop's assumptions; it does not yet prove that a selected setup will converge on a brand-new Omarchy machine.
