# Omarchy 4.0.6 VM acceptance — safe profile

## Result and scope

**The safe application profile passed fresh installation, normal password login, reboot, readiness checks and repeat-run convergence in a real disposable VM.** This is not acceptance of the personal desktop/plugin profile, authenticated integrations, real games or physical display hardware.

No setup application/desktop installers were applied to the primary host. Host system changes were limited to the authorized VM prerequisite packages; test disks, credentials and logs remain in a private local artifact directory. At the time of this VM acceptance the setup changes were uncommitted and hosted CI had not run; subsequent PR validation is recorded separately.

## Environment and isolation

- Official Omarchy **4.0.6** ISO; verified official SHA256: `b542db5fecc37395d9af6654a8146ebed225f275ae4d5a6fcf432e40afe7bb88`.
- Adapted official `omacom/omarchy-iso` integration harness at `886f2899f1bb54e5c622764fef16e1b05a6a03e4`. The actual ISO's cidata/unattended support was inspected before use.
- KVM/QEMU, UEFI, 2 vCPUs, 4096 MiB RAM, 40 GiB sparse disk, virtio devices and headless EGL/virgl rendering. **No physical GPU passthrough.**
- Disposable `vmtester` account on `setup-vm`, not the host username. Disposable local password/key, unencrypted guest, localhost-only SSH forwarding, user-mode NAT.
- No host drives, home directory, SSH agent, application credentials, game libraries or desktop configuration forwarded into the guest.
- Fresh installation completed and was shut down to preserve a clean base. Independent copy-on-write overlays were used for failed attempts and final acceptance.
- Observed platform: Omarchy `4.0.6-1`, kernel `7.2.8-9-omarchy`, mise `2026.10.13`.

## Findings fixed during real VM testing

1. **Read-only plan wrote Python bytecode.** A stock shell, unlike the test runner's environment, created `steam/__pycache__`. Entrypoint and read-only Python import paths now suppress bytecode writes. The regression explicitly removes an inherited `PYTHONDONTWRITEBYTECODE` flag. Fresh VM plan/preflight left no source bytecode caches.
2. **Fresh ISO lacked online package indexes.** Only `offline.db` existed. Chrome/Brave could install using existing dependencies, but Zen failed because normal repository dependencies could not be resolved. The entrypoint now detects missing/empty configured indexes and requests confirmation before Omarchy snapshot/keyring/full system-package update/migration/post-update-hook stages. `--approve-system-update` explicitly approves automation. Omarchy's update lock is used when available; no application installer runs between keyring refresh and the full package upgrade. Setup does not call the interactive restart picker or perform a database-only partial upgrade. Interrupted updates are remembered; required restart returns exit 3. Existing indexed systems skip preparation unless recovery is pending.
3. **Current stock CLI shims were mistaken for custom wrappers.** Omarchy 4.0.6's exact `mise use -g --quiet` Codex/GitHub templates still mutate tool setup at runtime. Those exact bytes now migrate to read-only wrappers with private original backups; unknown custom wrappers/symlinks remain preserved. Real Codex/GH execution and repeat installs were checked.

Recovery validation was additionally hardened: existing `null`, array, boolean, incomplete, unknown-status or empty-boot-ID markers fail closed rather than looking ready. A deliberately invalid marker in an isolated guest state directory blocked the real entrypoint even with update approval, left the marker unchanged, and ran no updater/application stages. CI's dependencies now explicitly include GNU Stow, required by its no-skips test contract.

## Actual execution evidence

