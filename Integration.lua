local addonName, MPL = ...
local L = MPL.L

local pvpCategories={[4]=true,[7]=true,[8]=true,[9]=true,[10]=true}
local function safe(value)
    return not (issecretvalue and issecretvalue(value))
end

function MPL.GroupLogCategory(activity)
    if type(activity)~="table" or not safe(activity) then return end
    if not safe(activity.isMythicPlusActivity) or not safe(activity.isPvpActivity) or not safe(activity.isRatedPvpActivity)
        or not safe(activity.categoryID) then return end
    if activity.isMythicPlusActivity then return "mythicPlus" end
    if activity.isPvpActivity or activity.isRatedPvpActivity==true or pvpCategories[activity.categoryID] then return "showInPvp" end
    if activity.categoryID==3 then
        if not safe(activity.difficultyID) then return end
        -- Open-world boss listings have no instance difficulty.
        if activity.difficultyID==0 then return "showInOtherGroups" end
        return "showInRaids"
    end
    if type(activity.categoryID)=="number" then return "showInOtherGroups" end
end

function MPL.GroupLogsEnabled(activityIDs)
    if InCombatLockdown() or not C_LFGList.GetActivityInfoTable then return false end
    if not activityIDs and C_LFGList.GetActiveEntryInfo then
        if C_LFGList.HasActiveEntryInfo and not C_LFGList.HasActiveEntryInfo() then return false end
        local entry=C_LFGList.GetActiveEntryInfo()
        activityIDs=entry and entry.activityIDs
    end
    if type(activityIDs)~="table" or not safe(activityIDs) then return false end
    for _,id in ipairs(activityIDs) do
        if safe(id) then
            local key=MPL.GroupLogCategory(C_LFGList.GetActivityInfoTable(id))
            if key=="mythicPlus" or (key and MPL.GetOption(key)) then return true end
        end
    end
    return false
end

-- Match the activity's instance map ID through Blizzard's challenge-map API.
local dungeonNames={
    [584]="The Blinding Vale",[585]="Voidscar Arena",[586]="Den of Nalorakk",[587]="Murder Row",
    [588]="Altar of Fangs",[249]="Kings' Rest",[250]="Temple of Sethraliss",[399]="Ruby Life Pools",
}
function MPL.ListedDungeon(activityIDs)
    if InCombatLockdown() or not C_LFGList.GetActivityInfoTable then return end
    if not activityIDs and C_LFGList.GetActiveEntryInfo then
        local entry=C_LFGList.GetActiveEntryInfo()
        activityIDs=entry and entry.activityIDs
    end
    if type(activityIDs)~="table" then return end
    local found
    for _,id in ipairs(activityIDs) do
        if issecretvalue and issecretvalue(id) then return end
        local activity=C_LFGList.GetActivityInfoTable(id)
        if not activity or (issecretvalue and issecretvalue(activity.isMythicPlusActivity)) or not activity.isMythicPlusActivity then return end
        local name
        if C_ChallengeMode and C_ChallengeMode.GetMapUIInfo then
            for mapID,canonical in pairs(dungeonNames) do
                local localized,_,_,_,_,instanceMap=C_ChallengeMode.GetMapUIInfo(mapID)
                local safeMap=not (issecretvalue and issecretvalue(activity.mapID)) and type(activity.mapID)=="number"
                if (safeMap and instanceMap and activity.mapID==instanceMap)
                    or (not safeMap and MPL.SafeString(localized) and ((MPL.SafeString(activity.fullName) and activity.fullName:find(localized,1,true))
                    or (MPL.SafeString(activity.shortName) and activity.shortName==localized))) then name=canonical; break end
            end
        end
        if not name or (found and found~=name) then return end
        found=name
    end
    return found
end

