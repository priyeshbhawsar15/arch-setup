#!/usr/bin/env python3
# Managed by arch-setups: room ambilight helper deployed by install-hyperhdr.sh.
"""Room ambilight: HyperHDR (3 instances) -> 3 WLED controllers.

  ambilight status                      current mapping/profile and instance state
  ambilight mapping spatial|average|toggle
                                        room zones mirror their side of the image, or all show the screen
                                        average (under-bed is always the average); restarts HyperHDR ~3 s
  ambilight profile auto|movie|game|work|off|cycle
                                        movie: black-bar detection on; game: off; work: all zones back to normal WLED;
                                        off: everything back to normal WLED; auto: picked from what is fullscreen
  ambilight watch                       daemon: follows Hyprland fullscreen + gaming-mode
  ambilight test monitor|window|bed     light LED 0 green, corners blue, last LED red (pauses HyperHDR output)
  ambilight setup-db                    (HyperHDR stopped) create the instances and reconcile the settings
                                        this tool owns; other HyperHDR settings (web UI edits) are kept
  ambilight verify-db                   exit 0 when the database already matches layout.json and state
  ambilight wled-limits [--check]       apply each controller's maxCurrent (mA) power limit from layout.json

Geometry lives in ~/.config/ambilight/layout.json; edit counts/starts there, then run
`ambilight mapping <current>` to push new layouts. Change HyperHDR settings in its web UI
(http://localhost:8090) as usual; this tool only owns the LED layouts.
"""
import json, os, socket, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

HOME = Path.home()
CFG_DIR = HOME / ".config/ambilight"
LAYOUT_FILE = CFG_DIR / "layout.json"
STATE_FILE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "ambilight/state.json"
DB = HOME / ".config/HyperHDR/db/hyperhdr.db"
API = ("127.0.0.1", 19444)

# Applied live through HyperHDR's non-admin API: black-bar detection, which zones run, monitor gain.
PROFILES = {
    "movie": {"bbd": True,  "room": True,  "mon_gain": 1.0},
    "game":  {"bbd": False, "room": True,  "mon_gain": 1.0},
    "work":  {"bbd": False, "room": False, "mon_gain": 1.0, "monitor": False},
    "off":   {"bbd": False, "room": False, "mon_gain": 1.0, "monitor": False},
}
SMOOTHING_MS = {"monitor": 80, "room": 280}   # fixed; written by setup-db


# ---------------------------------------------------------------- geometry
def clamp(v):
    return max(0.0, min(1.0, v))


def area(h0, h1, v0, v1, group=0):
    led = {"hmin": round(clamp(min(h0, h1)), 4), "hmax": round(clamp(max(h0, h1)), 4),
           "vmin": round(clamp(min(v0, v1)), 4), "vmax": round(clamp(max(v0, v1)), 4), "group": group}
    if led["hmax"] - led["hmin"] < 0.005:
        led["hmax"] = round(min(1.0, led["hmin"] + 0.005), 4)
    if led["vmax"] - led["vmin"] < 0.005:
        led["vmax"] = round(min(1.0, led["vmin"] + 0.005), 4)
    return led


def run(n, fn):
    """n LEDs along a run; fn(t0, t1, i) gets the slice [t0,t1] in 0..1 and returns an area."""
    return [fn(i / n, (i + 1) / n, i) for i in range(n)]


def soften(t0, t1, k, lo=0.0, hi=1.0):
    """Widen a slice by k slices each side (smoother, less sparkly sampling)."""
    w = t1 - t0
    return max(lo, t0 - k * w), min(hi, t1 + k * w)


