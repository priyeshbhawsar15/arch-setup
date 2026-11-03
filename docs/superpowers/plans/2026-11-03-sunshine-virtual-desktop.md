# Virtual Desktop 1080p implementation plan

Approved direction: a separate Moonlight PC entry preserves the existing
physical Desktop and Steam capture profile. The isolated live probe confirmed
wlr capture of a 1920x1080@60 headless Hyprland output with RX 6800 VAAPI H.264/HEVC.

1. Add regression tests for isolated configuration/state, required apps schema,
   idempotence and refusal to adopt unowned profiles/virtual outputs.
2. Add a single runtime/configuration helper under `sunshine/`, a dedicated
   systemd user unit and a feature installer requiring the existing Sunshine
   installer. Keep the native package and main config untouched. Port base
   48989, private independent state/certs, fixed 1080p output, native theme,
   clean owned-output removal and focus preparation/restoration.
3. Add only LAN-private/Tailscale-scoped UFW rules using an owned application
   profile/helper, with on/off cleanup. Do not enable UFW or forward router ports.
4. Register the opt-in installer after Sunshine, disable it in shipped profiles,
   remember direct choices, and update SCRIPTS.md, PLUGINS.md and the feature guide.
5. Deploy and inspect virtual output/capture/ports, verify the original host stays
   active, test disable/enable cleanup and run the repository suite. Client pairing,
   actual stream performance and monitors-off/reboot behavior remain explicit
   end-to-end checks; no reboot or physical monitor shutdown during setup.
