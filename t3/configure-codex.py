#!/usr/bin/env python3
"""Use the protocol-safe mise wrapper for T3's existing-install Codex provider."""

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def configure(data, home):
    result = copy.deepcopy(data)
    default_paths = {"", "codex", "/usr/bin/codex", str(home / ".local/bin/codex")}
    instances = result.setdefault("providerInstances", {})
    if not any(instance.get("driver") == "codex" for instance in instances.values()):
        instances["codex"] = {
            "driver": "codex", "enabled": True,
            "config": {"binaryPath": "codex", "setupMode": "existing"},
        }
    for instance in instances.values():
        if instance.get("driver") != "codex":
            continue
        config = instance.setdefault("config", {})
        if config.get("setupMode") == "managed":
            continue
        if config.get("binaryPath", "").strip() in default_paths:
            config["binaryPath"] = "codex"
    # Older T3 releases store provider config here rather than in instances.
    legacy = result.get("providers", {}).get("codex")
    if legacy is not None and legacy.get("setupMode") != "managed":
        if legacy.get("binaryPath", "").strip() in default_paths:
            legacy["binaryPath"] = "codex"
    return result


def update(path, home):
    original = path.read_bytes() if path.exists() else None
    data = json.loads(original) if original is not None else {}
    desired = configure(data, home)
    if desired == data:
        print("T3 Code already installed; Codex configuration is current (custom/managed paths preserved).")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if original is not None:
        backup = path.with_name(f"{path.name}.bak-codex-path-{stamp}")
        shutil.copy2(path, backup)
        print(f"Backed up T3 settings to {backup}")
    fd, temp = tempfile.mkstemp(prefix=".settings-codex-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(desired, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Avoid overwriting an intervening edit from T3's settings UI.
        current = path.read_bytes() if path.exists() else None
        if current != original:
            raise RuntimeError("T3 settings changed during update; rerun the installer.")
        if path.exists():
            shutil.copymode(path, temp)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print("T3 Codex configured to use the mise-backed codex command; refresh providers or reopen T3 if needed.")
    return True


if __name__ == "__main__":
    update(Path(sys.argv[1]), Path.home())
