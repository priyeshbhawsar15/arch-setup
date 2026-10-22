-- Display selectors are rendered from monitor-layout.json by the installers.
-- Quattro monitor layout. See https://wiki.hypr.land/Configuring/Basics/Monitors/

-- Modes, positioning, scale and HDR belong to the selected host policy.
-- @monitor-rules@

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
-- @workspace-rules@
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
