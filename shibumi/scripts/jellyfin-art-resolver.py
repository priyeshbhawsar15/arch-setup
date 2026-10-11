#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

JELLYFIN_CONFIG = os.path.expanduser("~/.config/omarchy-desktop-widgets/jellyfin.json")
CACHE_ART_PATH = "/tmp/jellyfin-now-playing-art.jpg"

def fetch_art():
    if not os.path.exists(JELLYFIN_CONFIG):
        return ""
    try:
        with open(JELLYFIN_CONFIG, "r") as f:
            cfg = json.load(f)
        endpoint = cfg.get("endpoint")
        api_key = cfg.get("apiKey")
        if not endpoint or not api_key:
            return ""

        headers = {
            "X-Emby-Token": api_key,
            "Authorization": f'MediaBrowser Client="omarchy", Device="desktop", DeviceId="1", Version="1.0.0", Token="{api_key}"'
        }
        url = f"{endpoint}/Sessions"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            sessions = json.loads(resp.read().decode())
            for s in sessions:
                now = s.get("NowPlayingItem")
                if now:
                    item_id = now.get("Id")
                    series_id = now.get("SeriesId")
                    img_id = item_id or series_id
                    if img_id:
                        img_url = f"{endpoint}/Items/{img_id}/Images/Primary?fillWidth=300&fillHeight=300&quality=90"
                        img_req = urllib.request.Request(img_url, headers=headers)
                        with urllib.request.urlopen(img_req, timeout=3) as img_resp:
                            data = img_resp.read()
                            with open(CACHE_ART_PATH, "wb") as out_file:
                                out_file.write(data)
                            mtime = int(os.path.getmtime(CACHE_ART_PATH))
                            return f"file://{CACHE_ART_PATH}?v={mtime}"
    except Exception as e:
        pass
    return ""

if __name__ == "__main__":
    art_url = fetch_art()
    if art_url:
        print(art_url)
