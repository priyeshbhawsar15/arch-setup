# Virtual desktop validation — 2026-11-03

Approved setup: separate **pb-desk Virtual 1080p** PC entry in Moonlight, preserving
the existing physical Desktop/Steam host. Both share the actual Linux session.

Verified on this PC:

- Hyprland created the named headless output at **1920×1080, 60 Hz, scale 1**.
- An isolated wlr capture probe selected the named virtual output. Sunshine
  detected the **AMD Radeon RX 6800 VAAPI H.264/HEVC encoders**. Initial temporary
  probe failures were traced to a missing required `env` object in apps.json;
  the corrected schema is covered by the configuration test. This was not a
  virtual-capture failure. Temporary probe output, profile and keys were removed.
- The installed virtual service is active, with zero automatic restarts after
  enable. Its independent profile, server key/cert and client trust are separate
  from the main host; only admin authentication was seeded once.
- Native serverinfo reports **pb-desk** on 47989 and **pb-desk Virtual 1080p** on
  48989 with distinct host identities. The original service remains running
  with its original process and physical settings; its config/apps were not
  modified by this feature.
- Virtual native HTTP returns 200 and unauthenticated admin HTTPS returns 401
  through loopback, LAN `<LAN-IP>` and Tailscale `<Tailscale-IP>` from this host.
  TCP listeners bind 48984/48989/48990/49010 on IPv4. Scoped UFW rules permit
  only RFC1918 sources or the tailscale0 interface; no router forwarding added.
- Disable removed the owned virtual output and exact feature firewall rules;
  all three physical outputs and the original Sunshine service remained active.
  Re-enable restored output/rules, retained data and reported existing config.
- App `prepare` focused the virtual monitor; `finish` restored the previous
  physical monitor. Resolution/rate remained 1920×1080@60.
- Eleven virtual-host regression tests cover profile isolation/auth-only seeding,
  required apps schema, user-added app preservation, refusal to adopt/remove
  unowned outputs, creation/focus restoration/removal, compositor-session and
  output-ID mismatches, disabled-output cleanup, ended-compositor cleanup, live
  removal failures/CLI status and unchanged enable without restart. Fifteen tests
  across both Sunshine test files pass. Shell syntax and diff checks pass;
  error-severity ShellCheck 0.11.0 and systemd user-unit verification pass too.
  Six feature-profile tests also pass. The updated helper was backed up/deployed
  without restarting the running virtual host (PID 203802, zero restarts), keeping
  the diagnostic terminal available for the client's next connection.
- The independent host paired with a client. Logs show client connection,
  VAAPI H.264 stream initialization and later disconnection. The user reported
  an empty/blue view. Inspection found no windows on the virtual workspace. A
  diagnostic terminal was then opened on that output, and a 1920×1080 grim
  capture shows the terminal correctly. The user subsequently confirmed that
  **the virtual desktop works in the native mobile Moonlight app**, as does the
  original Desktop host.
- The blank/blue view was through the separate Moonlight Web gateway at
  `<gateway-IP>:8084`, not the native mobile app. Both physical and virtual hosts
  fail in that browser gateway. Its container logs report reception of the first
  video packet, then termination with `a received video rtp packet doesn't have
  the configured packet size`. The gateway's moonlight-common-rust library
  [does not support video encryption](https://github.com/MrCreativ3001/moonlight-common-rust#feature-support),
  while both Sunshine profiles require LAN/WAN encryption (mode 2). This matches
  the observed failure; no packet-content inspection was needed.
- The user chose **keep encryption mandatory; use the native app**. Both services
  remain active with their original process IDs and zero automatic restarts.
  No gateway deployment, pairing resets or encryption-policy changes were made
  during browser diagnosis. The gateway's Compose explicitly keeps WebRTC UDP
  unpublished for WebSocket use; this was inspected and left unchanged. Its
  WebRTC logs also show ICE negotiation failures, so encryption support alone
  would not establish browser connectivity.

Pending real-client checks: audio/input validation and quantitative
latency/drop-rate measurement at 1080p60, physical monitors powered off, virtual
lock-screen capture/remote unlocking, and reboot with all physical monitors off.
The encoder probe is not a stream benchmark or proof of those lifecycle cases.
Do not run both Sunshine hosts concurrently when input/audio conflicts matter.

Full repository suite: 246 tests, five preexisting Lutris GTK/display integration
failures; 27 private-source tests explicitly unselected. Failures:

- `test_active_lutris_refuses_sync_before_creating_user_state`
- `test_existing_game_preserves_unmanaged_fields_and_backs_up_changes`
- `test_fresh_profile_initializes_database_before_importing_games`
- `test_selected_profile_loads_through_lutris_in_both_directory_layouts`
  (`legacy=False` and `legacy=True`)

These fail because a display/glxinfo is unavailable and Gdk 4 is already loaded
where Lutris requires Gdk 3. No virtual-desktop tests failed.
