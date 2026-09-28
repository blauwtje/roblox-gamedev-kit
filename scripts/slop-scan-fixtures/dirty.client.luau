-- dirty.client.luau: fixture for slop-scan.py --self-test (the client-only rule)
local AntiCheat = {}

local function onFlag(player)
    player:Kick("banned by client anti-cheat")
end