- Captured the uncommitted working tree rather than testing only the old Git commit. No ignored local settings or Git metadata were transferred.
- Clean-base final apply: `./install-all.sh --ignore-local-choices --approve-system-update` — **exit 0; 10 selected installers applied, 23 skipped; doctor acceptance passed**.
- Applications: Chrome, Brave Origin, Zen, Stow, Hermes Desktop, Codex, GitHub CLI, T3 Code, Steam and Lutris. No personal desktop features or games selected.
- Before/after inventories showed **no changes to baseline Hyprland or Omarchy personal configuration** from safe apply. Package inventory grew from 959 to 1100 entries, including dependencies; ShellCheck was added afterward solely as a verification tool.
- Second apply without update approval or sudo authentication — exit 0, no platform bootstrap. Package versions and inventoried configuration/helper/state bytes, modes and links were identical.
- Additional repeat plus real `codex --version` / `gh --version` preserved the inventory, including `~/.t3/userdata/settings.json` and mise configuration. Versions observed: Codex `0.163.0`, GH `2.103.0`. Both installed wrapper files matched this repository's read-only sources; original shims were retained under private backup directories.
- Authenticated through the actual SDDM password field using only the disposable account's password; Hyprland and the stock Omarchy shell rendered on the virtual output. No autologin/lock bypass was configured.
- Graceful reboot returned a different boot ID and working SDDM; password login, doctor acceptance and a further no-drift setup apply succeeded afterward. Hyprland reported no nonempty configuration errors. System state was `running`, with zero failed system units.
- All **7 selected graphical applications** mapped real windows and remained visible after an eight-second observation: Chrome, Brave Origin, Zen, Hermes, T3 Code, Lutris and Steam. Screenshots were captured through the guest's native Wayland screencopy, not mocked UI. Steam completed its own client bootstrap and reached its sign-in screen; no account was enrolled/authenticated.
- Corrected GUI smoke used normal Lua window-close requests and generated **no new coredumps**. This proves limited startup/close behavior, not sustained application operation or authenticated workflows.
- **205 setup tests passed, no skips**, including all 27 Planner-Executor integrations against a separate clean checkout at exact pin `7ab9c0dd9774a75ee814a49ef41b281a03e96c36`. The original dirty development checkout was not overwritten. Test source was recreated locally after the previous `/tmp` checkout had disappeared.
- CI-equivalent shell syntax and error-level ShellCheck passed inside the VM. Public pinned Shibumi/Omaland source contracts, host shell syntax and whitespace checks also passed. This is not a hosted CI result.

## Test-harness issues, not silently counted as product success

The first GUI harness terminated complete Electron process groups. T3/Hermes then produced SIGTRAP cores: their logs show terminated network/GPU services followed by fatal GPU relaunch failure immediately after forced teardown. No OOM event was found. Those initial attempts were not counted as clean GUI acceptance; the normal-close retest produced no new cores.

A short Steam deadline interrupted first-start client extraction after its approximately 505 MB bootstrap download. The longer normal-close retest reached the sign-in UI. Stock idle locking also blocked screencopy during an unattended attempt; its JSON API reported a secure PAM-backed lock. The harness subsequently used normal virtual input/activity and a fresh authenticated session, not disabled security settings. QMP screendump reported `no surface` with this EGL configuration; native guest screenshots worked. An optional host VNC-module installation timed out awaiting authorization and was not installed or needed.

## Reproducible evidence and remaining boundaries

Private artifacts: `~/.local/state/arch-setups/vm-tests/fresh-omarchy-4.0.6.93jEYF/`. Keep this directory private: it contains disposable SSH/password material, unencrypted guest disks, application logs and transient sign-in screens. Do not commit or publish it.

- `vm.json`, `vmctl.py`, install driver/harness, clean base and `runs/safe-profile-final/` retain configuration, disks, logs, inventories, reboot result and screenshots.
- Fresh end-to-end source archive: `setup-snapshot-r4.tar.gz`, SHA256 `a13e6d55c6d7cc732f7b200b2357eb9251104dd8c2bd261e71208dfe5fba446a`.
- Corrupt-marker hardening/final repeat-validation archive: `setup-snapshot-r5.tar.gz`, SHA256 `4e3f92f73178eac0643e8017718431512656c5431726540c393c69295193dd65`. Its only runtime-code difference from r4 is stricter rejection of invalid existing recovery markers; that path was exercised in the guest. Documentation and the CI Stow dependency were finalized afterward.
- Adjacent snapshot manifests record source revision, per-file hashes and modes. Test log: `/tmp/arch-setups-vm-followup-tests.log`; the `/tmp` copy is temporary, not a setup dependency.

Still required: personal/custom-plugin live lifecycle acceptance; physical monitor/hotplug/DPMS/scaling/theme/lock checks; service and provider authentication/real dispatch; game runners, actual games, HDR and upscalers; hosted clean-checkout CI. The image did not need a new kernel during initial preparation, so the bootstrap's new-kernel stop/retry paths remain fixture-tested rather than experimentally forced. No power-loss or global rollback guarantee is claimed.
