-- Display selectors are rendered from monitor-layout.json by the installers.
-- Quattro monitor layout. See https://wiki.hypr.land/Configuring/Basics/Monitors/

-- Modes, positioning, scale and HDR belong to the selected host policy.
-- @monitor-rules@

-- Omarchy numbers each monitor's workspaces, so numeric workspace rules from the
-- generated file must not load. hyprmoncfgd also writes a block that replaces
-- Omarchy's workspace module and rebinds Super + 1-0 to global numbers whenever
-- it can see `o.workspaces`, even with the profile's workspace plan disabled
-- (for example in the layout it restores after rejecting a profile). Super + 2
-- would then open the workspace 2 of whichever monitor owns 1-10, so the file
-- sees `o` without its workspaces. A lexical loader keeps that isolated from
-- Hyprland's global API. The standard include line below must stay last: hyprmoncfg 1.22.1
-- recognizes and maintains that spelling during manage/unmanage operations.
local dofile = function(path)
	local state_home = os.getenv("XDG_STATE_HOME")
	if not state_home or state_home == "" then
		state_home = os.getenv("HOME") .. "/.local/state"
	end
	local managed = io.open(state_home .. "/arch-setups/crmne.hyprmoncfg/managed", "r")
	if not managed then return end
	managed:close()
	local api = setmetatable({ workspace_rule = function() end }, { __index = hl })
	local omarchy = type(o) == "table" and setmetatable({ workspaces = false }, { __index = o }) or o
	local environment = setmetatable({ hl = api, o = omarchy }, { __index = _G })
	local chunk, error_message = loadfile(path, "t", environment)
	assert(chunk, error_message)
	return chunk()
end

-- Added by hyprmoncfg: its generated monitor rules load last, so nothing before this can override the applied layout.
do local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"; local file = io.open(path, "r"); if file then file:close(); dofile(path) end end
