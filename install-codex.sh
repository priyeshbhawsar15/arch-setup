#!/bin/bash

set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

install_mise_cli codex "$SCRIPT_DIR/t3/codex" \
  $'#!/bin/bash\nexport MISE_MINIMUM_RELEASE_AGE=0\nmise use -g "codex" || exit 1\nexec mise x "codex" -- "codex" "$@"' \
  '#!/bin/bash
# Preserve mise setup, but reserve stdout for the Codex app-server protocol.
export MISE_MINIMUM_RELEASE_AGE=0
mise use -g "codex" >&2 || exit 1
exec mise x "codex" -- "codex" "$@"'