local dungeonAbbreviations={
    ["The Blinding Vale"]="BV",["Voidscar Arena"]="VA",["Den of Nalorakk"]="DON",["Murder Row"]="MR",
    ["Altar of Fangs"]="AOF",["Kings' Rest"]="KR",["Temple of Sethraliss"]="TOS",["Ruby Life Pools"]="RLP",
}

function MPL.AddDungeonTooltip(tooltip,profile,metric,stale,dungeon)
    if not dungeon then return end
    local prefix="["..(dungeonAbbreviations[dungeon] or dungeon).."] "
    for _,row in ipairs(profile.dungeons or {}) do
        if row.name==dungeon then
            local level,_,best,median=MPL.MetricValues(profile,row,metric)
            if MPL.GetOption("percentile")=="dungeon_dps" then
                tooltip:AddDoubleLine(prefix..L["Лучший "]..metric:upper(),MPL.PrimaryStatistic(profile,metric,dungeon,stale))
            end
            best,median=MPL.OrderPercentiles(best,median)
            tooltip:AddDoubleLine(prefix..metric:upper().." "..MPL.PercentileCaption(),MPL.Percent(best,stale).." / "..MPL.Percent(median,stale))
            tooltip:AddDoubleLine(prefix..L["Ключ лучшего результата"],level and ("+"..level) or "—")
            tooltip:AddDoubleLine(prefix..L["Залогированные прохождения"],tostring(row.runs or "—"))
            return
        end
    end
    tooltip:AddLine(prefix..L["Нет загруженных логов этого подземелья"],0.65,0.65,0.65)
end

function MPL.AddTooltip(tooltip, fullName, realm, dungeon)
    if InCombatLockdown() or not MPlusLogsDB or not MPL.GetOption("tooltips") then return end
    if MPL.UsesDungeonMetric() then dungeon=dungeon or MPL.ListedDungeon() end
    local profile, name, server = MPL.GetProfile(fullName,realm)
    if not name then return end
    local state=MPL.GetProfileState(name,server,MPL.SelectedSpec(name,server))
    if state and (state.reason=="hidden" or state.reason=="empty" or state.reason=="missing") then profile=nil end
    local key = MPL.Key(name,server)..":"..(profile and MPL.VariantKey(profile) or MPL.SelectedSpec(name,server) or "")..":"..(dungeon or "")..":"..(state and state.reason or "")
    MPL.Remember(name,server)
    if tooltip.mplKey == key then return end
    tooltip.mplKey = key
    tooltip:AddLine(" ")
    tooltip:AddLine("MPlusLogs / M+ S2",0.4,0.8,1)
    if profile then
        local stale=MPL.IsProfileStale(profile)
        local primary=MPL.PrimaryMetric(profile,name,server)
        local secondary=primary=="hps" and "dps" or "hps"
        local _,_,best,median=MPL.MetricValues(profile,nil,primary)
        local _,_,otherBest,otherMedian=MPL.MetricValues(profile,nil,secondary)
        best,median=MPL.OrderPercentiles(best,median)
        otherBest,otherMedian=MPL.OrderPercentiles(otherBest,otherMedian)
        tooltip:AddLine(MPL.SpecLabel(profile.spec) .. L[" / по уровню ключа"],0.8,0.8,0.8)
        MPL.AddDungeonTooltip(tooltip,profile,primary,stale,dungeon)
        tooltip:AddDoubleLine(primary:upper().." "..MPL.PercentileCaption(),MPL.Percent(best,stale).." / "..MPL.Percent(median,stale))
        tooltip:AddDoubleLine(secondary:upper().." "..MPL.PercentileCaption(),MPL.Percent(otherBest,stale).." / "..MPL.Percent(otherMedian,stale))
        tooltip:AddDoubleLine(L["Залогированные прохождения"],tostring(profile.runs or "—"))
        if stale then tooltip:AddLine(L["Обновите логи персонажа"],0.65,0.65,0.65) end
    elseif state and state.reason=="hidden" then
        tooltip:AddLine(L["Логи скрыты в Warcraft Logs."],0.65,0.65,0.65)
    else
        local spec=MPL.SelectedSpec(name,server)
        if spec then tooltip:AddLine(MPL.SpecLabel(spec),0.8,0.8,0.8) end
        tooltip:AddLine(L["Профиль не загружен"],0.65,0.65,0.65)
    end
    tooltip:AddLine(L["ПКМ > M+ логи"],0.4,0.8,1)
    tooltip:Show()
