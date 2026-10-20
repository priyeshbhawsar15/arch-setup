#!/usr/bin/env python3
"""Wrap installed Steam game launch commands with Gamescope HDR."""

from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

WRAPPER = "steam-gamescope-hdr"
NON_GAME_NAMES = (
    "proton",
    "steam linux runtime",
    "steamworks common redistributables",
    "wallpaper engine",
)
VDF_STRING = r'((?:\\.|[^"\\])*)'


def unescape_vdf(value: str) -> str:
    escapes = {'"': '"', '\\': '\\', 'n': '\n', 'r': '\r', 't': '\t'}
    return re.sub(r'\\(.)', lambda match: escapes.get(match[1], match[0]), value)


def escape_vdf(value: str) -> str:
    return (value.replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t'))


def parse_binary_vdf(data: bytes) -> dict:
    offset = 0

    def read_string() -> str:
        nonlocal offset
        end = data.find(b"\x00", offset)
        if end == -1:
            raise ValueError("Unterminated binary VDF string")
        s = data[offset:end].decode("utf-8")
        offset = end + 1
        return s

    def parse_dict() -> dict:
        nonlocal offset
        res = {}
        while offset < len(data):
            type_byte = data[offset]
            offset += 1
            if type_byte == 8:
                break
            key = read_string()
            if type_byte == 0:
                res[key] = (0, parse_dict())
            elif type_byte == 1:
                res[key] = (1, read_string())
            elif type_byte == 2:
                val = struct.unpack("<I", data[offset : offset + 4])[0]
                offset += 4
                res[key] = (2, val)
            elif type_byte == 7:
                val = struct.unpack("<Q", data[offset : offset + 8])[0]
                offset += 8
                res[key] = (7, val)
            else:
                raise ValueError(f"Unknown type_byte {type_byte} at offset {offset - 1}")
        return res

    return parse_dict()


def serialize_binary_vdf(d: dict) -> bytes:
    buf = bytearray()
    for k, (t, v) in d.items():
        buf.append(t)
        buf.extend(k.encode("utf-8") + b"\x00")
        if t == 0:
            buf.extend(serialize_binary_vdf(v))
            buf.append(8)
        elif t == 1:
            buf.extend(v.encode("utf-8") + b"\x00")
        elif t == 2:
            buf.extend(struct.pack("<I", v))
        elif t == 7:
            buf.extend(struct.pack("<Q", v))
    return bytes(buf)


def process_shortcuts_vdf(path: Path) -> tuple[bool, list[str]]:
    data = path.read_bytes()
    tree = parse_binary_vdf(data)
    # Refuse to rewrite anything we cannot round-trip without data loss.
    if serialize_binary_vdf(tree) + b"\x08" != data:
        raise ValueError(f"Binary VDF did not round-trip: {path}")
    if "shortcuts" not in tree or tree["shortcuts"][0] != 0:
        return False, []

    shortcuts = tree["shortcuts"][1]
    changed = False
    updated_shortcuts: list[str] = []

    for idx, (t, sc) in list(shortcuts.items()):
        if t != 0:
            continue
        # Only Windows game shortcuts: do not wrap arbitrary native utilities.
        exe = sc.get("Exe", (1, ""))[1].strip('"')
        if not exe.lower().endswith(".exe"):
            continue
        opts = sc.get("LaunchOptions", (1, ""))[1]
        new_opts = wrap_launch_options(opts)
        if new_opts != opts:
            app_name = sc.get("AppName", (1, f"shortcut-{idx}"))[1]
            sc["LaunchOptions"] = (1, new_opts)
            changed = True
            updated_shortcuts.append(app_name)

    if changed:
        serialized = serialize_binary_vdf(tree) + b"\x08"
        backup_config(path)
        path.write_bytes(serialized)

    return changed, updated_shortcuts


def configure_halo_proton(steam_root: Path) -> bool:
    """Enable the Windows compatibility tool for the existing Halo shortcut."""
    appids = set()
    for path in (steam_root / "userdata").glob("*/config/shortcuts.vdf"):
        tree = parse_binary_vdf(path.read_bytes())
        for _, (_, shortcut) in tree.get("shortcuts", (0, {}))[1].items():
            exe = shortcut.get("Exe", (1, ""))[1].strip('"')
            if exe.lower().endswith("/halocampaignevolved.exe"):
                appids.add(str(shortcut["appid"][1]))
    if not appids:
        return False
    path = steam_root / "config/config.vdf"
    lines = path.read_text().splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines)
                  if line.strip() == '"CompatToolMapping"'), None)
    if start is None:
        raise ValueError("Steam CompatToolMapping is absent; enable Halo compatibility in Steam first")
    depth = 0
    end = None
    for i in range(start + 1, len(lines)):
        depth += lines[i].strip() == "{"
        depth -= lines[i].strip() == "}"
        if depth == 0:
            end = i
            break
    if end is None:
        raise ValueError("Unclosed CompatToolMapping")
    block = "".join(lines[start:end])
    additions = []
    for appid in sorted(appids):
        # Never override a compatibility tool explicitly chosen by the user.
        if re.search(r'^\s*"' + appid + r'"\s*$', block, re.MULTILINE):
            continue
        additions.append(
            f'\t\t\t\t\t"{appid}"\n\t\t\t\t\t{{\n'
            '\t\t\t\t\t\t"name"\t\t"proton_experimental"\n'
            '\t\t\t\t\t\t"config"\t\t""\n'
            '\t\t\t\t\t\t"priority"\t\t"250"\n\t\t\t\t\t}\n'
        )
    if not additions:
        return False
    backup_config(path)
    lines[end:end] = additions
    path.write_text("".join(lines))
    print("Enabled Proton Experimental for Halo - Campaign Evolved.")
    return True


