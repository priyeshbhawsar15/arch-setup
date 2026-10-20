-- Display selectors are rendered from monitor-layout.json by the installers.
-- Quattro monitor layout. See https://wiki.hypr.land/Configuring/Basics/Monitors/

hl.env("GDK_SCALE", "2")

-- Safe fallback for displays not explicitly configured below.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })

-- Main 4K HDR monitor.
hl.monitor({
	output = "@monitor:main@",
	mode = "3840x2160@120",
	position = "0x0",
	scale = 1.5,
	bitdepth = 10,
	cm = "hdr",
	sdrbrightness = 1.0,
	sdrsaturation = 1.0,
})

-- Portrait side monitors.
hl.monitor({ output = "@monitor:side_left@", mode = "1920x1080@60", position = "2560x0", scale = 1, transform = 1 })
hl.monitor({ output = "@monitor:side_right@", mode = "1920x1080@60", position = "3640x0", scale = 1, transform = 3 })

-- Per-monitor Workspaces owns named workspaces while its managed toggle is
-- present. Keep the numeric assignment rules as the stock fallback so disabling
-- that independently managed plugin restores the current desktop behavior.
local per_monitor_workspace_toggle = os.getenv("HOME")
	.. "/.local/state/omarchy/toggles/hypr/per-monitor-workspaces.lua"
local per_monitor_workspace_state = io.open(per_monitor_workspace_toggle, "r")
local per_monitor_workspaces_enabled = per_monitor_workspace_state ~= nil
if per_monitor_workspace_state then
	per_monitor_workspace_state:close()
end

if not per_monitor_workspaces_enabled then
	hl.workspace_rule({ workspace = "1", monitor = "@monitor:main@", default = true, persistent = true })
	hl.workspace_rule({ workspace = "2", monitor = "@monitor:main@", persistent = true })
	hl.workspace_rule({ workspace = "3", monitor = "@monitor:side_left@", default = true, persistent = true })
	hl.workspace_rule({ workspace = "4", monitor = "@monitor:side_left@", persistent = true })
	hl.workspace_rule({ workspace = "5", monitor = "@monitor:side_right@", default = true, persistent = true })
	hl.workspace_rule({ workspace = "6", monitor = "@monitor:side_right@", persistent = true })
end

-- A lexical loader keeps the generated file isolated from Hyprland's global
-- API. The standard include line below must stay last: hyprmoncfg 1.22.1
-- recognizes and maintains that spelling during manage/unmanage operations.
local dofile = function(path)
	local state_home = os.getenv("XDG_STATE_HOME")
	if not state_home or state_home == "" then
		state_home = os.getenv("HOME") .. "/.local/state"
	end
	local managed = io.open(state_home .. "/arch-setups/crmne.hyprmoncfg/managed", "r")
	if not managed then return end
	managed:close()
	local api = setmetatable({}, { __index = hl })
	if per_monitor_workspaces_enabled then
		api.workspace_rule = function() end
	end
	local environment = setmetatable({ hl = api }, { __index = _G })
	local chunk, error_message = loadfile(path, "t", environment)
	assert(chunk, error_message)
	return chunk()
end

-- Added by hyprmoncfg: its generated monitor rules load last, so nothing before this can override the applied layout.
do local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"; local file = io.open(path, "r"); if file then file:close(); dofile(path) end end