end

local function applicant(owner)
    if not owner or not owner.memberIdx then return end
    local parent = owner:GetParent()
    if not parent or not parent.applicantID then return end
    local fullName,class,_,_,_,_,_,_,_,role,_,_,_,_,_,specID = C_LFGList.GetApplicantMemberInfo(parent.applicantID,owner.memberIdx)
    MPL.RecordApplicant(fullName,role,specID,class)
    if MPL.SafeString(fullName) then return fullName end
end
-- Search leaders need not be inspectable units. Use Blizzard's listing data;
-- never assume that member #1 is the leader.
local function recordSearchLeader(resultID,info)
    if type(info)~="table" or not safe(info) or not MPL.SafeString(info.leaderName) then return end
    local leader
    if C_LFGList.GetSearchResultLeaderInfo then
        leader=C_LFGList.GetSearchResultLeaderInfo(resultID)
    end
    if not leader and C_LFGList.GetSearchResultPlayerInfo and safe(info.numMembers)
        and type(info.numMembers)=="number" and info.numMembers>=1 and info.numMembers<=40 then
        for index=1,info.numMembers do
            local member=C_LFGList.GetSearchResultPlayerInfo(resultID,index)
            if type(member)=="table" and safe(member) and safe(member.isLeader) and member.isLeader==true then
                leader=member; break
            end
        end
    end
    if type(leader)~="table" or not safe(leader) or not MPL.SafeString(leader.classFilename) then return end
    local specID
    if MPL.SafeString(leader.specName) then
        for id,spec in pairs(MPL.specInfo) do
            if spec[3]==leader.classFilename and MPL.SpecLabel(spec[1],spec[3])==leader.specName then
                specID=id; break
            end
        end
    end
    MPL.RecordApplicant(info.leaderName,leader.assignedRole,specID,leader.classFilename)
end

local function menu(root, fullName, realm,context,searchResultID)
    local name, server = MPL.Identity(fullName,realm)
    if not name then return end
    root:CreateDivider()
    root:CreateButton(L["M+ логи (MPlusLogs)"],function()
        -- Session capabilities are unknown after /reload. Keep the requested
        -- roster; the group exchange negotiates support with older helpers.
        if searchResultID and MPL.ShowSearchGroupLogs then
            local players=MPL.CollectSearchGroup(searchResultID)
            if players and #players>1 then MPL.ShowSearchGroupLogs(searchResultID); return end
        end
        if not context and not (IsInRaid and IsInRaid()) then
            local players=MPL.CollectParty()
            for _,player in ipairs(players) do
                if #players>1 and MPL.Key(player.name,player.realm)==MPL.Key(name,server) then
                    MPL.ShowGroupProfiles(players,player,true); return
                end
            end
        end
        MPL.ShowProfile(name,server,context)
    end)
    root:CreateButton(L["Ссылка на логи M+"],function()
        local profile=MPL.GetProfile(name,server)
        MPL.CopyURL(name,server,profile)
    end)
end

