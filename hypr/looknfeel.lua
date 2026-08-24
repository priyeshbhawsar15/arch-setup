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

o.window("^steam_app_.*", { border_size = 0, rounding = 0 })
o.window("^(RDR2\\.exe|Launcher\\.exe)$", { border_size = 0, rounding = 0 })
