#!/bin/bash

set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

install_mise_cli gh "$SCRIPT_DIR/github/gh" \
  $'#!/bin/bash\nexport MISE_MINIMUM_RELEASE_AGE=0\nmise use -g "gh" || exit 1\nexec mise x "gh" -- "gh" "$@"' \
  $'#!/bin/bash\n# Keep GitHub CLI stdout machine-readable for T3 and other integrations.\nexec /usr/bin/gh "$@"'
