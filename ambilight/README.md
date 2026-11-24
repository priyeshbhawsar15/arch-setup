# Room ambilight (HyperHDR → WLED)

HyperHDR captures the main OLED (MSI MAG321UP, `DP-6`) through PipeWire and drives three WLED
controllers, so the room extends the picture while watching films or playing games.
`install-hyperhdr.sh` sets everything up; `~/.local/bin/ambilight` (this directory's `ambilight.py`)
owns the LED layouts and profiles.

| Zone | WLED | LEDs | Shows |
|---|---|---|---|
| monitor (instance 0) | `192.168.2.160` | 129 behind the monitor + 40 under it | screen edges; the 40 show the bottom of the image |
| window (instance 1) | `192.168.2.161` | 213 | left side of the image |
| bed (instance 2) | `192.168.2.162` | 209 curtain + 205 under the bed | right side of the image; under-bed is always the screen average |

Strip directions, as seen from the desk chair: the monitor strip starts bottom-left and runs
counter-clockwise; the window strip starts bottom-right and runs up, across the top and down (no
bottom run); the bed-curtain strip starts bottom-left and runs up, across and down. The under-bed
strip starts at the head of the bed. Counts, start corners, hosts and power limits are in
`~/.config/ambilight/layout.json`, seeded once from `ambilight/layout.json` and then yours to edit.

## Use

| Keys | Command | Effect |
|---|---|---|
| Super + Alt + A | `ambilight mapping toggle` | **spatial** (each zone mirrors its side of the image) ⇄ **average** (window and bed curtain show the screen average; the monitor stays spatial). Restarts HyperHDR, about 3 s. |
| Super + Ctrl + Alt + A | `ambilight profile cycle` | auto → movie → game → work → off |

Profiles are applied live:

- **movie**: all zones on, black-bar detection on.
- **game**: all zones on, black-bar detection off.
- **work**: every WLED returns to its own preset.
- **off**: the same as work, and automatic switching stops.
- **auto** (default): `ambilight-watch.service` picks **game** while Gaming Mode is active or a
  Steam/Gamescope/`.exe` window is fullscreen on the OLED, **movie** for any other fullscreen app
  there, and **work** otherwise.

Other commands: `ambilight status`, `ambilight capture-check`, `ambilight test monitor|window|bed` (LED 0 green, first LED of
each side blue, last LED red, first under-monitor LED yellow; Enter resumes), `ambilight
wled-limits [--check]`, `ambilight verify-db`.

## Design notes

- **Three instances**: HyperHDR drives one LED device per instance, and separate instances give
  each zone its own smoothing (monitor 80 ms, room 280 ms) and brightness cap (room 190/255).
- **Capture**: PipeWire with `hardware: false`. GPU dmabuf import fails on the RX 6800
  (`eglCreateImageKHR … Arguments are inconsistent`), so frames come through MemFD at 30 fps and a
  512 px width, using about 18% of one CPU core. Hyprland's screencopy already delivers SDR-mapped
  frames with `cm = "hdr"`, so HyperHDR's HDR tone mapping stays off. The screen-share choice is
  stored as a restore token in HyperHDR's database (`xdph` has `allow_token_by_default`).
- **Capture watchdog**: at login HyperHDR sometimes never receives the screen-cast portal's
  `CreateSession` reply and never retries, so no frames arrive and every zone switches off
  (`No source left`). `ambilight capture-check` runs as `ExecStartPost` and fails the start when the
  capture input is not active within 30 s, so systemd restarts HyperHDR (at most 5 tries in 10 min).
  It is skipped while no screen-share choice is saved, so the first-run picker is never interrupted,
  and while screen capture is switched off in the web UI.
- **Database ownership**: HyperHDR's admin API needs the web-UI password, so layout changes are
  written to `~/.config/HyperHDR/db/hyperhdr.db` with HyperHDR stopped. `setup-db` only reconciles
  the settings it owns: instances, `device`, `leds`, `smoothing`, `systemControl`, `videoControl`
  and the PipeWire grabber. Colour calibration and other web-UI changes survive reruns. Profiles
  use only non-admin API calls (component state and adjustment).
- **Under-bed average**: the 205 LEDs tile the whole screen once and share LED group 2, so HyperHDR
  averages them into one colour without sampling the full frame 205 times.
- **Power**: the LEDs run off a 450 W PC PSU's 5 V rail. WLED's limiter is set to 3/4/6 A
  (13 A total) from `maxCurrent` in the layout.
- **WLED hand-back**: `restoreOriginalState` makes each controller return to its own preset when
  HyperHDR stops or a profile turns a zone off.

## Enable, disable, remove

- `./install-hyperhdr.sh` installs or reconciles the feature. Reruns report `already installed`.
- `--disable` stops both services; every WLED returns to its preset.
- `--remove` also backs up and removes the helper and units. The HyperHDR package, its database and
  `layout.json` are kept.
- The keys are bound only while `~/.local/bin/ambilight` exists.

## Pending acceptance

- On the first start, pick the main monitor in the screen-share dialog.
- Check each strip with `ambilight test`.
- Calibrate curtain colour (navy fabric shifts the colour) in HyperHDR's per-instance colour settings.