local hooked = {}
local function hookLFG()
    if not hooked.logColumn and type(LFGListApplicationViewer_UpdateApplicantMember)=="function" then
        hooksecurefunc("LFGListApplicationViewer_UpdateApplicantMember",function(member,id,index,status)
            MPL.UpdateApplicantLog(member,id,index,status)
        end)
        hooked.logColumn=true
    end
    if not hooked.applicant and type(LFGListApplicantMember_OnEnter) == "function" then
        hooksecurefunc("LFGListApplicantMember_OnEnter",function(owner)
            if InCombatLockdown() or not MPL.GroupLogsEnabled() then return end
            local name = applicant(owner)
            if name then MPL.AddTooltip(GameTooltip,name,nil,MPL.ListedDungeon()) end
        end)
        hooked.applicant = true
    end
    if not hooked.search and type(LFGListSearchEntry_OnEnter) == "function" then
        hooksecurefunc("LFGListSearchEntry_OnEnter",function(owner)
            if InCombatLockdown() or not owner.resultID then return end
            local info = C_LFGList.GetSearchResultInfo(owner.resultID)
            if info and MPL.SafeString(info.leaderName) and MPL.GroupLogsEnabled(info.activityIDs) then
                recordSearchLeader(owner.resultID,info)
                MPL.AddTooltip(GameTooltip,info.leaderName,nil,MPL.ListedDungeon(info.activityIDs))
            end
        end)
        hooked.search = true
    end
    if not hooked.menu and Menu and Menu.ModifyMenu then
        Menu.ModifyMenu("MENU_LFG_FRAME_MEMBER_APPLY",function(owner,root)
            if not MPL.GroupLogsEnabled() then return end
            local fullName=applicant(owner)
            local context
            if MPL.SafeString(fullName) then
                local name,realm=MPL.Identity(fullName)
                local parent=owner and owner:GetParent()
                for _,player in ipairs(MPL.CollectApplicants()) do
                    if parent and player.applicantID==parent.applicantID and player.memberIndex==owner.memberIdx
                        and MPL.Key(player.name,player.realm)==MPL.Key(name,realm) then context=player; break end
                end
            end
            menu(root,fullName,nil,context)
        end)
        Menu.ModifyMenu("MENU_LFG_FRAME_SEARCH_ENTRY",function(owner,root)
            if not owner or not owner.resultID then return end
            local info = C_LFGList.GetSearchResultInfo(owner.resultID)
            if info and MPL.GroupLogsEnabled(info.activityIDs) then
                recordSearchLeader(owner.resultID,info)
                menu(root,info.leaderName,nil,nil,owner.resultID)
            end
        end)
        for _, tag in ipairs({"PLAYER","SELF","TARGET","FOCUS","PARTY","RAID_PLAYER","FRIEND","GUILD","GUILD_OFFLINE","CHAT_ROSTER"}) do
            Menu.ModifyMenu("MENU_UNIT_"..tag,function(_,root,context)
                if not context then return end
                if MPL.SafeString(context.unit) and UnitExists(context.unit) and UnitIsPlayer(context.unit) then
                    local name, realm = UnitFullName(context.unit)
                    menu(root,name,realm)
                else menu(root,context.name,context.realm or context.server) end
            end)
        end
        hooked.menu = true
    end
end

