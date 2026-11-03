# Validation (2026-10-31)

Current policy: simultaneous LAN and Tailscale access via an IPv4 wildcard listener. Earlier single-address entries below are historical checkpoints.

- Sunshine configuration regression passes: disables old UPnP settings (including duplicates), removes obsolete CSRF origins, preserves monitor selection and pairing data, privately backs up the original and makes no extra backup on a second run.
- `bash -n install-sunshine.sh sunshine/start.sh install-all.sh` passes.
- `git diff --check` passes; personal feature-profile validation passes.
- `python3 tests/run.py`: 234 tests run, five failures in the existing Lutris integration tests, with 27 private-source integration tests explicitly unselected. Each failure reports unavailable display/glxinfo and incompatible Gdk namespace versions (Gdk 4 loaded where Lutris requires 3):
  - `test_active_lutris_refuses_sync_before_creating_user_state`
  - `test_existing_game_preserves_unmanaged_fields_and_backs_up_changes`
  - `test_fresh_profile_initializes_database_before_importing_games`
  - `test_selected_profile_loads_through_lutris_in_both_directory_layouts` (`legacy=False`)
  - `test_selected_profile_loads_through_lutris_in_both_directory_layouts` (`legacy=True`)
- `python3 -m unittest discover -s tests`: 139 tests run, passing with 27 private-source tests skipped.
- The network policy was applied to this PC after a private backup and a second run confirmed idempotence.
- ShellCheck is unavailable: the local mise shim has no configured ShellCheck version.
- Live Tailscale is enrolled at `<Tailscale-IP>`; Sunshine package installation requires system authentication. Live encoder/capture, input/audio, Moonlight pairing and enable/disable verification remain pending until installation is authorized/completed. The preexisting `output_name = DP-5` points to a currently attached 1080p monitor; it is preserved.

## Live installation (2026-11-03)

System authentication completed; Omarchy Sunshine `2026.914.233613-1` installed. The first startup exposed an invalid bracketed CSRF origin and a stall on Hyprland's unavailable RemoteDesktop portal. Corrected the origin to the documented comma-separated format and configured DRM/KMS capture. The package provides `cap_sys_admin,cap_sys_nice=p`. Sunshine now maps the preserved DP-5 display successfully, detects AMD Radeon RX 6800 Vulkan H.264/HEVC hardware encoders and starts its UI. HTTP authentication returns 401 as expected without credentials. TCP listeners 47984/47989/47990/48010 bind only `<Tailscale-IP>`, with IPv4, mandatory stream encryption and UPnP disabled. Existing credentials were retained. Moonlight pairing and end-to-end video/audio/input validation still require the client device.

Disable/enable lifecycle verified: disable stops the service and removes its listeners; enable restores autostart and Tailscale-only listeners. A subsequent normal installer run reports existing package/configuration and starts successfully. The full suite was rerun on November 3: the same five Lutris integration failures remain; no Sunshine/configuration tests failed.

## Mobile pairing repair (2026-11-03)

Confirmed repeated TLS rejection with `Client certificate identity is not enabled`.
Inspection of the installed version's upstream `nvhttp.cpp` showed its
`is_client_enabled` rejects multiple records matching the same X.509 certificate.
The phone certificate occurred six times, all enabled. A stopped-service repair
privately backed up the full state and removed five duplicate records, retaining
the newest phone pairing and the two unrelated unique clients. No admin password,
server key/certificate or client trust checks were reset. Regression tests cover
identity deduplication, preservation of unrelated state, no mutation of the input,
idempotence and refusal to override disabled records. Client retry is pending.

After repair, verified three records with three unique certificate identities, active service and all four TCP listeners restricted to Tailscale. Both Sunshine regression tests pass. Full suite: 235 tests, the same five previously listed Lutris display/GTK integration failures; 27 private-source tests explicitly unselected.

## Full identity reset (2026-11-03)

At the user's request after the retry still failed, added and ran explicit
`--reset-pairing`. With the service stopped, privately backed up the full state,
host certificate and private key, removed all current/legacy pairing trust and
the previous host identity, and restarted Sunshine. Verified zero paired clients,
a newly generated host certificate with a different SHA-256 fingerprint, a new
private key, unchanged username/password hash/salt, active service and HTTP 401
for unauthenticated administration. All three Sunshine tests pass, including
reset preservation/backups. Each Moonlight client must forget the old PC entry
and pair once against this new identity; end-to-end client retry remains pending.

Full suite after reset support: 236 tests, the same five Lutris display/GTK failures listed above; 27 private-source tests explicitly unselected. No Sunshine test failures.

## LAN binding fix (2026-11-03)

Confirmed SIGABRT/coredump with `Cannot assign requested address` while Sunshine
was launched with the absent `<Tailscale-IP>` Tailscale address. Stopped the crash
loop, replaced the managed launcher with private-LAN address discovery from the
active default-route interface, and removed Sunshine's Tailscale dependency.
Backed up/migrated the owned legacy launcher/drop-in to `sunshine-host` and
`arch-setups-network.conf`. Tailscale's service, enrollment and unrelated settings
were not changed. Current LAN binding is `<LAN-IP>` and is detected at startup,
not pinned to this machine in source. No firewall/router rules were changed.

Verified live with Tailscale absent: active service, zero automatic restarts
since the fix, and TCP 47984/47989/47990/48010 listening only on `<LAN-IP>`.
Administration returns 401 without credentials. UPnP remains disabled and stream
encryption required. Five Sunshine tests pass, including current/DHCP-changed
private addresses, Tailscale independence and refusal of non-LAN addresses.
Shell syntax and diff checks pass. Complete suite: 244 tests, the same five
Lutris display/GTK integration failures listed above; 27 private-source tests
explicitly unselected. Client video/audio/input and external LAN firewall access
still require testing from Moonlight.

## Simultaneous LAN and Tailscale (2026-11-03)

Changed the managed launcher to `bind_address=0.0.0.0` so the same Sunshine
instance accepts LAN, loopback and Tailscale IPv4 connections, including when
interfaces appear after startup. It no longer queries routes or calls Tailscale.
UPnP remains disabled, both encryption modes stay mandatory, and the configuration
keeps native CSRF checks outside exact current host IPv4 origins. Removed an
initial empty CLI override rejected by this Sunshine version; the existing
managed empty config value provides the native defaults correctly.

Verified service active with zero automatic restarts after correction. All four
TCP listeners bind `0.0.0.0`. From this host, `127.0.0.1`, `<LAN-IP>` and
`<Tailscale-IP>` each return HTTP 200 for native serverinfo and HTTP 401 for
unauthenticated administration. The bundled frontend reports CSRF errors but does not fetch tokens, so the
launcher retains exact current host IPv4 origin allowances for browser administration.
Origin discovery is best-effort and is not used for binding or startup readiness. No firewall, router, pairing or Tailscale settings were
changed. External client playback/input and remote LAN administration remain
subject to firewall/tailnet policy and need a client test.

Four Sunshine regression tests pass, including wildcard binding with both
network helpers unavailable. Shell syntax and diff checks pass. Complete suite:
243 tests run with the same five Lutris display/GTK failures named above;
27 private-source tests explicitly unselected.
