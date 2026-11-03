# Sunshine over LAN and Tailscale

Install from this checkout with `./install-sunshine.sh`, or select that installer
in the profile passed to `./install-all.sh --profile FILE`. Sunshine is optional
in the safe base. Successful direct installer on/off choices are remembered.
Tailscale is a separate optional application, not a Sunshine startup dependency.

Use the same Sunshine host through either address in Moonlight:

- On the local network: this PC's LAN IPv4.
- Remotely through Tailscale: this PC's Tailscale IPv4,
  with both devices connected and authorized by your tailnet policy.

Find the current addresses with `ip -4 -brief address`, or `tailscale ip -4`
while Tailscale is connected. The service listens on IPv4 `0.0.0.0`, meaning all
local IPv4 interfaces, so it supports LAN and Tailscale at the same time. It
starts even if neither interface is ready yet and automatically accepts traffic
on interfaces that appear later; changing DHCP addresses or reconnecting
Tailscale does not require restarting Sunshine. Never enter `0.0.0.0` as the
host address in Moonlight. `~/.local/bin/sunshine-host --print-address` displays
this wildcard binding only for diagnostics.

On this PC, open `https://localhost:47990` to administer Sunshine. The LAN or
Tailscale IP with port 47990 also works where the host firewall permits remote
administration. Verify the address before accepting the self-signed certificate.
Enter Moonlight's pairing PIN in Sunshine and start Desktop. Existing credentials
and pairings are preserved. Start with 1080p60 and 15–20 Mbps, then test video,
audio, keyboard/mouse and controller input through both network paths.

UPnP remains disabled and encryption is required for LAN- and WAN-classified
streams. The packaged browser UI needs exact trusted origins for its requests; the
launcher discovers current host IPv4 origins best-effort at each startup. Other
origins retain native CSRF checks. Native streaming accepts newly appearing
addresses without restarting; remote administration through a new address may
require a Sunshine restart to refresh the origin list. Localhost administration
remains available. Missing address discovery never blocks startup. Administration requires the existing login. Manual Sunshine starts
outside the managed service default to loopback through the configuration file.

No router forwarding or firewall rules are changed by the installer. Binding
`0.0.0.0` listens on every IPv4 interface; the host firewall determines which
networks may reach it. For LAN access, allow only intended LAN sources/interface
to TCP 47984,47989,48010 and UDP 47998,47999,48000,48002,48010. For tailnet access,
allow these on `tailscale0` as needed; Tailscale's normal netfilter integration
usually accepts tailnet traffic. TCP 47990 is needed only for remote
administration. Existing broad rules are not automatically removed. No public
router forwarding is needed for LAN or Tailscale use. Public/browser streaming
is not configured here.

Check service and capture logs:

```sh
systemctl --user status sunshine
journalctl --user -u app-dev.lizardbyte.app.Sunshine -b --no-pager
```

Existing `output_name` is preserved: change it in Sunshine's Audio/Video settings
if needed. Managed capture uses DRM/KMS to avoid the unsupported RemoteDesktop
portal on Hyprland; the package supplies the required capture capabilities.
Sunshine probes the available encoders rather than hardcoding a GPU. It shares
the running desktop; it does not create a headless display or bypass the lock.
For optional automatic session startup and locking, see [SDDM controls](../sddm/README.md).

Disable/re-enable using `./install-sunshine.sh --disable` or `--enable`.
Updates preserve unrelated settings and pairings. Backups live under
`~/.local/state/arch-setups/backups/sunshine-*`. The installer privately backs up
and removes its owned legacy `sunshine-tailscale` launcher and
`arch-setups-tailscale.conf` drop-in when migrating to `sunshine-host` and
`arch-setups-network.conf`. Foreign files are refused. Packages update through
Omarchy; rerun the installer afterward. See `PLUGINS.md` for removal and
[validation results](VALIDATION.md) for pending client checks.

## Mobile client certificate rejection

Sunshine 2026.914.233613 can retain multiple paired-device records with the
same certificate after repeated PIN pairing. Its exact-identity verification
rejects duplicate matches with `Client certificate identity is not enabled`,
which Moonlight reports as “client is not verified” / “certificate not verified”.
This is separate from a browser's self-signed server-certificate warning.

Run `./install-sunshine.sh --repair-pairing` to stop Sunshine, privately back up
its complete state and retain the newest enabled record per duplicate
certificate. The previous running state is restored afterward. Unique clients,
server identity and administrator credentials are retained; groups containing
any disabled entry are refused so deliberate revocations are not overridden.
Try the existing host entry in Moonlight afterward; avoid repeatedly pairing
an already-paired device. No certificate checks or encryption are disabled.
Backups are in `~/.local/state/arch-setups/backups/sunshine-pairing-*`.

## Start pairing completely fresh

Explicitly run `./install-sunshine.sh --reset-pairing` to back up and clear all
Sunshine paired-client certificates (including legacy records) and regenerate
its host certificate/key and host ID on restart. The administrator login and
streaming/network settings are preserved. This revokes every prior Sunshine
client, including laptop and web clients; it does not alter Tailscale identities.
Normal installs and updates never run this reset automatically.

On each Moonlight client, delete/forget the old PC entry first. Add this PC's
current LAN address again, start pairing once and enter that PIN in Sunshine's
web UI. The browser may show a certificate warning again because the host
certificate changed. Don't repeatedly enter new PINs for an already-paired PC.
Private recovery backups live in `~/.local/state/arch-setups/backups/sunshine-reset-*`.

For an independent software-only 1080p monitor and separate Moonlight PC entry,
see [Virtual Desktop 1080p](VIRTUAL-DESKTOP.md).
