local _, MPL = ...

-- Recommend an already published release. Raise this with the next addon release
-- after its matching Companion is available; Companion-only releases stay independent.
MPL.recommendedCompanionVersion = "1.0.26"

local function versionParts(version)
    if type(version)~="string" then return end
    local major,minor,patch=version:match("^(%d+)%.(%d+)%.(%d+)$")
    if major then return {tonumber(major),tonumber(minor),tonumber(patch)} end
end

function MPL.GetCompanionUpdateNotice(version)
    local recommended=MPL.recommendedCompanionVersion
    local target=versionParts(recommended)
    if not target or (MPlusLogsDB and MPlusLogsDB.companionUpdateNoticeVersion==recommended) then return end
    local installed=versionParts(version)
    if installed then
        for i=1,3 do
            if installed[i]>target[i] then return end
            if installed[i]<target[i] then
                return {installed=version,recommended=recommended}
            end
        end
        return
    end
    return {recommended=recommended}
end

function MPL.TryCompanionUpdateNotice()
    local notice=MPL.pendingCompanionUpdateNotice
    if not notice or InCombatLockdown() or not MPL.ShowCompanionUpdates then return end
    if not MPL.GetCompanionUpdateNotice(notice.installed) then
        MPL.pendingCompanionUpdateNotice=nil
        return
    end
    MPL.ShowCompanionUpdates(notice)
    MPlusLogsDB=MPlusLogsDB or {}
    MPlusLogsDB.companionUpdateNoticeVersion=notice.recommended
    MPL.pendingCompanionUpdateNotice=nil
end

function MPL.QueueCompanionUpdateNotice(version)
    -- A newer valid reply can cancel an older queued notice before it is shown.
    MPL.pendingCompanionUpdateNotice=MPL.GetCompanionUpdateNotice(version)
    if MPL.pendingCompanionUpdateNotice then
        -- Let paste/import and its window closure finish first.
        C_Timer.After(0,MPL.TryCompanionUpdateNotice)
    end
end
