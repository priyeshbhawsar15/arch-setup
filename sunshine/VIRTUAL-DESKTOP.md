# Optional Virtual Desktop 1080p

This adds a second **pb-desk Virtual 1080p** PC in Moonlight. It shares the same
Linux login, applications, input and audio as the local desktop, with a dedicated
1920×1080@60 virtual monitor. It is not a separate Linux user session or VM.
The physical Desktop/Steam Sunshine host retains its KMS backend, monitor
selection, ports, credentials and pairings. Sunshine chooses capture/display
globally, so independent hardware/virtual profiles need separate host instances.

Enable, inspect or disable from the repository:

```sh
./install-virtual-desktop.sh --enable
./install-virtual-desktop.sh --status
./install-virtual-desktop.sh --disable
```

Requires installed Sunshine, Mesa VAAPI (from `install-sunshine.sh`), a running
Hyprland UWSM graphical session, iproute2/Python and systemd user services. No
additional package or plugin source is installed. This is opt-in in both shipped
profiles, registered after/requiring Sunshine in the single-script setup. Direct
successful choices are remembered; disabling prevents later automatic reinstall.
For fresh setup, include both installers in the selected profile.

The installer creates an independent private profile under
`~/.config/sunshine-virtual/sunshine/`, a helper at
`~/.local/lib/arch-setups/sunshine-virtual.py`, and the user service
`arch-sunshine-virtual.service`. The profile uses `capture=wlr`, `encoder=vaapi`,
fixed output `SUNSHINE-VIRTUAL-1080P`, SDR H.264/HEVC and port base **48989**.
The initial live probe captured this named headless output and detected the
RX 6800 VAAPI hardware encoders. An enabled feature keeps the virtual output
present, even before a stream, so capture probing also works with real monitors
off. It adds desktop rendering work; actual 1080p60 latency/drop-rate testing
requires a Moonlight client.

The service creates only its owned output, sizes it via the current Hyprland Lua
API, and removes it on stop. Output ownership is tied to the compositor session
and output ID; a preexisting unowned output with the same name is refused.
Physical outputs are not disabled or repositioned. Starting the virtual app
focuses its monitor; quitting the app in Moonlight restores the previous monitor
if the focus is still virtual. Window placement is shared: windows opened before
streaming can remain on physical monitors. Local and remote users should avoid
using both Sunshine hosts concurrently, since input and audio are shared.
No physical monitor power, keybindings, theme or package-managed Lua files change.
The virtual monitor uses the normal Omarchy desktop/lock theme.

### Scale, position and input

`hypr/monitors.lua` (deployed by `install-monitor-layout.sh`) owns two rules for
`SUNSHINE-VIRTUAL-1080P`, re-applied on every config reload and monitor change:

- **Scale 1.** The helper sets scale only at runtime. Any reload, including
  hyprmoncfgd re-applying its profile on each monitor change, drops that, and
  the catch-all `scale = "auto"` picks 2, so the stream looks zoomed in.
- **A monitor at 0,0.** Sunshine sends absolute mouse positions as a fraction
  of a desktop it measures from 0,0. Hyprland spreads them across the enabled
  outputs only. When the left monitor is off the layout starts at x=2560, and
  the cursor lands up to ~740 px left of where the client points. So the
  virtual output takes 0,0 whenever no other monitor is there, and otherwise
  sits to the right of everything. While it is at 0,0 there is a gap to the
  physical monitors, so the local mouse cannot slide onto it.

Use Moonlight's absolute ("Follow") mouse mode. Relative mode moves the shared
cursor, which can leave the virtual monitor. Sunshine measures the desktop when
a stream starts, so reconnect after turning a monitor on or off.

