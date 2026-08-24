-- Quattro monitor layout. See https://wiki.hypr.land/Configuring/Basics/Monitors/

hl.env("GDK_SCALE", "2")

-- Safe fallback for displays not explicitly configured below.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })

-- Main 4K HDR monitor.
hl.monitor({
	output = "DP-5",
	mode = "3840x2160@120",
	position = "0x0",
	scale = 1.5,
	bitdepth = 10,
	cm = "hdr",
	sdrbrightness = 1.5,
	sdrsaturation = 1.0,
})

-- Portrait side monitors.
hl.monitor({ output = "DP-6", mode = "1920x1080@60", position = "2560x0", scale = 1, transform = 1 })
hl.monitor({ output = "DP-4", mode = "1920x1080@60", position = "3640x0", scale = 1, transform = 3 })

hl.workspace_rule({ workspace = "1", monitor = "DP-5", default = true, persistent = true })
hl.workspace_rule({ workspace = "2", monitor = "DP-5", persistent = true })
hl.workspace_rule({ workspace = "3", monitor = "DP-6", default = true, persistent = true })
hl.workspace_rule({ workspace = "4", monitor = "DP-6", persistent = true })
hl.workspace_rule({ workspace = "5", monitor = "DP-4", default = true, persistent = true })
hl.workspace_rule({ workspace = "6", monitor = "DP-4", persistent = true })