def get_installed_games(steam_root: Path) -> dict[str, str]:
    games: dict[str, str] = {}
    libraries = {steam_root.resolve()}
    for config in (steam_root / "steamapps/libraryfolders.vdf", steam_root / "config/libraryfolders.vdf"):
        if not config.is_file():
            continue
        # New libraryfolders entries have a path field; old entries map an index
        # directly to the library path. Ignore app IDs and unavailable libraries.
        for match in re.finditer(r'^\s*"(?:path|\d+)"\s+"' + VDF_STRING + '"',
                                 config.read_text(), re.MULTILINE | re.IGNORECASE):
            path = Path(unescape_vdf(match[1]))
            if path.is_absolute():
                libraries.add(path.resolve())
    for library in sorted(libraries):
        for manifest in sorted((library / "steamapps").glob("appmanifest_*.acf")):
            text = manifest.read_text(errors="replace")
            m_id = re.search(r'^\s*"appid"\s+"(\d+)"', text, re.MULTILINE)
            m_name = re.search(r'^\s*"name"\s+"' + VDF_STRING + '"', text, re.MULTILINE)
            if m_id and m_name:
                appid, name = m_id.group(1), unescape_vdf(m_name.group(1))
                if not any(marker in name.casefold() for marker in NON_GAME_NAMES):
                    games[appid] = name
    return games


