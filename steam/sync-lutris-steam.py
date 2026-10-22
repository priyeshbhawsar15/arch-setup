#!/usr/bin/env python3
"""Sync installed Steam games and non-Steam shortcuts into Lutris."""

import argparse
import copy
from datetime import datetime, timezone
import glob
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile

import yaml
from gaming_profile import load_selection, owned_shortcuts

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from lutris import settings
    from lutris.config import write_game_config, LutrisConfig
    from lutris.database import sql
    from lutris.database.schema import syncdb
    from lutris.database.games import add_game, get_game_by_field, get_games
    from lutris.services.steam import SteamService, SteamGame
    from lutris.util.steam.appmanifest import AppManifest, get_appmanifests
    from lutris.util.steam.config import get_steamapps_dirs, get_steam_dir
    from lutris.util.strings import slugify
    from lutris.util.system import create_folder
except ImportError as ex:
    print(f"Lutris libraries not available: {ex}", file=sys.stderr)
    sys.exit(1)


def initialize_lutris():
    """Prepare only the directories/schema needed by this non-GUI import."""
    for directory in (settings.DATA_DIR, settings.CONFIG_DIR, settings.GAME_CONFIG_DIR,
                      os.path.dirname(settings.DB_PATH)):
        create_folder(directory)
    syncdb()


def save_yaml_update(path, desired, original):
    """Back up and atomically replace a changed YAML file without racing its UI."""
    current = path.read_bytes() if path.exists() else None
    if current != original:
        raise RuntimeError(f"Lutris configuration changed during synchronization: {path}")
    if original is not None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = path.with_name(f"{path.name}.bak-steam-{stamp}")
        shutil.copy2(path, backup)
        print(f"Backed up Lutris configuration to {backup}")
    fd, temporary = tempfile.mkstemp(prefix=".lutris-steam-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            yaml.safe_dump(desired, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        current = path.read_bytes() if path.exists() else None
        if current != original:
            raise RuntimeError(f"Lutris configuration changed during synchronization: {path}")
        if original is not None:
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def update_game_config(filename, managed):
    path = Path(filename).resolve()
    original = path.read_bytes() if path.exists() else None
    data = yaml.safe_load(original) if original is not None else {}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"Lutris configuration is not a mapping: {path}")
    desired = copy.deepcopy(data)
    game = desired.setdefault("game", {})
    system = desired.setdefault("system", {})
    if not isinstance(game, dict) or not isinstance(system, dict):
        raise ValueError(f"Invalid game/system mapping in Lutris configuration: {path}")
    environment = system.setdefault("env", {})
    if not isinstance(environment, dict):
        raise ValueError(f"Invalid environment mapping in Lutris configuration: {path}")
    game.update(managed["game"])
    environment.update(managed["system"]["env"])
    if desired == data:
        return False
    save_yaml_update(path, desired, original)
    return True


def parse_binary_vdf(data):
    offset = 0

    def read_string():
        nonlocal offset
        end = data.find(b"\x00", offset)
        if end == -1:
            raise ValueError('Unterminated binary VDF string')
        s = data[offset:end].decode("utf-8")
        offset = end + 1
        return s

    def parse_dict():
        nonlocal offset
        res = {}
        while offset < len(data):
            type_byte = data[offset]
            offset += 1
            if type_byte == 8:
                break
            key = read_string()
            if type_byte == 0:
                res[key] = parse_dict()
            elif type_byte == 1:
                res[key] = read_string()
            elif type_byte == 2:
                val = struct.unpack("<I", data[offset:offset + 4])[0]
                offset += 4
                res[key] = val
            elif type_byte == 7:
                val = struct.unpack("<Q", data[offset:offset + 8])[0]
                offset += 8
                res[key] = val
            else:
                raise ValueError('Unsupported binary VDF type')
        return res

    return parse_dict()


def parse_launch_options(launch_options):
    if not launch_options or not launch_options.strip():
        return {}, ""
    if "%command%" in launch_options:
        before_cmd, _, after_cmd = launch_options.partition("%command%")
        env = {}
        tokens = shlex.split(before_cmd)
        for token in tokens:
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', token):
                k, v = token.split("=", 1)
                env[k] = v
        return env, after_cmd.strip()
    return {}, launch_options.strip()


