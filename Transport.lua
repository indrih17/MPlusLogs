local _, MPL = ...
local L = MPL.L
local sequence = 0
local transientErrors={budget=true,schema=true,network=true,auth=true,unknown=true}

-- Negotiate specialization details so older addons still receive legacy rows
-- from the updated Companion, while new requests can include ranks and icons.
local function envelope(id, body,includeSpecs,refresh)
    local capabilities,seen={},{}
    local function add(value)
        if not seen[value] then capabilities[#capabilities+1]=value; seen[value]=true end
    end
    if includeSpecs then add("specprofiles") end
    if refresh then add("refresh") end
    add("specdetails")
    if MPL.CompanionSupports("lazyspecs") then add("lazyspecs") end
    if MPL.CompanionSupports("primarymetric") then add("primarymetric") end
    -- Request display fields on the first exchange too; discovery must not
    -- turn a fresh profile into one that immediately needs another load.
    if MPL.RequestRankColors() then add("rankcolors") end
    -- Optional extension: never require it from an unrecognized/older helper.
    if MPL.CompanionSupports("errorcodes") then add("errorcodes") end
    for _,value in ipairs(MPL.requiredCompanionCapabilities or {}) do add(value) end
    if #capabilities>0 then
        return "MPLS2\n"..id.."\nMPLC1 "..table.concat(capabilities,",").."\n"..body
    end
    return "MPLS1\n"..id.."\n"..body
end

function MPL.CompanionSupports(capability)
    if not MPL.companionInfo then return nil end
    return MPL.companionInfo.capabilities[capability] or false
end

function MPL.RequestRankColors()
    return MPL.CompanionSupports("rankcolors")~=false
end

function MPL.CompanionHasReplied()
    return MPlusLogsDB and MPlusLogsDB.companionReplySeen==true
end

function MPL.CompanionHasHistory()
    if MPL.CompanionHasReplied() then return true end
    -- Older saved profiles predate the reply marker. They justify skipping
    -- onboarding, but do not establish that Companion is running now.
    for _,profile in pairs(MPlusLogsDB and MPlusLogsDB.profiles or {}) do
        if type(profile)=="table" and type(profile.source)=="string" and profile.source:find("^WCL API:") then
            return true
        end
    end
    return false
end

function MPL.NeedsCompanionIntro()
    -- Saved acknowledgement and confirmed exchange are independent. Legacy WCL
    -- profiles suppress setup help without claiming a current connection.
    return not MPL.GetOption("hideTutorial") and not MPL.CompanionHasHistory()
        and not (MPlusLogsDB and MPlusLogsDB.companionIntroDismissed)
end

local function companionReplied()
    MPlusLogsDB=MPlusLogsDB or {}
    MPlusLogsDB.companionReplySeen=true
end

function MPL.SendRequest(name,realm,metric,spec,context,includeSpecs,refresh)
    if InCombatLockdown() then return nil,L["Запрос доступен вне боя"] end
    local role=MPL.roles and MPL.roles[MPL.Key(name,realm)]
    spec=spec or MPL.SelectedSpec(name,realm,role) or ""
    if spec=="All specs" then spec="" end
    local state=MPL.GetProfileState(name,realm,spec)
    if state and state.reason=="hidden" then return nil,L["Логи скрыты в Warcraft Logs."] end
    if MPL.ProfileRetryRemaining(name,realm,spec)>0 then
        return nil,"MPLERR1 "..(state.errorCode or "retry").." "..string.format("%.0f",state.expires)..":"..(state.error or MPL.RetryDelayText(state.expires))
    end
    sequence=sequence+1
    local id=tostring(GetServerTime()).."-"..sequence
    if spec~="" then role=MPL.ProfileRole({spec=spec}) or role end
    local request=envelope(id,MPL.ExportCharacterRequest(name,realm,metric,spec,role),includeSpecs,refresh)
    MPL.pendingReply={id=id,name=name,realm=realm,metric=metric,spec=spec,role=role,context=context,includeSpecs=includeSpecs,refresh=refresh,
        rankColors=MPL.RequestRankColors()}
    return id,request
end

function MPL.SendBatchRequest(players,refresh)
    if InCombatLockdown() then return nil,L["Запрос доступен вне боя"] end
    if #players==0 then return nil,L["Нет кандидатов для загрузки"] end
    if #players>250 then return nil,L["Слишком много кандидатов (максимум 250)"] end
    local available,retryAt={}
    for _,player in ipairs(players) do
        local selected=player.spec or MPL.SelectedSpec(player.name,player.realm,player.role)
        local state=MPL.GetProfileState(player.name,player.realm,selected)
        local waiting=MPL.ProfileRetryRemaining(player.name,player.realm,selected)>0
        if waiting then retryAt=math.min(retryAt or state.expires,state.expires)
        elseif not state or state.reason~="hidden" then
            -- The reply belongs to this selection even if a live tab changes.
            local snapshot={}
            for key,value in pairs(player) do snapshot[key]=value end
            available[#available+1]=snapshot
        end
    end
    if #available==0 then
        if retryAt then return nil,L["Все оставшиеся запросы временно отложены."].."\n"..MPL.RetryDelayText(retryAt) end
        return nil,L["Логи скрыты в Warcraft Logs."]
    end
    players=available
    local rows,expected={},{}
    for _,player in ipairs(players) do
        local key=MPL.Key(player.name,player.realm)
        if not expected[key] then
            expected[key]=player
            local spec=player.spec or MPL.SelectedSpec(player.name,player.realm,player.role) or ""
            if spec=="All specs" then spec="" end
            player.spec=spec
            rows[#rows+1]=MPL.ExportCharacterRequest(player.name,player.realm,"dps",spec,player.role):gsub("^MPLQ1\n","")
        end
    end
    sequence=sequence+1
    local id=tostring(GetServerTime()).."-"..sequence
    MPL.pendingReply={id=id,batch=true,expected=expected,players=players,refresh=refresh,
        rankColors=MPL.RequestRankColors()}
    return id,envelope(id,"MPLQ2\n"..table.concat(rows),false,refresh)
end

local function recordProfileFailure(name,realm,spec,message,code,retryAt)
    local lower=string.lower(message)
    local reason
    if code then
        reason=({hidden="hidden",missing="missing",empty="empty",retry="retry",auth="auth"})[code]
        if transientErrors[code] and code~="auth" and retryAt and retryAt>GetServerTime() then reason="retry" end
    elseif lower:find("rankings hidden",1,true) then reason="hidden"
    elseif lower:find("character not found",1,true) then reason="missing"
    elseif lower:find("no public logs",1,true)
        or message:find(string.char(208,159,209,131,208,177,208,187,208,184,209,135,208,189,209,139,208,181,32,208,187,208,190,208,179,208,184),1,true) then reason="empty"
    elseif lower:find("profile refresh is cooling down",1,true) then reason="retry" end
    if not reason then return end
    MPL.profileStates=MPL.profileStates or {}
    MPlusLogsDB.profileStates=MPlusLogsDB.profileStates or {}
    local key=MPL.Key(name,realm)
    local known=MPL.GetProfileState(name,realm,spec)
    local wasRetry=reason=="retry"
    if wasRetry and known and known.reason=="hidden" then reason="hidden" end
    local state={reason=reason,spec=reason~="hidden" and spec or nil}
    if reason=="retry" and retryAt and retryAt>GetServerTime() then state.expires=retryAt end
    if (reason=="retry" or reason=="auth") and transientErrors[code] then
        state.error=message; state.errorCode=code
    end
    if reason=="hidden" then
        state.expires=wasRetry and known.expires or GetServerTime()+6*3600
        MPlusLogsDB.profileStates[key]=state
    else
        MPlusLogsDB.profileStates[key]=nil
    end
    MPL.profileStates[key]=state
    return state
end

function MPL.ReceiveReply(text, strict)
    local replySupportsRankColors=false
    local pendingReply=MPL.pendingReply
    local replyVersion
    if text:match("^MPLS2[\r\n]") then
        local id=text:match("^MPLS2\r?\n([^\r\n]+)")
        if not pendingReply or id~=pendingReply.id then return nil,L["Это ответ на другой запрос"] end
        return nil,L["Для загрузки этих логов обновите MPlusLogs Companion."]
    end
    if text:match("^MPLE1[\r\n]") then
        local id,message=text:match("^MPLE1\r?\n([^\r\n]+)\r?\n(.*)")
        if not pendingReply or id~=pendingReply.id then return nil,L["Это ответ на другой запрос"] end
        message=message:gsub("%%(%x%x)",function(hex) return string.char(tonumber(hex,16)) end)
        if message=="" then return nil,L["Неверный формат ответа логов"] end
        local code,retryAt
        message,code,retryAt=MPL.DecodeCompanionError(message)
        companionReplied()
        if not pendingReply.batch then
            local state=recordProfileFailure(pendingReply.name,pendingReply.realm,pendingReply.spec,message,code,retryAt)
            if state and not transientErrors[code] then
                MPL.pendingReply=nil
                MPL.ShowProfile(pendingReply.name,pendingReply.realm,pendingReply.context,true)
                return 0
            end
        end
        message=(message:gsub("[|%z]",""))
        if code then return nil,"MPLERR1 "..code.." "..string.format("%.0f",retryAt)..":"..message end
        return nil,MPL.T(message)
    end
    if text:match("^MPLS1[\r\n]") then
        local id,body=text:match("^MPLS1\r?\n([^\r\n]+)\r?\n(.*)")
        if not pendingReply or id~=pendingReply.id then return nil,L["Это ответ на другой запрос; повторите загрузку нужного игрока"] end
        if body:match("^MPLV1 ") then
            local version,capabilities,payload=body:match("^MPLV1 (%d+%.%d+%.%d+) ([a-z,]+)\r?\n(.*)")
            if not version then return nil,L["Неверный формат ответа логов"] end
            local available={}
            for capability in capabilities:gmatch("[a-z]+") do available[capability]=true end
            MPL.companionInfo={version=version,capabilities=available}
            replySupportsRankColors=available.rankcolors==true
            replyVersion=version
            if pendingReply.includeSpecs and not available.specprofiles then return nil,L["Для загрузки этих логов обновите MPlusLogs Companion."] end
            if pendingReply.refresh and not available.refresh then return nil,L["Для загрузки этих логов обновите MPlusLogs Companion."] end
            for _,capability in ipairs(MPL.requiredCompanionCapabilities or {}) do
                if not available[capability] then return nil,L["Для загрузки этих логов обновите MPlusLogs Companion."] end
            end
            body=payload
        elseif pendingReply.includeSpecs or pendingReply.refresh or (MPL.requiredCompanionCapabilities and #MPL.requiredCompanionCapabilities>0) then
            return nil,L["Для загрузки этих логов обновите MPlusLogs Companion."]
        end
        if body:match("^MPLQ[12]") then return nil,L["Ответ ещё не получен. Попробуйте Ctrl+V чуть позже; проверьте, что помощник запущен."] end
        if body:match("^MPLB1\r?\n") then
            body=body:gsub("^MPLB1\r?\n", "",1)
            body=body:gsub("%%(%x%x)",function(hex) return string.char(tonumber(hex,16)) end)
        end
        if pendingReply.batch then
            local result,err=MPL.Parse(body,true)
            if not result then return nil,err end
            MPL.SetProfileDisplayMetadata(result.profiles,pendingReply.rankColors,replySupportsRankColors)
            for key,profile in pairs(result.profiles) do
                local expected=pendingReply.expected[key]
                if not expected then return nil,L["Ответ содержит персонажа вне списка кандидатов"] end
                if expected.role and profile.role~=expected.role then return nil,L["Ответ содержит другую роль кандидата"] end
                if profile.spec~=(expected.spec~="" and expected.spec or "All specs") then return nil,L["Ответ содержит другую специализацию"] end
            end
            for key in pairs(result.failures) do
                if not pendingReply.expected[key] then return nil,L["Ошибка относится к персонажу вне списка кандидатов"] end
            end
            for key in pairs(pendingReply.expected) do
                if not result.profiles[key] and not result.failures[key] then return nil,L["Не получен результат для всех кандидатов"] end
            end
            for key,profile in pairs(result.profiles) do
                if result.failures[key] then
                    local current=MPL.GetProfile(profile.name,profile.realm)
                    if current and current.updated:match("^%d%d%d%d%-%d%d%-%d%d") and current.updated>profile.updated then
                        result.profiles[key]=current
                    end
                end
            end
            local count=MPL.StoreProfiles(result.profiles)
            for key,failure in pairs(result.failures) do
                local player=pendingReply.expected[key]
                recordProfileFailure(player.name,player.realm,player.spec,failure.error,failure.errorCode,failure.retryAt)
            end
            companionReplied()
            if MPL.QueueCompanionUpdateNotice then MPL.QueueCompanionUpdateNotice(replyVersion) end
            MPL.pendingReply=nil
            local loaded,errorCount=0,0
            for _,player in ipairs(pendingReply.players) do
                local key=MPL.Key(player.name,player.realm)
                if result.failures[key] then errorCount=errorCount+1
                elseif result.profiles[key] then loaded=loaded+1 end
            end
            MPL.lastBatchResult={players=pendingReply.players,profiles=result.profiles,failures=result.failures,
                count=count,loaded=loaded,errorCount=errorCount}
            if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
            local f=MPL.panel
            -- Roster events replace the live player table while this snapshot
            -- is in flight. Match the displayed character, not table identity.
            if pendingReply.groupPlayers and f and type(f.groupPlayers)=="table"
                and (f.groupPlayers==pendingReply.groupPlayers or pendingReply.expected[MPL.Key(f.name,f.realm)])
                and f:IsShown() then
                f.groupFailures=result.failures
                MPL.ShowProfile(f.name,f.realm,f.applicant,true,true)
            end
            return count
        end
        local profiles,err=MPL.Parse(body)
        if not profiles then return nil,err end
        local expected=MPL.Key(pendingReply.name,pendingReply.realm)
        if not profiles[expected] then return nil,L["Ответ не содержит выбранного персонажа"] end
        if strict then
            for key,profile in pairs(profiles) do
                if (not pendingReply.includeSpecs and key~=expected)
                    or MPL.Key(profile.name,profile.realm,profile.region)~=expected then return nil,L["Ответ содержит данные другого персонажа"] end
            end
            if not profiles[expected].dual and profiles[expected].metric~=pendingReply.metric then return nil,L["Ответ содержит другую метрику логов"] end
            if profiles[expected].spec~=(pendingReply.spec~="" and pendingReply.spec or "All specs") then
                return nil,L["Ответ содержит другую специализацию"]
            end
            if pendingReply.role and MPL.ProfileRole(profiles[expected])~=pendingReply.role then return nil,L["Ответ содержит другую роль персонажа"] end
        end
        MPL.SetProfileDisplayMetadata(profiles,pendingReply.rankColors,replySupportsRankColors)
        local count,importError=MPL.StoreProfiles(profiles)
        if count then
            if count>0 and pendingReply.includeSpecs and pendingReply.spec=="" then
                MPL.RecordSpecDiscovery(pendingReply.name,pendingReply.realm,profiles[expected],pendingReply.metric)
            end
            companionReplied()
            if MPL.QueueCompanionUpdateNotice then MPL.QueueCompanionUpdateNotice(replyVersion) end
            if MPL.profileStates then MPL.profileStates[expected]=nil end
            if MPlusLogsDB.profileStates then MPlusLogsDB.profileStates[expected]=nil end
            MPL.pendingReply=nil; MPL.ShowProfile(pendingReply.name,pendingReply.realm,pendingReply.context,true)
            if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
        end
        return count,importError
    end
    if strict then return nil,L["В буфере нет ответа MPlusLogs для этого запроса. Нажмите Ctrl+V позже; проверьте помощник."] end
    return MPL.Import(text)
end