def screen_average(n, group):
    """n LEDs that together cover the whole screen once; the group makes them all show the mean."""
    cols = max(1, round((n * 16 / 9) ** 0.5))
    rows = -(-n // cols)
    leds = []
    for i in range(n):
        r, c = divmod(i, cols)
        leds.append(area(c / cols, (c + 1) / cols, r / rows, (r + 1) / rows, group))
    return leds


def monitor_leds(g):
    m = g["monitor"]
    D_TB, D_LR = 0.10, 0.07        # sampling depth: top/bottom (of height), sides (of width)
    runs = {
        # each: list of areas in strip order for a counter-clockwise walk from bottom-left
        "bottom": lambda n, rev: run(n, lambda a, b, i: area(*(sorted((1 - b, 1 - a)) if rev else (a, b)), 1 - D_TB, 1)),
        "right":  lambda n, rev: run(n, lambda a, b, i: area(1 - D_LR, 1, *(sorted((a, b)) if rev else (1 - b, 1 - a)))),
        "top":    lambda n, rev: run(n, lambda a, b, i: area(*((a, b) if rev else (1 - b, 1 - a)), 0, D_TB)),
        "left":   lambda n, rev: run(n, lambda a, b, i: area(0, D_LR, *((1 - b, 1 - a) if rev else (a, b)))),
    }
    ccw_from = {"bottom-left": ["bottom", "right", "top", "left"],
                "bottom-right": ["right", "top", "left", "bottom"],
                "top-right": ["top", "left", "bottom", "right"],
                "top-left": ["left", "bottom", "right", "top"]}
    order = ccw_from[m["start"]]
    rev = m.get("direction", "ccw") == "cw"
    if rev:  # clockwise: same corner, sides in reverse order, each side walked backwards
        order = list(reversed(order))
    leds = []
    for side in order:
        leds += runs[side](m[side], rev)
    # 40 LEDs under the monitor: bottom of the image, a bit deeper and softer
    n = m.get("under", 0)
    if n:
        ltr = m.get("under_direction", "left-to-right") == "left-to-right"
        def under(a, b, i):
            a, b = soften(a, b, 1)
            if not ltr:
                a, b = 1 - b, 1 - a
            return area(a, b, 0.80, 1.0)
        leds += run(n, under)
    return leds


def window_leds(g, mapping):
    w = g["window"]
    total = w["right"] + w["top"] + w["left"]
    if mapping == "average":
        return screen_average(total, 1)
    leds = []
    # right side (next to the monitor): left edge of the image, bottom -> top
    leds += run(w["right"], lambda a, b, i: area(0, 0.12, *soften(1 - b, 1 - a, 1.5)))
    # top: top-left band, right end (near monitor) = x 45%, far end = x 0
    leds += run(w["top"], lambda a, b, i: area(*soften(0.45 * (1 - b), 0.45 * (1 - a), 2, 0, 0.45), 0, 0.18))
    # left side (far from the monitor): deeper left area, top -> bottom
    leds += run(w["left"], lambda a, b, i: area(0, 0.25, *soften(a, b, 2)))
    return leds


def bed_leds(g, mapping):
    b_ = g["bed"]
    curtain = b_["left"] + b_["top"] + b_["right"]
    if mapping == "average":
        leds = screen_average(curtain, 1)
    else:
        leds = []
        # left side (nearer the monitor): right edge of the image, bottom -> top
        leds += run(b_["left"], lambda a, b, i: area(0.88, 1, *soften(1 - b, 1 - a, 1.5)))
        # top: top-right band, left end = x 55%, right end = x 100%
        leds += run(b_["top"], lambda a, b, i: area(*soften(0.55 + 0.45 * a, 0.55 + 0.45 * b, 2, 0.55, 1), 0, 0.18))
        # right side (far): deeper right area, top -> bottom
        leds += run(b_["right"], lambda a, b, i: area(0.75, 1, *soften(a, b, 2)))
    # under the bed: always the screen average (its own group)
    leds += screen_average(b_["under"], 2)
    return leds


def layouts(mapping):
    g = load_layout()
    return {"monitor": monitor_leds(g), "window": window_leds(g, mapping), "bed": bed_leds(g, mapping)}


def load_layout():
    if not LAYOUT_FILE.exists():
        sys.exit(f"{LAYOUT_FILE} is missing; run install-hyperhdr.sh from arch-setups to seed it")
    return json.loads(LAYOUT_FILE.read_text())


# ---------------------------------------------------------------- state
def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"mapping": "spatial", "profile": "movie", "auto": True}


def save_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2) + "\n")
    tmp.replace(STATE_FILE)


# ---------------------------------------------------------------- HyperHDR API
class Hyper:
    def __init__(self):
        self.s = socket.create_connection(API, timeout=5)
        self.f = self.s.makefile("rb")
        self.tan = 0

    def call(self, msg):
        self.tan += 1
        msg = dict(msg, tan=self.tan)
        self.s.sendall((json.dumps(msg) + "\n").encode())
        while True:
            line = self.f.readline()
            if not line:
                raise RuntimeError("HyperHDR closed the connection")
            r = json.loads(line)
            if r.get("tan") == self.tan or r.get("command", "").startswith(msg["command"]):
                if not r.get("success", True):
                    raise RuntimeError(f"{msg['command']}: {r.get('error')}")
                return r

    def switch(self, idx):
        return self.call({"command": "instance", "subcommand": "switchTo", "instance": idx})


