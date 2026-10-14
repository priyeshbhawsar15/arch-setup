#!/usr/bin/env python3
"""Manage T3 Planner-Executor configuration seeding, current-state validation, and safe unconfiguration."""

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

EXPECTED_ABSENT = object()


def load_json(path, fail_closed=False):
    path = Path(path)
    if not path.exists():
        return None, None
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Root JSON element in {path} must be a dict.")
        return data, raw
    except Exception as exc:
        if fail_closed:
            raise ValueError(f"Malformed JSON in {path}: {exc}. Failing closed to preserve original bytes.") from exc
        return None, raw


def atomic_write_json(path, data, expected_bytes=None, backup_label="mutation", mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Initial check before serialization
    if expected_bytes is EXPECTED_ABSENT:
        if path.exists():
            raise RuntimeError(
                f"Concurrent edit detected in {path}; file was expected to be absent but already exists."
            )
    elif expected_bytes is not None:
        if not path.exists():
            raise RuntimeError(
                f"Concurrent edit detected in {path}; expected existing file but it was deleted."
            )
        current_bytes = path.read_bytes()
        if current_bytes != expected_bytes:
            raise RuntimeError(
                f"Concurrent edit detected in {path}; expected content bytes do not match current disk bytes."
            )

    # Determine permissions to preserve
    target_mode = mode
    if path.exists():
        existing_stat = path.stat().st_mode & 0o777
        if target_mode is None:
            target_mode = existing_stat
        backup_file(path, backup_label)
    else:
        if target_mode is None:
            target_mode = 0o600

    serialized = json.dumps(data, indent=2) + "\n"
    new_bytes = serialized.encode("utf-8")

    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}-tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp_path, target_mode)

        # Recheck disk bytes immediately before os.replace to prevent race/clobber
        if expected_bytes is EXPECTED_ABSENT:
            if path.exists():
                raise RuntimeError(
                    f"Concurrent edit detected in {path} immediately before replace; file was expected to be absent."
                )
        elif expected_bytes is not None:
            if not path.exists():
                raise RuntimeError(
                    f"Concurrent edit detected in {path} immediately before replace; file was deleted."
                )
            disk_now = path.read_bytes()
            if disk_now != expected_bytes:
                raise RuntimeError(
                    f"Concurrent edit detected in {path} immediately before replace; disk bytes changed."
                )

        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def backup_file(path, label="backup"):
    path = Path(path)
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = path.with_name(f"{path.name}.bak-{label}-{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def seed_config(target_path, seed_path):
    target_path = Path(target_path)
    seed_path = Path(seed_path)
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed config not found: {seed_path}")

    seed_data, _ = load_json(seed_path, fail_closed=True)
    if not isinstance(seed_data, dict):
        raise ValueError(f"Invalid seed config in {seed_path}")

    if not target_path.exists():
        atomic_write_json(target_path, seed_data, expected_bytes=EXPECTED_ABSENT, backup_label="seed-new", mode=0o600)
        return True, "Seeded new configuration from personal defaults."

    target_data, expected_bytes = load_json(target_path, fail_closed=True)

    changed = False

    # Seed top-level keys
    for k, v in seed_data.items():
        if k not in target_data:
            target_data[k] = copy.deepcopy(v)
            changed = True
        elif isinstance(v, dict) and isinstance(target_data.get(k), dict):
            # Seed sub-keys (e.g. planner, executor)
            for sub_k, sub_v in v.items():
                if sub_k not in target_data[k]:
                    target_data[k][sub_k] = copy.deepcopy(sub_v)
                    changed = True

    # Seed providerDefaults specifically
    if "providerDefaults" in seed_data and isinstance(target_data.get("providerDefaults"), dict):
        for prov, defaults in seed_data["providerDefaults"].items():
            if prov not in target_data["providerDefaults"]:
                target_data["providerDefaults"][prov] = copy.deepcopy(defaults)
                changed = True
            elif isinstance(target_data["providerDefaults"][prov], dict) and isinstance(defaults, dict):
                for sub_k, sub_v in defaults.items():
                    if sub_k not in target_data["providerDefaults"][prov]:
                        target_data["providerDefaults"][prov][sub_k] = copy.deepcopy(sub_v)
                        changed = True

    if changed:
        atomic_write_json(target_path, target_data, expected_bytes=expected_bytes, backup_label="seed-merge", mode=0o600)
        return True, "Merged missing seed defaults into configuration (custom settings preserved)."

    return False, "Configuration already contains required defaults."


def set_enabled(target_path, enabled):
    target_path = Path(target_path)
    if not target_path.exists():
        return False, "Target configuration does not exist."
    data, expected_bytes = load_json(target_path, fail_closed=True)
    if not isinstance(data, dict):
        raise ValueError("Target configuration is not a valid JSON dict.")
    if data.get("enabled") == enabled:
        return False, f"enabled is already {enabled}"
    data["enabled"] = enabled
    atomic_write_json(target_path, data, expected_bytes=expected_bytes, backup_label="set-enabled", mode=0o600)
    return True, f"Set enabled to {enabled} (backup created)."


def is_executable(path):
    if not path:
        return False
    p = Path(path)
    return p.is_file() and os.access(p, os.X_OK)


def command_path(name, env=None):
    env_path = (env or os.environ).get("PATH", "")
    for directory in env_path.split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / name
        if is_executable(candidate):
            return str(candidate)
    return None


def is_our_wrapper(path):
    if not path:
        return False
    s = str(path)
    if s.endswith("wrapper.mjs") or s.endswith("t3-planner-executor"):
        return True
    if "planner-executor" in s and ("wrapper" in s or "bin/t3-planner-executor" in s):
        return True
    return False


def resolve_via_mise(tool, home=None, env=None):
    env = env or os.environ
    home = Path(home or Path.home())
    mise_candidates = [
        command_path("mise", env),
        str(home / ".local/bin/mise"),
        str(home / ".local/share/mise/bin/mise"),
    ]
    mise_bin = None
    for cand in mise_candidates:
        if cand and is_executable(cand):
            mise_bin = cand
            break
    if not mise_bin:
        return None

    try:
        proc = subprocess.run(
            [mise_bin, "which", tool],
            capture_output=True,
            text=True,
            timeout=3,
            env=dict(env, HOME=str(home)),
        )
        if proc.returncode == 0 and proc.stdout:
            cand = proc.stdout.strip().splitlines()[-1].strip()
            if cand and is_executable(cand):
                resolved = str(Path(cand).resolve())
                if not is_our_wrapper(resolved):
                    return resolved
    except Exception:
        pass
    return None


def parse_shell_tokens(s):
    """Tokenize a shell string into (token_str, start_idx, end_idx, unquoted_val) tuples."""
    tokens = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        val_chars = []
        quote = None
        escaped = False
        while i < n:
            c = s[i]
            if escaped:
                val_chars.append(c)
                escaped = False
                i += 1
            elif c == "\\" and quote != "'":
                escaped = True
                i += 1
            elif quote:
                if c == quote:
                    quote = None
                else:
                    val_chars.append(c)
                i += 1
            elif c in ("'", '"'):
                quote = c
                i += 1
            elif c.isspace():
                break
            else:
                val_chars.append(c)
                i += 1
        end = i
        tokens.append((s[start:end], start, end, "".join(val_chars)))
    return tokens


def has_extension_token(s, ext_target):
    tokens = parse_shell_tokens(s)
    idx = 0
    while idx < len(tokens):
        tok_str, start, end, val = tokens[idx]
        if val == "--extension" and idx + 1 < len(tokens):
            _, _, _, next_val = tokens[idx + 1]
            if next_val == ext_target:
                return True
            idx += 2
            continue
        elif val.startswith("--extension="):
            parts = val.split("=", 1)
            if parts[1] == ext_target:
                return True
        idx += 1
    return False


def remove_extension_token(s, ext_target):
    tokens = parse_shell_tokens(s)
    to_remove = []
    idx = 0
    while idx < len(tokens):
        tok_str, start, end, val = tokens[idx]
        if val == "--extension" and idx + 1 < len(tokens):
            _, _, nend, next_val = tokens[idx + 1]
            if next_val == ext_target:
                to_remove.append((start, nend))
                idx += 2
                continue
        elif val.startswith("--extension="):
            parts = val.split("=", 1)
            if parts[1] == ext_target:
                to_remove.append((start, end))
                idx += 1
                continue
        idx += 1

    if not to_remove:
        return s

    res = s
    for rstart, rend in reversed(to_remove):
        lead = rstart
        trail = rend
        while trail < len(res) and res[trail].isspace():
            trail += 1
        if trail == len(res) and lead > 0:
            while lead > 0 and res[lead - 1].isspace():
                lead -= 1
        res = res[:lead] + res[trail:]
    return res


def find_real_codex(home, env=None):
    env = env or os.environ
    home = Path(home or Path.home())
    custom = env.get("T3_CODEX_REAL_BINARY", "").strip()
    if custom and is_executable(custom) and not is_our_wrapper(custom):
        return str(Path(custom).resolve())
    mise_res = resolve_via_mise("codex", home, env)
    if mise_res:
        return mise_res
    mise_codex = home / ".local/share/mise/installs/codex"
    if mise_codex.is_dir():
        for ver_dir in sorted(mise_codex.iterdir(), reverse=True):
            cand = ver_dir / "bin/codex"
            if is_executable(cand) and not is_our_wrapper(cand):
                return str(cand.resolve())
    local_bin = home / ".local/bin/codex"
    if is_executable(local_bin) and not is_our_wrapper(local_bin):
        return str(local_bin.resolve())
    on_path = command_path("codex", env)
    if on_path and not is_our_wrapper(on_path):
        return str(Path(on_path).resolve())
    return None


def find_real_claude(home, env=None):
    env = env or os.environ
    home = Path(home or Path.home())
    custom = env.get("T3_CLAUDE_REAL_BINARY", "").strip()
    if custom and is_executable(custom) and not is_our_wrapper(custom):
        return str(Path(custom).resolve())
    # Prefer actual mise binary over noisy ~/.local/bin/claude
    mise_res = resolve_via_mise("claude", home, env)
    if mise_res:
        return mise_res
    mise_claude = home / ".local/share/mise/installs/claude"
    if mise_claude.is_dir():
        for ver_dir in sorted(mise_claude.iterdir(), reverse=True):
            for sub in ["claude", "bin/claude"]:
                cand = ver_dir / sub
                if is_executable(cand) and not is_our_wrapper(cand):
                    return str(cand.resolve())
    on_path = command_path("claude", env)
    if on_path and not is_our_wrapper(on_path):
        resolved = Path(on_path).resolve()
        if not str(resolved).endswith("/.local/bin/claude"):
            return str(resolved)
    local_bin = home / ".local/bin/claude"
    if is_executable(local_bin) and not is_our_wrapper(local_bin):
        return str(local_bin.resolve())
    return None


def find_real_pi(home, env=None):
    env = env or os.environ
    home = Path(home or Path.home())
    custom = env.get("T3_PI_REAL_BINARY", "").strip()
    if custom and is_executable(custom) and not is_our_wrapper(custom):
        return str(Path(custom).resolve())
    mise_res = resolve_via_mise("pi", home, env)
    if mise_res:
        return mise_res
    mise_installs = home / ".local/share/mise/installs/pi"
    if mise_installs.is_dir():
        for ver_dir in sorted(mise_installs.iterdir(), reverse=True):
            for sub in ["pi/pi", "bin/pi", "pi"]:
                cand = ver_dir / sub
                if is_executable(cand) and not is_our_wrapper(cand):
                    return str(cand.resolve())
    mise_node = home / ".local/share/mise/installs/node"
    if mise_node.is_dir():
        for ver_dir in sorted(mise_node.iterdir(), reverse=True):
            cand = ver_dir / "bin/pi"
            if is_executable(cand) and not is_our_wrapper(cand):
                return str(cand.resolve())
    on_path = command_path("pi", env)
    if on_path and not is_our_wrapper(on_path):
        return str(Path(on_path).resolve())
    local_bin = home / ".local/bin/pi"
    if is_executable(local_bin) and not is_our_wrapper(local_bin):
        return str(local_bin.resolve())
    return None


def find_antigravity_pair(home, runtime_dir, settings_data=None, env=None, settings_path=None):
    """Discover native Antigravity binary pair without fabricating files."""
    env = env or os.environ
    home = Path(home or Path.home())
    runtime_dir = Path(runtime_dir)
    names = {
        "executable": "agy_acp_server.par" if sys.platform != "win32" else "agy_acp_server.exe",
        "harness": "localharness_external" if sys.platform != "win32" else "localharness_external.exe",
    }

    # 1. Check existing descriptor.json if present
    descriptor_path = runtime_dir / "antigravity/descriptor.json"
    if descriptor_path.exists():
        desc, _ = load_json(descriptor_path, fail_closed=False)
        if isinstance(desc, dict):
            real_bin = desc.get("realBinary")
            real_harn = desc.get("realHarness") or (Path(real_bin).parent / names["harness"] if real_bin else None)
            if real_bin and is_executable(real_bin) and real_harn and is_executable(real_harn):
                return {
                    "binaryPath": str(real_bin),
                    "harnessPath": str(real_harn),
                    "source": desc.get("source", "descriptor"),
                }

    # 2. Check T3_ANTIGRAVITY_REAL_BINARY override
    custom_bin = env.get("T3_ANTIGRAVITY_REAL_BINARY", "").strip()
    if custom_bin:
        cand = Path(custom_bin)
        harn = cand.parent / names["harness"]
        if is_executable(cand) and is_executable(harn):
            return {
                "binaryPath": str(cand),
                "harnessPath": str(harn),
                "source": "custom_env",
            }

    # 3. Check existing binaryPath in settings if it is a real binary (not wrapper)
    if settings_data and isinstance(settings_data, dict):
        ag_cfg = settings_data.get("providerInstances", {}).get("antigravity", {}).get("config", {})
        cand_path = ag_cfg.get("binaryPath", "").strip()
        if cand_path and not is_our_wrapper(cand_path):
            cand = Path(cand_path)
            harn = cand.parent / names["harness"]
            if is_executable(cand) and is_executable(harn):
                return {
                    "binaryPath": str(cand),
                    "harnessPath": str(harn),
                    "source": "settings",
                }

    # 4. Check ~/.t3/tools/antigravity-acp/<platform>-<arch>/
    platform_arch = f"{sys.platform}-{'x64' if os.uname().machine in ('x86_64', 'amd64') else os.uname().machine}"
    candidates = [
        home / ".t3/tools/antigravity-acp" / platform_arch,
    ]
    t3_home = env.get("T3CODE_HOME")
    if t3_home:
        candidates.insert(0, Path(t3_home) / "tools/antigravity-acp" / platform_arch)
    if settings_path:
        s_str = str(settings_path)
        t3_idx = s_str.rfind(".t3")
        if t3_idx != -1:
            candidates.insert(0, Path(s_str[:t3_idx + 3]) / "tools/antigravity-acp" / platform_arch)

    for managed_dir in candidates:
        active_path = managed_dir / "active.json"
        if active_path.exists():
            active, _ = load_json(active_path, fail_closed=False)
            if isinstance(active, dict) and active.get("releaseId"):
                version_dir = managed_dir / "versions" / active["releaseId"]
                binary = version_dir / names["executable"]
                harness = version_dir / names["harness"]
                if is_executable(binary) and is_executable(harness):
                    return {
                        "binaryPath": str(binary),
                        "harnessPath": str(harness),
                        "releaseId": active["releaseId"],
                        "source": "managed",
                    }

    # 5. Check PATH
    on_path = command_path(names["executable"], env)
    if on_path and not is_our_wrapper(on_path):
        cand = Path(on_path)
        harn = cand.parent / names["harness"]
        if is_executable(harn):
            return {
                "binaryPath": str(cand),
                "harnessPath": str(harn),
                "source": "path",
            }

    return None


def detect_providers(settings_path, runtime_dir, home=None, env=None):
    home = Path(home or os.environ.get("HOME") or Path.home())
    settings_data, _ = load_json(settings_path, fail_closed=False)
    if not isinstance(settings_data, dict):
        settings_data = {}
    instances = settings_data.get("providerInstances", {})
    if not isinstance(instances, dict):
        instances = {}

    available = []
    ag_status = "not_configured"

    # Pi: include CLI available fresh Pi even if missing instance in settings
    real_pi = find_real_pi(home, env)
    pi_instance = instances.get("pi")
    if pi_instance:
        cfg_bin = pi_instance.get("config", {}).get("binaryPath", "")
        if cfg_bin and is_executable(cfg_bin) and not is_our_wrapper(cfg_bin):
            real_pi = cfg_bin
    if real_pi:
        available.append("pi")

    # Codex: detect actual backend
    real_codex = find_real_codex(home, env)
    if not real_codex and "codex" in instances:
        codex_cfg = instances["codex"].get("config", {})
        codex_bin = codex_cfg.get("binaryPath", "")
        if codex_bin and not is_our_wrapper(codex_bin) and is_executable(codex_bin):
            real_codex = codex_bin
    if real_codex:
        available.append("codex")

    # ClaudeAgent: detect actual backend
    real_claude = find_real_claude(home, env)
    if not real_claude and "claudeAgent" in instances:
        claude_cfg = instances["claudeAgent"].get("config", {})
        claude_bin = claude_cfg.get("binaryPath", "")
        if claude_bin and not is_our_wrapper(claude_bin) and is_executable(claude_bin):
            real_claude = claude_bin
    if real_claude:
        available.append("claudeAgent")

    # Antigravity: detect actual backend pair
    ag_pair = find_antigravity_pair(home, runtime_dir, settings_data, env, settings_path)
    if ag_pair:
        available.append("antigravity")
        ag_status = "available"
    else:
        if "antigravity" in instances or (runtime_dir / "antigravity/descriptor.json").exists():
            ag_status = "pending"
        else:
            ag_status = "not_configured"

    return {
        "available": available,
        "antigravityStatus": ag_status,
    }


def ensure_provider_instances(settings_path, providers, runtime_dir=None, home=None, env=None):
    settings_path = Path(settings_path)
    home = Path(home or os.environ.get("HOME") or Path.home())
    if not settings_path.exists():
        data = {"providerInstances": {}}
        expected_bytes = EXPECTED_ABSENT
    else:
        data, expected_bytes = load_json(settings_path, fail_closed=True)
        if not isinstance(data, dict):
            raise ValueError(f"Malformed settings JSON in {settings_path}")

    instances = data.setdefault("providerInstances", {})
    if not isinstance(instances, dict):
        raise ValueError(f"providerInstances in {settings_path} must be a dict.")

    changed = False
    for p in providers:
        if p not in instances:
            instances[p] = {
                "driver": p,
                "displayName": p.capitalize(),
                "enabled": True,
                "config": {},
            }
            if p == "pi":
                real = find_real_pi(home, env)
                if real:
                    instances[p]["config"]["binaryPath"] = real
            elif p == "codex":
                real = find_real_codex(home, env)
                if real:
                    instances[p]["config"]["binaryPath"] = real
            elif p == "claudeAgent":
                real = find_real_claude(home, env)
                if real:
                    instances[p]["config"]["binaryPath"] = real
            elif p == "antigravity":
                ag_pair = find_antigravity_pair(home, runtime_dir or (home / ".config/t3code/planner-executor"), data, env, settings_path)
                if ag_pair:
                    instances[p]["config"]["binaryPath"] = ag_pair["binaryPath"]
            changed = True

    if changed or expected_bytes is EXPECTED_ABSENT:
        atomic_write_json(settings_path, data, expected_bytes=expected_bytes, backup_label="ensure-providers", mode=0o600)
        return True
    return False


def git_checkout_current(directory, expected_url, expected_commit):
    dir_path = Path(directory)
    if not (dir_path / ".git").is_dir() or dir_path.is_symlink():
        return False
    try:
        url_proc = subprocess.run(
            ["git", "-C", str(dir_path), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        origin_url = url_proc.stdout.strip()
        if origin_url != expected_url:
            return False

        head_proc = subprocess.run(
            ["git", "-C", str(dir_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        head_commit = head_proc.stdout.strip()
        if head_commit != expected_commit:
            return False

        status_proc = subprocess.run(
            ["git", "-C", str(dir_path), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=True
        )
        if status_proc.stdout.strip() != "":
            return False

        return True
    except subprocess.SubprocessError:
        return False


def check_current(source_dir, source_url, source_commit, runtime_dir, settings_path, helper_path, available_providers, expected_enabled=True):
    source_dir = Path(source_dir)
    runtime_dir = Path(runtime_dir)
    settings_path = Path(settings_path)
    helper_path = Path(helper_path)

    # 1. Pinned source checkout check
    if not git_checkout_current(source_dir, source_url, source_commit):
        return False, "Source repository checkout is missing, unpinned, or dirty."

    # 2. Config presence, valid JSON, and expected enable behavior
    config_path = runtime_dir / "config.json"
    if not config_path.is_file():
        return False, "Runtime config.json is absent."
    config_data, _ = load_json(config_path, fail_closed=True)
    if not isinstance(config_data, dict):
        return False, "Runtime config.json is not a JSON dict."
    for req_key in ("enabled", "planner", "executor", "providerDefaults"):
        if req_key not in config_data:
            return False, f"Runtime config.json missing required key: {req_key}."
    if expected_enabled is not None:
        if bool(config_data.get("enabled")) != bool(expected_enabled):
            return False, f"Runtime config.json enabled is {config_data.get('enabled')}, expected {expected_enabled}."

    # Verify exact nested config symlink
    nested_config = runtime_dir / "config/config.json"
    if not nested_config.is_symlink():
        return False, "Nested config/config.json is absent or not a symlink."
    link_raw = os.readlink(str(nested_config))
    if link_raw != "../config.json" and nested_config.resolve() != config_path.resolve():
        return False, f"Nested config/config.json symlink target {link_raw} does not resolve to {config_path}."

    # Helper symlink check
    if not helper_path.is_symlink():
        return False, f"Helper symlink at {helper_path} is missing."
    bin_helper = runtime_dir / "bin/t3-planner-executor"
    if not is_executable(bin_helper):
        return False, f"Launcher {bin_helper} is missing or not executable."
    if helper_path.resolve() != bin_helper.resolve():
        return False, f"Helper symlink at {helper_path} does not point to {bin_helper}."

    # 3. Compare ALL source installer-managed runtime files byte-for-byte and expected modes
    managed_modules = ["lib", "pi", "codex", "claude", "antigravity", "bin"]
    for mod in managed_modules:
        src_mod = source_dir / mod
        if not src_mod.is_dir():
            continue
        for src_file in src_mod.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(source_dir)
            rel_str = str(rel)
            # Exclude operator config, runtime state, and generated AG artifacts
            if rel_str in ("config/config.json", "antigravity/descriptor.json", "antigravity/localharness_external", "antigravity/runtime.json"):
                continue

            dst_file = runtime_dir / rel
            if not dst_file.is_file():
                return False, f"Runtime managed file is missing: {rel}"
            if dst_file.read_bytes() != src_file.read_bytes():
                return False, f"Runtime managed file bytes do not match pinned source: {rel}"

            # Check expected execution mode
            expected_executable = (
                rel_str.startswith("bin/") or
                rel_str.endswith("wrapper.mjs") or
                rel_str.endswith("hooks.mjs")
            )
            if expected_executable and not is_executable(dst_file):
                return False, f"Runtime file {rel} is expected to be executable."

    for top_file in ["install.mjs", "README.md"]:
        src_tf = source_dir / top_file
        if src_tf.is_file():
            dst_tf = runtime_dir / top_file
            if not dst_tf.is_file():
                return False, f"Runtime {top_file} is missing."
            if dst_tf.read_bytes() != src_tf.read_bytes():
                return False, f"Runtime {top_file} bytes do not match pinned source."

    # 4. Antigravity native pair and helper symlink verification (if antigravity active)
    if "antigravity" in available_providers:
        desc_file = runtime_dir / "antigravity/descriptor.json"
        if not desc_file.is_file():
            return False, "Antigravity descriptor.json is absent."
        desc, _ = load_json(desc_file, fail_closed=True)
        if not isinstance(desc, dict):
            return False, "Antigravity descriptor.json is malformed."
        real_bin = desc.get("realBinary")
        real_harn = desc.get("realHarness")
        if not real_bin or not is_executable(real_bin):
            return False, "Antigravity descriptor.json does not reference a valid executable realBinary."
        if not real_harn or not is_executable(real_harn):
            return False, "Antigravity descriptor.json does not reference a valid executable realHarness."
        harness_link = runtime_dir / "antigravity/localharness_external"
        if not harness_link.is_symlink():
            return False, "Antigravity localharness_external is missing or not a symlink."
        if os.path.realpath(str(harness_link)) != os.path.realpath(str(real_harn)):
            return False, f"Antigravity localharness_external link ({os.path.realpath(str(harness_link))}) does not match descriptor realHarness ({os.path.realpath(str(real_harn))})."

    # 5. Managed T3 settings.json check
    if not settings_path.is_file():
        return False, "T3 settings.json is absent."
    settings_data, _ = load_json(settings_path, fail_closed=True)
    instances = settings_data.get("providerInstances")
    if not isinstance(instances, dict):
        return False, "providerInstances missing in T3 settings.json."

    for p in available_providers:
        inst = instances.get(p)
        if not inst:
            return False, f"T3 provider instance {p} is missing in settings.json."
        if inst.get("enabled") is False:
            return False, f"T3 provider instance {p} is disabled in settings.json despite declared managed activation."

        cfg = inst.get("config", {})
        if p == "pi":
            ext_file = str(runtime_dir / "pi/planner-executor.mjs")
            launch_args = str(cfg.get("launchArgs", ""))
            if not has_extension_token(launch_args, ext_file):
                return False, f"Pi launchArgs missing planner-executor extension: {ext_file}"
        elif p == "codex":
            expected_bin = str(runtime_dir / "codex/wrapper.mjs")
            if cfg.get("binaryPath") != expected_bin:
                return False, f"Codex binaryPath is {cfg.get('binaryPath')}, expected {expected_bin}."
        elif p == "claudeAgent":
            expected_bin = str(runtime_dir / "claude/wrapper.mjs")
            if cfg.get("binaryPath") != expected_bin:
                return False, f"Claude binaryPath is {cfg.get('binaryPath')}, expected {expected_bin}."
        elif p == "antigravity":
            expected_bin = str(runtime_dir / "antigravity/wrapper.mjs")
            if cfg.get("binaryPath") != expected_bin:
                return False, f"Antigravity binaryPath is {cfg.get('binaryPath')}, expected {expected_bin}."

    return True, "All managed files, configurations, and pins are current."


def unconfigure_settings(settings_path, runtime_dir, home=None, env=None, dry_run=False):
    settings_path = Path(settings_path)
    runtime_dir = Path(runtime_dir)
    home = Path(home or os.environ.get("HOME") or Path.home())
    env = env or os.environ

    if not settings_path.exists():
        return False, "settings.json not found."

    settings_data, expected_bytes = load_json(settings_path, fail_closed=True)
    if not isinstance(settings_data, dict):
        raise ValueError("Invalid settings.json.")

    instances = settings_data.get("providerInstances", {})
    if not isinstance(instances, dict):
        raise ValueError("No providerInstances in settings.json.")

    # 1. Preflight all instances (including aliases) to ensure verified backend paths exist before modifying
    planned_binary_restores = {}
    planned_launch_arg_cleans = {}

    for name, inst in instances.items():
        if not isinstance(inst, dict):
            continue
        cfg = inst.get("config", {})
        if not isinstance(cfg, dict):
            continue

        # Check launchArgs for extension ref
        launch_args = str(cfg.get("launchArgs", ""))
        ext_target = str(runtime_dir / "pi/planner-executor.mjs")
        if has_extension_token(launch_args, ext_target):
            cleaned = remove_extension_token(launch_args, ext_target)
            planned_launch_arg_cleans[name] = cleaned

        # Check binaryPath for wrapper ref
        bin_path = str(cfg.get("binaryPath", "")).strip()
        if not bin_path:
            continue

        # Check if binaryPath points to something inside runtime_dir
        points_to_runtime = False
        try:
            rel = Path(bin_path).relative_to(runtime_dir)
            points_to_runtime = True
        except ValueError:
            points_to_runtime = False

        if not points_to_runtime and not is_our_wrapper(bin_path):
            # Preserving foreign custom refs
            continue

        # Determine real backend to restore
        driver = str(inst.get("driver", "")).lower()
        inst_name = name.lower()
        bin_lower = bin_path.lower()

        is_codex = driver == "codex" or "codex" in inst_name or "codex" in bin_lower
        is_claude = driver in ("claude", "claudeagent") or "claude" in inst_name or "claude" in bin_lower
        is_ag = driver == "antigravity" or "antigravity" in inst_name or "antigravity" in bin_lower

        real_backend = None
        if is_codex:
            real_backend = find_real_codex(home, env)
            if not real_backend:
                raise RuntimeError(
                    f"Cannot unconfigure provider instance '{name}': verified backend for Codex not found. "
                    "Refusing removal to avoid breaking T3."
                )
        elif is_claude:
            real_backend = find_real_claude(home, env)
            if not real_backend:
                raise RuntimeError(
                    f"Cannot unconfigure provider instance '{name}': verified backend for Claude not found. "
                    "Refusing removal to avoid breaking T3."
                )
        elif is_ag:
            desc_file = runtime_dir / "antigravity/descriptor.json"
            if desc_file.exists():
                desc, _ = load_json(desc_file, fail_closed=False)
                if isinstance(desc, dict) and desc.get("realBinary") and is_executable(desc.get("realBinary")):
                    real_backend = str(desc["realBinary"])
            if not real_backend:
                ag_pair = find_antigravity_pair(home, runtime_dir, settings_data, env, settings_path)
                if ag_pair and is_executable(ag_pair["binaryPath"]):
                    real_backend = ag_pair["binaryPath"]
            if not real_backend:
                raise RuntimeError(
                    f"Cannot unconfigure provider instance '{name}': verified backend for Antigravity not found. "
                    "Refusing removal to avoid breaking T3."
                )
        else:
            raise RuntimeError(
                f"Cannot unconfigure provider instance '{name}': unknown wrapper target '{bin_path}'. "
                "Refusing removal to avoid breaking T3."
            )

        planned_binary_restores[name] = real_backend

    # 2. Apply verified changes
    changed = False
    for name, cleaned_args in planned_launch_arg_cleans.items():
        cfg = instances[name].setdefault("config", {})
        if cfg.get("launchArgs") != cleaned_args:
            cfg["launchArgs"] = cleaned_args
            changed = True

    for name, real_bin in planned_binary_restores.items():
        cfg = instances[name].setdefault("config", {})
        if cfg.get("binaryPath") != real_bin:
            cfg["binaryPath"] = real_bin
            changed = True

    # 3. Post-verification: ensure no provider instance still has owned runtime refs
    for name, inst in instances.items():
        if not isinstance(inst, dict):
            continue
        cfg = inst.get("config", {})
        b_path = str(cfg.get("binaryPath", "")).strip()
        if b_path:
            try:
                Path(b_path).relative_to(runtime_dir)
                raise RuntimeError(f"Post-verification failed: instance '{name}' still points to runtime dir: {b_path}")
            except ValueError:
                pass
        l_args = str(cfg.get("launchArgs", ""))
        ext_target = str(runtime_dir / "pi/planner-executor.mjs")
        if has_extension_token(l_args, ext_target):
            raise RuntimeError(f"Post-verification failed: instance '{name}' still references extension: {ext_target}")

    if dry_run:
        return True, "Preflight unconfigure passed."

    if changed:
        atomic_write_json(settings_path, settings_data, expected_bytes=expected_bytes, backup_label="unconfigure", mode=0o600)
        return True, "T3 settings restored safely."

    return False, "No managed workflow settings were found in settings.json."


def preflight_remove(settings_path, runtime_dir, home=None, env=None):
    runtime_dir = Path(runtime_dir)
    config_path = runtime_dir / "config.json"
    if config_path.exists():
        data, _ = load_json(config_path, fail_closed=True)
        if not isinstance(data, dict):
            raise ValueError(f"Malformed configuration JSON in {config_path}")

    settings_path = Path(settings_path)
    if settings_path.exists():
        unconfigure_settings(settings_path, runtime_dir, home=home, env=env, dry_run=True)

    return True, "Preflight removal validation passed."


def safe_unlink_runtime(runtime_dir, source_dir=None):
    runtime_dir = Path(runtime_dir)
    if not runtime_dir.exists():
        return True, "Runtime directory does not exist."

    # Build inventory of owned files
    owned_rel_files = {
        "bin/t3-planner-executor",
        "install.mjs",
        "README.md",
        "antigravity/descriptor.json",
        "antigravity/localharness_external",
        "config/config.json",
    }

    if source_dir:
        src = Path(source_dir)
        if src.exists():
            for mod in ["lib", "pi", "claude", "codex", "antigravity", "bin"]:
                from_dir = src / mod
                if from_dir.exists():
                    for item in from_dir.rglob("*"):
                        if item.is_file():
                            rel = item.relative_to(src)
                            owned_rel_files.add(str(rel))
            for f in ["install.mjs", "README.md"]:
                if (src / f).is_file():
                    owned_rel_files.add(f)
    else:
        owned_rel_files.update([
            "lib/mcp-client.mjs", "lib/runtime.mjs", "lib/policy.mjs", "lib/state.mjs",
            "pi/planner-executor.mjs",
            "codex/wrapper.mjs", "codex/bootstrap.mjs", "codex/hooks.mjs",
            "claude/wrapper.mjs", "claude/bridge.mjs", "claude/hooks.mjs", "claude/README.md",
            "antigravity/wrapper.mjs", "antigravity/bridge.mjs", "antigravity/README.md",
        ])

    unlinked = []
    retained = []

    adapter_dirs = ["lib", "pi", "codex", "claude", "antigravity", "bin", "config"]
    for ad in adapter_dirs:
        dir_path = runtime_dir / ad
        if not dir_path.exists():
            continue
        for item in list(dir_path.rglob("*")):
            if item.is_file() or item.is_symlink():
                rel = str(item.relative_to(runtime_dir))
                if rel in owned_rel_files:
                    try:
                        item.unlink()
                        unlinked.append(rel)
                    except OSError:
                        pass
                else:
                    retained.append(rel)

    for top_f in ["install.mjs", "README.md"]:
        tf_path = runtime_dir / top_f
        if tf_path.is_file() and top_f in owned_rel_files:
            try:
                tf_path.unlink()
                unlinked.append(top_f)
            except OSError:
                pass

    # Try removing empty directories without touching non-empty ones
    for ad in adapter_dirs:
        dir_path = runtime_dir / ad
        if dir_path.exists():
            for sub in sorted(dir_path.glob("**/*"), reverse=True):
                if sub.is_dir():
                    try:
                        sub.rmdir()
                    except OSError:
                        pass
            try:
                dir_path.rmdir()
            except OSError:
                pass

    return True, f"Unlinked {len(unlinked)} owned files. Retained {len(retained)} unknown files."


def get_executor_cli(target_path, seed_path):
    cfg = None
    if target_path:
        tp = Path(target_path)
        if tp.exists():
            cfg, _ = load_json(tp, fail_closed=True)
    if cfg is None:
        sp = Path(seed_path)
        if not sp.exists():
            raise FileNotFoundError(f"Seed config not found: {seed_path}")
        cfg, _ = load_json(sp, fail_closed=True)

    if not isinstance(cfg, dict):
        raise ValueError("Config root must be a dict.")
    executor = cfg.get("executor")
    if not isinstance(executor, dict):
        return "pi"
    return executor.get("provider", "pi")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    # seed-config
    p_seed = sub.add_parser("seed-config")
    p_seed.add_argument("--target", required=True, type=Path)
    p_seed.add_argument("--seed", required=True, type=Path)

    # set-enabled
    p_enable = sub.add_parser("set-enabled")
    p_enable.add_argument("--target", required=True, type=Path)
    p_enable.add_argument("--value", required=True, choices=("true", "false"))

    # validate-config
    p_val = sub.add_parser("validate-config")
    p_val.add_argument("--target", required=True, type=Path)

    # detect-providers
    p_detect = sub.add_parser("detect-providers")
    p_detect.add_argument("--settings", required=True, type=Path)
    p_detect.add_argument("--runtime-dir", required=True, type=Path)
    p_detect.add_argument("--home", type=Path, default=Path(os.environ.get("HOME", str(Path.home()))))

    # ensure-provider-instances
    p_ens = sub.add_parser("ensure-provider-instances")
    p_ens.add_argument("--settings", required=True, type=Path)
    p_ens.add_argument("--providers", required=True)
    p_ens.add_argument("--runtime-dir", type=Path)
    p_ens.add_argument("--home", type=Path, default=Path(os.environ.get("HOME", str(Path.home()))))

    # check-current
    p_check = sub.add_parser("check-current")
    p_check.add_argument("--source-dir", required=True, type=Path)
    p_check.add_argument("--source-url", required=True)
    p_check.add_argument("--source-commit", required=True)
    p_check.add_argument("--runtime-dir", required=True, type=Path)
    p_check.add_argument("--settings", required=True, type=Path)
    p_check.add_argument("--helper", required=True, type=Path)
    p_check.add_argument("--providers", required=True)
    p_check.add_argument("--expected-enabled", choices=("true", "false", "none"), default="true")

    # unconfigure
    p_unconf = sub.add_parser("unconfigure")
    p_unconf.add_argument("--settings", required=True, type=Path)
    p_unconf.add_argument("--runtime-dir", required=True, type=Path)
    p_unconf.add_argument("--home", type=Path, default=Path(os.environ.get("HOME", str(Path.home()))))
    p_unconf.add_argument("--dry-run", action="store_true")

    # preflight-remove
    p_pf_rem = sub.add_parser("preflight-remove")
    p_pf_rem.add_argument("--settings", required=True, type=Path)
    p_pf_rem.add_argument("--runtime-dir", required=True, type=Path)
    p_pf_rem.add_argument("--home", type=Path, default=Path(os.environ.get("HOME", str(Path.home()))))

    # safe-unlink-runtime
    p_unlink = sub.add_parser("safe-unlink-runtime")
    p_unlink.add_argument("--runtime-dir", required=True, type=Path)
    p_unlink.add_argument("--source-dir", type=Path)

    # get-executor-cli
    p_exec = sub.add_parser("get-executor-cli")
    p_exec.add_argument("--target", type=Path)
    p_exec.add_argument("--seed", required=True, type=Path)

    args = parser.parse_args()

    if args.command == "seed-config":
        changed, msg = seed_config(args.target, args.seed)
        print(msg)
        return 0

    elif args.command == "set-enabled":
        val = args.value == "true"
        changed, msg = set_enabled(args.target, val)
        print(msg)
        return 0

    elif args.command == "validate-config":
        data, _ = load_json(args.target, fail_closed=True)
        if not isinstance(data, dict) or "enabled" not in data:
            raise ValueError(f"Invalid configuration in {args.target}")
        print("Valid configuration.")
        return 0

    elif args.command == "detect-providers":
        res = detect_providers(args.settings, args.runtime_dir, args.home)
        print(json.dumps(res))
        return 0

    elif args.command == "ensure-provider-instances":
        providers = [p.strip() for p in args.providers.split(",") if p.strip()]
        ensure_provider_instances(args.settings, providers, args.runtime_dir, args.home)
        return 0

    elif args.command == "check-current":
        providers = [p.strip() for p in args.providers.split(",") if p.strip()]
        exp_en = None if args.expected_enabled == "none" else (args.expected_enabled == "true")
        is_curr, reason = check_current(
            args.source_dir, args.source_url, args.source_commit,
            args.runtime_dir, args.settings, args.helper, providers,
            expected_enabled=exp_en
        )
        if is_curr:
            print(reason)
            return 0
        else:
            print(f"NOT_CURRENT: {reason}", file=sys.stderr)
            return 1

    elif args.command == "unconfigure":
        changed, msg = unconfigure_settings(args.settings, args.runtime_dir, args.home, dry_run=args.dry_run)
        print(msg)
        return 0

    elif args.command == "preflight-remove":
        ok, msg = preflight_remove(args.settings, args.runtime_dir, args.home)
        print(msg)
        return 0

    elif args.command == "safe-unlink-runtime":
        ok, msg = safe_unlink_runtime(args.runtime_dir, args.source_dir)
        print(msg)
        return 0

    elif args.command == "get-executor-cli":
        executor_prov = get_executor_cli(args.target, args.seed)
        print(executor_prov)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