Windows keeps the Win key unless a browser client's Keyboard Lock is active.
`install-keyd.sh` therefore makes Caps Lock (and a held `` ` ``) act as Super
for Sunshine's virtual keyboard only; physical keyboards are unaffected.

## Connect and pair

In Moonlight, add the PC manually using:

- LAN: `<LAN-IP>:48989` (replace the IP if DHCP changes).
- Tailscale: `<Tailscale-IP>:48989` while both devices are connected/authorized.

The advertised name is **pb-desk Virtual 1080p** (hostname-derived on another PC).
Open **https://localhost:48990** on this PC to approve the new host's pairing PIN.
Remote administration is also available at the corresponding IP and port where
firewall/tailnet policy allows. The host has its own certificate, UUID and client
pairing list. The existing Sunshine administrator username/password hash/salt are
seeded once if present, so initially use the same administrator login; subsequent
password changes are independent. No existing client trust is copied or reset.
If the main host has no admin account yet, the installer stops: create one at
`https://localhost:47990` first, then rerun it. The virtual host never starts without a login.
Accept the self-signed certificate only after verifying the host address.

Launch the **Virtual Desktop 1080p** tile in that new PC. Set Moonlight to
1920×1080, 60 FPS, SDR initially. Check its statistics overlay for dropped frames
and decode/network latency, then test with the physical monitors off and after
reboot. Do not assume the probe established stream performance or remote unlock.

The new monitor can initially be an empty background: existing windows remain
on their physical monitors, and desktop bars/wallpaper depend on the installed
shell's monitor selection. Launch an application on the focused virtual monitor
using the normal desktop shortcuts. Moonlight's keyboard/sidebar controls are
client UI; their visibility alone does not establish that desktop video works.

Use the native Moonlight app for this encrypted host. The user's separate
Moonlight Web gateway currently uses a protocol library that
[does not support encrypted video](https://github.com/MrCreativ3001/moonlight-common-rust#feature-support).
It can report connection completion and then show an empty background while its
server logs a video packet-size error. Both Sunshine hosts deliberately retain
mandatory LAN/WAN encryption; the native mobile app has been confirmed to show
the virtual desktop. Browser-gateway compatibility needs a client implementation
that supports encrypted video as well as working browser transport/decoding.

## Network policy

Both interfaces are supported through IPv4 wildcard binding. UPnP is disabled,
stream encryption mandatory, and exact active-host administration origins are
added best-effort. No router ports are forwarded and Tailscale is not required
to start the service.

A dedicated UFW application profile, `/etc/ufw/applications.d/arch-sunshine-virtual`,
opens only this instance's TCP **48984,48989,48990,49010** and UDP
**48998–49000,49002,49010**. Rules permit RFC1918 private LAN sources (10/8,
172.16/12, 192.168/16) or traffic arriving on `tailscale0`; Tailscale ACLs still
apply. The installer uses system authentication, never enables UFW itself, and
removes these exact feature rules on disable. Other firewall/router rules remain
unchanged. The application profile is retained for safe re-enabling. Custom
firewalls must permit equivalent traffic explicitly. This host uses different
ports from the physical Sunshine instance.

## Maintenance and removal

Rerun the installer for owned updates. Managed configuration, helper/unit and
firewall-profile changes are backed up privately under user/root
`arch-setups/backups` directories. User-added apps/environment in the independent
apps list are preserved. Unowned profiles/helpers/units are refused. No credentials
are printed, invented or uploaded. Pairing/profile data survives disable.
Unchanged installs ensure the enabled service is running without restarting it;
managed configuration/helper/unit updates restart the virtual host. Cleanup
includes disabled owned outputs and reports live-compositor failures, retaining
ownership state for retry. An already-ended compositor requires no output removal.

To remove, disable first, then privately archive and remove only the virtual
profile directory, its helper and `arch-sunshine-virtual.service`, and run
`systemctl --user daemon-reload`. Remove the owned UFW application-profile file
only after its rules are deleted. The native Sunshine package, main host and
Tailscale remain intact. No submodule/fork/plugin repository is involved.

Logs: `journalctl --user -u arch-sunshine-virtual -b --no-pager`.
See [validation](VIRTUAL-VALIDATION.md) for actual checks and pending client tests.
