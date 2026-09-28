-- dirty.luau: fixture for slop-scan.py --self-test (every non-client rule must hit here)
wait(1)
spawn(function() end)
delay(1, function() end)
local part = Instance.new("Part", workspace)
local mover = Instance.new("BodyVelocity")
local connection = obj:connect(onTouch)
if workspace.FilteringEnabled then end
local hitPart = workspace:FindPartOnRay(ray)
local hitIgnoring = workspace:FindPartOnRayWithIgnoreList(ray, {})
local track = Humanoid:LoadAnimation(anim)
local jumpTrack = humanoid:LoadAnimation(jumpAnim)
model:SetPrimaryPartCFrame(cf)
local mouse = player:GetMouse()
label.Font = Enum.Font.Gotham
title.Font = Enum.Font.GothamBold
local grad = Instance.new("UIGradient")
label.Text = "Coins 🪙"
status.Text = "Done ✅"
counter.Text = `Coins 🪙 {coins}`
store:SetAsync("key", value)
icon.Image = "rbxassetid://0"

function ProcessReceipt(receiptInfo)
    return Enum.ProductPurchaseDecision.PurchaseGranted
end

local coinStore = DataStoreService:GetDataStore("Coins")

remote.OnServerEvent:Connect(function(player, amount)
    coins[player] = coins[player] + amount
end)
