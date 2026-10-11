#!/usr/bin/env bash
# Recover a missing shell after compositor/config recovery, without restarting
# a healthy shell or racing other recovery hooks.
set -euo pipefail
exec 9>"${XDG_RUNTIME_DIR:?}/omarchy-shell-recover.lock"
flock -n 9 || exit 0
if OMARCHY_SHELL_IPC_TIMEOUT=2s omarchy-shell shell ping >/dev/null 2>&1; then
  exit 0
fi
# The stock restart command preserves an active lock and launches from Hyprland
# with the canonical compositor environment.
omarchy restart shell