function MPL.CollectParty()
    if InCombatLockdown() then return {} end
    local players,seen={},{}
    for _,unit in ipairs({"player","party1","party2","party3","party4"}) do
        if UnitExists(unit) and UnitIsPlayer(unit) then
            local name,realm=MPL.Identity(UnitFullName(unit))
            if name and realm then
                local key=MPL.Key(name,realm)
                if not seen[key] then
                    local role=UnitGroupRolesAssigned and UnitGroupRolesAssigned(unit)
                    role=MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] and role or nil
                    MPL.RefreshCharacterSpec(name,realm)
                    if role then MPL.roles=MPL.roles or {}; MPL.roles[key]=role end
                    players[#players+1]={name=name,realm=realm,role=role,spec=MPL.SelectedSpec(name,realm,role)}
                    seen[key]=true
                end
            end
        end
    end
    return players
end

function MPL.CollectApplicantGroup(context)
    local players={}
    for _,player in ipairs(MPL.CollectApplicants()) do
        if player.applicantID==context.applicantID then players[#players+1]=player end
    end
    table.sort(players,function(a,b) return a.memberIndex<b.memberIndex end)
    return players
end

function MPL.CollectApplicants()
    if InCombatLockdown() then return {},L["Список кандидатов доступен вне боя"] end
    if not C_LFGList.GetApplicants then return {},L["Окно сбора группы ещё не загружено"] end
    local players,seen={},{}
    for _,id in ipairs(C_LFGList.GetApplicants() or {}) do
        local info=C_LFGList.GetApplicantInfo(id)
        if info and not (issecretvalue and (issecretvalue(info.numMembers) or issecretvalue(info.applicationStatus)))
            and type(info.numMembers)=="number" and (not info.applicationStatus or info.applicationStatus=="applied") then
            local roster={}
            for member=1,info.numMembers do
                local fullName,class,_,_,_,_,_,_,_,role,_,_,_,_,_,specID=C_LFGList.GetApplicantMemberInfo(id,member)
                local spec=MPL.RecordApplicant(fullName,role,specID,class)
                local name,realm=MPL.Identity(fullName)
                if MPL.SafeString(name) and MPL.SafeString(realm) then
                    local key=MPL.Key(name,realm)
                    roster[key]=true
                    if not seen[key] then
                        local knownRole=MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] and role or nil
                        players[#players+1]={name=name,realm=realm,role=knownRole,spec=spec,applicantID=id,memberIndex=member,groupSize=info.numMembers,roster=roster}
                        seen[key]=true
                        if knownRole then MPL.roles=MPL.roles or {}; MPL.roles[key]=knownRole end
                    end
                end
            end
        end
    end
    table.sort(players,function(a,b) return a.realm..a.name<b.realm..b.name end)
    return players
end

function MPL.ValidateApplicant(context)
    if InCombatLockdown() then return nil,L["Приглашение доступно вне боя"] end
    if type(context)~="table" or not context.applicantID then return nil,L["Сводка открыта вне списка заявок"] end
    if type(context.memberIndex)~="number" or type(context.groupSize)~="number"
        or context.memberIndex<1 or context.memberIndex>context.groupSize then return nil,L["Данные выбранной заявки недоступны"] end
    if not LFGListUtil_IsEntryEmpowered or not LFGListUtil_IsEntryEmpowered() then return nil,L["Нет прав на приглашение"] end
    if C_LFGList.HasActiveEntryInfo and not C_LFGList.HasActiveEntryInfo() then return nil,L["Объявление закрыто"] end
    local found=false
    for _,id in ipairs(C_LFGList.GetApplicants() or {}) do if id==context.applicantID then found=true; break end end
    if not found then return nil,L["Заявка больше не активна"] end
    local info=C_LFGList.GetApplicantInfo(context.applicantID)
    if not info or (issecretvalue and (issecretvalue(info.applicationStatus) or issecretvalue(info.numMembers))) then return nil,L["Данные заявки недоступны"] end
    if info.applicationStatus~="applied" then return nil,L["Заявка больше не ожидает приглашения"] end
    if info.numMembers~=context.groupSize then return nil,L["Состав заявки изменился; откройте сводку заново"] end
    local seen={}
    for member=1,info.numMembers do
        local fullName=C_LFGList.GetApplicantMemberInfo(context.applicantID,member)
        if not MPL.SafeString(fullName) then return nil,L["Данные участника недоступны"] end
        local name,realm=MPL.Identity(fullName)
        if not MPL.SafeString(name) or not MPL.SafeString(realm) then return nil,L["Данные участника недоступны"] end
        local key=MPL.Key(name,realm)
        if not context.roster or not context.roster[key] then return nil,L["Состав заявки изменился; откройте сводку заново"] end
        seen[key]=true
        if member==context.memberIndex and key~=MPL.Key(context.name,context.realm) then return nil,L["Выбранный кандидат изменился"] end
    end
    local members=0
    for key in pairs(context.roster or {}) do if not seen[key] then return nil,L["Состав заявки изменился"] end; members=members+1 end
    if members~=info.numMembers then return nil,L["Состав заявки изменился"] end
    if GetNumGroupMembers then
        local capacity=IsInRaid and IsInRaid() and 40 or 5
        local invited=C_LFGList.GetNumInvitedApplicantMembers and C_LFGList.GetNumInvitedApplicantMembers() or 0
        if math.max(1,GetNumGroupMembers())+invited+info.numMembers>capacity then return nil,L["В группе недостаточно свободных мест"] end
    end
    return true
end

function MPL.InviteFromProfile(context)
    local valid,err=MPL.ValidateApplicant(context)
    if not valid then return nil,err end
    local ok=pcall(C_LFGList.InviteApplicant,context.applicantID)
    if not ok then return nil,L["WoW не разрешил приглашение"] end
    return true
end

function MPL.InstallBatchButton()
    local viewer=LFGListFrame and LFGListFrame.ApplicationViewer
    if not viewer or MPL.batchButton then return end
    local b=CreateFrame("Button",nil,viewer,"UIPanelButtonTemplate")
    b:SetSize(260,24)
    b:SetPoint("BOTTOMLEFT",viewer,"TOPLEFT",8,4)
    b:SetScript("OnClick",function()
        if MPL.GroupLogsEnabled() then MPL.ShowBatchDownload() end
    end)
    MPL.batchButton=b
    if MPL.CreateTutorialHelpButton then
        MPL.batchTutorialButton=MPL.CreateTutorialHelpButton(viewer,"applicants")
        MPL.batchTutorialButton:SetSize(24,24)
        MPL.batchTutorialButton:SetPoint("LEFT",b,"RIGHT",4,0)
        MPL.batchTutorialButton:SetText("?")
    end
    local loaded,total,hidden,waiting,retryAt=0,0,0,0,nil
    local function update()
        local players,err=MPL.CollectApplicants()
        local pending
        local details={}
        pending,loaded=MPL.FilterFreshProfiles(players,nil,nil,details)
        waiting=details.waiting or 0; retryAt=details.retryAt
        total=#players
        hidden=0
        for _,player in ipairs(players) do
            local state=MPL.GetProfileState(player.name,player.realm,player.spec)
            if state and state.reason=="hidden" then hidden=hidden+1 end
        end
        b:SetText(L["Загрузить логи всех ("]..loaded.."/"..total..")")
        local visible=MPL.GroupLogsEnabled()
        b:SetShown(visible)
        if MPL.batchTutorialButton then MPL.batchTutorialButton:SetShown(visible and not MPL.GetOption("hideTutorial")) end
        if visible and #pending>0 and not err then b:Enable() else b:Disable() end
        if MPL.RefreshApplicantLogs then MPL.RefreshApplicantLogs() end
        if MPL.UpdateProfileInvite then MPL.UpdateProfileInvite() end
    end
    MPL.UpdateBatchButton=update
    viewer:HookScript("OnShow",update)
    if MPL.InstallApplicantLogColumn then MPL.InstallApplicantLogColumn(viewer) end
    local elapsedTotal=0
    b:SetScript("OnUpdate",function(self,elapsed)
        if not self:IsShown() then return end
        elapsedTotal=elapsedTotal+elapsed
        if elapsedTotal>=(waiting>0 and 1 or 30) then elapsedTotal=0; update() end
    end)
    b:SetScript("OnEnter",function()
        update()
        GameTooltip:SetOwner(b,"ANCHOR_TOP")
        GameTooltip:ClearLines()
        GameTooltip:AddLine(L["Логи текущих кандидатов"])
        GameTooltip:AddLine(L["Актуальные данные: "]..loaded..L[" из "]..total,1,1,1)
        GameTooltip:AddLine(L["Нет актуальных данных: "]..(total-loaded-hidden),0.7,0.7,0.7)
        if waiting>0 then
            GameTooltip:AddLine(L["Ожидают повторной загрузки: "]..waiting,1,0.7,0.2)
            GameTooltip:AddLine(MPL.RetryDelayText(retryAt),1,0.7,0.2,true)
        end
        if hidden>0 then GameTooltip:AddLine(L["Скрытые логи: "]..hidden,0.7,0.7,0.7) end
        GameTooltip:AddLine(L["Срок актуальности логов"]..": "..string.format(L["%d ч."],MPL.GetOption("freshHours")),0.7,0.7,0.7)
        GameTooltip:AddLine(L["Загружаются только отсутствующие или устаревшие логи."],0.7,0.7,0.7,true)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave",function() GameTooltip:Hide() end)
    b:SetMotionScriptsWhileDisabled(true)
    update()
end

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED"); events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("LFG_LIST_APPLICANT_LIST_UPDATED"); events:RegisterEvent("LFG_LIST_APPLICANT_UPDATED")
events:RegisterEvent("LFG_LIST_SEARCH_RESULT_UPDATED")
events:RegisterEvent("PLAYER_REGEN_ENABLED"); events:RegisterEvent("PLAYER_REGEN_DISABLED")
events:RegisterEvent("PARTY_LEADER_CHANGED"); events:RegisterEvent("GROUP_ROSTER_UPDATE")
events:RegisterEvent("LFG_LIST_ACTIVE_ENTRY_UPDATE")
events:RegisterEvent("PLAYER_SPECIALIZATION_CHANGED"); events:RegisterEvent("INSPECT_READY")
events:SetScript("OnEvent",function(_,event,loaded)
    if event=="PLAYER_REGEN_ENABLED" and MPL.TryPendingTutorial then MPL.TryPendingTutorial() end
    if event=="PLAYER_REGEN_ENABLED" and MPL.TryCompanionUpdateNotice then MPL.TryCompanionUpdateNotice() end
    if (event=="GROUP_ROSTER_UPDATE" or event=="PLAYER_REGEN_ENABLED") and not InCombatLockdown() then
        local panel=MPL.panel
        if panel and panel:IsShown() and panel.partyTracked and not (IsInRaid and IsInRaid()) then
            local players=MPL.CollectParty()
            if #players>0 then
                local present=false
                for _,p in ipairs(players) do
                    if MPL.Key(p.name,p.realm)==MPL.Key(panel.name,panel.realm) then present=true; break end
                end
                if not present then
                    for _,p in ipairs(panel.groupPlayers or {}) do
                        if MPL.Key(p.name,p.realm)==MPL.Key(panel.name,panel.realm) then players[#players+1]=p; break end
                    end
                end
                panel.groupPlayers=players; MPL.RenderPlayerTabs(panel)
            end
        end
    end
    if event=="PLAYER_REGEN_ENABLED" and MPL.searchGroupWindow and MPL.UpdateSearchGroupRoster then
        MPL.UpdateSearchGroupRoster(MPL.searchGroupWindow.resultID)
    end
    if event=="LFG_LIST_SEARCH_RESULT_UPDATED" and not InCombatLockdown() then
        local handled=MPL.UpdateSearchGroupRoster and MPL.UpdateSearchGroupRoster(loaded)
        local f=MPL.panel
        if not handled and f and f:IsShown() then
            local info=C_LFGList.GetSearchResultInfo(loaded)
            local name,realm
            if info then name,realm=MPL.Identity(info.leaderName) end
            if name and realm and MPL.Key(name,realm)==MPL.Key(f.name,f.realm) then
                recordSearchLeader(loaded,info)
                local metric=f.viewMetric
                MPL.ShowProfile(f.name,f.realm,f.applicant,true,true)
                f.viewMetric=metric; MPL.RenderProfileStats(f)
            end
        end
    end
    if (event=="PLAYER_SPECIALIZATION_CHANGED" or event=="INSPECT_READY")
        and MPL.panel and MPL.panel:IsShown() and not InCombatLockdown() then
        local f=MPL.panel
        local sent,metric=f.inviteSent,f.viewMetric
        MPL.ShowProfile(f.name,f.realm,f.applicant,true)
        f.viewMetric=metric; MPL.RenderProfileStats(f)
        if sent then f.inviteSent=true; MPL.UpdateProfileInvite() end
    end
    if event == "ADDON_LOADED" and loaded == addonName then
        MPlusLogsDB = MPlusLogsDB or {}
        MPlusLogsDB.profiles = MPlusLogsDB.profiles or {}
        if MPL.InitAppearance then MPL.InitAppearance() end
        MPL.LoadBundle()
    end
    if event == "PLAYER_LOGIN" then
        if MPL.RegisterSettings then MPL.RegisterSettings() end
        GameTooltip:HookScript("OnTooltipCleared",function(self) self.mplKey = nil end)
        GameTooltip:HookScript("OnHide",function(self) self.mplKey = nil end)
        if TooltipDataProcessor and Enum and Enum.TooltipDataType then
            TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Unit,function(tooltip)
                if tooltip ~= GameTooltip or InCombatLockdown() then return end
                local _, unit = tooltip:GetUnit()
                if MPL.SafeString(unit) and UnitIsPlayer(unit) then
                    local name,realm = UnitFullName(unit)
                    name,realm=MPL.Identity(name,realm)
                    if not name then return end
                    local role=UnitGroupRolesAssigned and UnitGroupRolesAssigned(unit)
                    if MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] then
                        MPL.roles=MPL.roles or {}; MPL.roles[MPL.Key(name,realm)]=role
                    end
                    MPL.AddTooltip(tooltip,name,realm)
                end
            end)
        end
    end
    hookLFG()
    MPL.InstallBatchButton()
    if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
end)

SLASH_MPLUSLOGS1 = "/mpl"
SLASH_MPLUSLOGS2 = "/mpluslogs"
SlashCmdList.MPLUSLOGS = function(text)
    text = strtrim(text or "")
    if text == "appearance" then MPL.OpenAppearanceSettings()
    elseif text == "appearance reset" then
        if MPL.ResetAppearanceForCharacter then MPL.ResetAppearanceForCharacter()
        elseif MPL.ResetAppearance then MPL.ResetAppearance() end
    elseif text == "settings" then MPL.OpenSettings()
    elseif text == "tutorial" then MPL.ShowTutorial()
    elseif text == "testintro" then MPL.ShowCompanionIntroPreview()
    elseif text == "testupdate" then
        MPL.ShowCompanionUpdates({installed="1.0.23",recommended=MPL.recommendedCompanionVersion})
    elseif text == "import" then MPL.ShowImport()
    elseif text == "applicants" then MPL.ShowBatchDownload()
    elseif text == "testimport" then MPL.ShowImportTest()
    elseif text == "results" then MPL.OpenBatchResults()
    elseif text == "requests" then MPL.ShowRequests()
    elseif text == "demo" then MPL.ShowProfile("Киндрих","Гордунни")
    elseif text == "tooltip" then
        MPL.SetOption("tooltips",not MPL.GetOption("tooltips"))
        print(L["MPlusLogs: тултипы "] .. (MPlusLogsDB.tooltips and L["включены"] or L["выключены"]))
    elseif text ~= "" then MPL.ShowProfile(text)
    elseif UnitExists("party1") and not (IsInRaid and IsInRaid()) then MPL.ShowGroupProfiles(MPL.CollectParty(),nil,true)
    elseif UnitExists("target") and UnitIsPlayer("target") then
        local name,realm = UnitFullName("target"); MPL.ShowProfile(name,realm)
    else MPL.ShowProfile(UnitFullName("player")) end
end
