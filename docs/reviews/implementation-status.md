# Fresh-install fixes: implementation follow-up

This supersedes the historical behavior described in the [audit](fresh-install-audit.md). Application/desktop setup was applied only in a disposable VM, not to the primary host; authorized VM prerequisites were installed on the host. See the subsequent [real VM acceptance report](vm-acceptance.md).

## Implemented

- Safe application defaults and an explicit personal preset. Feature selection now controls the real entrypoint, with a complete/topologically checked registry, read-only plan, early preflight, root rejection, install lock, failure summary and final acceptance checks.
- Explicit feature lists must include their prerequisites. Remembered disabled dependencies skip their dependents rather than silently enabling them. All successful direct plugin lifecycle actions persist preferences independently of installer cleanup/rollback traps; failed actions do not.
- Configurable dotfiles path, validated before any application/desktop installation. Its separate repository remains authoritative. No unknown private source is guessed or duplicated here.
- Opt-in game catalog/selection with host-provided library roots, stable default prefix identities, optional generic Steam import, explicit graphics/artwork/mod choices, required/deferred game outcomes, and no unconditional accounts, retirements, game links or personal webapps.
- Lutris uses its real configured data/config/database paths, including legacy and modern layouts. Positively identified misplaced legacy files are archived. Real Lutris API tests load the results in both layouts, including a no-desktop-launcher profile. The audit's initial universal `.config` claim was corrected: modern Lutris may intentionally use its data directory.
- Private per-game configuration ownership records remove unchanged owned HDR/env values when opted out while preserving unrelated fields. Mod ownership hashes reject foreign/modified files unless explicit adoption is selected. Game backups are private; managed file symlinks are refused. Previously installed mods/game files are **not** automatically uninstalled when a selection is omitted.
- Steam package installation no longer forces 4K/HDR/80% UI scaling. HDR dimensions come from the selected game or focused output, including rotation. Existing custom Gamescope flags remain intact; client scaling is an explicit separate operation.
- Optional display roles and empty spans/side lists; a single-output laptop policy. Modes, orientation, scaling, HDR, workspace assignments and toolkit scale are data rather than fixed Lua. The existing three-monitor setup remains an explicit preset. Widget destinations are restricted to known configuration paths; UTF-8 descriptions render as valid Lua.
- Portable blank widget/service seeds, including HA's URL/entities and Obsidian's vault. Local settings and private credential-file references are supported without printing values. HA retains the token-file reference. Existing private config/token permissions are repaired where owned.
- A selectable workflow provider/model seed (`--planner-config`), with early executor checks derived from its actual config rather than an unconditional Pi requirement. Existing explicit runtime values are preserved. Native executor binaries must actually exist; no fake provider paths are invented.
- Defined backup helpers for all lifecycle branches; JSONC-safe multiline Wallpaper menu removal; private before-disable removal archives.
- Wallpaper replacement is staged/validated before stopping the previous plugin, with checkout/config/enabled-state rollback on hook/activation failure. Dirty/foreign/symlinked sources are not overwritten; supported existing SSH/HTTPS origins are recognized consistently.
- Lock-state checks use the JSON API and fail closed on unknown/failed responses. Doctor consumes registry/source-lock metadata, distinguishes pending from ready, checks actual Git transport access and avoids network checks for exact clean local sources. Local diagnostics never claim remote API/physical acceptance.
- Shared configuration locking, atomic replacement and intervening-edit checks in supported Python helpers. Lock settings are validated before writing. Existing user/Omaland appearance and Shibumi slot visibility edits survive reruns.
- Read-only Codex/GitHub runtime wrappers: no implicit `mise use -g` or tool update during ordinary protocol/API calls. Known prior wrappers are migrated with backups; unknown custom wrappers remain preserved. Stale desktop entries no longer count as installed applications by existence alone.
- A clean-checkout CI workflow, exact public-source API contract check, isolated tests and explicit private integration acceptance. Mandatory integration can no longer be silently represented by a skipped class. Monitor tests no longer leave fixture backups under the host's inherited XDG state.
- Removed copied Shibumi/Indicators source and obsolete personal account/webapp launcher payloads from this setup repository. Custom source now has one owning plugin repository. Updated `README.md`, `SCRIPTS.md`, `PLUGINS.md` and gaming configuration documentation.

## Published plugin sources

Only the authorized development branches were pushed. No upstream branch, main-branch merge, PR, tag, binary package or release was created by this work.

- Shibumi: `https://github.com/priyeshbhawsar15/Shibumi-Shell.git`, commit `8b96105a10ef5128589adda7a4b50c4ff903a97d`, branch `audit-lifecycle-fixes`. Based on upstream `7a6c853b1947d303bad9a5b640c224c01b669106`, retaining its license/attribution and 24-plugin ownership contract. Implements the actual user-layout/repair APIs required here, main-display filtering and personal media/notch presentation. Media uses the existing suite service, not a new owner. An unused unpublished hardcoded Jellyfin helper was preserved outside the source tree at `~/.local/state/arch-setups/backups/shibumi-unpublished-source.rcHuaq/`; it is not deployed.
- Omaland: `https://github.com/priyeshbhawsar15/omaland.git`, commit `796f134b98f97363290f13a5708eaf1045e11325`, branch `audit-lifecycle-fixes`. The public fork was created from the documented upstream; the personal-module manifest contract now matches the installer. License and attribution retained.
- Indicators: `https://github.com/priyeshbhawsar15/omarchy-indicators.git`, private, commit `f159ed5d870c7b402a4885ad1c72236620819e0f`, branch `audit-lifecycle-fixes`. The documented private repository was created and the reviewed source published, preserving built-in clone/reminder IPC identity. The placeholder pin is gone and the installer is registered.