def backup_config(path: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    shutil.copy2(path, path.with_name(f"{path.name}.bak-4k-{stamp}"))


def wrap_launch_options(val: str) -> str:
    val = val.strip()
    # Preserve existing Gamescope HDR/refresh/environment flags while replacing
    # its display dimensions, rather than nesting a second compositor.
    match = re.search(r"(?<![\w-])gamescope\s+(.*?)\s+--\s+", val)
    if match:
        flags = match.group(1)
        flags = re.sub(
            r"(?<!\S)(?:-[whWH]|--nested-width|--nested-height|--output-width|--output-height)(?:=|\s+)\d+\b",
            "", flags,
        )
        flags = re.sub(r"(?<!\S)(?:-F|--filter)(?:=|\s+)fsr\b", "", flags)
        flags = re.sub(r"(?<!\S)--fsr-sharpness(?:=|\s+)\d+\b", "", flags)
        flags = " ".join(flags.split())
        dimensions = "-w 3840 -h 2160 -W 3840 -H 2160"
        return val[:match.start(1)] + dimensions + (" " + flags if flags else "") + val[match.end(1):]
    if not val:
        return f"{WRAPPER} %command%"
    if WRAPPER in val:
        return val
    if "%command%" in val:
        return val.replace("%command%", f"{WRAPPER} %command%", 1)
    # Without %command%, Steam interprets the value as arguments to the game.
    return f"{WRAPPER} %command% {val}"


def process_vdf(path: Path, games: dict[str, str]) -> tuple[bool, set[str]]:
    lines = path.read_text().splitlines(keepends=True)
    stack: list[str] = []
    pending_key: str | None = None

    apps_closing_idx: int | None = None
    apps_indent = "\t\t\t\t"
    game_blocks: dict[str, tuple[int, int, str]] = {}
    active_game: tuple[str, int, str, int] | None = None

    key_only = re.compile(r'^(\s*)"' + VDF_STRING + r'"\s*(?:\r?\n)?$')
    key_val = re.compile(r'^(\s*)"' + VDF_STRING + r'"\s+"' + VDF_STRING + r'"\s*(\r?\n)?$')

    for idx, line in enumerate(lines):
        stripped = line.strip()
        mk = key_only.match(line)
        if mk:
            pending_key = unescape_vdf(mk.group(2))
            continue
        if stripped == "{":
            key = pending_key or ""
            stack.append(key)
            pending_key = None
            if len(stack) >= 4 and stack[-4:] == ["Software", "Valve", "Steam", "apps"]:
                apps_indent = line[: len(line) - len(line.lstrip())]
            elif len(stack) >= 5 and stack[-2] == "apps":
                active_game = (stack[-1], idx, line[: len(line) - len(line.lstrip())], len(stack))
            continue
        if stripped == "}":
            if active_game and len(stack) == active_game[3]:
                appid, o_idx, ind, _ = active_game
                game_blocks[appid] = (o_idx, idx, ind)
                active_game = None
            elif len(stack) >= 4 and stack[-4:] == ["Software", "Valve", "Steam", "apps"]:
                apps_closing_idx = idx
            if stack:
                stack.pop()
            pending_key = None
            continue
        pending_key = None

    configured: set[str] = set()
    edits: list[tuple[int, int, list[str]]] = []

    # 1. Update existing game blocks
    for appid, (o_idx, c_idx, ind) in game_blocks.items():
        if appid not in games:
            continue
        configured.add(appid)
        launch_line = None
        launch_val = ""
        launch_ind = ind + "\t"
        for i in range(o_idx + 1, c_idx):
            mv = key_val.match(lines[i])
            if mv and unescape_vdf(mv.group(2)) == "LaunchOptions":
                launch_line = i
                launch_ind = mv.group(1)
                launch_val = unescape_vdf(mv.group(3))
                break

        new_val = wrap_launch_options(launch_val)
        nl = "\r\n" if lines[o_idx].endswith("\r\n") else "\n"
        repl = f'{launch_ind}"LaunchOptions"\t\t"{escape_vdf(new_val)}"{nl}'
        if launch_line is None:
            edits.append((c_idx, c_idx, [repl]))
        elif lines[launch_line] != repl:
            edits.append((launch_line, launch_line + 1, [repl]))

    # 2. Add missing game blocks before apps closing brace
    if apps_closing_idx is not None:
        nl = "\r\n" if lines[apps_closing_idx].endswith("\r\n") else "\n"
        app_ind = apps_indent + "\t"
        inner_ind = app_ind + "\t"
        missing_lines = []
        for appid in sorted(games.keys()):
            if appid not in game_blocks:
                configured.add(appid)
                missing_lines.append(f'{app_ind}"{appid}"{nl}')
                missing_lines.append(f'{app_ind}{{{nl}')
                missing_lines.append(f'{inner_ind}"LaunchOptions"\t\t"{wrap_launch_options("")}"{nl}')
                missing_lines.append(f'{app_ind}}}{nl}')
        if missing_lines:
            edits.append((apps_closing_idx, apps_closing_idx, missing_lines))

    new_lines = list(lines)
    for start, end, repl in sorted(edits, reverse=True):
        new_lines[start:end] = repl

    changed = bool(edits)
    if changed:
        backup_config(path)
        path.write_text("".join(new_lines))
    return changed, configured


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--steam-root",
        type=Path,
        default=Path.home() / ".local/share/Steam",
    )
    args = parser.parse_args()

    if subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0:
        parser.error("Close Steam before editing its saved launch options (Steam can overwrite them).")

    games = get_installed_games(args.steam_root)
    configured_by_game: dict[str, int] = {appid: 0 for appid in games}
    changed_files = int(configure_halo_proton(args.steam_root))

    configs = sorted((args.steam_root / "userdata").glob("*/config/localconfig.vdf"))
    for config in configs:
        changed, configured = process_vdf(config, games)
        changed_files += int(changed)
        for appid in configured:
            configured_by_game[appid] += 1

    shortcut_files = sorted((args.steam_root / "userdata").glob("*/config/shortcuts.vdf"))
    updated_shortcuts: list[str] = []
    for sc_file in shortcut_files:
        changed_sc, names = process_shortcuts_vdf(sc_file)
        if changed_sc:
            changed_files += 1
            updated_shortcuts.extend(names)

    for appid, name in games.items():
        count = configured_by_game[appid]
        print(f"{appid}: {name} -> configured in {count} profile(s)")

    for name in updated_shortcuts:
        print(f"Updated non-Steam shortcut: {name} -> 4K Gamescope HDR")

    if changed_files:
        print(f"Updated {changed_files} Steam configuration file(s).")
    else:
        print("All installed games and Windows shortcuts already have managed 4K Gamescope launch options.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
