-- Personal Quattro binding overrides.

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

-- SUPER+ALT+W previously toggled the legacy systemd Wallpaper Engine service.
hl.unbind("SUPER + ALT + W")
o.bind("SUPER + ALT + W", "Open Wallpaper Controller", "omarchy-shell shell summon priyesh.wallpaper-controller")
-- SUPER+SHIFT+R previously started the legacy Wallpaper Engine rotation unit.
hl.unbind("SUPER + SHIFT + R")
o.bind("SUPER + SHIFT + R", "Next wallpaper", "wallpaper-controller cycle")
o.bind("SUPER + CTRL + SHIFT + F", "Toggle window span DP-6 + DP-4", "~/.config/hypr/scripts/window-span-dp6-dp4-toggle.sh")

-- Replace Omarchy's binary top-bar toggle with per-monitor visibility modes.
hl.unbind("SUPER + SHIFT + SPACE")
o.bind("SUPER + SHIFT + SPACE", "Cycle top bar visibility mode", "~/.config/hypr/scripts/bar-visibility-mode-toggle.sh")