All pins above were verified through GitHub after publication; public Shibumi/Omaland source capabilities were fetched at those exact commits and checked without executing downloaded code.

## Ownership and recovery boundaries

- **Managed:** selected application installation, exact plugin/source pins, helper links, generated monitor rules, most Hyprland personal modules, and explicitly selected game/settings fields.
- **Seed-only/user-owned:** existing `looknfeel.lua`, Shibumi slot visibility preferences, existing widget settings not explicitly supplied by the local settings input, artwork/mod tuning where documented, and external dotfiles contents.
- **Private/runtime:** credentials, account enrollment/OAuth, game binaries/saves, mutable wallpaper selection/rotation, provider authentication and caches. These are not committed into profiles.

Per-feature backups and guarded writes are not a global transaction. In particular, package operations, SDDM/Hyprland multi-file deployment, Lutris database/YAML/launchers and game-file writes do not all roll back together on power loss or arbitrary process failure. Preserve backups and rerun/reconcile after resolving the reported problem. A complete all-preferences export and generalized multi-feature transaction engine were not introduced; feature export covers feature choices, while other reproducible choices belong in the documented user/host/game/settings files.

## Verification evidence

- Setup repository: **209 tests passed, no skips** after integration with latest `main` (`b768a19`), including all 27 private Planner-Executor integration tests against an isolated clean checkout at exact pin `7ab9c0dd9774a75ee814a49ef41b281a03e96c36`. The test runner rejects a dirty/wrong/missing required integration source.
- PR preparation pulled `main` and preserved its Halo Gamescope capture and engine-display changes as explicit game/resolution/HDR opt-ins. Engine INI edits preserve encoding, line endings and unrelated sections, reject ambiguous input, and retain original backups. Added selection, capture, encoding, idempotence and backup regression coverage. The earlier VM evidence remains scoped to its recorded pre-pull snapshots; merged Halo behavior is fixture-tested, not a new physical-game/HDR acceptance claim.
- VM follow-up fixed stock-shell bytecode writes during plan, missing cold-ISO package indexes, and unmigrated Omarchy 4.0.6 quiet CLI shims. Added confirmed/explicitly approved initial platform preparation, private interrupted-update recovery, restart gating and strict corrupt-state refusal. Existing indexed systems are not routinely updated. See [VM evidence and scope](vm-acceptance.md).
- New regressions cover cold package preparation/approval/recovery, exact stock-shim migration, entrypoint feature gating/order, read-only safe plan, failure reporting, invalid inputs, JSON lock state, private secret references, portable HA defaults, configurable workflow executor, single-monitor/UTF-8 rendering, configuration preservation, empty/opt-in game selection, dynamic HDR dimensions, owned HDR opt-out, foreign mod refusal, real Lutris layouts, wallpaper failure rollback/removal and multiline JSONC.
- Published Shibumi clean commit: **313 Python tests passed**, plus `node tests/personal-presentation.test.js`, shared-source check and whitespace checks. This includes source/package-boundary and lifecycle fixtures, not physical desktop acceptance.
- Omaland's `node test/run.js`: all passing. Indicators clone-contract test: passed.
- Exact public source contract check, all repository shell syntax checks and `git diff --check`: passed.
- Fresh safe-profile Omarchy 4.0.6 VM: all 10 selected applications installed, readiness passed, password login/reboot/repeat convergence passed, and seven graphical apps passed limited startup/normal-close smoke. This does not certify the personal plugin profile or physical hardware. The CI-equivalent error-level ShellCheck command passed inside the VM.
- CI workflow is configured with GNU Stow among its required test dependencies; the original acceptance evidence does not claim a hosted CI run.

Temporary logs: `/tmp/arch-setups-acceptance-tests.log`, `/tmp/shibumi-clean-commit-tests.log`, and associated `/tmp/*setup-fix-tests*` logs. These are local evidence, not a project dependency or durable release archive.

## Acceptance still required

1. Personal/custom-plugin VM lifecycle acceptance and any platform revisions beyond the tested image. The safe profile on a new Omarchy 4.0.6 user, real package downloads, password login/reboot and repeat convergence have now passed; [details and remaining boundaries](vm-acceptance.md).
2. Actual physical monitor topology, hotplug/DPMS, mixed scaling, shell restarts, theme changes and authenticated lock/unlock. No live desktop configuration was changed or hardware acceptance claimed.
3. HA/Immich/Quota/Calendar authorization and live server data, Sunshine pairing/capture, Tailscale enrollment, and workflow provider/model authentication/real dispatch. A configured local file or active service alone cannot prove these.
4. Real games, Proton/GE-Proton compatibility, HDR and explicitly selected experimental upscalers. Checksums are not an anti-cheat or runtime-safety guarantee.
5. The separately documented unaccepted native live-wallpaper experiment remains outside the installed pin. It was not enabled or declared accepted here.

Start with `./install-all.sh --plan`; use a small feature profile and provide host/data/authentication inputs deliberately before apply.
