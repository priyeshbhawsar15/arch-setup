# Audit fixes implementation plan

> **For agentic workers:** Use the executing-plans and dispatching-parallel-agents workflows. Implement the authorized audit corrections with failing regression tests before production changes.

**Goal:** Resolve all 17 historical audit findings against the current working tree without losing existing configuration or pre-existing repository edits.

**Architecture:** Retain per-feature installers and dedicated plugin repositories. Consolidate checkout, backup, and configuration reconciliation helpers where repeated behavior caused defects. Move Shibumi and indicators source out of this repository, preserving the installed customization and supported lifecycle identity.

**Tech Stack:** Bash, Python unittest, JSON/JSONC, Hyprland Lua, Quickshell QML, Git and GitHub CLI.

**Spec:** audit.md and AGENTS.md.

## Constraints and ownership

- Preserve all existing working-tree modifications; baseline snapshot is archived under ~/.local/state/arch-setups/backups/audit-fixes-workspace-20261012T200851.
- Do not edit package-owned Omarchy source or publish credentials.
- Keep personal settings in allowed Lua modules, not hyprland.lua.
- Original indicators repository: priyeshbhawsar15/omarchy-indicators, private, as selected by user.
- Test external dependencies with isolated temporary user directories and controlled package/session responses; do not mutate the live desktop during tests.
- Publish reviewed plugin revisions before changing installer pins. Obtain explicit publishing approval for prepared repositories if it has not been given.
- Root owns lib.sh, install-all.sh, common configuration helper, widget installers, main documentation and audit status.
- Application worker owns install-dotfiles.sh, install-lutris.sh, steam/, install-steam.sh, install-keyd.sh, install-tailscale.sh, github/gh, t3/codex and their regression tests.
- Lifecycle worker owns install-hyprmoncfg.sh, install-per-monitor-workspaces.sh, install-calendar.sh and their regression tests.
- Shell worker owns install-shibumi-shell.sh, install-omaland.sh, indicators installer, Shibumi/indicators/Omaland dedicated source repositories, and their regression tests. Do not remove setup source overrides until they have been preserved in the dedicated repositories.
- Documentation edits are coordinated by root after receiving worker notes.

## Review focus

- Repeated installation and partial failure must preserve data and unrelated settings.
- Disabling an absent feature after changing the active bar must leave unrelated bar entries intact.
- Dirty plugin checkouts and unsupported layouts must fail without overwriting local source.
- Credential-bearing files and backups must remain user-private.
- Fresh user databases, secondary Steam libraries, escaped launch options and offline services must behave correctly.

## Tasks

- [ ] 1. Revalidate current fixes and record baseline tests. Existing baseline: 29 tests passed (11 monitor, 9 GitHub, 5 T3, 4 Steam).
- [ ] 2. Back up dotfiles destinations, preflight Stow packages/conflicts, and restore on failure. Test real Stow with a conflict and failed deployment.
- [ ] 3. Merge Lutris game YAML and initialize supported database state. Test empty user state and preservation of independent game fields.
- [ ] 4. Correct Steam argument placement, VDF quoted values and secondary library discovery. Add fixtures for all three failures and permission reconciliation.
- [ ] 5. Reconcile keyd/Tailscale services and make CLI wrappers execute the resolved mise binary without recursive PATH lookup. Test interrupted service setup and matching nonexecutable wrappers.
- [ ] 6. Use the AUR hyprmoncfg variant, manage its service explicitly, and call management-off on disable/remove. Test missing binary, service state and repeat lifecycle.
- [ ] 7. Preserve previous workspace/brightness/calendar slots, gate restoration by current ownership, and retain independent bar widgets. Test stock-bar and changed-layout cases.
- [ ] 8. Reproduce calendar sync infrastructure when authenticated, stop/remove its managed timer safely, and back up its actual configuration/state. Test no-authentication and existing timer behavior.
- [ ] 9. Build the custom Shibumi fork from the reviewed pin with current overrides included in its validated payload. Test admission and install/status/disable/re-enable/removal with isolated state.
- [ ] 10. Build independently managed private indicators with correct clonedFrom metadata, stable reminder refresh behavior and explicit layout/lifecycle. Test installation and removal preserve unrelated settings.
- [ ] 11. Correct Omaland menu merge/removal and route personal full-opacity rules into allowed modules in a dedicated fork. Test JSONC input and unchanged package entrypoint.
- [ ] 12. Fix Weather update directory and telemetry failure/forecast selection in its dedicated repository. Test offline preservation and 14:15 hourly selection.
- [ ] 13. Restrict quota credentials; reconcile helper links, menus, toggle files and executable modes before already-installed exits. Test missing integration artifacts.
- [ ] 14. Back up differing Hyprland destinations and verify current monitor-owner/span corrections, retaining pre-existing tested identity policy. Test preservation and supported deployment.
- [ ] 15. Add install preflight and read-only doctor, documenting authentication/assets that require user-local provisioning. Keep optional service credentials local.
- [ ] 16. Update SCRIPTS.md and PLUGINS.md in the same changes, record final ownership/pins and audit resolution evidence.
- [ ] 17. Run all regression suites, shell/Python/Lua checks and dedicated plugin tests; obtain a fresh review; report any manual acceptance work without claiming it passed.

Every implementation task follows RED (regression fails for the reported behavior), GREEN (minimal fix), then the affected suite. Final validation includes the entire setup test suite. New shared helpers have behavioral tests for preservation and failure paths.

## Execution record

- Baseline state preserved; existing tests pass.
- GitHub API authentication verified through /usr/bin/gh. Existing wrapper recursively resolves itself through mise x; application worker will fix this observed integration defect.

