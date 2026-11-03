#!/usr/bin/env python3
# Managed by arch-setups/install-sddm-autologin.sh
"""Request the native Omarchy lock as soon as its IPC is ready, verify secure."""
import json
import os
import subprocess
import sys
import time


def lock_session(run=subprocess.run, sleep=time.sleep, monotonic=time.monotonic):
    os.environ.setdefault('OMARCHY_PATH', '/usr/share/omarchy')
    deadline = monotonic() + 30
    requested = False
    while monotonic() < deadline:
        try:
            if not requested:
                result = run(['omarchy-shell', 'lock', 'lock'], capture_output=True, text=True, timeout=3)
                requested = result.returncode == 0 and result.stdout.strip() == 'ok'
            result = run(['omarchy-shell', 'lock', 'status'], capture_output=True, text=True, timeout=3)
            status = json.loads(result.stdout) if result.returncode == 0 else {}
            if isinstance(status, dict) and status.get('secure') is True:
                print('Startup session lock is secure.', flush=True)
                return 0
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass  # Shell IPC/PAM can become ready slightly after the compositor.
        sleep(0.2)
    print('Startup lock did not become secure; requesting UWSM session shutdown.', file=sys.stderr, flush=True)
    try:
        run(['uwsm', 'stop'], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f'Unable to request session shutdown: {error}', file=sys.stderr, flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(lock_session())
