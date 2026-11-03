# Optional SDDM automatic login with startup locking

Enable for the current desktop user:

```sh
./install-sddm-autologin.sh --enable
./install-sddm-autologin.sh --status
```

Disable and return to the SDDM password prompt on the next boot:

```sh
./install-sddm-autologin.sh --disable
```

These commands request system authentication only when the SDDM configuration
needs to change; an identical setup is checked without privilege. Neither restarts SDDM, reboots,
locks the existing session nor logs you out. Enable takes effect on the next boot;
disable takes effect on the next SDDM login cycle. `Relogin=false` means deliberate
logout returns to the greeter rather than automatically logging back in.

The installer requires installed SDDM, the `hyprland-uwsm.desktop` session,
Python 3, systemd user services and a currently working Omarchy password lock.
It checks the native lock's `passwordPam` readiness before enabling. The feature
is disabled in both the safe and personal profiles by default. Direct successful
enable/disable commands remember your choice for future `./install-all.sh` runs.
For a fresh install, opt into `install-sddm-autologin.sh` in your selected profile
and run setup from the logged-in desktop. The installed Omarchy UWSM session
is required; this feature does not require deploying personal Hyprland settings. The installer is registered after Hyprland in `install-all.sh`; normal
runs reconcile the selected enabled policy and print `already installed` for
existing software/configuration.

The root helper manages only `/etc/sddm.conf.d/90-arch-setups-autologin.conf`,
backing up changed owned versions under `/var/lib/arch-setups/backups/` in private
directories. Enabling selects the invoking user and the UWSM Hyprland session.
Disabling writes empty User/Session values so earlier defaults cannot silently
restore autologin. Foreign contents, symlinks and conflicting higher-priority
SDDM settings are refused. Themes, greeter compositor settings and PAM files
are left alone. The dedicated session avoids changes to the package-managed
Hyprland entrypoint and personal Lua modules.

The user service `arch-sddm-autolock.service` starts on graphical-session
activation. It requests the existing themed Omarchy lock as soon as shell IPC is
ready, with no deliberate startup delay, then polls until the session lock reports
`secure=true`. A successful lock request alone does not count as success. If this
does not happen within about 30 seconds, it requests `uwsm stop` to return to
SDDM and fails visibly in the journal. `Relogin=false` avoids an autologin loop.
This is a bounded startup check, not a replacement for Omarchy's regular lock,
idle, suspend or shell-crash recovery. It uses whichever supported native lock
implementation is active (built-in or Lock Explorer), preserving theme tokens.
While enabled, every new graphical session is locked, including manual logins.
The service remains completed after unlocking and stops with the session; it
should not relock when just the shell is restarted. Existing independent lock
units, including disabled legacy Hyprlock files, are not modified or enabled.

Automatic login happens **before** the locker can initialize. A brief unlocked
interval is possible; this is not equivalent to requiring authentication at SDDM.
If stopping UWSM fails too, the helper reports failure and cannot guarantee a
locked session. Disk-encryption prompts still require their own boot unlock, and
password-protected keyrings may remain locked after automatic login. Sunshine
can start inside the session, but capturing/typing at the lock screen remotely
still requires a real client test.

Verify after the next reboot:

```sh
./install-sddm-autologin.sh --status
systemctl --user status arch-sddm-autolock.service
journalctl --user -b -u arch-sddm-autolock.service
omarchy-shell lock status
```

Expect a locked screen without first entering the SDDM password; the journal
should report `Startup session lock is secure.` Authenticate using your normal
password. Confirm Moonlight video/input and remote unlocking before relying on
unattended access. The installer never initiates a reboot for this check.

Removal: disable first, then remove only the owned user helper
`~/.local/lib/arch-setups/sddm-autolock.py` and unit
`~/.config/systemd/user/arch-sddm-autolock.service`, followed by
`systemctl --user daemon-reload`. Keep the disabled SDDM drop-in to override any
older automatic-login configuration, or remove it only after checking no other
SDDM file enables automatic login. Keep SDDM and unrelated configuration intact.
User-file updates are backed up under `~/.local/state/arch-setups/backups/`.

References: [SDDM configuration](https://man.archlinux.org/man/sddm.conf.5.en),
[Hyprland/UWSM shutdown guidance](https://wiki.hypr.land/Configuring/Basics/Dispatchers/).

See [validation results and pending reboot checks](VALIDATION.md).
