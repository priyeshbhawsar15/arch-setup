#!/usr/bin/env bash

# Install and configure the T3 Planner->Executor->Planner Review workflow adapter
# for T3 Code, orchestrating Pi, Codex, Claude, and native Antigravity.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

DEFAULT_REPO_URL="git@github.com:priyeshbhawsar15/t3-planner-executor.git"
DEFAULT_REPO_PIN="e0a0481c8c590ccc825a1e7509e6d663846927dd"

REPO_URL="${T3_PLANNER_EXECUTOR_REPO_URL:-$DEFAULT_REPO_URL}"
REPO_PIN="${T3_PLANNER_EXECUTOR_REPO_PIN:-$DEFAULT_REPO_PIN}"
SOURCE_DIR="${T3_PLANNER_EXECUTOR_SOURCE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/t3-planner-executor/source}"
RUNTIME_DIR="${T3_PLANNER_EXECUTOR_RUNTIME_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/t3code/planner-executor}"
SETTINGS_PATH="${T3_PLANNER_EXECUTOR_SETTINGS:-${T3CODE_HOME:-$HOME/.t3}/userdata/settings.json}"
HELPER_LINK="${T3_PLANNER_EXECUTOR_HELPER:-$HOME/.local/bin/t3-planner-executor}"
SEED_CONFIG="$SCRIPT_DIR/t3/planner-executor.json"
CONFIG_HELPER="$SCRIPT_DIR/t3/configure-planner-executor.py"

mode=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable) mode="enable"; shift ;;
    --disable) mode="disable"; shift ;;
    --remove) mode="remove"; shift ;;
    --source-url) REPO_URL="$2"; shift 2 ;;
    --pin) REPO_PIN="$2"; shift 2 ;;
    --runtime-dir) RUNTIME_DIR="$2"; shift 2 ;;
    --settings) SETTINGS_PATH="$2"; shift 2 ;;
    --source-dir) SOURCE_DIR="$2"; shift 2 ;;
    --helper) HELPER_LINK="$2"; shift 2 ;;
    *)
      log "Usage: $0 [--enable|--disable|--remove] [--source-url URL] [--pin COMMIT]"
      exit 1
      ;;
  esac
done

if [[ "$mode" == "disable" ]]; then
  # Preflight check and update config.json if it exists
  if [[ -f "$RUNTIME_DIR/config.json" ]]; then
    python3 "$CONFIG_HELPER" set-enabled --target "$RUNTIME_DIR/config.json" --value false
  fi
  remember_feature_choice "$0" false
  log "T3 Planner-Executor is disabled."
  exit 0
fi

if [[ "$mode" == "remove" ]]; then
  # 1. Complete preflight BEFORE any mutation:
  # Validates both config.json and settings.json/backend resolution without modifying disk
  python3 "$CONFIG_HELPER" preflight-remove \
    --settings "$SETTINGS_PATH" \
    --runtime-dir "$RUNTIME_DIR"

  # 2. Archive original configuration, settings, and runtime state before any changes
  backup_dir="$(backup_feature_paths t3-planner-executor-remove \
    "$RUNTIME_DIR" "$SETTINGS_PATH")"

  # 3. Disable before deleting to prevent active hook misbehavior
  if [[ -f "$RUNTIME_DIR/config.json" ]]; then
    python3 "$CONFIG_HELPER" set-enabled --target "$RUNTIME_DIR/config.json" --value false
  fi

  # 4. Unconfigure settings
  if [[ -f "$SETTINGS_PATH" ]]; then
    python3 "$CONFIG_HELPER" unconfigure --settings "$SETTINGS_PATH" --runtime-dir "$RUNTIME_DIR"
  fi

  # 5. Safe unlink of only owned adapter runtime files (preserves unknown/custom manual files and personal config/state)
  python3 "$CONFIG_HELPER" safe-unlink-runtime \
    --runtime-dir "$RUNTIME_DIR" \
    ${SOURCE_DIR:+"--source-dir" "$SOURCE_DIR"}

  # 6. Remove helper symlink if it points to runtime bin
  if [[ -L "$HELPER_LINK" && "$(readlink "$HELPER_LINK" 2>/dev/null || true)" == "$RUNTIME_DIR/bin/t3-planner-executor" ]]; then
    rm -f -- "$HELPER_LINK"
  fi

  # 7. Mark feature disabled in profile
  remember_feature_choice "$0" false

  log "Removed T3 Planner-Executor. Configuration and state were backed up to: $backup_dir"
  exit 0
fi

# Pin publication check: early validation before touching dependencies, configs, or feature choices
if [[ "$REPO_PIN" == "PENDING_PUBLICATION" ]]; then
  log "T3 Planner-Executor repository pin is PENDING_PUBLICATION; awaiting final reviewed commit publication."
  exit 1
fi

if [[ ! "$REPO_PIN" =~ ^[0-9a-f]{40}$ ]]; then
  log "Invalid repository commit pin: $REPO_PIN"
  exit 1
fi

if [[ "$mode" != "enable" ]]; then
  # Default invocation: respect remembered feature choice
  if ! feature_is_enabled "$(basename -- "$0")"; then
    log "T3 Planner-Executor is disabled in feature profile."
    exit 0
  fi
fi

# Preflight config.json if already present to fail closed on malformed files
if [[ -f "$RUNTIME_DIR/config.json" ]]; then
  python3 "$CONFIG_HELPER" validate-config --target "$RUNTIME_DIR/config.json"
