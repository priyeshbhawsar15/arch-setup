-- Personal appearance, color-management, and window-rule overrides.

hl.config({
	general = {
		gaps_in = 2,
		gaps_out = 5,
		border_size = 1,
	},
	decoration = {
		rounding = 8,
	},
	render = {
		cm_enabled = true,
		cm_auto_hdr = 1,
	},
})

o.window("^chrome-jellyfin\\.home\\.priyeshbhawsar\\.com__-Default$", {
	tag = "-default-opacity",
	opacity = "1 override 1 override",
})

-- Confine AoE2's visible cursor at the compositor boundary, not just inside
-- Gamescope. Switch away with Alt+Tab or a workspace shortcut to leave the game.
-- Keep this scoped: other games and desktop applications retain normal input.
o.window({ class = "^(gamescope|steam_app_813780)$", title = "^Age of Empires II: Definitive Edition$" }, {
	confine_pointer = true,
})

o.window("^steam_app_.*", { border_size = 0, rounding = 0 })
o.window("^(RDR2\\.exe|Launcher\\.exe)$", { border_size = 0, rounding = 0 })
