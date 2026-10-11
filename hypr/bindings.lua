-- Personal Quattro binding overrides.

-- Per-monitor Workspaces is enabled only while its managed Lua toggle exists.
-- The plugin supplies the complete named-workspace keymap; keeping the switch
-- here makes disabling the feature also restore Omarchy's normal keybindings.
local per_monitor_workspace_toggle = os.getenv("HOME")
  .. "/.local/state/omarchy/toggles/hypr/per-monitor-workspaces.lua"
local per_monitor_workspace_state = io.open(per_monitor_workspace_toggle, "r")
if per_monitor_workspace_state then
  per_monitor_workspace_state:close()
  pcall(dofile, os.getenv("HOME")
    .. "/.config/omarchy/plugins/mmsbrggr.per-monitor-workspaces/hypr/init.lua")
end

o.bind("ALT + H", "Focus on left window", hl.dsp.focus({ direction = "l" }))
o.bind("ALT + J", "Focus on below window", hl.dsp.focus({ direction = "d" }))
o.bind("ALT + K", "Focus on above window", hl.dsp.focus({ direction = "u" }))
o.bind("ALT + L", "Focus on right window", hl.dsp.focus({ direction = "r" }))

o.bind("CTRL + ALT + J", "Previous window in group", hl.dsp.group.prev())
o.bind("CTRL + ALT + L", "Next window in group", hl.dsp.group.next())

-- Quattro uses these keys for Music and Omawrite; retain the previous custom actions.
hl.unbind("SUPER + SHIFT + M")
o.bind("SUPER + SHIFT + M", "Toggle single/multi monitor mode", "~/.config/hypr/scripts/monitor-mode-toggle.sh")
hl.unbind("SUPER + SHIFT + W")
o.bind("SUPER + SHIFT + W", "Typora", "uwsm-app -- typora --enable-wayland-ime")

-- Wallpaper Controller plugin shortcuts. These keys had no active Omarchy binding.
hl.unbind("SUPER + ALT + W")
o.bind("SUPER + ALT + W", "Open Wallpaper Controller", "omarchy-shell shell summon priyesh.wallpaper-controller")
hl.unbind("SUPER + SHIFT + R")
o.bind("SUPER + SHIFT + R", "Next wallpaper", "wallpaper-controller cycle")
hl.unbind("SUPER + ALT + Q")
o.bind("SUPER + ALT + Q", "Stop Wallpaper Engine", "wallpaper-controller stop")

o.bind("SUPER + CTRL + SHIFT + F", "Toggle window span DP-6 + DP-4", "~/.config/hypr/scripts/window-span-dp6-dp4-toggle.sh")

-- Cycle top bar visibility mode (Always show -> Auto-hide -> Disabled)
hl.unbind("SUPER + SHIFT + SPACE")
o.bind("SUPER + SHIFT + SPACE", "Cycle top bar visibility mode", "~/.config/hypr/scripts/bar-visibility-mode-toggle.sh")
