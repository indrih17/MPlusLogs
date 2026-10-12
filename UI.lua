local _, MPL = ...
local L = MPL.L
local function label(parent, x, y, width, text, template)
    local f = parent:CreateFontString(nil, "OVERLAY", template or "GameFontHighlightSmall")
    f:SetPoint("TOPLEFT", x, y); f:SetWidth(width); f:SetJustifyH("LEFT"); f:SetText(text or "")
    return f
end
local function button(parent, text, x, y, width, callback)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetSize(width, 24); b:SetPoint("BOTTOMLEFT", x, y); b:SetText(text); b:SetScript("OnClick", callback)
    return b
end
local function window(name, title, width, height, opaque)
    local f = CreateFrame("Frame", name, UIParent, "BackdropTemplate")
    f:SetSize(width, height); f:SetPoint("CENTER"); f:SetFrameStrata("DIALOG")
    f:SetBackdrop({bgFile=opaque and "Interface/Buttons/WHITE8X8" or "Interface/Tooltips/UI-Tooltip-Background", edgeFile="Interface/Tooltips/UI-Tooltip-Border", tile=true, tileSize=16, edgeSize=16, insets={left=4,right=4,top=4,bottom=4}})
    f:SetBackdropColor(0.035,0.035,0.05,opaque and 1 or 0.98)
    if opaque then f:SetFrameLevel(100) end
    f:EnableMouse(true); f:SetMovable(true); f:SetClampedToScreen(true)
    f:RegisterForDrag("LeftButton"); f:SetScript("OnDragStart", f.StartMoving); f:SetScript("OnDragStop", f.StopMovingOrSizing)
    label(f, 20, -16, width-60, title, "GameFontNormalLarge")
    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -2, -2)
    UISpecialFrames[#UISpecialFrames+1] = name
    f:Hide()
    return f
end

function MPL.UpdatePanelScroll(f)
    local overflow=f.content:GetHeight()>math.max(1,f.scroll:GetHeight())+1
    if f.scroll.ScrollBar then f.scroll.ScrollBar:SetShown(overflow) end
    f.scroll:EnableMouseWheel(overflow)
    if not overflow then f.scroll:SetVerticalScroll(0) end
end

local function buildPanel()
    local f = window("MPlusLogsWindow", "MPlusLogs — Warcraft Logs", 940, 540)
    f.character = label(f,20,-48,900,"","GameFontHighlightLarge")
    f.context = label(f,20,-77,900)
    f.summary = label(f,20,-104,900,"","GameFontNormal")
    f.source = label(f,20,-130,900)
    f.note = label(f,20,-155,900)
    local headings = {L["Данж"], L["Прохождения"], L["Ключ"], L["Лучший DPS"], L["Best %"], L["Median %"], L["Ключ"], L["Лучший HPS"], L["Best %"], L["Median %"]}
    f.columns = {0,164,254,300,402,470,554,600,702,770}
    f.widths = {160,86,42,98,64,70,42,98,64,100}
    f.headings={}
    for i, text in ipairs(headings) do
        f.headings[i]=label(f,20+f.columns[i],-208,f.widths[i],text,"GameFontNormalSmall")
    end
    local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT",20,-234); scroll:SetPoint("BOTTOMRIGHT",-40,85)
    local content = CreateFrame("Frame", nil, scroll); content:SetSize(880,1); scroll:SetScrollChild(content)
    f.content, f.scroll, f.rows = content, scroll, {}
    scroll:HookScript("OnScrollRangeChanged",function() MPL.UpdatePanelScroll(f) end)
    scroll:HookScript("OnSizeChanged",function() MPL.UpdatePanelScroll(f) end)
    -- Keep a reference to the metric heading for healer profiles.
    f.metricHeading=f.headings[4]
    f.primaryGroup=label(f,274,-184,285,L["DPS / по уровню ключа"],"GameFontNormal")
    f.secondaryGroup=label(f,574,-184,300,L["HPS / по уровню ключа"],"GameFontNormal")
    f.headings[#f.headings+1]=f.primaryGroup; f.headings[#f.headings+1]=f.secondaryGroup
    f.footer = label(f,20,-464,900)
    button(f,L["Ссылка WCL"],20,20,120,function() MPL.CopyURL(f.name,f.realm,f.profile) end)
    f.loadButton=button(f,L["Обновить M+ логи"],730,53,170,function() MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant) end)
    f.emptyMessage=label(f,80,-218,660,L["Данные этого персонажа ещё не загружены."],"GameFontHighlightLarge")
    f.emptyMessage:SetJustifyH("CENTER")
    f.lookup = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
    f.lookup:SetSize(530,24); f.lookup:SetPoint("BOTTOMLEFT",150,20); f.lookup:SetAutoFocus(false)
    f.lookup:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
    local function lookup() MPL.ShowProfile(strtrim(f.lookup:GetText())); f.lookup:ClearFocus() end
    f.lookup:SetScript("OnEnterPressed",lookup)
    f.lookupButton=button(f,L["Показать профиль"],710,20,190,lookup)
    f.lookupButton:SetScript("OnEnter",function(self)
        GameTooltip:SetOwner(self,"ANCHOR_TOP")
        GameTooltip:AddLine(L["Профиль персонажа"],1,0.82,0)
        GameTooltip:AddLine(L["Введите Имя-Сервер в поле слева.\nЕсли профиль уже открыт, таблица останется прежней."],1,1,1,true)
        GameTooltip:Show()
    end)
    f.lookupButton:SetScript("OnLeave",function() GameTooltip:Hide() end)
    f.applicant=false; f.inviteSent=false
    f.inviteInfo=label(f,150,-500,530)
    f.inviteButton=button(f,L["Пригласить"],710,20,190,function()
        local ok,err=MPL.InviteFromProfile(f.applicant)
        if ok then f.inviteSent=true; MPL.UpdateProfileInvite()
        else f.inviteInfo:SetText(err); f.inviteButton:Disable() end
    end)
    return f
end

function MPL.UpdateProfileInvite()
    local f=MPL.panel
    if not f then return end
    local fromApplicant=type(f.applicant)=="table"
    f.lookup:SetShown(not fromApplicant); f.lookupButton:SetShown(not fromApplicant)
    f.inviteButton:SetShown(fromApplicant); f.inviteInfo:SetShown(fromApplicant)
    if not fromApplicant then return end
    local valid,err=MPL.ValidateApplicant(f.applicant)
    local size=f.applicant.groupSize or 1
    f.inviteButton:SetText(f.inviteSent and L["Отправлено"] or (size>1 and L["Пригласить группу ("]..size..")" or L["Пригласить"]))
    f.inviteButton:SetEnabled(valid and not f.inviteSent or false)
    f.inviteInfo:SetText(f.inviteSent and L["Запрос приглашения отправлен"] or (err or (size>1 and L["Пригласится вся заявка: "]..size..L[" чел."] or L["Приглашение выбранного кандидата"])))
end

function MPL.ShowProfile(fullName, realm,context)
    if not MPL.SafeString(fullName) then fullName, realm = UnitFullName("player") end
    local profile, name, server = MPL.GetProfile(fullName, realm)
    if not name then return end
    MPL.Remember(name,server)
    MPL.panel = MPL.panel or buildPanel()
    local f = MPL.panel
    f.applicant=type(context)=="table" and MPL.Key(context.name,context.realm)==MPL.Key(name,server) and context or false
    f.inviteSent=false
    if MPL.staleWindow then MPL.staleWindow:Hide() end
    local stale,lastDate=false,nil
    if profile then stale,lastDate=MPL.IsProfileStale(profile) end
    local primary=profile and MPL.PrimaryMetric(profile,name,server) or "dps"
    local secondary=primary=="hps" and "dps" or "hps"
    f.name, f.realm, f.profile = name, server, profile
    f.character:SetText(name .. " — " .. server)
    f.lookup:SetText(name .. "-" .. server)
    f.scroll:SetVerticalScroll(0)
    for _, row in ipairs(f.rows) do row:Hide() end
    f.metricHeading:SetText(L["Лучший "]..primary:upper())
    f.headings[8]:SetText(L["Лучший "]..secondary:upper())
    f.primaryGroup:SetText(primary:upper()..L[" / по уровню ключа"])
    f.secondaryGroup:SetText(secondary:upper()..L[" / по уровню ключа"])
    f.loadButton:ClearAllPoints()
    for _,heading in ipairs(f.headings) do if profile then heading:Show() else heading:Hide() end end
    if profile then
        f.scroll:Show(); f.metricHeading:Show(); f.emptyMessage:Hide()
        f.loadButton:SetPoint("BOTTOMLEFT",730,53); f.loadButton:SetSize(170,24)
        f.loadButton:SetText(L["Обновить M+ логи"])
    else
        f.scroll:Hide(); f.metricHeading:Hide(); f.emptyMessage:Show()
        f.loadButton:SetPoint("CENTER",0,-15); f.loadButton:SetSize(260,36)
        f.loadButton:SetText(L["Загрузить M+ логи"])
    end
    if profile then
        f.context:SetText(profile.season .. "  /  " .. MPL.T(profile.spec) .. "  /  " .. primary:upper() .. L[" и "]..secondary:upper()..L[" по уровню ключа"])
        local _,_,best,median=MPL.MetricValues(profile,nil,primary)
        local _,_,otherBest,otherMedian=MPL.MetricValues(profile,nil,secondary)
        f.summary:SetText(L["WCL score: "] .. (profile.score and string.format("%.0f",profile.score) or "—") .. "    "..primary:upper()..L[" Best / Median: "] .. MPL.Percent(best,stale) .. " / " .. MPL.Percent(median,stale) .. "    "..secondary:upper()..L[" Best / Median: "] .. MPL.Percent(otherBest,stale).." / "..MPL.Percent(otherMedian,stale)..L["    Логи: "] .. (profile.runs or "—"))
        f.source:SetText(MPL.T(profile.source) .. L["  /  Последняя загрузка: "] .. lastDate .. (stale and L[" / Обновите логи"] or ""))
        f.note:SetText(L["Процентиль урона/исцеления не оценивает выживание, прерывания и механику."])
        for index, dungeon in ipairs(profile.dungeons) do
            local row = f.rows[index]
            if not row then
                row = CreateFrame("Frame", nil, f.content); row:SetSize(880,24); row:SetPoint("TOPLEFT",0,-(index-1)*26)
                row.cells = {}
                for i = 1,10 do row.cells[i] = label(row,f.columns[i],-4,f.widths[i]) end
                f.rows[index] = row
            end
            local level,amount,best,median=MPL.MetricValues(profile,dungeon,primary)
            local otherLevel,otherAmount,otherBest,otherMedian=MPL.MetricValues(profile,dungeon,secondary)
            local values = {dungeon.name,dungeon.runs or "—",level and "+"..level or "—",amount and string.format("%.2fK",amount/1000) or "—",MPL.Percent(best,stale)..(dungeon.flagged and profile.metric==primary and "*" or ""),MPL.Percent(median,stale),otherLevel and "+"..otherLevel or "—",otherAmount and string.format("%.2fK",otherAmount/1000) or "—",MPL.Percent(otherBest,stale),MPL.Percent(otherMedian,stale)}
            for i, value in ipairs(values) do
                row.cells[i]:SetText(value)
                row.cells[i]:SetTextColor(stale and 0.53 or 1,stale and 0.53 or 1,stale and 0.53 or 1)
            end
            row:Show()
        end
        f.content:SetHeight(math.max(1,#profile.dungeons*26))
        f.footer:SetText(profile.characterID == 81818678 and profile.source == "Снимок со скриншота пользователя" and L["* Пометка WCL сохранена со скриншота. Общие 162 лога и строки показаны как в источнике."] or L["Логи: только прохождения, доступные WCL; отсутствие данных не означает плохую игру."])
    else
        f.context:SetText("Midnight M+ Season 2")
        f.summary:SetText("")
        f.source:SetText("")
        f.note:SetText("")
        f.footer:SetText(L["Нажмите «Загрузить M+ логи». Локальный помощник должен быть запущен."])
        f.content:SetHeight(1)
    end
    for _,text in ipairs({f.character,f.context,f.source,f.note,f.footer}) do
        text:SetTextColor(stale and 0.53 or 1,stale and 0.53 or 1,stale and 0.53 or 1)
    end
    for _,text in ipairs({f.summary,f.metricHeading,unpack(f.headings)}) do
        text:SetTextColor(stale and 0.53 or 1,stale and 0.53 or 0.82,stale and 0.53 or 0)
    end
    f:Show()
    MPL.UpdateProfileInvite()
    MPL.UpdatePanelScroll(f)
    if stale then MPL.ShowStaleNotice(name,server,profile,lastDate) end
end

function MPL.ShowStaleNotice(name,realm,profile,lastDate)
    MPL.staleWarnings=MPL.staleWarnings or {}
    local key=MPL.Key(name,realm)..":"..profile.updated
    if MPL.staleWarnings[key] then return end
    MPL.staleWarnings[key]=true
    if not MPL.staleWindow then
        local f=window("MPlusLogsStaleWindow",L["Обновите логи персонажа"],480,205,true)
        f.message=label(f,24,-57,432,"","GameFontHighlight")
        f.message:SetHeight(88); f.message:SetJustifyV("TOP")
        button(f,L["Обновить логи"],24,24,205,function()
            f:Hide(); MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant)
        end)
        button(f,L["Позже"],251,24,205,function() f:Hide() end)
        MPL.staleWindow=f
    end
    local f=MPL.staleWindow
    f.name=name; f.realm=realm; f.profile=profile
    f.applicant=MPL.panel and MPL.panel.applicant or false
    f.message:SetText(name.." — "..realm..L["\nПоследняя дата загрузки - "]..lastDate..L[".\nДанные старше 24 часов или дата неизвестна."])
    f:Show()
end

function MPL.ShowDownload(fullName, realm, profile,context,batch)
    local name, server = MPL.Identity(fullName,realm)
    if not name then return end
    if not MPL.downloadWindow then
        local f=window("MPlusLogsDownloadWindow",L["M+ логи / Warcraft Logs"],520,330,true)
        f.programmatic=false; f.revision=0; f.phase="idle"; f.request=""
        f.character=label(f,24,-53,472,"","GameFontHighlightLarge")
        f.steps=label(f,24,-84,472,L["1. Отправка запроса    /    2. Получение логов"],"GameFontNormal")
        local divider=f:CreateTexture(nil,"ARTWORK")
        divider:SetColorTexture(0.55,0.48,0.28,0.35)
        divider:SetPoint("TOPLEFT",24,-108); divider:SetSize(472,1)
        f.status=label(f,24,-126,472,"","GameFontHighlight")
        f.status:SetHeight(48); f.status:SetJustifyV("TOP")
        label(f,24,-180,472,L["Запрос: Ctrl+A выделить, Ctrl+C скопировать"],"GameFontDisableSmall")
        local inputClip=CreateFrame("Frame",nil,f,"BackdropTemplate")
        inputClip:SetPoint("TOPLEFT",24,-198); inputClip:SetSize(472,64)
        inputClip:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Tooltips/UI-Tooltip-Border",edgeSize=8,insets={left=2,right=2,top=2,bottom=2}})
        inputClip:SetBackdropColor(0.08,0.08,0.09,1)
        inputClip:SetClipsChildren(true); inputClip:EnableMouse(true)
        f.edit=CreateFrame("EditBox",nil,inputClip)
        local edit=f.edit
        edit:SetPoint("TOPLEFT",inputClip,"TOPLEFT",6,-5); edit:SetSize(460,54)
        edit:SetMultiLine(true); edit:SetFontObject(GameFontHighlightSmall)
        edit:SetAutoFocus(false); edit:SetMaxLetters(500000)
        edit:SetTextColor(0.48,0.48,0.52,1); edit:EnableMouse(true)
        local function focusInput()
            edit:SetFocus(); edit:HighlightText()
            local revision=f.revision
            -- Button release can change focus after OnClick has returned.
            C_Timer.After(0,function()
                if f:IsShown() and revision==f.revision and (f.phase=="copy" or f.phase=="waiting") then
                    edit:SetFocus(); edit:HighlightText()
                    if not edit:HasFocus() then
                        f.status:SetText(L["Не удалось активировать ввод. Щёлкните в поле запроса, затем Ctrl+C или Ctrl+V."])
                    end
                end
            end)
        end
        f.focusInput=focusInput
        inputClip:SetScript("OnMouseDown",focusInput)
        local function setText(text)
            f.programmatic=true; edit:SetText(text); f.programmatic=false
            focusInput()
        end
        local function checkStatus()
            if f.phase=="idle" then return end
            f.phase="waiting"
            f.steps:SetText(L["|cff8888881. Отправка запроса|r    /    |cffffd1002. Получение логов|r"])
            setText(f.request)
            f.status:SetText(L["Теперь нажмите |cffffd100Ctrl+V|r.\nБез вставки WoW не может получить ответ помощника."])
        end
        f.begin=function()
            local spec=f.profile and f.profile.spec~="All specs" and f.profile.spec or ""
            local id,request,skipped,total
            if f.batch then
                local players,err=MPL.CollectApplicants()
                if err then f.status:SetText(err); return end
                total=#players
                players,skipped=MPL.FilterFreshProfiles(players)
                if total>0 and #players==0 then
                    f.character:SetText(L["Нужно загрузить: "].."0 / "..total)
                    f.status:SetText(L["Все кандидаты уже имеют актуальные логи."])
                    if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
                    return
                end
                id,request=MPL.SendBatchRequest(players)
                f.character:SetText(L["Нужно загрузить: "]..#players.." / "..total)
            else id,request=MPL.SendRequest(f.name,f.realm,f.profile and f.profile.metric or "dps",spec,f.applicant) end
            if not id then f.status:SetText(request); return end
            f.phase="copy"; f.request=request
            f.steps:SetText(L["|cffffd1001. Отправка запроса|r    /    |cff8888882. Получение логов|r"])
            -- The paste step must remain accessible even if WoW does not
            -- deliver a Ctrl+C key-up event (or Ctrl is released first).
            f.refresh:Enable()
            f.status:SetText(L["Нажмите |cffffd100Ctrl+C|r, чтобы начать загрузку.\nПомощник получит запрос и подготовит логи."]
                ..(skipped and skipped>0 and ("\n"..L["Актуальные данные: "]..skipped..L[" из "]..total) or ""))
            setText(request)
        end
        f.refresh=button(f,L["Получить ответ (Ctrl+V)"],144,24,232,checkStatus)
        f.refresh:SetHeight(32)
        edit:SetScript("OnEscapePressed",function() f:Hide() end)
        f:SetScript("OnHide",function() edit:ClearFocus(); f.revision=f.revision+1 end)
        local function copied(key)
            if key=="C" and f.phase=="copy" then
                f.phase="waiting"; f.refresh:Enable()
                f.steps:SetText(L["|cff8888881. Отправка запроса|r    /    |cffffd1002. Получение логов|r"])
                f.status:SetText(L["Подождите немного и нажмите |cffffd100Ctrl+V|r.\nМожно повторять проверку до получения ответа."])
                edit:HighlightText()
            end
        end
        edit:SetScript("OnKeyDown",function(_,key)
            if IsControlKeyDown() then copied(key) end
        end)
        edit:SetScript("OnKeyUp",function(_,key) copied(key) end)
        edit:SetScript("OnTextChanged",function()
            f.revision=f.revision+1
            local revision=f.revision
            if f.programmatic or f.phase=="idle" then return end
            C_Timer.After(0.15,function()
                if revision~=f.revision or f.programmatic or not f:IsShown() then return end
                local text=edit:GetText()
                if text==f.request then return end
                local count,err=MPL.ReceiveReply(text,true)
                if count then
                    f.phase="done"; f.status:SetText(L["Логи получены."])
                    f.programmatic=true; edit:SetText(""); f.programmatic=false
                    f:Hide()
                else
                    f.status:SetText(err or L["Ответ ещё не получен. Нажмите Ctrl+V позже."])
                    f.refresh:Enable()
                    setText(f.request)
                end
            end)
        end)
        MPL.downloadWindow=f
    end
    local f=MPL.downloadWindow
    MPL.pendingReply=nil
    f.revision=f.revision+1
    f.name=name; f.realm=server; f.profile=profile or false; f.phase="idle"; f.request=""
    f.batch=batch or false
    f.applicant=context or false
    f.character:SetText(name.." — "..server)
    f.steps:SetText(L["|cff8888881. Отправка запроса    /    2. Получение логов|r"])
    f.status:SetText(L["Подготовка запроса…"])
    f.refresh:Disable()
    f.programmatic=true; f.edit:SetText(""); f.programmatic=false; f.edit:ClearFocus()
    if MPL.importWindow then MPL.importWindow:Hide() end
    f:Show()
    f.begin()
end

function MPL.ShowBatchDownload()
    MPL.ShowDownload(L["Кандидаты"],GetNormalizedRealmName(),nil,nil,true)
end

function MPL.ShowBatchResults(players,profiles,failures,count,open)
    local errorCount=0
    for _,player in ipairs(players) do if failures[MPL.Key(player.name,player.realm)] then errorCount=errorCount+1 end end
    if not open then
        MPL.lastBatchResult={players=players,profiles=profiles,failures=failures,count=count}
        if MPL.batchResultsWindow then MPL.batchResultsWindow:Hide() end
        if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
        return
    end
    if not MPL.batchResultsWindow then
        local f=window("MPlusLogsBatchResults",L["Логи кандидатов"],660,420,true)
        f.summary=label(f,24,-52,610,"","GameFontHighlight")
        f.scroll=CreateFrame("ScrollFrame",nil,f,"UIPanelScrollFrameTemplate")
        f.scroll:SetPoint("TOPLEFT",24,-94); f.scroll:SetPoint("BOTTOMRIGHT",-42,58)
        f.content=CreateFrame("Frame",nil,f.scroll); f.content:SetSize(590,1)
        f.scroll:SetScrollChild(f.content); f.rows={}
        f.scroll:HookScript("OnScrollRangeChanged",function() MPL.UpdatePanelScroll(f) end)
        button(f,L["Закрыть"],24,20,140,function() f:Hide() end)
        MPL.batchResultsWindow=f
    end
    local f=MPL.batchResultsWindow
    for _,row in ipairs(f.rows) do row:Hide() end
    f.summary:SetText(L["Загружено: "]..count..L[" из "]..#players..L[". Ошибки обновления: "]..errorCount)
    for index,player in ipairs(players) do
        local key=MPL.Key(player.name,player.realm)
        local row=f.rows[index]
        if not row then
            row=CreateFrame("Frame",nil,f.content); row:SetSize(590,62); row:SetPoint("TOPLEFT",0,-(index-1)*64)
            row.name=label(row,0,-2,425,"","GameFontHighlight")
            row.status=label(row,0,-22,425); row.status:SetHeight(38); row.status:SetJustifyV("TOP")
            row.open=button(row,L["Показать"],450,20,135,function() MPL.ShowProfile(row.player.name,row.player.realm,row.player) end)
            f.rows[index]=row
        end
        row.player=player
        row.name:SetText(player.name.." — "..player.realm)
        local failure=failures[key]
        row.status:SetText(failure and ((profiles[key] and L["Сохранён кеш. "] or L["Не загружено. "])..MPL.T(failure.error)) or L["Логи загружены: доступны DPS и HPS"])
        if MPL.GetProfile(player.name,player.realm) then row.open:Enable() else row.open:Disable() end
        row:Show()
    end
    f.content:SetHeight(math.max(1,#players*64)); f:Show(); MPL.UpdatePanelScroll(f)
end

function MPL.OpenBatchResults()
    local result=MPL.lastBatchResult
    if not result then print(L["MPlusLogs: групповой загрузки ещё не было"]); return end
    MPL.ShowBatchResults(result.players,result.profiles,result.failures,result.count,true)
end

-- Extra space belongs to the applicant viewer, rather than compressed columns.
local logColumns={120,62,44,54,56}
local applicantExtraWidth=90
function MPL.InstallApplicantLogColumn(viewer)
    if MPL.logColumn then return end
    local headers={viewer.NameColumnHeader,viewer.RoleColumnHeader,viewer.ItemLevelColumnHeader,viewer.RatingColumnHeader}
    for _,header in ipairs(headers) do if not header or type(header)=="function" then return end end
    if #headers~=4 then return end
    local f=CreateFrame("Button",nil,viewer,"LFGListColumnHeaderTemplate")
    f:SetSize(56,24); f:SetPoint("LEFT",headers[4],"RIGHT",0,0)
    f:SetText(L["Логи"]); f.Label:ClearAllPoints(); f.Label:SetPoint("CENTER")
    f.Label:SetWidth(56); f.Label:SetJustifyH("CENTER")
    f:Enable(); f:SetScript("OnClick",function() end)
    f:EnableMouse(true)
    f:SetScript("OnEnter",function()
        GameTooltip:SetOwner(f,"ANCHOR_TOP"); GameTooltip:ClearLines()
        GameTooltip:AddLine(L["M+ Best % по уровню ключа"])
        GameTooltip:AddLine(L["HPS для хилера, DPS для остальных"],1,1,1)
        GameTooltip:AddLine(L["Серый процент: данные старше 24 часов"],0.7,0.7,0.7)
        GameTooltip:Show()
    end)
    f:SetScript("OnLeave",function() GameTooltip:Hide() end)
    f.headers=headers; f.original={}; f.compact=false; f.viewer=viewer; f.expanded=false
    f.baseWidth=PVEFrame and (PVE_FRAME_BASE_WIDTH or PVEFrame:GetWidth()) or false
    f.panelWidths=setmetatable({},{__mode="k"})
    f.backgroundWidth=viewer.InfoBackground and type(viewer.InfoBackground)~="function" and viewer.InfoBackground:GetWidth() or false
    f.descriptionWidth=viewer.DescriptionFrame and type(viewer.DescriptionFrame)~="function" and viewer.DescriptionFrame:GetWidth() or false
    for i,header in ipairs(headers) do
        f.original[i]={width=header:GetWidth(),text=header.Label:GetText()}
    end
    MPL.logColumn=f
    MPL.applicantLogCells=setmetatable({},{__mode="k"})
    viewer:HookScript("OnHide",function() MPL.RefreshApplicantLogs(true) end)
    if type(LFGListFrame_SetActivePanel)=="function" then
        hooksecurefunc("LFGListFrame_SetActivePanel",function() MPL.RefreshApplicantLogs() end)
    end
    if type(LFGListApplicationViewer_UpdateInfo)=="function" then
        hooksecurefunc("LFGListApplicationViewer_UpdateInfo",function() MPL.RefreshApplicantLogs() end)
    end
    if type(PVEFrame_ShowFrame)=="function" then
        hooksecurefunc("PVEFrame_ShowFrame",function() MPL.RefreshApplicantLogs() end)
    end
end

local function applicantLogLayout(forceInactive)
    local f=MPL.logColumn
    if not f then return false end
    local active=not forceInactive and LFGListFrame and LFGListFrame.activePanel==f.viewer
        and f.viewer:IsVisible() and f.headers[4]:IsShown()
        and (not C_LFGList.HasActiveEntryInfo or C_LFGList.HasActiveEntryInfo())
    if not InCombatLockdown() then
        -- The native LFG stub has a fixed width, even when PVEFrame grows.
        local stub=LFGListFrame and type(LFGListFrame.GetParent)=="function" and LFGListFrame:GetParent()
        if stub and not f.panelWidths[stub] then f.panelWidths[stub]=stub:GetWidth() end
        for panel,width in pairs(f.panelWidths) do
            local target=width+((active and panel==stub) and applicantExtraWidth or 0)
            if math.abs(panel:GetWidth()-target)>0.01 then panel:SetWidth(target) end
        end
        if f.backgroundWidth then f.viewer.InfoBackground:SetWidth(f.backgroundWidth+(active and applicantExtraWidth or 0)) end
        if f.descriptionWidth then f.viewer.DescriptionFrame:SetWidth(f.descriptionWidth+(active and applicantExtraWidth or 0)) end
        if PVEFrame and f.baseWidth then
            local target=active and f.baseWidth+applicantExtraWidth or f.baseWidth
            local current=PVEFrame:GetWidth()
            -- WoW reports scaled widths with fractional rounding. Track our
            -- expansion instead of requiring an exact float equality to undo it.
            local restore=f.expanded and math.abs(current-(f.baseWidth+applicantExtraWidth))<1
            f.expanded=active
            if (active or restore) and math.abs(current-target)>0.01 then
                PVEFrame:SetWidth(target)
                if UpdateUIPanelPositions then UpdateUIPanelPositions(PVEFrame) end
            end
        end
        if active then
            for i,header in ipairs(f.headers) do
                header:SetWidth(logColumns[i])
                header.Label:ClearAllPoints(); header.Label:SetPoint("CENTER")
                header.Label:SetWidth(logColumns[i]); header.Label:SetJustifyH("CENTER")
            end
            f.headers[3].Label:SetText(f.original[3].text)
            f.compact=true
        elseif f.compact then
            for i,header in ipairs(f.headers) do
                header:SetWidth(f.original[i].width); header.Label:SetText(f.original[i].text)
                header.Label:ClearAllPoints(); header.Label:SetPoint("LEFT",8,0)
                header.Label:SetWidth(0); header.Label:SetJustifyH("LEFT")
            end
            f.compact=false
        end
    end
    f:SetShown(active)
    return active
end

function MPL.UpdateApplicantLog(member,appID,index,status)
    if not MPL.logColumn or not member then return end
    local cells=MPL.applicantLogCells
    local cell=cells[member]
    if InCombatLockdown() then if cell then cell:Hide() end; return end
    local active=applicantLogLayout()
    local name,_,_,_,_,_,_,_,_,role=C_LFGList.GetApplicantMemberInfo(appID,index)
    if not cell then
        cell=CreateFrame("Button",nil,member); cell:SetSize(56,20)
        cell:SetPoint("LEFT",member,"LEFT",280,0)
        cell.text=label(cell,0,-4,56,"","GameFontHighlightSmall"); cell.text:SetJustifyH("CENTER")
        cell:SetScript("OnClick",function()
            for _,player in ipairs(MPL.CollectApplicants()) do
                if player.applicantID==cell.appID and player.memberIndex==cell.index
                    and MPL.Key(player.name,player.realm)==cell.key then
                    MPL.ShowProfile(player.name,player.realm,player); return
                end
            end
        end)
        cell:SetScript("OnEnter",function()
            GameTooltip:SetOwner(cell,"ANCHOR_RIGHT"); GameTooltip:ClearLines()
            GameTooltip:AddLine(cell.metric:upper()..L[" Best % по уровню ключа"])
            GameTooltip:AddLine(cell.detail,0.8,0.8,0.8,true)
            GameTooltip:AddLine(L["Нажмите для полной сводки"],1,1,1); GameTooltip:Show()
        end)
        cell:SetScript("OnLeave",function() GameTooltip:Hide() end)
        cells[member]=cell
    end
    cell.appID=appID; cell.index=index; cell.key=false; cell.metric="dps"; cell.detail=L["Логи не загружены"]
    cell.text:SetText("—")
    local row=member:GetParent()
    if row then row:SetWidth(309+(active and applicantExtraWidth or 0)) end
    member:SetWidth(active and 256+applicantExtraWidth or (MPL.logColumn.headers[4]:IsShown() and 256 or 200))
    member.Name:SetPoint("RIGHT",member,"LEFT",active and 115 or 95,0)
    member.RoleIcon1:ClearAllPoints(); member.RoleIcon1:SetPoint("LEFT",active and 124 or 104,0)
    member.ItemLevel:ClearAllPoints(); member.ItemLevel:SetPoint("CENTER",member,"LEFT",active and 204 or 177,0)
    member.Rating:ClearAllPoints(); member.Rating:SetPoint("CENTER",member,"LEFT",active and 253 or 218,0)
    if not active or not MPL.SafeString(name) or not MPL.SafeString(status) or status~="applied" then cell:Hide(); return end
    local shortName,realm=MPL.Identity(name)
    cell.key=MPL.Key(shortName,realm)
    local knownRole=MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] and role or nil
    if knownRole then
        MPL.roles=MPL.roles or {}; MPL.roles[cell.key]=role
    end
    cell.metric=knownRole=="HEALER" and "hps" or "dps"
    local profile=MPL.GetProfile(shortName,realm)
    if profile then
        local stale,lastDate=MPL.IsProfileStale(profile)
        cell.metric=MPL.PrimaryMetric(profile,shortName,realm)
        local _,_,best=MPL.MetricValues(profile,nil,cell.metric)
        cell.text:SetText(MPL.Percent(best,stale))
        cell.detail=L["Последняя загрузка: "]..lastDate..(stale and L[" / Обновите логи"] or "")
    else cell.text:SetText("|cff888888—|r") end
    cell:Show()
end

function MPL.RefreshApplicantLogs(forceInactive)
    local viewer=LFGListFrame and LFGListFrame.ApplicationViewer
    if not viewer or not MPL.logColumn then return end
    local active=applicantLogLayout(forceInactive)
    if InCombatLockdown() or not active then
        for _,cell in pairs(MPL.applicantLogCells) do cell:Hide() end
        return
    end
    if viewer.ScrollBox and viewer.ScrollBox.ForEachFrame then
        viewer.ScrollBox:ForEachFrame(function(row)
            local id=row.applicantID
            local info=id and C_LFGList.GetApplicantInfo(id)
            for index,member in ipairs(row.Members or {}) do
                if info and not (issecretvalue and issecretvalue(info.numMembers))
                    and type(info.numMembers)=="number" and index<=info.numMembers and member:IsShown() then
                    MPL.UpdateApplicantLog(member,id,index,info.applicationStatus)
                elseif MPL.applicantLogCells[member] then MPL.applicantLogCells[member]:Hide() end
            end
        end)
    end
end

function MPL.ShowRequests()
    local text, count = MPL.ExportRequests()
    if not MPL.requestsWindow then
        local f = window("MPlusLogsRequestsWindow",L["Игроки для обновления базы"],700,430)
        f.status = label(f,20,-48,650)
        local scroll = CreateFrame("ScrollFrame",nil,f,"UIPanelScrollFrameTemplate")
        scroll:SetPoint("TOPLEFT",22,-80); scroll:SetPoint("BOTTOMRIGHT",-42,65)
        f.edit = CreateFrame("EditBox",nil,scroll)
        f.edit:SetMultiLine(true); f.edit:SetFontObject(ChatFontNormal); f.edit:SetSize(620,260); f.edit:SetAutoFocus(false)
        scroll:SetScrollChild(f.edit)
        f.edit:SetScript("OnEscapePressed",function() f:Hide() end)
        label(f,20,-385,650,L["Ctrl+C > сохранить в requests.mplq > build_database.py --requests requests.mplq"])
        MPL.requestsWindow = f
    end
    local f = MPL.requestsWindow
    f.status:SetText(L["Сохранённых игроков: "] .. count .. L[". Ctrl+C — скопировать список."])
    f:Show(); f.edit:SetText(text); f.edit:SetFocus(); f.edit:HighlightText()
end

function MPL.CopyURL(name, realm, profile)
    MPL.copy = MPL.copy or window("MPlusLogsCopyWindow",L["Ссылка Warcraft Logs"],650,150,true)
    local f = MPL.copy
    if not f.edit then
        label(f,20,-48,610,L["Ctrl+C — скопировать и закрыть, Esc — закрыть"])
        f.edit = CreateFrame("EditBox",nil,f,"InputBoxTemplate"); f.edit:SetSize(600,28); f.edit:SetPoint("TOPLEFT",25,-80); f.edit:SetAutoFocus(false)
        f.edit:SetScript("OnEscapePressed",function() f:Hide() end)
        f.revision=0
        f:SetScript("OnHide",function() f.edit:ClearFocus(); f.revision=f.revision+1 end)
        f.edit:SetScript("OnKeyDown",function(_,key)
            if key~="C" or not IsControlKeyDown() or not f.edit:HasFocus() then return end
            local revision=f.revision
            -- Let the edit box finish its native copy before releasing focus.
            C_Timer.After(0,function()
                if f:IsShown() and revision==f.revision then f:Hide() end
            end)
        end)
    end
    f.revision=f.revision+1
    f:Show(); f.edit:SetText(MPL.URL(name,realm,profile)); f.edit:SetFocus(); f.edit:HighlightText()
end

function MPL.ShowImport()
    if not MPL.importWindow then
        local f = window("MPlusLogsImportWindow",L["Импорт данных MPlusLogs"],700,430,true)
        f.programmatic=false; f.handling=false; f.textRevision=0
        f.prompt=label(f,20,-48,650,L["Вставьте ответ помощника (Ctrl+V). Он будет обработан автоматически."])
        local scroll = CreateFrame("ScrollFrame",nil,f,"UIPanelScrollFrameTemplate")
        scroll:SetPoint("TOPLEFT",22,-78); scroll:SetPoint("BOTTOMRIGHT",-42,85)
        local edit = CreateFrame("EditBox",nil,scroll)
        edit:SetMultiLine(true); edit:SetFontObject(ChatFontNormal); edit:SetSize(620,250); edit:SetAutoFocus(false); edit:SetMaxLetters(500000)
        scroll:SetScrollChild(edit); f.edit = edit
        edit:SetScript("OnEscapePressed",function() edit:ClearFocus() end)
        edit:SetScript("OnKeyUp",function(_,key)
            if key=="C" and IsControlKeyDown() and MPL.pendingReply then
                f.status:SetText(L["Ctrl+C нажат. Это не подтверждение получения помощником. Ctrl+V: проверить ответ."])
            end
        end)
        scroll:SetScript("OnMouseDown",function() edit:SetFocus() end)
        f.status = label(f,20,-355,660)
        local function receive()
            if f.handling then return end
            f.handling=true
            local text=edit:GetText()
            -- WoW can notify OnTextChanged after programmatic SetText has
            -- returned. A request is outgoing text, never an importable reply.
            -- Keep it selected so a premature paste cannot destroy the request.
            if text:match("^MPLS1\r?\n[^\r\n]+\r?\nMPLQ1") then
                f.status:SetText(L["Запрос в поле. Ctrl+C: отправить помощнику. Затем Ctrl+V: вставить ответ."])
                edit:HighlightText()
                f.handling=false
                return
            end
            local count, err = MPL.ReceiveReply(text)
            f.status:SetText(count and (L["Загружено профилей: "]..count) or (err or L["Ошибка"]))
            f.programmatic=true
            if count then
                edit:SetText(""); edit:ClearFocus()
                if MPL.panel and MPL.panel:IsShown() then MPL.ShowProfile(MPL.panel.name,MPL.panel.realm,MPL.panel.applicant) end
                f:Hide()
            else
                -- Display readable feedback in the main field, not an encoded
                -- transport envelope. Ctrl+V can replace it on another attempt.
                if not text:match("^MPLS1\r?\n[^\r\n]+\r?\nMPL[1B]") and not text:match("^MPL1\r?\n") then
                    edit:SetText(err or L["Не удалось обработать ответ"])
                end
                edit:SetFocus(); edit:HighlightText()
            end
            f.programmatic=false; f.handling=false
        end
        button(f,L["Импортировать"],20,20,150,receive)
        edit:SetScript("OnTextChanged",function(self)
            -- Do not depend on userInput: client paste paths can fire with a
            -- different flag. Guard our own SetText calls explicitly instead.
            f.textRevision=(f.textRevision or 0)+1
            local revision=f.textRevision
            if f.programmatic or f.handling then return end
            -- Multiline paste may fire several notifications. Never replace
            -- the edit box from inside the paste operation itself.
            C_Timer.After(0.15,function()
                if revision~=f.textRevision or f.programmatic or f.handling or not f:IsShown() then return end
                local text=self:GetText()
                local isReply=text:match("^MPLE1\r?\n[^\r\n]+\r?\n.+")
                    or text:match("^MPLS1\r?\n[^\r\n]+\r?\nMPL1\r?\n")
                    or text:match("^MPLS1\r?\n[^\r\n]+\r?\nMPLB1\r?\n.+")
                    or text:match("^MPL1\r?\n")
                if isReply then receive() end
            end)
        end)
        MPL.importWindow = f
    end
    MPL.importWindow.status:SetText(""); MPL.importWindow:Show(); MPL.importWindow.edit:SetFocus()
end
