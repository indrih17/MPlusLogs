local addonName, MPL = ...
local L = MPL.L

function MPL.AddTooltip(tooltip, fullName, realm)
    if InCombatLockdown() or not MPlusLogsDB or not MPL.GetOption("tooltips") then return end
    local profile, name, server = MPL.GetProfile(fullName,realm)
    if not name then return end
    local key = MPL.Key(name,server)
    MPL.Remember(name,server)
    if tooltip.mplKey == key then return end
    tooltip.mplKey = key
    tooltip:AddLine(" ")
    tooltip:AddLine("MPlusLogs / M+ S2",0.4,0.8,1)
    if profile then
        local stale,lastDate=MPL.IsProfileStale(profile)
        local primary=MPL.PrimaryMetric(profile,name,server)
        local secondary=primary=="hps" and "dps" or "hps"
        local _,_,best,median=MPL.MetricValues(profile,nil,primary)
        local _,_,otherBest,otherMedian=MPL.MetricValues(profile,nil,secondary)
        best,median=MPL.OrderPercentiles(best,median)
        otherBest,otherMedian=MPL.OrderPercentiles(otherBest,otherMedian)
        tooltip:AddLine(MPL.T(profile.spec) .. L[" / по уровню ключа"],0.8,0.8,0.8)
        tooltip:AddDoubleLine(primary:upper().." "..MPL.PercentileCaption(),MPL.Percent(best,stale).." / "..MPL.Percent(median,stale))
        tooltip:AddDoubleLine(secondary:upper().." "..MPL.PercentileCaption(),MPL.Percent(otherBest,stale).." / "..MPL.Percent(otherMedian,stale))
        tooltip:AddDoubleLine(L["Залогированные прохождения"],tostring(profile.runs or "—"))
        tooltip:AddLine(MPL.T(profile.source).." / "..lastDate,0.65,0.65,0.65,true)
        if stale then tooltip:AddLine(L["Обновите логи персонажа"],0.65,0.65,0.65) end
    else tooltip:AddLine(L["Профиль не загружен"],0.65,0.65,0.65) end
    tooltip:AddLine(L["ПКМ > M+ логи"],0.4,0.8,1)
    tooltip:Show()
end

local function applicant(owner)
    if not owner or not owner.memberIdx then return end
    local parent = owner:GetParent()
    if not parent or not parent.applicantID then return end
    local fullName,_,_,_,_,_,_,_,_,role = C_LFGList.GetApplicantMemberInfo(parent.applicantID,owner.memberIdx)
    if MPL.SafeString(fullName) and MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] then
        local name,realm=MPL.Identity(fullName)
        MPL.roles=MPL.roles or {}; MPL.roles[MPL.Key(name,realm)]=role
    end
    if MPL.SafeString(fullName) then return fullName end
end
local function menu(root, fullName, realm,context)
    local name, server = MPL.Identity(fullName,realm)
    if not name then return end
    root:CreateDivider()
    root:CreateButton(L["M+ логи (MPlusLogs)"],function() MPL.ShowProfile(name,server,context) end)
    root:CreateButton(L["Загрузить M+ логи"],function()
        MPL.ShowDownload(name,server,MPL.GetProfile(name,server),context)
    end)
    root:CreateButton(L["Ссылка на логи M+"],function()
        MPL.CopyURL(name,server,MPL.GetProfile(name,server))
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
            if InCombatLockdown() then return end
            local name = applicant(owner)
            if name then MPL.AddTooltip(GameTooltip,name) end
        end)
        hooked.applicant = true
    end
    if not hooked.search and type(LFGListSearchEntry_OnEnter) == "function" then
        hooksecurefunc("LFGListSearchEntry_OnEnter",function(owner)
            if InCombatLockdown() or not owner.resultID then return end
            local info = C_LFGList.GetSearchResultInfo(owner.resultID)
            if info and MPL.SafeString(info.leaderName) then MPL.AddTooltip(GameTooltip,info.leaderName) end
        end)
        hooked.search = true
    end
    if not hooked.menu and Menu and Menu.ModifyMenu then
        Menu.ModifyMenu("MENU_LFG_FRAME_MEMBER_APPLY",function(owner,root)
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
            if info then menu(root,info.leaderName) end
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
                local fullName,_,_,_,_,_,_,_,_,role=C_LFGList.GetApplicantMemberInfo(id,member)
                if MPL.SafeString(fullName) then
                    local name,realm=MPL.Identity(fullName)
                    local key=MPL.Key(name,realm)
                    roster[key]=true
                    if not seen[key] then
                        local knownRole=MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] and role or nil
                        players[#players+1]={name=name,realm=realm,role=knownRole,applicantID=id,memberIndex=member,groupSize=info.numMembers,roster=roster}
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
    b:SetScript("OnClick",function() MPL.ShowBatchDownload() end)
    MPL.batchButton=b
    local loaded,total=0,0
    local function update()
        local players,err=MPL.CollectApplicants()
        local pending
        pending,loaded=MPL.FilterFreshProfiles(players)
        total=#players
        b:SetText(L["Загрузить логи всех ("]..loaded.."/"..total..")")
        if #pending>0 and not err then b:Enable() else b:Disable() end
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
        if elapsedTotal>=30 then elapsedTotal=0; update() end
    end)
    b:SetScript("OnEnter",function()
        update()
        GameTooltip:SetOwner(b,"ANCHOR_TOP")
        GameTooltip:ClearLines()
        GameTooltip:AddLine(L["Логи текущих кандидатов"])
        GameTooltip:AddLine(L["Актуальные данные: "]..loaded..L[" из "]..total,1,1,1)
        GameTooltip:AddLine(L["Нет актуальных данных: "]..(total-loaded),0.7,0.7,0.7)
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
events:RegisterEvent("PLAYER_REGEN_ENABLED"); events:RegisterEvent("PLAYER_REGEN_DISABLED")
events:RegisterEvent("PARTY_LEADER_CHANGED"); events:RegisterEvent("GROUP_ROSTER_UPDATE")
events:RegisterEvent("LFG_LIST_ACTIVE_ENTRY_UPDATE")
events:SetScript("OnEvent",function(_,event,loaded)
    if event == "ADDON_LOADED" and loaded == addonName then
        MPlusLogsDB = MPlusLogsDB or {}
        MPlusLogsDB.profiles = MPlusLogsDB.profiles or {}
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
                    local role=UnitGroupRolesAssigned and UnitGroupRolesAssigned(unit)
                    if MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] then
                        MPL.roles=MPL.roles or {}; MPL.roles[MPL.Key(name,realm or GetNormalizedRealmName())]=role
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
    if text == "settings" then MPL.OpenSettings()
    elseif text == "import" then MPL.ShowImport()
    elseif text == "applicants" then MPL.ShowBatchDownload()
    elseif text == "results" then MPL.OpenBatchResults()
    elseif text == "probe" then MPL.ShowProbe()
    elseif text == "requests" then MPL.ShowRequests()
    elseif text == "demo" then MPL.ShowProfile("Киндрих","Гордунни")
    elseif text == "tooltip" then
        MPL.SetOption("tooltips",not MPL.GetOption("tooltips"))
        print(L["MPlusLogs: тултипы "] .. (MPlusLogsDB.tooltips and L["включены"] or L["выключены"]))
    elseif text ~= "" then MPL.ShowProfile(text)
    elseif UnitExists("target") and UnitIsPlayer("target") then
        local name,realm = UnitFullName("target"); MPL.ShowProfile(name,realm)
    else MPL.ShowProfile(UnitFullName("player")) end
end