def sync_all():
    if subprocess.run(["pgrep", "-x", "lutris"], capture_output=True).returncode == 0:
        raise RuntimeError("Close Lutris before synchronizing its database and game configurations.")
    initialize_lutris()
    changes = 0
    managed_ids = owned_shortcuts(load_selection())
    # 1. Sync Native Steam Games
    svc = SteamService()
    runtime_appids = {"228980", "1070560", "1493710", "1628350", "3658110", "4183110"}
    native_count = 0

    for d in get_steamapps_dirs():
        for f in get_appmanifests(d):
            m = AppManifest(os.path.join(d, f))
            if m.steamid in runtime_appids or not m.is_installed():
                continue
            game_dict = {
                "appid": str(m.steamid),
                "name": m.name,
                "playtime_forever": 0,
            }
            g = SteamGame.new_from_steam_game(game_dict)
            g.save()
            native_count += 1

            lutris_game_id = f"steam-{m.steamid}"
            existing = get_game_by_field(lutris_game_id, "installer_slug")
            if not existing:
                svc.install_from_steam(m)
                if not get_game_by_field(lutris_game_id, "installer_slug"):
                    raise RuntimeError(f"Lutris failed to import Steam game {m.steamid}")
                changes += 1

    print(f"Synced {native_count} native Steam games to Lutris.")

    # 2. Sync Non-Steam Games
    steam_dir = get_steam_dir() or os.path.expanduser("~/.local/share/Steam")
    userdata_dir = os.path.join(steam_dir, "userdata")
    non_steam_count = 0

    if os.path.isdir(userdata_dir):
        shortcut_files = glob.glob(os.path.join(userdata_dir, "*/config/shortcuts.vdf"))
        for shortcuts_path in shortcut_files:
            try:
                with open(shortcuts_path, "rb") as f:
                    vdf_data = parse_binary_vdf(f.read())
            except Exception as ex:
                raise ValueError(f'Failed to parse Steam shortcuts: {shortcuts_path}') from ex

            shortcuts = vdf_data.get("shortcuts", {})
            for idx, sc in shortcuts.items():
                name = sc.get("AppName", "Unknown")
                exe = sc.get("Exe", "").strip('"')
                start_dir = sc.get("StartDir", "").strip('"')
                launch_options = sc.get("LaunchOptions", "")
                appid_32 = sc.get("appid", 0)
                if not appid_32:
                    continue
                # Personal direct-Proton profiles own these entries. Importing
                # their Steam settings here would discard OptiScaler overrides.
                if appid_32 in managed_ids:
                    continue

                shortcut_id_64 = (appid_32 << 32) | 0x02000000
                env, args = parse_launch_options(launch_options)
                slug = slugify(name)
                installer_slug = f"steam-shortcut-{appid_32}"

                existing = get_game_by_field(installer_slug, "installer_slug")

                game_config = {
                    "game": {
                        "appid": str(shortcut_id_64),
                        "args": args,
                        "exe": exe,
                        "steamless_binary": exe,
                    },
                    "system": {
                        "env": env,
                    },
                }

                if existing:
                    config_filename = os.path.join(settings.CONFIG_DIR, "games/%s.yml" % existing["configpath"])
                    changes += int(update_game_config(config_filename, game_config))
                else:
                    configpath = write_game_config(installer_slug, game_config)
                    add_game(
                        name=name,
                        runner="steam",
                        slug=slug,
                        installed=1,
                        installer_slug=installer_slug,
                        configpath=configpath,
                        platform="Windows" if exe.lower().endswith(".exe") else "Linux",
                        service="steam",
                        service_id=str(shortcut_id_64),
                        directory=start_dir if start_dir else os.path.dirname(exe),
                    )
                    print(f"Added non-Steam game: {name} (appid: {shortcut_id_64})")
                    changes += 1
                non_steam_count += 1

    print(f"Synced {non_steam_count} non-Steam shortcuts to Lutris.")

    # 3. Fix Epic Games Launcher if installed
    lutris_games_dir = settings.GAME_CONFIG_DIR
    if os.path.isdir(lutris_games_dir):
        for yml_file in glob.glob(os.path.join(lutris_games_dir, "epic-games-store*.yml")):
            try:
                path = Path(yml_file).resolve()
                original = path.read_bytes()
                data = yaml.safe_load(original) or {}

                modified = False
                if "game" in data and "args" in data["game"]:
                    args = data["game"]["args"]
                    if "-opengl" in args:
                        data["game"]["args"] = args.replace("-opengl", "").strip()
                        if "-no-cef-sandbox" not in data["game"]["args"]:
                            data["game"]["args"] += " -no-cef-sandbox"
                        modified = True

                if "system" in data and "env" in data["system"]:
                    if "MESA_GL_VERSION_OVERRIDE" in data["system"]["env"]:
                        del data["system"]["env"]["MESA_GL_VERSION_OVERRIDE"]
                        modified = True

                if modified:
                    save_yaml_update(path, data, original)
                    changes += 1
                    print(f"Fixed Epic Games Launcher configuration in {yml_file}")
            except Exception as ex:
                print(f"Error checking {yml_file}: {ex}", file=sys.stderr)
                raise
    if not changes:
        print("Lutris library is already installed and current.")
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize-only', action='store_true')
    args = parser.parse_args()
    if args.initialize_only:
        if subprocess.run(['pgrep', '-x', 'lutris'], capture_output=True).returncode == 0:
            raise RuntimeError('Close Lutris before initializing its database.')
        initialize_lutris()
    else:
        sync_all()
