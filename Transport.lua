local _, MPL = ...
local L = MPL.L
local sequence = 0

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

function MPL.SendRequest(name,realm,metric,spec,context,includeSpecs,refresh)
    if InCombatLockdown() then return nil,L["Запрос доступен вне боя"] end
    sequence=sequence+1
    local id=tostring(GetServerTime()).."-"..sequence
    local role=MPL.roles and MPL.roles[MPL.Key(name,realm)]
    spec=spec or MPL.SelectedSpec(name,realm,role) or ""
    if spec=="All specs" then spec="" end
    if includeSpecs and spec~="" then role=MPL.ProfileRole({spec=spec}) end
    local request=envelope(id,MPL.ExportCharacterRequest(name,realm,metric,spec,role),includeSpecs,refresh)
    MPL.pendingReply={id=id,name=name,realm=realm,metric=metric,spec=spec,role=role,context=context,includeSpecs=includeSpecs,refresh=refresh}
    return id,request
end

function MPL.SendBatchRequest(players,refresh)
    if InCombatLockdown() then return nil,L["Запрос доступен вне боя"] end
    if #players==0 then return nil,L["Нет кандидатов для загрузки"] end
    if #players>250 then return nil,L["Слишком много кандидатов (максимум 250)"] end
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
    MPL.pendingReply={id=id,batch=true,expected=expected,players=players,refresh=refresh}
    return id,envelope(id,"MPLQ2\n"..table.concat(rows),false,refresh)
end

function MPL.ReceiveReply(text, strict)
    local pendingReply=MPL.pendingReply
    if text:match("^MPLS2[\r\n]") then
        local id=text:match("^MPLS2\r?\n([^\r\n]+)")
        if not pendingReply or id~=pendingReply.id then return nil,L["Это ответ на другой запрос"] end
        return nil,L["Для загрузки этих логов обновите MPlusLogs Companion."]
    end
    if text:match("^MPLE1[\r\n]") then
        local id,message=text:match("^MPLE1\r?\n([^\r\n]+)\r?\n(.*)")
        if not pendingReply or id~=pendingReply.id then return nil,L["Это ответ на другой запрос"] end
        message=message:gsub("%%(%x%x)",function(hex) return string.char(tonumber(hex,16)) end)
        if not pendingReply.batch then
            local lower=string.lower(message)
            local reason
            if lower:find("rankings hidden",1,true) then reason="hidden"
            elseif lower:find("no public logs",1,true) or lower:find("character not found",1,true)
                or message:find(string.char(208,159,209,131,208,177,208,187,208,184,209,135,208,189,209,139,208,181,32,208,187,208,190,208,179,208,184),1,true) then reason="empty"
            elseif lower:find("profile refresh is cooling down",1,true) then reason="retry" end
            if reason then
                MPL.profileStates=MPL.profileStates or {}
                local key=MPL.Key(pendingReply.name,pendingReply.realm)
                MPlusLogsDB.profileStates=MPlusLogsDB.profileStates or {}
                local known=MPlusLogsDB.profileStates[key]
                local wasRetry=reason=="retry"
                if reason=="retry" and known and known.reason=="hidden" and (known.expires or 0)>GetServerTime() then
                    reason="hidden"
                end
                local state={reason=reason,spec=pendingReply.spec}
                if reason=="hidden" then
                    state.expires=wasRetry and known.expires or GetServerTime()+6*3600
                    MPlusLogsDB.profileStates[key]=state
                end
                MPL.profileStates[key]=state
                MPL.pendingReply=nil
                MPL.ShowProfile(pendingReply.name,pendingReply.realm,pendingReply.context,true)
                return 0
            end
        end
        return nil,MPL.T((message:gsub("[|%z]","")))
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
            MPL.pendingReply=nil
            MPL.ShowBatchResults(pendingReply.players,result.profiles,result.failures,count)
            local f=MPL.panel
            if pendingReply.groupPlayers and f and f.groupPlayers==pendingReply.groupPlayers and f:IsShown() then
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
        local count,importError=MPL.Import(body)
        if count then
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
