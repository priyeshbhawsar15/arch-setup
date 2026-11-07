-- Display selectors are rendered from monitor-layout.json by the installers.
-- Quattro monitor layout. See https://wiki.hypr.land/Configuring/Basics/Monitors/

-- Modes, positioning, scale and HDR belong to the selected host policy.
-- @monitor-rules@

-- Sunshine virtual desktop (install-virtual-desktop.sh). The rules only apply
-- while its SUNSHINE-VIRTUAL-1080P output exists.
-- * Keep it unscaled: the helper sets scale=1 only at runtime, and every config
--   reload (hyprmoncfgd re-applies on any monitor change) drops that, so the
--   catch-all scale="auto" picks 2 and the stream looks zoomed in.
-- * Keep a monitor at 0,0: Sunshine measures the desktop from 0,0, while
--   Hyprland maps the absolute stream mouse across the enabled outputs only.
--   With the left monitor off the layout starts further right and the stream
--   cursor drifts, so the virtual output takes 0,0 whenever nothing else does
--   and otherwise sits to the right of everything.
local SUNSHINE_VIRTUAL = "SUNSHINE-VIRTUAL-1080P"
local SUNSHINE_VIRTUAL_W, SUNSHINE_VIRTUAL_H = 1920, 1080

local function logical_size(m)
	-- width/height are the raw mode; the layout uses the rotated, scaled size.
	local w, h = m.width / m.scale, m.height / m.scale
	if m.transform % 2 == 1 then w, h = h, w end
	return w, h
end

local function sunshine_virtual_position()
	local left, top, right, bottom, others = math.huge, math.huge, 0, 0, {}
	local virtual
	for _, m in ipairs(hl.get_monitors()) do
		if m.name == SUNSHINE_VIRTUAL then
			virtual = m
		elseif not m.is_mirror then
			local w, h = logical_size(m)
			others[#others + 1] = { m.x, m.y, m.x + w, m.y + h }
			left, top = math.min(left, m.x), math.min(top, m.y)
			right, bottom = math.max(right, m.x + w), math.max(bottom, m.y + h)
		end
	end
	if #others == 0 then return 0, 0, virtual end
	if left == 0 and top == 0 then return right, 0, virtual end
	for _, b in ipairs(others) do
		if b[1] < SUNSHINE_VIRTUAL_W and b[2] < SUNSHINE_VIRTUAL_H then
			return 0, bottom, virtual -- 0,0 is taken; below everything still gives x=0
		end
	end
	return 0, 0, virtual
end

local function place_sunshine_virtual()
	local x, y, virtual = sunshine_virtual_position()
	x, y = math.floor(x + 0.5), math.floor(y + 0.5)
	-- Re-applying an identical rule still fires layout events; skip no-ops.
	if virtual and virtual.x == x and virtual.y == y and virtual.scale == 1 then return end
	hl.monitor({ output = SUNSHINE_VIRTUAL, mode = "1920x1080@60", position = string.format("%dx%d", x, y), scale = 1 })
end
place_sunshine_virtual()
for _, event in ipairs({ "hyprland.start", "config.reloaded", "monitor.added", "monitor.removed", "monitor.layout_changed" }) do
	hl.on(event, place_sunshine_virtual)
end

-- Omarchy numbers each monitor's workspaces, so numeric workspace rules from the
-- generated file must not load. A lexical loader keeps that isolated from
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
	local environment = setmetatable({ hl = api }, { __index = _G })
	local chunk, error_message = loadfile(path, "t", environment)
	assert(chunk, error_message)
	return chunk()
end

-- Added by hyprmoncfg: its generated monitor rules load last, so nothing before this can override the applied layout.
do local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"; local file = io.open(path, "r"); if file then file:close(); dofile(path) end end
