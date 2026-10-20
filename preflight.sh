#!/bin/bash
# Validate setup prerequisites before any installer changes system state.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/config/doctor.py" --preflight "$@"