fi

# Ensure basic packages via Omarchy
if ! is_command_available git; then
  require_omarchy
  omarchy pkg add git
fi

if ! is_command_available node; then
  require_omarchy
  omarchy pkg add nodejs
fi

if ! is_command_available python3; then
  require_omarchy
  omarchy pkg add python
fi

if ! is_command_available flock; then
  require_omarchy
  omarchy pkg add util-linux
fi

# Check configured executor CLI
executor_cli="$(python3 "$CONFIG_HELPER" get-executor-cli --target "$RUNTIME_DIR/config.json" --seed "$SEED_CONFIG")"
if [[ "$executor_cli" == "pi" ]]; then
  pi_available=false
  if is_command_available pi; then
    pi_available=true
  elif is_command_available mise; then
    # Read-only resolution via 'mise which pi' without mutating global mise state
    mise_pi="$(mise which pi 2>/dev/null || true)"
    if [[ -n "$mise_pi" && -x "$mise_pi" ]]; then
      pi_available=true
    fi
  fi

  if [[ "$pi_available" != true ]]; then
    log "Configured executor 'pi' is not available on PATH or through read-only mise resolution."
    log "Install pi using 'mise use -g pi' or adjust executor in $SEED_CONFIG."
    exit 1
  fi
fi

# Detect genuinely available providers
detect_json="$(python3 "$CONFIG_HELPER" detect-providers --settings "$SETTINGS_PATH" --runtime-dir "$RUNTIME_DIR")"
available_csv="$(python3 -c "import json, sys; d = json.loads(sys.argv[1]); print(','.join(d.get('available', [])))" "$detect_json")"
ag_status="$(python3 -c "import json, sys; d = json.loads(sys.argv[1]); print(d.get('antigravityStatus', 'not_configured'))" "$detect_json")"

if [[ "$ag_status" == "pending" ]]; then
  log "Notice: Native Antigravity binary pair not found (status: pending)."
  log "Antigravity provider is pending native setup in T3."
  log "Once Antigravity is configured in T3 (or active.json exists in ~/.t3/tools/antigravity-acp/), rerun $0 to activate the Antigravity adapter."
fi

# Determine effective expected enabled status (existing config with enabled:false is preserved on normal no-arg run)
expected_target_enabled="true"
if [[ "$mode" == "enable" ]]; then
  expected_target_enabled="true"
elif [[ -f "$RUNTIME_DIR/config.json" ]]; then
  cfg_enabled="$(python3 -c "import json, sys; d = json.load(open(sys.argv[1])); print(str(d.get('enabled', True)).lower())" "$RUNTIME_DIR/config.json" 2>/dev/null || echo "true")"
  if [[ "$cfg_enabled" == "false" ]]; then
    expected_target_enabled="false"
  fi
fi

# Check whether existing installation is current (exact bytes, pins, modes, settings, links)
if python3 "$CONFIG_HELPER" check-current \
  --source-dir "$SOURCE_DIR" \
  --source-url "$REPO_URL" \
  --source-commit "$REPO_PIN" \
  --runtime-dir "$RUNTIME_DIR" \
  --settings "$SETTINGS_PATH" \
  --helper "$HELPER_LINK" \
  --providers "$available_csv" \
  --expected-enabled "$expected_target_enabled"; then
  if [[ "$mode" == "enable" ]]; then
    remember_feature_choice "$0" true
  fi
  log "T3 Planner-Executor is already installed."
  exit 0
fi

# Install / update pinned git source checkout
install_pinned_git_checkout "$SOURCE_DIR" "$REPO_URL" "$REPO_PIN" "t3-planner-executor"

# Ensure provider instances exist in settings before runtime installer (always bootstraps minimal settings if absent)
python3 "$CONFIG_HELPER" ensure-provider-instances \
  --settings "$SETTINGS_PATH" \
  --providers "$available_csv" \
  --runtime-dir "$RUNTIME_DIR"

# Seed personal configuration before running runtime installer
python3 "$CONFIG_HELPER" seed-config --target "$RUNTIME_DIR/config.json" --seed "$SEED_CONFIG"

# Run runtime package installer
node "$SOURCE_DIR/install.mjs" \
  --root "$SOURCE_DIR" \
  --install-dir "$RUNTIME_DIR" \
  --settings "$SETTINGS_PATH" \
  --providers "$available_csv"

# Seed personal configuration again to ensure missing seed defaults are present
python3 "$CONFIG_HELPER" seed-config --target "$RUNTIME_DIR/config.json" --seed "$SEED_CONFIG"

# If explicit enable mode was requested, ensure config is marked enabled and remember feature choice
if [[ "$mode" == "enable" ]]; then
  python3 "$CONFIG_HELPER" set-enabled --target "$RUNTIME_DIR/config.json" --value true
  remember_feature_choice "$0" true
elif [[ "$expected_target_enabled" == "false" ]]; then
  # Existing operator config with enabled:false remains disabled on normal no-arg run
  python3 "$CONFIG_HELPER" set-enabled --target "$RUNTIME_DIR/config.json" --value false
fi

# Reconcile helper symlink
reconcile_plugin_helper t3-planner-executor "$RUNTIME_DIR/bin/t3-planner-executor"

log "Installed and configured T3 Planner-Executor at $REPO_PIN."
