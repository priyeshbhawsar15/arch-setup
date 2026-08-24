#!/bin/bash

set -euo pipefail

readonly state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/window-span-dp6-dp4"

notify() {
  notify-send -u low "󰍹    $1" 2>/dev/null || true
}

fail() {
  notify "$1"
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Window span unavailable: missing $1"
}

dispatch() {
  hyprctl dispatch "$1" >/dev/null || fail "Window span command failed"
}

restore_tiled_position() {
  local desired_x="$1"
  local desired_y="$2"
  local current_window current_x current_y direction
  local attempt

  # Re-entering the tiled layout can place a window at the end of its column.
  # Swap it toward the slot it occupied before the temporary floating layout.
  for ((attempt = 0; attempt < 16; attempt++)); do
    current_window="$(hyprctl -j activewindow)"
    current_x="$(jq -er '.at[0]' <<<"$current_window")"
    current_y="$(jq -er '.at[1]' <<<"$current_window")"

    [[ "$current_x" == "$desired_x" && "$current_y" == "$desired_y" ]] && return 0

    if (( current_y > desired_y )); then
      direction="u"
    elif (( current_y < desired_y )); then
      direction="d"
    elif (( current_x > desired_x )); then
      direction="l"
    else
      direction="r"
    fi

    hyprctl dispatch "hl.dsp.window.swap({ direction = \"$direction\" })" >/dev/null || return 0
  done
}

require_command hyprctl
require_command jq

active_window="$(hyprctl -j activewindow)"
address="$(jq -er '.address' <<<"$active_window")" || fail "No active window to span"
state_file="$state_dir/${address#0x}.json"

if [[ -f "$state_file" ]]; then
  saved_window="$(jq -e . "$state_file")" || fail "Saved window span state is invalid"

  current_pinned="$(jq -r '.pinned' <<<"$active_window")"
  current_floating="$(jq -r '.floating' <<<"$active_window")"
  current_workspace="$(jq -r '.workspace.name' <<<"$active_window")"
  saved_workspace="$(jq -er '.workspace' <<<"$saved_window")"
  saved_floating="$(jq -r '.floating' <<<"$saved_window")"
  saved_pinned="$(jq -r '.pinned' <<<"$saved_window")"
  saved_fullscreen="$(jq -er '.fullscreen' <<<"$saved_window")"
  saved_fullscreen_client="$(jq -er '.fullscreenClient' <<<"$saved_window")"

  # Geometry changes require leaving fullscreen first.
  dispatch 'hl.dsp.window.fullscreen_state({ internal = 0, client = 0, action = "set" })'

  if [[ "$current_pinned" != "$saved_pinned" ]]; then
    if [[ "$saved_pinned" == "true" ]]; then
      dispatch 'hl.dsp.window.pin({ action = "set" })'
    else
      dispatch 'hl.dsp.window.pin({ action = "unset" })'
    fi
  fi

  if [[ "$current_workspace" != "$saved_workspace" ]]; then
    dispatch "hl.dsp.window.move({ workspace = \"$saved_workspace\", follow = false })"
  fi

  if [[ "$saved_floating" == "true" ]]; then
    saved_x="$(jq -er '.at[0]' <<<"$saved_window")"
    saved_y="$(jq -er '.at[1]' <<<"$saved_window")"
    saved_width="$(jq -er '.size[0]' <<<"$saved_window")"
    saved_height="$(jq -er '.size[1]' <<<"$saved_window")"

    dispatch "hl.dsp.window.move({ x = $saved_x, y = $saved_y, relative = false })"
    dispatch "hl.dsp.window.resize({ x = $saved_width, y = $saved_height, relative = false })"
  elif [[ "$current_floating" == "true" ]]; then
    saved_x="$(jq -er '.at[0]' <<<"$saved_window")"
    saved_y="$(jq -er '.at[1]' <<<"$saved_window")"
    dispatch 'hl.dsp.window.float({ action = "toggle" })'
    restore_tiled_position "$saved_x" "$saved_y"
  fi

  if [[ "$saved_fullscreen" != "0" || "$saved_fullscreen_client" != "0" ]]; then
    dispatch "hl.dsp.window.fullscreen_state({ internal = $saved_fullscreen, client = $saved_fullscreen_client, action = \"set\" })"
  fi

  dispatch "hl.dsp.focus({ window = \"address:$address\" })"
  rm -f -- "$state_file"
  exit 0
fi

canvas="$(hyprctl -j monitors | jq -cer '
  def logical_dimensions:
    if (.transform == 1 or .transform == 3 or .transform == 5 or .transform == 7) then
      [(.height / .scale | round), (.width / .scale | round)]
    else
      [(.width / .scale | round), (.height / .scale | round)]
    end;

  map(select(.name == "DP-6" or .name == "DP-4") | . + { logical: logical_dimensions })
  | if length != 2 then
      error("DP-6 and DP-4 must both be connected")
    else
      (.[] | select(.name == "DP-6")) as $left
      | (.[] | select(.name == "DP-4")) as $right
      | if ($left.disabled or $right.disabled
            or $left.y != $right.y
            or $left.logical[1] != $right.logical[1]
            or $left.x + $left.logical[0] != $right.x) then
          error("DP-6 and DP-4 must be adjacent with matching heights")
        else
          { x: $left.x, y: $left.y, width: ($left.logical[0] + $right.logical[0]), height: $left.logical[1] }
        end
    end
')" || fail "DP-6 and DP-4 are not available as a shared canvas"

mkdir -p -- "$state_dir"
temporary_state="$(mktemp "$state_dir/.${address#0x}.XXXXXX")"
jq -n \
  --arg address "$address" \
  --arg workspace "$(jq -er '.workspace.name' <<<"$active_window")" \
  --argjson floating "$(jq -r '.floating' <<<"$active_window")" \
  --argjson pinned "$(jq -r '.pinned' <<<"$active_window")" \
  --argjson fullscreen "$(jq -e '.fullscreen' <<<"$active_window")" \
  --argjson fullscreenClient "$(jq -e '.fullscreenClient' <<<"$active_window")" \
  --argjson at "$(jq -e '.at' <<<"$active_window")" \
  --argjson size "$(jq -e '.size' <<<"$active_window")" \
  '{ address: $address, workspace: $workspace, floating: $floating, pinned: $pinned, fullscreen: $fullscreen, fullscreenClient: $fullscreenClient, at: $at, size: $size }' \
  >"$temporary_state"
mv -- "$temporary_state" "$state_file"

canvas_x="$(jq -er '.x' <<<"$canvas")"
canvas_y="$(jq -er '.y' <<<"$canvas")"
canvas_width="$(jq -er '.width' <<<"$canvas")"
canvas_height="$(jq -er '.height' <<<"$canvas")"

dispatch 'hl.dsp.window.fullscreen_state({ internal = 0, client = 0, action = "set" })'
dispatch 'hl.dsp.window.float({ action = "set" })'
dispatch "hl.dsp.window.move({ x = $canvas_x, y = $canvas_y, relative = false })"
dispatch "hl.dsp.window.resize({ x = $canvas_width, y = $canvas_height, relative = false })"
if [[ "$(jq -r '.pinned' <<<"$active_window")" == "false" ]]; then
  dispatch 'hl.dsp.window.pin({ action = "set" })'
fi
dispatch "hl.dsp.focus({ window = \"address:$address\" })"