def wait_api(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            Hyper().call({"command": "serverinfo"})
            return True
        except OSError:
            time.sleep(0.5)
    return False


def push_mapping(mapping):
    """Layouts need HyperHDR's admin API, so write them to its database and restart it (~3 s)."""
    systemctl = ["systemctl", "--user"]
    subprocess.run(systemctl + ["stop", "hyperhdr.service"], check=True)
    try:
        write_leds(mapping)
    finally:
        subprocess.run(systemctl + ["start", "hyperhdr.service"], check=True)
    if wait_api():
        time.sleep(2)
        apply_profile(current_profile(load_state()))


def write_leds(mapping):
    g = load_layout()
    L = layouts(mapping)
    con = sqlite3.connect(DB)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for name, meta in g["instances"].items():
        con.execute("update settings set config = ?, updated_at = ? where type = 'leds' and hyperhdr_instance = ?",
                    (json.dumps(L[name], separators=(",", ":")), now, meta["index"]))
    con.commit()
    con.close()


def apply_profile(name):
    p = PROFILES[name]
    h = Hyper()
    for inst, meta in load_layout()["instances"].items():
        room = inst != "monitor"
        h.switch(meta["index"])
        h.call({"command": "componentstate", "componentstate": {"component": "BLACKBORDER", "state": p["bbd"]}})
        if not room:
            h.call({"command": "adjustment", "adjustment": {"luminanceGain": p["mon_gain"]}})
        on = p["room"] if room else p.get("monitor", True)
        h.call({"command": "componentstate", "componentstate": {"component": "LEDDEVICE", "state": on}})


def current_profile(st):
    return (detect() if st.get("auto", True) else st.get("profile")) or "movie"


# ---------------------------------------------------------------- DB setup (HyperHDR must be stopped)
# Settings this tool owns. Everything else (colour calibration, web-UI edits) is left alone,
# except that a newly created instance starts from a copy of instance 0's settings.
GRABBER = {
    # Hardware (dmabuf/EGL) import fails on the RX 6800 ("eglCreateImageKHR ... inconsistent"),
    # so frames come through MemFD; 30 fps of a 512 px wide image is plenty for LEDs.
    "device": "Pipewire System Dialog selection", "fps": 30, "hardware": False, "videoMode": 512,
    # Hyprland screencopy already delivers SDR-mapped frames with cm=hdr: no extra tone mapping.
    "hdrToneMapping": False, "signalDetection": False,
}


def owned_settings(name, meta, leds):
    room = name != "monitor"
    return {
        "device": {"type": "wled", "host": meta["host"], "colorOrder": "rgb", "refreshTime": 1000,
                   "maxRetry": 60, "restoreOriginalState": True, "brightnessMax": True,
                   "brightnessMaxLevel": meta["brightness"]},
        "leds": leds,
        "smoothing": {"enable": True, "type": "RgbInterpolator", "updateFrequency": 50,
                      "time_ms": SMOOTHING_MS["room" if room else "monitor"], "continuousOutput": False},
        "systemControl": {"systemInstanceEnable": True, "systemInstancePriority": 245},
        "videoControl": {"videoInstanceEnable": False},
    }


def merged(current, owned):
    if isinstance(owned, list) or current is None:
        return owned
    out = dict(current)
    out.update(owned)
    return out


def db_differences(con, mapping):
    """List what differs between the database and the owned configuration."""
    g = load_layout()
    L = layouts(mapping)
    diffs = []
    rows = {(i, t): json.loads(c) for i, t, c in con.execute("select hyperhdr_instance, type, config from settings")}
    names = {i: n for i, n, e in con.execute("select instance, friendly_name, enabled from instances") if e}
    for name, meta in g["instances"].items():
        idx = meta["index"]
        if names.get(idx) != name:
            diffs.append(f"instance {idx} should be enabled as {name!r}")
        for typ, want in owned_settings(name, meta, L[name]).items():
            have = rows.get((idx, typ))
            if have is None or merged(have, want) != have:
                diffs.append(f"{name}: {typ}")
    grabber = rows.get((None, "systemGrabber"))
    if grabber is None or merged(grabber, GRABBER) != grabber:
        diffs.append("systemGrabber")
    return diffs


def setup_db():
    if subprocess.run(["pgrep", "-x", "hyperhdr"], capture_output=True).returncode == 0:
        sys.exit("stop HyperHDR first")
    if not DB.exists():
        sys.exit(f"{DB} does not exist yet; start HyperHDR once so it creates its database")
    g = load_layout()
    st = load_state()
    L = layouts(st["mapping"])
    con = sqlite3.connect(DB)
    cur = con.cursor()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = {(i, t): json.loads(c) for i, t, c in cur.execute("select hyperhdr_instance, type, config from settings")}
    base = {t: c for (i, t), c in rows.items() if i == 0}

    def put(inst, typ, cfg):
        cur.execute("delete from settings where type = ? and hyperhdr_instance is ?", (typ, inst))
        cur.execute("insert into settings (type, config, hyperhdr_instance, updated_at) values (?,?,?,?)",
                    (typ, json.dumps(cfg, separators=(",", ":")), inst, now))

    for name, meta in g["instances"].items():
        idx = meta["index"]
        if cur.execute("select 1 from instances where instance = ?", (idx,)).fetchone():
            cur.execute("update instances set friendly_name = ?, enabled = 1 where instance = ?", (name, idx))
        else:
            cur.execute("insert into instances (instance, friendly_name, enabled, last_use) values (?,?,1,?)", (idx, name, now))
        owned = owned_settings(name, meta, L[name])
        for typ in sorted(set(base) | set(owned)):
            have = rows.get((idx, typ))
            start = have if have is not None else json.loads(json.dumps(base.get(typ)))
            want = merged(start, owned[typ]) if typ in owned else start
            if want is not None and want != have:
                put(idx, typ, want)
    grabber = rows.get((None, "systemGrabber"))
    want = merged(grabber or {}, GRABBER)
    if want != grabber:
        put(None, "systemGrabber", want)
    con.commit()
    con.close()
    print(f"reconciled {len(g['instances'])} instances: " + ", ".join(f"{k}={len(v)} LEDs" for k, v in L.items()))


def verify_db():
    if not DB.exists():
        print("HyperHDR database missing")
        return 1
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    diffs = db_differences(con, load_state()["mapping"])
    con.close()
    for d in diffs:
        print("differs:", d)
    return 1 if diffs else 0


# ---------------------------------------------------------------- WLED power limits
def wled_get(host, path):
    return json.load(urllib.request.urlopen(f"http://{host}{path}", timeout=5))


def wled_limits(check_only=False):
    """Set WLED's automatic brightness limiter (global mA budget) per controller; unreachable ones are reported."""
    status = 0
    for name, meta in load_layout()["instances"].items():
        want = meta.get("maxCurrent")
        if not want:
            continue
        try:
            have = wled_get(meta["host"], "/json/cfg")["hw"]["led"].get("maxpwr")
            if have == want:
                print(f"{name}: power limit {want} mA already set")
                continue
            if check_only:
                print(f"{name}: power limit is {have} mA, want {want} mA")
                status = 1
                continue
            req = urllib.request.Request(f"http://{meta['host']}/json/cfg",
                                         data=json.dumps({"hw": {"led": {"maxpwr": want}}}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
            print(f"{name}: power limit {have} -> {want} mA")
        except (OSError, ValueError, KeyError) as e:
            print(f"{name}: {meta['host']} unreachable ({e}); power limit not checked")
            status = 1
    return status


# ---------------------------------------------------------------- test patterns (direct to WLED)
def wled(host, payload):
    req = urllib.request.Request(f"http://{host}/json/state", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=5).read()


def test(name):
    g = load_layout()
    meta = g["instances"][name]
    sides = {"monitor": ["bottom", "right", "top", "left"], "window": ["right", "top", "left"],
             "bed": ["left", "top", "right"]}[name]
    counts = [g[name][s] for s in sides]
    total = len(layouts(load_state()["mapping"])[name])
    h = Hyper()
    h.switch(meta["index"])
    h.call({"command": "componentstate", "componentstate": {"component": "LEDDEVICE", "state": False}})
    time.sleep(1.5)
    leds = [0, "00FF00"]           # LED 0 green
    pos = 0
    for c in counts[:-1]:
        pos += c
        leds += [pos, "0000FF"]    # first LED of each next side blue
    leds += [total - 1, "FF0000"]  # last LED red
    extra = g[name].get("under", 0)
    if name == "monitor" and extra:
        leds += [total - extra, "FFFF00"]  # first under-monitor LED yellow
    wled(meta["host"], {"on": True, "bri": 160, "live": False, "seg": [{"id": 0, "fx": 0, "col": [[0, 0, 0]], "i": leds}]})
    print("LED 0 = green, side starts = blue, last LED = red" + (", first under-monitor LED = yellow" if name == "monitor" else ""))
    print("Order expected: " + " -> ".join(sides) + ". Press Enter to resume ambilight.")
    try:
        input()
    finally:
        h = Hyper()
        h.switch(meta["index"])
        h.call({"command": "componentstate", "componentstate": {"component": "LEDDEVICE", "state": True}})


# ---------------------------------------------------------------- auto profile watcher
def hyprctl(*a):
    env = dict(os.environ)
    if not env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        runtime = Path(env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "hypr"
        sockets = sorted(runtime.glob("*/.socket.sock"), key=lambda p: p.stat().st_mtime, reverse=True)
        if sockets:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = sockets[0].parent.name
    try:
        out = subprocess.run(["hyprctl", "-j", *a], capture_output=True, text=True, env=env, timeout=5).stdout
        return json.loads(out)
    except (json.JSONDecodeError, subprocess.SubprocessError, OSError):
        return None


def detect():
    gm = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "omarchy/gaming-mode/session.json"
    try:
        if json.loads(gm.read_text()).get("active", True):
            return "game"
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    mons = hyprctl("monitors") or []
    main = next((m for m in mons if m.get("description", "").startswith("Microstep MAG321UP")), None)
    if not main:
        return "work"
    ws = main.get("activeWorkspace", {}).get("id")
    for c in hyprctl("clients") or []:
        if c.get("workspace", {}).get("id") != ws or not c.get("fullscreen"):
            continue
        cls = (c.get("class") or "").lower()
        if cls.startswith("steam_app_") or cls == "gamescope" or cls.endswith(".exe"):
            return "game"
        return "movie"          # any other fullscreen app on the OLED: video player, browser, Jellyfin
    return "work"


def watch():
    applied, stamp = None, 0.0
    while True:
        st = load_state()
        want = current_profile(st)
        if want != applied or time.time() - stamp > 20:
            try:
                apply_profile(want)
                if want != applied and st.get("auto", True):
                    st["profile"] = want
                    save_state(st)
                applied, stamp = want, time.time()
            except Exception as e:  # HyperHDR restarting etc.
                print("profile apply failed:", e, file=sys.stderr, flush=True)
                applied = None
        time.sleep(2)


# ---------------------------------------------------------------- CLI
def notify(text):
    subprocess.run(["notify-send", "-a", "Ambilight", "Ambilight", text], capture_output=True)


def main():
    a = sys.argv[1:]
    st = load_state()
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif a[0] == "status":
        print(json.dumps(st, indent=2))
        try:
            print(json.dumps(Hyper().call({"command": "serverinfo"})["info"]["instance"], indent=2))
        except Exception as e:
            print("HyperHDR:", e)
    elif a[0] == "mapping" and len(a) == 2:
        m = a[1] if a[1] != "toggle" else ("average" if st["mapping"] == "spatial" else "spatial")
        if m not in ("spatial", "average"):
            sys.exit("mapping: spatial | average | toggle")
        st["mapping"] = m
        save_state(st)
        push_mapping(m)
        notify(f"Mapping: {m}")
        print("mapping:", m)
    elif a[0] == "profile" and len(a) == 2:
        p = a[1]
        if p == "cycle":
            order = ["auto", "movie", "game", "work", "off"]
            cur = "auto" if st.get("auto", True) else st.get("profile")
            p = order[(order.index(cur) + 1) % len(order)] if cur in order else "auto"
        if p == "auto":
            st["auto"] = True
            st["profile"] = detect()
        elif p in PROFILES:
            st.update(profile=p, auto=False)
        else:
            sys.exit("profile: auto | movie | game | work | off | cycle")
        save_state(st)
        apply_profile(st["profile"])
        label = f"auto ({st['profile']})" if st["auto"] else p
        notify(f"Profile: {label}")
        print("profile:", label)
    elif a[0] == "watch":
        watch()
    elif a[0] == "test" and len(a) == 2:
        test(a[1])
    elif a[0] == "setup-db":
        setup_db()
    elif a[0] == "verify-db":
        sys.exit(verify_db())
    elif a[0] == "wled-limits":
        sys.exit(wled_limits(check_only="--check" in a[1:]))
    elif a[0] == "dump" and len(a) == 2:
        print(json.dumps(layouts(a[1]), indent=1))
    else:
        print(__doc__.strip())
        sys.exit(2)


if __name__ == "__main__":
    main()
