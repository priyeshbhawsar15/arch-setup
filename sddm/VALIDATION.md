# Validation — 2026-11-03

Enabled on this PC for user `priyesh`, session `hyprland-uwsm.desktop`, with
`Relogin=false`. The dedicated startup-lock unit is enabled and intentionally
inactive in the current session; enabling did not start the locker, restart
SDDM, log out or reboot. Installed helper and unit exactly match the repository.
A second installer run reports existing configuration and requires no system
authentication. Profile planning selects this remembered feature independently
of the repository's personal Hyprland-settings installer, which is not enabled
in this PC's current base selection.

Verified:

- Five feature tests pass: enable/disable idempotence and backups, unrelated-file
  preservation, foreign/conflicting SDDM override refusal, read-only checks,
  waiting for `secure=true` rather than a mere lock request, and requesting
  UWSM shutdown when the native lock cannot secure the session.
- Profile regression confirms opting into autologin does not also require or
  silently enable deployment of personal Hyprland settings.
- Live native Omarchy lock IPC reports password authentication ready.
- `systemd-analyze --user verify` accepts the installed service and its ordering.
- Shell syntax and `git diff --check` pass.
- Complete suite: 242 tests run, five existing Lutris integration failures;
  27 private-source tests explicitly unselected. The Lutris failures report an
  unavailable display/glxinfo and Gdk 4 already loaded where Lutris requires 3:
  - `test_active_lutris_refuses_sync_before_creating_user_state`
  - `test_existing_game_preserves_unmanaged_fields_and_backs_up_changes`
  - `test_fresh_profile_initializes_database_before_importing_games`
  - `test_selected_profile_loads_through_lutris_in_both_directory_layouts`
    (`legacy=False` and `legacy=True`)

Pending: a real next-boot check that SDDM automatically starts the user session,
the themed lock becomes secure and can be authenticated locally/remotely, and
Sunshine works through the locked session. No reboot or live forced lock was
initiated for testing. Automatic login still precedes the locker's initialization;
a brief unlocked startup interval is possible. Failure handling is tested with
an external-command fixture so a failed test cannot log out the actual user.
