#!/bin/bash
# Read-only diagnostics; --export-profile exports choices for another machine.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/config/doctor.py" "$@"
