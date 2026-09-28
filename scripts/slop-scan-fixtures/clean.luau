-- clean.luau: fixture for slop-scan.py --self-test (must yield zero hits)
local function myspawn(job)
    task.spawn(job)
end

local function onTouched(hit)
    task.wait(0.1)
    task.delay(1, function()
        print("cooldown done")
    end)
end

local part = Instance.new("Part")
part.Size = Vector3.new(4, 1, 2)
part.Parent = workspace

local connection = part.Touched:Connect(onTouched)
myspawn(function()
    print("ready")
end)

-- use task.wait, never wait()
local timer = { wait = function() end }
timer:wait(1)
timer.wait(1)
Promise.delay(1):andThen(function() end)
local walkTrack = animator:LoadAnimation(walkAnim)
title.Font = Enum.Font.BuilderSans
rating.Text = "★ 5 ✓"
