local _, MPL = ...
local L = MPL.L
-- Match Russian Companion diagnostics as UTF-8 bytes so addon localization
-- cannot translate these protocol strings before they are compared.
local ruSessionExpired=string.char(208,161,208,181,209,129,209,129,208,184,209,143,32,87,97,114,99,114,97,102,116,32,76,111,103,115,32,208,184,209,129,209,130,208,181,208,186,208,187,208,176)
local ruApiAccess=string.char(208,180,208,190,209,129,209,130,209,131,208,191,32,208,186,32)
local ruNoPublicLogs=string.char(208,159,209,131,208,177,208,187,208,184,209,135,208,189,209,139,208,181,32,208,187,208,190,208,179,208,184,32,77,43,32,208,189,208,181,32,208,189,208,176,208,185,208,180,208,181,208,189,209,139)
local function companionError(errorText,code,retryAt)
    if not errorText then return "" end
    local decoded,wireCode,wireRetry=MPL.DecodeCompanionError(errorText)
    errorText=decoded; code=code or wireCode; retryAt=retryAt or wireRetry
    errorText=errorText:match("^%s*(.-)%s*$")
    local personal=errorText:find("Personal API; ",1,true)
    local reset=retryAt and retryAt>0 and retryAt or tonumber(errorText:match("API reset at (%d+); "))
    errorText=errorText:gsub("Personal API; ",""):gsub("Shared API; ","")
    errorText=errorText:gsub("API reset at %d+; ","")
    local lower=string.lower(errorText)
    local function details(message)
        return message.."\n"..L["Подробности: "]..errorText
    end
    if code=="auth" or lower:find("http 401",1,true) or lower:find("unauthor",1,true)
        or lower:find("authentication",1,true) or lower:find("authorization",1,true)
        or lower:find("access token",1,true) or lower:find("session expired",1,true)
        or errorText:find(ruSessionExpired,1,true) then
        return details(L["\nОткройте MPlusLogs Companion, войдите в Warcraft Logs, затем введите /reload и повторите загрузку."])
    elseif lower:find("http 403",1,true) or lower:find("forbidden",1,true)
        or lower:find("permission",1,true) or errorText:find(ruApiAccess,1,true) then
        return details(L["\nПроверьте вход в Warcraft Logs и доступ к API в Companion, затем повторите загрузку."])
    elseif code=="budget" or lower:find("http 429",1,true) or lower:find("rate limit",1,true)
        or lower:find("hourly query limit",1,true) or lower:find("api budget is low",1,true) then
        local hint=L["\nДостигнут лимит запросов Warcraft Logs или Companion. Подождите и попробуйте снова."]
        if reset then
            local remaining=math.max(0,math.ceil(reset-GetServerTime()))
            local label=personal and L["\nСброс личного API через %d мин. %d сек."] or L["\nСброс общего API через %d мин. %d сек."]
            hint=hint..string.format(label,math.floor(remaining/60),remaining%60)
        else
            hint=hint..L["\nWarcraft Logs не сообщил время сброса лимита."]
        end
        if not personal then
            hint=hint..L["\nРекомендуем открыть MPlusLogs Companion и нажать «Перейти на личный API», чтобы использовать свой API-клиент Warcraft Logs."]
        end
        return details(hint)
    elseif code=="hidden" or lower:find("rankings hidden",1,true) then
        return L["Логи этого персонажа скрыты в Warcraft Logs. Доступ к ним не разрешён для текущего аккаунта."]
    elseif lower:find("no matching character found",1,true) then
        return L["В Warcraft Logs не найден персонаж с таким именем, классом и подходящим уровнем."]
    elseif lower:find("lookup response",1,true) or lower:find("class lookup",1,true) then
        return details(L["Не удалось определить персонажа: Warcraft Logs вернул неполные или некорректные данные поиска."])
    elseif code=="retry" or lower:find("profile refresh is cooling down",1,true) then
        return details(L["Повторный запрос логов отложен. Его можно отправить позже."])
    elseif code=="missing" or lower:find("character not found",1,true) then
        return details(L["Персонаж не найден"])
    elseif code=="empty" or lower:find("no public logs",1,true) or errorText:find(ruNoPublicLogs,1,true) then
        return L["Для этого персонажа нет доступных логов M+."]
    elseif code=="schema" or lower:find("unknown ",1,true) and lower:find(" shape",1,true)
        or lower:find("throughputrankings missing",1,true)
        or lower:find("graphql error",1,true) then
        return details(L["\nCompanion не распознал формат ответа Warcraft Logs. Обновите MPlusLogs Companion; если ошибка повторится, сообщите об этой ошибке."])
    elseif code=="network" or lower:find("could not connect",1,true) or lower:find("timed out",1,true)
        or lower:find("name resolution",1,true) or lower:find("getaddrinfo",1,true)
        or lower:find("http 5",1,true) then
        return details(L["\nПроверьте подключение к интернету и попробуйте снова."])
    elseif lower:find("clipboard is busy",1,true) or lower:find("clipboard write failed",1,true) then
        return details(L["\nОсвободите буфер обмена, снова скопируйте запрос через Ctrl+C, дождитесь Companion и нажмите Ctrl+V."])
    elseif lower:find("unknown/ambiguous realm",1,true) or lower:find("unknown realm",1,true) then
        return details(L["\nПроверьте регион и название игрового мира персонажа, затем повторите запрос."])
    elseif lower:find("too many",1,true) or lower:find("queue is too large",1,true) then
        return details(L["\nУменьшите число персонажей в запросе и повторите загрузку."])
    end
    for _,key in ipairs({"Неверный формат ответа логов","Пустой или незавершённый импорт",
        "Отсутствует обязательное поле","Некорректное число","Некорректная запись профиля",
        "Некорректная запись данжа","Некорректное завершение профиля","Некорректный результат загрузки",
        "Некорректное описание ошибки","Неполная запись DPS/HPS","Неизвестный регион",
        "Неизвестная метрика","Неизвестная роль","Метрика не соответствует роли",
        "Дублирующийся профиль","Повторный результат загрузки","Слишком большой импорт (максимум 500 КБ)",
        "Слишком много профилей","Слишком много данжей","Ошибка импорта","Не удалось обработать ответ"}) do
        if errorText==L[key] then return details(L["Ошибка чтения данных"]) end
    end
    if errorText:find(L["Неизвестная строка импорта; строка "],1,true) then
        return details(L["Ошибка чтения данных"])
    end
    return errorText
end
MPL.CompanionError=companionError
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
local windowStack={}
local function highestWindowLevel(frame)
    local highest=frame:GetFrameLevel()
    for _,child in ipairs({frame:GetChildren()}) do
        highest=math.max(highest,highestWindowLevel(child))
    end
    return highest
end
local function bringWindowForward(frame)
    for i,other in ipairs(windowStack) do
        if other==frame then table.remove(windowStack,i); break end
    end
    -- The profile stays below dialogs even when refreshed or clicked.
    if frame.mplBaseWindow then table.insert(windowStack,1,frame)
    else windowStack[#windowStack+1]=frame end
    -- Rebuild compact ranges instead of increasing levels on every reopen.
    -- Reserve the complete child subtree, including scroll frames and edit boxes.
    local level=100
    for _,other in ipairs(windowStack) do
        if other:IsShown() then
            other:SetFrameLevel(level)
            level=highestWindowLevel(other)+10
        end
    end
end
local function window(name, title, width, height)
    local f = CreateFrame("Frame", name, UIParent, "BackdropTemplate")
    f:SetSize(width, height); f:SetPoint("CENTER"); f:SetFrameStrata("DIALOG")
    f:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8", edgeFile="Interface/Tooltips/UI-Tooltip-Border", tile=true, tileSize=16, edgeSize=16, insets={left=4,right=4,top=4,bottom=4}})
    f:SetBackdropColor(0.035,0.035,0.05,1)
    f.mplBaseWindow=name=="MPlusLogsWindow"
    f:HookScript("OnShow",bringWindowForward)
    f:HookScript("OnMouseDown",bringWindowForward)
    f:EnableMouse(true); f:SetMovable(true); f:SetClampedToScreen(true)
    f:RegisterForDrag("LeftButton"); f:SetScript("OnDragStart", f.StartMoving); f:SetScript("OnDragStop", f.StopMovingOrSizing)
    f.title=label(f, 20, -16, width-60, title, "GameFontNormalLarge")
    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -2, -2)
    UISpecialFrames[#UISpecialFrames+1] = name
    f:Hide()
    return f
end

-- Reuse the same opaque backgrounds and dialog stacking for auxiliary views.
MPL.CreateDialog=window

function MPL.UpdatePanelScroll(f)
    local overflow=f.content:GetHeight()>math.max(1,f.scroll:GetHeight())+1
    if f.scroll.ScrollBar then f.scroll.ScrollBar:SetShown(overflow) end
    f.scroll:EnableMouseWheel(overflow)
    if not overflow then f.scroll:SetVerticalScroll(0) end
end

local function panelFill(parent,x,y,width,height,r,g,b)
    local texture=parent:CreateTexture(nil,"BACKGROUND")
    texture:SetPoint("TOPLEFT",x,y); texture:SetSize(width,height); texture:SetColorTexture(r,g,b,1)
    return texture
end
local function tablePercent(value,stale)
    local text=MPL.Percent(value,stale):gsub("%%|r$","|r")
    return text
end
local function gridLine(parent,x,y,width,height)
    return panelFill(parent,x,y,width,height,0.20,0.20,0.20)
end
local function specTexture(spec,class)
    if not spec or not GetSpecializationInfoByID then return end
    class=class or MPL.SpecClass(spec)
    for id,info in pairs(MPL.specInfo) do
        if info[1]==spec and class and info[3]==class then
            local _,_,_,texture=GetSpecializationInfoByID(id)
            if texture and not (issecretvalue and issecretvalue(texture)) then return texture end
            return
        end
    end
end
local function missingMetric(profile,metric)
    return profile and ((profile.secondaryPending and metric=="hps")
        or (profile.dual==false and metric~=profile.metric))
end
local function metricTab(f,metric,x)
    local b=CreateFrame("Button",nil,f,"BackdropTemplate")
    b:SetSize(86,28); b:SetPoint("TOPLEFT",x,-112)
    b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    b:SetBackdropBorderColor(0.27,0.27,0.27,1)
    b.caption=label(b,8,-7,70,metric:upper()); b.caption:SetJustifyH("CENTER")
    b.selectionBar=b:CreateTexture(nil,"ARTWORK")
    b.selectionBar:SetColorTexture(1,0.78,0.30,1)
    b.selectionBar:SetPoint("BOTTOMLEFT",2,2); b.selectionBar:SetPoint("BOTTOMRIGHT",-2,2)
    b.selectionBar:SetHeight(3); b.selectionBar:Hide()
    b.hover=b:CreateTexture(nil,"HIGHLIGHT")
    b.hover:SetAllPoints(); b.hover:SetColorTexture(1,1,1,0.07)
    b:SetScript("OnClick",function()
        f.viewMetric=metric; MPL.RenderProfileStats(f)
        MPL.UpdateProfileLoadButton()
        if missingMetric(f.profile,metric) then
            f.metricNoticeFooter=f.metricNoticeFooter or f.footer:GetText()
            f.footer:SetText(metric=="hps" and L["Healing data loads on request. Click Load HPS."]
                or L["Damage data loads on request. Click Load DPS."])
        elseif f.metricNoticeFooter then
            f.footer:SetText(f.metricNoticeFooter); f.metricNoticeFooter=nil
        end
    end)
    return b
end
local function specSelector(parent,callback)
    local b=CreateFrame("Button",nil,parent,"BackdropTemplate")
    b:SetSize(310,44); b:SetPoint("TOPRIGHT",-40,-72)
    b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    b:SetBackdropColor(0.12,0.09,0.18,1); b:SetBackdropBorderColor(0.64,0.45,0.83,1)
    b.icon=b:CreateTexture(nil,"ARTWORK"); b.icon:SetSize(28,28); b.icon:SetPoint("LEFT",10,0)
    b.caption=label(b,48,-7,232,"","GameFontHighlight")
    b:SetFontString(b.caption)
    b.detail=label(b,48,-26,232); b.detail:SetTextColor(0.77,0.71,0.87)
    b.arrow=b:CreateTexture(nil,"ARTWORK"); b.arrow:SetSize(16,16); b.arrow:SetPoint("RIGHT",-10,0)
    b.arrow:SetTexture("Interface/ChatFrame/UI-ChatIcon-ScrollDown-Up")
    b:SetScript("OnClick",callback)
    b:SetScript("OnEnter",function(self)
        if not self.canSelectSpecs then return end
        self:SetBackdropColor(0.22,0.15,0.31,1); self:SetBackdropBorderColor(0.86,0.67,1,1)
        GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
        GameTooltip:AddLine(L["Выбрать специализацию логов"],1,1,1)
        GameTooltip:AddLine(L["Основной спек отмечен в списке. Переключение использует сохранённые логи; отсутствующий профиль можно загрузить."],0.85,0.85,0.85,true)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave",function(self)
        self:SetBackdropColor(0.12,0.09,0.18,1); self:SetBackdropBorderColor(0.64,0.45,0.83,1)
        GameTooltip:Hide()
    end)
    return b
end
local function buildPanel()
    local f = window("MPlusLogsWindow", "MPlusLogs — Warcraft Logs", 940, 700)
    f:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1,insets={left=1,right=1,top=1,bottom=1}})
    f:SetBackdropColor(0,0,0,1); f:SetBackdropBorderColor(0.27,0.27,0.27,1)
    panelFill(f,1,-1,938,36,0.105,0.06,0.12)
    f.title:SetTextColor(0.9,0.94,0.96)
    do
        local settings=CreateFrame("Button",nil,f,"BackdropTemplate")
        settings:SetSize(104,22); settings:SetPoint("TOPRIGHT",-38,-7)
        settings:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
        settings:SetBackdropColor(0.16,0.10,0.21,1)
        settings:SetBackdropBorderColor(0.40,0.29,0.51,1)
        settings.caption=label(settings,0,0,104,L["Settings"],"GameFontHighlight")
        settings.caption:ClearAllPoints(); settings.caption:SetPoint("CENTER"); settings.caption:SetJustifyH("CENTER")
        settings:SetScript("OnClick",function() MPL.OpenSettings() end)
        settings:SetScript("OnEnter",function()
            settings:SetBackdropBorderColor(0.75,0.55,0.96,1)
            settings.caption:SetTextColor(1,0.82,0)
        end)
        settings:SetScript("OnLeave",function()
            settings:SetBackdropBorderColor(0.40,0.29,0.51,1)
            settings.caption:SetTextColor(1,1,1)
        end)
        settings:SetShown(not MPL.GetOption("hideLogSettings"))
        f.settingsButton=settings
        f.title:SetWidth(740)
    end
    f.character = label(f,20,-48,400,"","GameFontHighlightLarge")
    f.character:SetWordWrap(false)
    f.currentSpec=CreateFrame("Frame",nil,f,"BackdropTemplate")
    f.currentSpec:SetPoint("TOPLEFT",440,-39); f.currentSpec:SetSize(460,32)
    f.currentSpec:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    f.currentSpec:SetBackdropColor(0.13,0.10,0.035,1)
    f.currentSpec:SetBackdropBorderColor(0.70,0.53,0.18,1)
    f.currentSpec.icon=f.currentSpec:CreateTexture(nil,"ARTWORK")
    f.currentSpec.icon:SetPoint("TOPLEFT",5,-4); f.currentSpec.icon:SetSize(24,24)
    f.currentSpec.caption=label(f.currentSpec,37,-3,415,L["Текущая специализация"])
    f.currentSpec.caption:SetTextColor(0.85,0.72,0.42)
    f.currentSpec.caption:SetWordWrap(false)
    f.currentSpec.name=label(f.currentSpec,37,-16,415,"","GameFontHighlight")
    f.currentSpec.name:SetTextColor(1,0.90,0.55)
    f.currentSpec.name:SetWordWrap(false)
    panelFill(f,20,-80,880,26,0.105,0.06,0.12)
    f.context = label(f,30,-87,860)
    f.specButton=specSelector(f,function()
        if not f.specButton.canSelectSpecs then return end
        if InCombatLockdown() or not MenuUtil or not MenuUtil.CreateContextMenu then return end
        local role=MPL.roles and MPL.roles[MPL.Key(f.name,f.realm)]
        MenuUtil.CreateContextMenu(f.specButton,function(_,root)
            root:CreateTitle(L["Выбрать специализацию логов"])
            local main=MPL.MainProfileSpec(f.name,f.realm,role)
            local specs={"All specs"}
            for _,spec in ipairs(MPL.ProfileSpecs(f.name,f.realm)) do specs[#specs+1]=spec end
            for _,spec in ipairs(specs) do
                local caption=MPL.SpecLabel(spec,f.class)
                if spec==main then caption=caption..L[" — основной"] end
                local stored=MPL.GetProfile(f.name,f.realm,spec)
                if stored then caption=caption..L[" — загружено"] end
                root:CreateRadio(caption,function()
                    return f.selectedSpec==spec
                end,function()
                    MPL.SelectSpec(f.name,f.realm,spec,role)
                    local sent=f.inviteSent
                    MPL.ShowProfile(f.name,f.realm,f.applicant,true)
                    if sent then f.inviteSent=true; MPL.UpdateProfileInvite() end
                    if not stored then MPL.ShowDownload(f.name,f.realm,nil,f.applicant,false,false) end
                    if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
                end)
            end
            root:CreateDivider()
            root:CreateButton(L["Загрузить другие специализации"],function()
                -- A targeted spec discovery must not expand back into the
                -- party batch, which only refreshes one profile per member.
                MPL.SelectSpec(f.name,f.realm,"All specs",role)
                MPL.ShowProfile(f.name,f.realm,f.applicant,true)
                MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant,false,true)
            end)
        end)
    end)
    f.context:SetWidth(540)
    f.metricTabs={dps=metricTab(f,"dps",20),hps=metricTab(f,"hps",112)}
    f.scoreLabel=label(f,64,-163,310,L["Рейтинг Mythic+"],"GameFontHighlight")
    f.scoreLabel:SetJustifyH("CENTER")
    f.scoreValue=label(f,64,-189,310,"","GameFontHighlightLarge")
    f.scoreValue:SetJustifyH("CENTER"); f.scoreValue:SetHeight(36)
    local font=f.scoreValue:GetFont()
    if font then f.scoreValue:SetFont(font,30,"") end
    f.summary=label(f,520,-159,370)
    f.medianSummary=label(f,520,-181,370)
    f.runSummary=label(f,520,-203,370)
    f.specRanks=label(f,20,-233,880); f.specRanks:SetJustifyH("CENTER")
    f.staleBanner=CreateFrame("Frame",nil,f,"BackdropTemplate")
    f.staleBanner:SetPoint("TOPLEFT",20,-254); f.staleBanner:SetSize(880,28)
    f.staleBanner:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    f.staleBanner:SetBackdropColor(0.12,0.075,0.015,1)
    f.staleBanner:SetBackdropBorderColor(0.65,0.40,0.06,1)
    f.staleBanner.icon=f.staleBanner:CreateTexture(nil,"ARTWORK")
    f.staleBanner.icon:SetSize(20,20); f.staleBanner.icon:SetPoint("LEFT",10,0)
    f.staleBanner.icon:SetTexture("Interface/AddOns/MPlusLogs/assets/stale-clock.tga")
    f.staleBanner.message=label(f.staleBanner,40,-7,828,"","GameFontHighlight")
    f.staleBanner.message:SetWordWrap(false)
    f.staleBanner:Hide()
    f.source = label(f,20,-566,900)
    f.note = label(f,20,-586,900)
    local headings = {L["Подземелье"],L["Уровень"],L["Время"],L["Прохождения"],L["Очки"],L["Место"],L["Лучший DPS"],L["Best %"],L["Median %"]}
    f.columns={0,242,292,358,414,484,554,684,768}
    f.widths={242,50,66,56,70,70,130,84,112}
    f.headings={}
    f.tableHeader=CreateFrame("Frame",nil,f)
    f.tableHeader:SetPoint("TOPLEFT",20,-254); f.tableHeader:SetSize(880,52)
    f.tableDecor={panelFill(f.tableHeader,0,0,880,52,34/255,34/255,34/255)}
    f.primaryGroup=label(f.tableHeader,414,-7,140,L["Рейтинг"]); f.primaryGroup:SetJustifyH("CENTER")
    f.secondaryGroup=label(f.tableHeader,554,-7,326,"DPS"..L[" / по уровню ключа"]); f.secondaryGroup:SetJustifyH("CENTER")
    for _,y in ipairs({0,-26,-52}) do f.tableDecor[#f.tableDecor+1]=gridLine(f.tableHeader,0,y,880,1) end
    for i, text in ipairs(headings) do
        local heading=label(f.tableHeader,4+f.columns[i],-28,f.widths[i]-8,text)
        heading:SetHeight(22); heading:SetJustifyV("MIDDLE"); heading:SetWordWrap(true); heading:SetNonSpaceWrap(true)
        heading:SetJustifyH("CENTER"); heading:SetTextColor(0.93,0.93,0.93)
        f.headings[i]=heading
        f.tableDecor[#f.tableDecor+1]=gridLine(f.tableHeader,f.columns[i],-26,1,26)
    end
    f.tableDecor[#f.tableDecor+1]=gridLine(f.tableHeader,414,0,1,26)
    f.tableDecor[#f.tableDecor+1]=gridLine(f.tableHeader,554,0,1,26)
    f.tableDecor[#f.tableDecor+1]=gridLine(f.tableHeader,880,0,1,52)
    local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT",20,-306); scroll:SetPoint("BOTTOMRIGHT",-40,145)
    scroll:SetSize(880,249)
    local content = CreateFrame("Frame", nil, scroll); content:SetSize(880,1); scroll:SetScrollChild(content)
    f.content, f.scroll, f.rows = content, scroll, {}
    scroll:HookScript("OnScrollRangeChanged",function() MPL.UpdatePanelScroll(f) end)
    scroll:HookScript("OnSizeChanged",function() MPL.UpdatePanelScroll(f) end)
    f.metricHeading=f.headings[7]
    f.tableElements={f.primaryGroup,f.secondaryGroup,f.scoreLabel,f.scoreValue,f.summary,f.medianSummary,f.runSummary}
    f.footer = label(f,20,-606,900)
    button(f,L["Ссылка WCL"],20,20,120,function() MPL.CopyURL(f.name,f.realm,f.profile) end)
    f.loadButton=button(f,L["Обновить M+ логи"],730,53,170,function()
        if type(f.searchMember)=="table" and IsShiftKeyDown and IsShiftKeyDown() then
            MPL.ShowSearchGroupLogs(f.searchMember.searchResultID,true); return
        end
        if missingMetric(f.profile,f.viewMetric) then
            MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant,false,false,nil,nil,f.viewMetric); return
        end
        if type(f.searchMember)=="table" and (not f.searchMember.loaded
            or MPL.SearchGroupHasPendingProfiles(f.searchMember.searchResultID)) then
            MPL.ShowSearchGroupLogs(f.searchMember.searchResultID); return
        end
        local state=MPL.GetProfileState(f.name,f.realm,f.selectedSpec)
        if state and state.reason=="hidden" then return end
        local cooling,remaining=MPL.UpdateProfileLoadButton()
        if cooling then
            f.cooldownNotice=true
            local grouped=type(f.groupPlayers)=="table" and #f.groupPlayers>1
            local key=grouped and "Обновить логи группы можно через %d мин. %d сек." or "Обновить логи можно через %d мин. %d сек."
            f.footer:SetText(string.format(L[key],math.floor(remaining/60),remaining%60))
            return
        end
        MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant,nil,true)
    end)
    f.loadButton:SetScript("OnEnter",function(self)
        if type(f.searchMember)=="table" then
            GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
            GameTooltip:AddLine(L["Shift-click to search realms again."],1,.82,0,true)
            GameTooltip:Show()
        end
    end)
    f.loadButton:SetScript("OnLeave",function() GameTooltip:Hide() end)
    f.loadElapsed=0
    f.loadButton:SetScript("OnUpdate",function(_,elapsed)
        f.loadElapsed=(f.loadElapsed or 0)+elapsed
        if f.loadElapsed>=1 then
            f.loadElapsed=0
            local cooling,remaining=MPL.UpdateProfileLoadButton()
            if f.cooldownNotice then
                if cooling then
                    local grouped=type(f.groupPlayers)=="table" and #f.groupPlayers>1
                    local key=grouped and "Обновить логи группы можно через %d мин. %d сек." or "Обновить логи можно через %d мин. %d сек."
                    f.footer:SetText(string.format(L[key],math.floor(remaining/60),remaining%60))
                else
                    f.cooldownNotice=false; f.footer:SetText("")
                end
            end
        end
    end)
    f.emptyMessage=label(f,80,-300,780,L["Данные этого персонажа ещё не загружены."],"GameFontHighlightLarge")
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
    f.inviteInfo=label(f,150,-660,530)
    f.inviteButton=button(f,L["Пригласить"],710,20,190,function()
        local ok,err=MPL.InviteFromProfile(f.applicant)
        if ok then f.inviteSent=true; MPL.UpdateProfileInvite()
        else f.inviteInfo:SetText(err); f.inviteButton:Disable() end
    end)
    -- Optional scaling via BlizzMove; keep our existing drag handlers.
    if BlizzMoveAPI and type(BlizzMoveAPI.RegisterAddOnFrames)=="function" then
        BlizzMoveAPI:RegisterAddOnFrames({MPlusLogs={
            MPlusLogsWindow={FrameReference=f,NonDraggable=true},
        }})
    end
    return f
end

function MPL.UpdateProfileLoadButton()
    local f=MPL.panel
    if not f then return false end
    if missingMetric(f.profile,f.viewMetric) then
        f.loadButton:Show(); f.loadButton:SetAlpha(1)
        f.loadButton:SetText(f.viewMetric=="hps" and L["Load HPS"] or L["Load DPS"])
        return false,0
    end
    f.loadButton:SetText(f.profile and L["Обновить M+ логи"] or L["Загрузить M+ логи"])
    if type(f.searchMember)=="table" and (not f.searchMember.loaded
        or MPL.SearchGroupHasPendingProfiles(f.searchMember.searchResultID)) then
        f.loadButton:Show(); f.loadButton:SetAlpha(1)
        f.loadButton:SetNormalFontObject("GameFontNormal")
        return false,0
    end
    local state=MPL.GetProfileState(f.name,f.realm,f.selectedSpec)
    f.loadButton:SetShown(not (state and state.reason=="hidden"))
    local remaining=math.ceil(MPL.ProfileRefreshRemaining(f.profile or nil))
    local cooling=remaining>0
    if type(f.groupPlayers)=="table" and #f.groupPlayers>1 then
        local pending=MPL.FilterFreshProfiles(f.groupPlayers,true)
        cooling=#pending==0
        if cooling then
            remaining=math.huge
            for _,player in ipairs(f.groupPlayers) do
                local spec=MPL.SelectedSpec(player.name,player.realm,player.role) or player.spec
                local playerState=MPL.GetProfileState(player.name,player.realm,spec)
                if not playerState or playerState.reason~="hidden" then
                    local profile=MPL.GetProfile(player.name,player.realm,spec,player.role)
                    remaining=math.min(remaining,math.ceil(MPL.ProfileRefreshRemaining(profile)))
                end
            end
            if remaining==math.huge then remaining=0 end
        end
    end
    -- Keep mouse clicks so the muted button can explain the cooldown.
    f.loadButton:SetAlpha(cooling and 0.5 or 1)
    f.loadButton:SetNormalFontObject(cooling and "GameFontDisable" or "GameFontNormal")
    return cooling,remaining
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

local dungeonIcons={
    ["Altar of Fangs"]="12993",["Den of Nalorakk"]="12825",["Kings' Rest"]="11762",["Murder Row"]="12813",
    ["Ruby Life Pools"]="12521",["Temple of Sethraliss"]="11877",["The Blinding Vale"]="12859",["Voidscar Arena"]="12923",
}
function MPL.RenderProfileStats(f)
    local profile=type(f.profile)=="table" and f.profile or nil
    -- A separate age banner keeps the usual result colors readable.
    local showStale=profile~=nil and f.stale==true
    local offset=showStale and 32 or 0
    f.staleBanner:SetShown(showStale)
    if showStale then
        local _,lastDate=MPL.ProfileDate(profile)
        f.staleBanner.message:SetText("|cffffc440"..L["Данные устарели"].."|r    "..L["Последняя загрузка: "]..lastDate)
    end
    f:SetHeight(700+offset)
    f.tableHeader:ClearAllPoints(); f.tableHeader:SetPoint("TOPLEFT",20,-254-offset)
    f.scroll:ClearAllPoints()
    f.scroll:SetPoint("TOPLEFT",20,-306-offset); f.scroll:SetPoint("BOTTOMRIGHT",-40,145)
    for i,text in ipairs({f.source,f.note,f.footer}) do
        text:ClearAllPoints(); text:SetPoint("TOPLEFT",20,-546-i*20-offset)
    end
    local metric=f.viewMetric or "dps"
    for _,heading in ipairs(f.headings) do heading:SetShown(profile~=nil) end
    for _,element in ipairs(f.tableElements) do element:SetShown(profile~=nil) end
    for _,texture in ipairs(f.tableDecor) do texture:SetShown(profile~=nil) end
    for key,tab in pairs(f.metricTabs) do
        local selected=key==metric
        tab:SetShown(profile~=nil)
        tab:SetBackdropColor(selected and 0.28 or 0.045,selected and 0.13 or 0.045,selected and 0.40 or 0.055,1)
        tab:SetBackdropBorderColor(selected and 1 or 0.35,selected and 0.78 or 0.35,selected and 0.30 or 0.38,1)
        tab.caption:SetTextColor(selected and 1 or 0.70,selected and 0.95 or 0.70,selected and 0.80 or 0.73)
        tab.selectionBar:SetShown(selected)
    end
    for _,row in ipairs(f.rows) do row:Hide() end
    f.metricHeading:SetText(L["Лучший "]..metric:upper())
    local firstHeading,secondHeading=MPL.OrderPercentiles(L["Best %"],L["Median %"])
    f.headings[8]:SetText(firstHeading); f.headings[9]:SetText(secondHeading)
    f.secondaryGroup:SetText(metric:upper()..L[" / по уровню ключа"])
    f.specRanks:SetText(""); f.specRanks:Hide()
    if not profile then return end
    local ranks={}
    for _,entry in ipairs(profile.specRanks or {}) do
        local texture=specTexture(entry.spec,f.class)
        local caption=texture and ("|T"..texture..":18:18|t") or MPL.SpecLabel(entry.spec,f.class)
        ranks[#ranks+1]=entry.rank.." "..caption
    end
    if #ranks>0 then
        f.specRanks:SetText("Spec Ranks:  "..table.concat(ranks,"    "))
        f.specRanks:SetTextColor(226/255,104/255,168/255)
        f.specRanks:Show()
    end
    f.scoreValue:SetText(profile.score and string.format("%.0f",profile.score) or "—")
    f.scoreValue:SetTextColor(226/255,104/255,168/255)
    local _,_,best,median=MPL.MetricValues(profile,nil,metric)
    local first,second=MPL.OrderPercentiles(best,median)
    local firstLabel,secondLabel=MPL.OrderPercentiles(L["Лучший % в среднем:"],L["Медианный % в среднем:"])
    f.summary:SetText(metric:upper().." "..firstLabel.."  "..tablePercent(first))
    if MPL.UsesDungeonMetric() then
        f.summary:SetText(MPL.PrimaryPercentileLabel(metric)..": "..MPL.PrimaryStatistic(profile,metric))
    end
    f.medianSummary:SetText(metric:upper().." "..secondLabel.."  "..tablePercent(second))
    f.runSummary:SetText(L["Прохождения"]..":  "..(profile.runs or "—"))
    for index,dungeon in ipairs(profile.dungeons) do
        local row=f.rows[index]
        if not row then
            row=CreateFrame("Frame",nil,f.content); row:SetSize(880,30); row:SetPoint("TOPLEFT",0,-(index-1)*30)
            row.background=panelFill(row,0,0,880,30,index%2==0 and 0.018 or 0,index%2==0 and 0.018 or 0,index%2==0 and 0.018 or 0)
            row.shade=index%2==0 and 0.018 or 0
            row:EnableMouse(true)
            row:SetScript("OnEnter",function(self)
                self.background:SetColorTexture(0.055,0.055,0.055,1)
                if self.url then
                    GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
                    GameTooltip:AddLine(L["Ссылка WCL"].." — "..self.dungeonName,1,1,1)
                    GameTooltip:Show()
                end
            end)
            row:SetScript("OnLeave",function(self)
                self.background:SetColorTexture(self.shade,self.shade,self.shade,1)
                GameTooltip:Hide()
            end)
            local function copyDungeonURL(_,mouseButton)
                if mouseButton=="LeftButton" and row.url then
                    GameTooltip:Hide()
                    MPL.CopyURL(f.name,f.realm,f.profile,row.url)
                end
            end
            row:SetScript("OnMouseUp",copyDungeonURL)
            row.cells={}
            for i=1,9 do
                row.cells[i]=label(row,f.columns[i]+6,-8,f.widths[i]-12)
                row.cells[i]:SetJustifyH(i==1 and "LEFT" or "RIGHT")
                gridLine(row,f.columns[i],0,1,30)
            end
            gridLine(row,880,0,1,30); gridLine(row,0,-29,880,1)
            row.icon=row:CreateTexture(nil,"ARTWORK"); row.icon:SetPoint("TOPLEFT",6,-4); row.icon:SetSize(22,22)
            row.scoreSpecIcon=CreateFrame("Frame",nil,row)
            row.scoreSpecIcon:SetSize(18,18)
            row.scoreSpecIcon:SetPoint("LEFT",row.cells[5],"RIGHT",4,0)
            row.scoreSpecIcon.texture=row.scoreSpecIcon:CreateTexture(nil,"ARTWORK")
            row.scoreSpecIcon.texture:SetAllPoints()
            row.scoreSpecIcon:EnableMouse(true)
            row.scoreSpecIcon:SetScript("OnMouseUp",copyDungeonURL)
            row.scoreSpecIcon:SetScript("OnEnter",function(self)
                GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
                GameTooltip:AddLine(MPL.SpecLabel(self.spec,f.class),1,1,1)
                GameTooltip:Show()
            end)
            row.scoreSpecIcon:SetScript("OnLeave",function() GameTooltip:Hide() end)
            row.cells[1]:ClearAllPoints(); row.cells[1]:SetPoint("TOPLEFT",34,-8); row.cells[1]:SetWidth(f.widths[1]-40)
            f.rows[index]=row
        end
        row.dungeonName=dungeon.name
        row.url=MPL.DungeonURL(f.name,f.realm,profile,dungeon.name,metric)
        local icon=dungeonIcons[dungeon.name]
        row.icon:SetTexture(icon and ("Interface\\AddOns\\MPlusLogs\\assets\\dungeons\\"..icon..".tga") or "Interface\\Icons\\INV_Misc_Map_01")
        local level,amount,best,median=MPL.MetricValues(profile,dungeon,metric)
        local first,second=MPL.OrderPercentiles(tablePercent(best)..(dungeon.flagged and profile.metric==metric and "*" or ""),tablePercent(median))
        local metadata=profile.metric==metric
        local scoreSpec=metadata and dungeon.points and (dungeon.scoreSpec or (profile.spec~="All specs" and profile.spec))
        local scoreTexture=specTexture(scoreSpec,f.class)
        row.scoreSpecIcon.spec=scoreSpec
        row.scoreSpecIcon.texture:SetTexture(scoreTexture)
        row.scoreSpecIcon:SetShown(scoreTexture~=nil)
        row.scoreSpecIcon:SetAlpha(1)
        row.cells[5]:SetWidth(f.widths[5]-(scoreTexture and 34 or 12))
        local time=metadata and dungeon.time or nil
        local values={dungeon.name,level or "—",time and time~="" and time or "—",dungeon.runs or "—",
            metadata and dungeon.points and string.format("%.0f",dungeon.points) or "—",
            metadata and dungeon.rank or "—",amount and string.format("%.2fK",amount/1000) or "—",first,second}
        for i,value in ipairs(values) do
            row.cells[i]:SetText(value)
            local r,g,b=225/255,242/255,245/255
            if i==1 then r,g,b=0.72,0.78,1 end
            if i==5 or i==6 then r,g,b=226/255,104/255,168/255 end
            if i==7 then r,g,b=0.82,0.96,0.65 end
            row.cells[i]:SetTextColor(r,g,b)
        end
        row:Show()
    end
    f.content:SetHeight(math.max(1,#profile.dungeons*30))
    f.scroll:SetVerticalScroll(0)
    MPL.UpdatePanelScroll(f)
end

function MPL.RenderPlayerTabs(f)
    f.playerTabs=type(f.playerTabs)=="table" and f.playerTabs or {}
    for _,tab in ipairs(f.playerTabs) do tab:Hide() end
    local players=type(f.searchPlayers)=="table" and f.searchPlayers or
        (type(f.groupPlayers)=="table" and f.groupPlayers or {})
    if #players<2 then return end
    local width=880/#players
    for i,player in ipairs(players) do
        local tab=f.playerTabs[i]
        if not tab then
            tab=CreateFrame("Button",nil,f,"BackdropTemplate")
            tab:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
            local caption=tab:CreateFontString(nil,"OVERLAY","GameFontNormal")
            caption:SetPoint("LEFT",10,0); caption:SetPoint("RIGHT",-10,0)
            caption:SetJustifyH("CENTER"); caption:SetWordWrap(false)
            tab:SetFontString(caption)
            -- Cover the panel border beneath the active tab to join it to the window.
            tab.join=tab:CreateTexture(nil,"OVERLAY")
            tab.join:SetColorTexture(0,0,0,1)
            tab.join:SetPoint("BOTTOMLEFT",1,-1); tab.join:SetPoint("BOTTOMRIGHT",-1,-1)
            tab.join:SetHeight(3)
            tab:SetScript("OnClick",function()
                local p=tab.player
                if p.searchResultID then
                    local group=MPL.searchGroupWindow
                    if group then
                        for index,member in ipairs(group.players) do
                            if member==p then MPL.OpenSearchGroupProfile(index); break end
                        end
                    end
                    return
                end
                MPL.ShowProfile(p.name,p.realm,p.applicantID and p or nil,true,true)
            end)
            tab:SetScript("OnEnter",function(self)
                if not self.selected then self:SetBackdropColor(0.40,0.07,0.07,1) end
                GameTooltip:SetOwner(self,"ANCHOR_TOP")
                GameTooltip:AddLine(self.player.name..(self.player.realm and "-"..self.player.realm or ""))
                if self.player.error then GameTooltip:AddLine(self.player.error,1,.3,.2,true) end
                if self.player.candidates then GameTooltip:AddLine(L["Choose the character's realm"],1,.82,0,true) end
                GameTooltip:Show()
            end)
            tab:SetScript("OnLeave",function(self)
                if not self.selected then self:SetBackdropColor(0.27,0.035,0.035,1) end
                GameTooltip:Hide()
            end)
            f.playerTabs[i]=tab
        end
        tab.player=player; tab:ClearAllPoints()
        local selected=(type(f.searchMember)=="table" and player==f.searchMember) or
            (not f.searchMember and player.realm and MPL.Key(player.name,player.realm)==MPL.Key(f.name,f.realm))
        tab.selected=selected
        tab:SetPoint("BOTTOMLEFT",f,"TOPLEFT",20+(i-1)*width,selected and 0 or 3)
        tab:SetSize(width-4,selected and 32 or 26)
        if selected then
            tab:SetBackdropColor(0,0,0,1)
            tab:SetBackdropBorderColor(0.83,0.66,0.25,1)
        else
            tab:SetBackdropColor(0.27,0.035,0.035,1)
            tab:SetBackdropBorderColor(0.35,0.25,0.25,1)
        end
        tab.join:SetShown(selected)
        tab:SetText((selected and "|cffffd100" or "|cffffffff")..player.name.."|r")
        tab:Show()
    end
end

function MPL.ShowGroupProfiles(players,selected,trackParty)
    if #players==0 then return end
    local first=players[1]
    if selected then
        for _,player in ipairs(players) do
            if MPL.Key(player.name,player.realm)==MPL.Key(selected.name,selected.realm) then first=player; break end
        end
    end
    MPL.panel=MPL.panel or buildPanel()
    MPL.panel.searchPlayers=nil
    MPL.panel.partyTracked=trackParty or false
    MPL.panel.groupPlayers=players
    MPL.panel.groupFailures=nil
    MPL.ShowProfile(first.name,first.realm,first.applicantID and first or nil,true,true)
    local pending=MPL.FilterFreshProfiles(players)
    if #pending>0 then
        MPL.ShowDownload(first.name,first.realm,nil,nil,players)
    end
end

function MPL.ShowProfile(fullName, realm,context,suppressNotice,keepGroup,unresolvedSearch)
    if not keepGroup and not suppressNotice and type(context)=="table" and (context.groupSize or 1)>1 then
        local players=MPL.CollectApplicantGroup(context)
        for _,player in ipairs(players) do
            if #players>1 and MPL.Key(player.name,player.realm)==MPL.Key(context.name,context.realm) then
                MPL.ShowGroupProfiles(players,context); return
            end
        end
    end
    if not MPL.SafeString(fullName) then fullName, realm = UnitFullName("player") end
    local unitName,unitRealm=MPL.Identity(fullName,realm)
    if unitName and not unresolvedSearch then MPL.RefreshCharacterSpec(unitName,unitRealm,true) end
    local profile, name, server = MPL.GetProfile(fullName, realm)
    if not name then return end
    local stateKey=MPL.Key(name,server)
    local requestedSpec=MPL.SelectedSpec(name,server) or (profile and profile.spec) or "All specs"
    local state=MPL.GetProfileState(name,server,requestedSpec)
    local hidden=state and state.reason=="hidden"
    if state and (state.reason=="hidden" or state.reason=="empty" or state.reason=="missing") then profile=nil end
    if not unresolvedSearch then MPL.Remember(name,server) end
    MPL.panel = MPL.panel or buildPanel()
    local f = MPL.panel
    f.searchMember=false
    if type(f.searchChoices)=="table" then for _,b in ipairs(f.searchChoices) do b:Hide() end end
    f.specButton:Show(); f.currentSpec:Show()
    f.emptyMessage:ClearAllPoints(); f.emptyMessage:SetPoint("TOPLEFT",80,-300)
    if not keepGroup and not suppressNotice then f.groupPlayers=nil; f.groupFailures=nil; f.searchPlayers=nil end
    if not keepGroup and not suppressNotice then f.partyTracked=false end
    f.applicant=type(context)=="table" and MPL.Key(context.name,context.realm)==MPL.Key(name,server) and context or false
    f.inviteSent=false
    if MPL.staleWindow then MPL.staleWindow:Hide() end
    local stale,lastDate=false,nil
    if profile then stale,lastDate=MPL.IsProfileStale(profile) end
    local primary=profile and MPL.PrimaryMetric(profile,name,server) or "dps"
    local secondary=primary=="hps" and "dps" or "hps"
    f.cooldownNotice=false
    f.metricNoticeFooter=nil
    f.name, f.realm, f.profile = name, server, profile or false
    f.selectedSpec=MPL.SelectedSpec(name,server) or (profile and profile.spec) or "All specs"
    local main=MPL.MainProfileSpec(name,server,MPL.roles and MPL.roles[MPL.Key(name,server)])
    f.class=(MPL.classes and MPL.classes[MPL.Key(name,server)]) or MPL.SpecClass(main)
    if not f.class then
        for _,spec in ipairs(MPL.ProfileSpecs(name,server)) do
            local class=MPL.SpecClass(spec)
            if class then f.class=class; break end
        end
    end
    local displayed=profile and profile.spec or f.selectedSpec
    local stateText=state and (state.reason=="hidden" and L["Логи скрыты в Warcraft Logs."]
        or state.reason=="missing" and L["Персонаж не найден"]
        or state.reason=="retry" and L["Повторный запрос логов отложен. Его можно отправить позже."]
        or L["Для этого персонажа нет доступных логов M+."])
    f.specButton:SetText(MPL.SpecLabel(displayed,f.class))
    local savedSpecs=MPL.ProfileSpecs(name,server)
    f.specButton.detail:SetText(not profile and L["Профиль не загружен"] or L["Выбрать специализацию логов"])
    local canSelectSpecs=not hidden and (profile~=nil or #savedSpecs>0)
    f.specButton.canSelectSpecs=canSelectSpecs
    f.specButton:SetEnabled(canSelectSpecs); f.specButton:EnableMouse(canSelectSpecs)
    f.specButton.arrow:SetShown(canSelectSpecs)
    f.specButton.detail:SetShown(canSelectSpecs or not profile)
    f.specButton.caption:ClearAllPoints()
    f.specButton.caption:SetPoint("TOPLEFT",48,(canSelectSpecs or not profile) and -7 or -15)
    local icon="Interface/AddOns/MPlusLogs/assets/mpluslogs-icon"
    if GetSpecializationInfoByID then
        for id,info in pairs(MPL.specInfo) do
            if info[1]==displayed and (not f.class or info[3]==f.class) then
                local _,_,_,texture=GetSpecializationInfoByID(id)
                if texture and not (issecretvalue and issecretvalue(texture)) then icon=texture end
                break
            end
        end
    end
    f.specButton.icon:SetTexture(icon)
    local current=MPL.specs and MPL.specs[MPL.Key(name,server)]
    f.character:SetText(name .. " — " .. server)
    f.currentSpec.name:SetText(current and MPL.SpecLabel(current[1],current[3]) or "—")
    local currentTexture=current and specTexture(current[1],current[3])
    f.currentSpec.icon:SetTexture(currentTexture or nil)
    f.currentSpec.icon:SetShown(currentTexture~=nil and currentTexture~=false)
    f.currentSpec:SetAlpha(current and 1 or 0.55)
    f.lookup:SetText(name .. "-" .. server:gsub(" ",""))
    f.scroll:SetVerticalScroll(0)
    for _, row in ipairs(f.rows) do row:Hide() end
    f.viewMetric=primary; f.stale=stale
    f.context:SetText(profile and profile.season or "Midnight M+ Season 2")
    f.loadButton:ClearAllPoints()
    if profile then
        f.scroll:Show(); f.emptyMessage:Hide()
        f.loadButton:SetPoint("BOTTOMLEFT",730,53); f.loadButton:SetSize(170,24)
        f.loadButton:SetText(L["Обновить M+ логи"])
        f.source:SetText(MPL.T(profile.source)..L["  /  Последняя загрузка: "]..lastDate)
        f.note:SetText(L["Процентиль урона/исцеления не оценивает выживание, прерывания и механику."])
        f.footer:SetText(profile.characterID == 81818678 and profile.source == "Снимок со скриншота пользователя" and L["* Пометка WCL сохранена со скриншота. Общие 162 лога и строки показаны как в источнике."] or L["Логи: только прохождения, доступные WCL; отсутствие данных не означает плохую игру."])
    else
        f.scroll:Hide(); f.emptyMessage:Show()
        f.emptyMessage:SetText(f.selectedSpec~="All specs" and (string.format(L["Профиль не загружен: %s"],MPL.SpecLabel(f.selectedSpec,f.class)))
            or L["Данные этого персонажа ещё не загружены."])
        if stateText then f.emptyMessage:SetText(stateText) end
        f.emptyMessage:SetHeight(72)
        f.loadButton:SetPoint("CENTER",0,-15); f.loadButton:SetSize(260,36)
        f.loadButton:SetText(L["Загрузить M+ логи"])
        f.source:SetText(""); f.note:SetText("")
        f.footer:SetText(L["Нажмите «Загрузить M+ логи». Локальный помощник должен быть запущен."])
        if stateText then
            f.loadButton:ClearAllPoints()
            f.loadButton:SetPoint("BOTTOMLEFT",730,53); f.loadButton:SetSize(170,24)
            f.loadButton:SetText(L["Обновить M+ логи"])
            f.footer:SetText("")
            f.specButton.detail:SetText(hidden and L["Логи скрыты"]
                or state.reason=="retry" and L["Повторный запрос отложен"] or L["Нет доступных логов"])
        end
        f.content:SetHeight(1)
    end
    if profile and stateText then f.footer:SetText(stateText) end
    local failure=type(f.groupFailures)=="table" and f.groupFailures[stateKey]
    if failure then f.footer:SetText(companionError(MPL.T(failure.error),failure.errorCode,failure.retryAt)) end
    if profile and profile.realmInferred then
        f.footer:SetText(f.footer:GetText().."\n"..L["Match based on name and class; realm not confirmed in game."])
    end
    MPL.RenderProfileStats(f)
    local footerHeight=f.footer:GetStringHeight()
    local extra=type(footerHeight)=="number" and math.max(0,math.ceil(footerHeight)-20) or 0
    if extra>0 then
        f:SetHeight(f:GetHeight()+extra)
        f.scroll:SetPoint("BOTTOMRIGHT",-40,145+extra)
    end
    for _,text in ipairs({f.character,f.context,f.source,f.note,f.footer}) do
        text:SetTextColor(0.88,0.95,0.96)
    end
    f:Show()
    MPL.UpdateProfileInvite()
    MPL.UpdatePanelScroll(f)
    MPL.RenderPlayerTabs(f)
    MPL.UpdateProfileLoadButton()
    if stale and not suppressNotice then MPL.ShowStaleNotice(name,server,profile,lastDate) end
end

function MPL.ShowStaleNotice(name,realm,profile,lastDate)
    if not MPL.GetOption("stalePopup") then return end
    MPL.staleWarnings=MPL.staleWarnings or {}
    local key=MPL.Key(name,realm)..":"..profile.updated
    if MPL.staleWarnings[key] then return end
    MPL.staleWarnings[key]=true
    if not MPL.staleWindow then
        local f=window("MPlusLogsStaleWindow",L["Обновите логи персонажа"],480,205)
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
    f.message:SetText(name.." — "..realm..L["\nПоследняя дата загрузки - "]..lastDate..L[".\nПревышен срок актуальности или дата неизвестна."])
    f:Show()
end

function MPL.ShowCompanionUpdates(notice)
    if not MPL.companionUpdateWindow then
        local f=window("MPlusLogsCompanionUpdates",L["Обновления Companion"],620,390)
        f.message=label(f,24,-48,572,"","GameFontHighlightLarge")
        f.message:SetHeight(64); f.message:SetJustifyV("TOP")
        local benefits=label(f,24,-115,572,L["Install the latest Companion for faster log loading and popup notifications."],"GameFontHighlightLarge")
        benefits:SetHeight(44); benefits:SetJustifyV("TOP")
        f.instructions=label(f,24,-165,572,"","GameFontHighlightLarge")
        f.instructions:SetHeight(80); f.instructions:SetJustifyV("TOP")
        f.edit=CreateFrame("EditBox",nil,f,"InputBoxTemplate")
        f.edit:SetSize(568,28); f.edit:SetPoint("TOPLEFT",28,-264); f.edit:SetAutoFocus(false)
        f.edit:SetScript("OnEscapePressed",function() f:Hide() end)
        f:SetScript("OnHide",function() f.edit:ClearFocus() end)
        f.openCompanion=button(f,L["Open Companion"],24,24,270,function()
            f.edit:SetFocus(); f.edit:HighlightText()
        end)
        button(f,L["Позже"],326,24,270,function() f:Hide() end)
        MPL.companionUpdateWindow=f
    end
    local f=MPL.companionUpdateWindow
    local recommended=notice and notice.recommended or MPL.recommendedCompanionVersion
    if notice and notice.installed then
        f.message:SetText(string.format(L["Your Companion: %s. Recommended version: %s."],notice.installed,recommended))
    else
        f.message:SetText(L["This Companion did not report its version. Check for updates."])
    end
    f.edit:SetText("MPLUI1 OPEN_UPDATES")
    f.instructions:SetText(L["Click Open Companion, then copy the command (Ctrl+C).\nIf no window opens, open Companion from the system tray."])
    f:Show()
end

function MPL.ShowCompanionDownload()
    MPL.CopyURL(nil,nil,nil,"https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Setup.exe",L["Скачать MPlusLogs Companion"])
end

function MPL.ShowCompanionIntro(continueLoading)
    if not MPL.companionIntroWindow then
        local f=window("MPlusLogsCompanionIntro",L["Для загрузки логов нужна программа MPlusLogs Companion"],700,260)
        f.message=label(f,24,-55,652,L["Она получает данные из Warcraft Logs и передаёт их в игру.\nУстановите программу, запустите её и войдите в Warcraft Logs."],"GameFontHighlightLarge")
        f.message:SetJustifyV("TOP")
        f.download=button(f,L["Скачать MPlusLogs Companion"],24,24,270,MPL.ShowCompanionDownload)
        f.continue=button(f,L["Уже установлен"],310,24,180,function()
            local callback=f.continueLoading
            MPlusLogsDB=MPlusLogsDB or {}
            MPlusLogsDB.companionIntroDismissed=true
            f.continueLoading=nil; f:Hide()
            if callback then callback() end
        end)
        f.close=button(f,L["Закрыть"],506,24,170,function() f:Hide() end)
        f:SetScript("OnHide",function() f.continueLoading=nil end)
        MPL.companionIntroWindow=f
    end
    local f=MPL.companionIntroWindow
    f.continueLoading=continueLoading
    local measured=f.message:GetStringHeight()
    local height=type(measured)=="number" and math.max(110,math.ceil(measured)) or 110
    f.message:SetHeight(height); f:SetHeight(150+height)
    f:Show()
end

function MPL.ShowDownload(fullName, realm, profile,context,batch,refresh,searchResultID,importTest,requestedMetric,forceSearch)
    local name, server = MPL.Identity(fullName,realm)
    if not name then return end
    local state=MPL.GetProfileState(name,server,MPL.SelectedSpec(name,server))
    if state and state.reason=="hidden" and not batch and not searchResultID then return end
    -- Loading from a player tab (including its stale-data notice) must keep
    -- the shared exchange instead of replacing it with a single-player one.
    local players=MPL.panel and MPL.panel.groupPlayers
    if not searchResultID and batch==nil and type(players)=="table" and #players>1 then
        for _,player in ipairs(players) do
            if MPL.Key(player.name,player.realm)==MPL.Key(name,server) then
                batch=players; break
            end
        end
    end
    -- A fresh party needs no exchange. Check before clearing a pending reply or
    -- opening an empty 0/N window; clicking a player must keep existing work.
    if type(batch)=="table" and #batch>0 and not importTest then
        local pending=MPL.FilterFreshProfiles(batch,refresh)
        if #pending==0 then return end
    elseif batch==true then
        local players,err=MPL.CollectApplicants()
        if not err and #players>0 and #MPL.FilterFreshProfiles(players,refresh)==0 then
            -- Keep the existing all-fresh message, but never offer a request
            -- when the only missing profiles are known to be hidden.
            for _,player in ipairs(players) do
                local playerState=MPL.GetProfileState(player.name,player.realm,player.spec)
                if playerState and playerState.reason=="hidden" then return end
            end
        end
    end
    if not InCombatLockdown() and MPL.NeedsCompanionIntro() then
        MPL.ShowCompanionIntro(function() MPL.ShowDownload(fullName,realm,profile,context,batch,refresh,searchResultID,importTest,requestedMetric,forceSearch) end)
        return
    end
    if not MPL.downloadWindow then
        local f=window("MPlusLogsDownloadWindow",L["M+ логи / Warcraft Logs"],520,382)
        f.programmatic=false; f.revision=0; f.phase="idle"; f.request=""; f.quotaElapsed=0
        f.character=label(f,24,-53,472,"","GameFontHighlightLarge")
        f.steps=label(f,24,-84,472,L["1. Отправка запроса    /    2. Получение логов"],"GameFontNormal")
        local divider=f:CreateTexture(nil,"ARTWORK")
        divider:SetColorTexture(0.55,0.48,0.28,0.35)
        divider:SetPoint("TOPLEFT",24,-108); divider:SetSize(472,1)
        f.status=label(f,24,-126,472,"","GameFontHighlight")
        f.status:SetHeight(144); f.status:SetJustifyV("TOP")
        f.requestLabel=label(f,24,-276,472,L["Запрос: Ctrl+A выделить, Ctrl+C скопировать"],"GameFontDisableSmall")
        f.errorIcon=f:CreateTexture(nil,"ARTWORK")
        f.errorIcon:SetTexture("Interface\\RaidFrame\\ReadyCheck-NotReady")
        f.errorIcon:SetSize(28,28); f.errorIcon:SetPoint("TOPLEFT",24,-124); f.errorIcon:Hide()
        local inputClip=CreateFrame("Frame",nil,f,"BackdropTemplate")
        inputClip:SetPoint("TOPLEFT",24,-294); inputClip:SetSize(472,64)
        inputClip:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Tooltips/UI-Tooltip-Border",edgeSize=8,insets={left=2,right=2,top=2,bottom=2}})
        inputClip:SetBackdropColor(0.08,0.08,0.09,1)
        inputClip:SetClipsChildren(true); inputClip:EnableMouse(true)
        f.companionHint=CreateFrame("Frame",nil,f)
        f.companionHint:SetPoint("TOPLEFT",24,-126); f.companionHint:SetSize(472,80)
        f.companionHint.text=label(f.companionHint,0,0,240,L["Первый раз загружаете логи? Сначала установите и запустите MPlusLogs Companion."])
        f.companionHint.text:SetJustifyV("TOP")
        f.companionHint.download=button(f.companionHint,L["Скачать MPlusLogs Companion"],252,25,220,MPL.ShowCompanionDownload)
        f.setStatus=function(text,isError)
            local showHint=not MPL.CompanionHasHistory()
            f.companionHint:SetShown(showHint)
            local measured=f.companionHint.text:GetStringHeight()
            local introOffset=showHint and math.max(80,type(measured)=="number" and math.ceil(measured)+12 or 80) or 0
            f.companionHint:SetHeight(introOffset)
            f.errorIcon:ClearAllPoints(); f.errorIcon:SetPoint("TOPLEFT",24,-124-introOffset)
            f.errorIcon:SetShown(isError==true)
            f.status:SetFontObject(isError and "GameFontHighlightLarge" or "GameFontHighlight")
            f.status:SetTextColor(1,isError and 0.4 or 1,isError and 0.35 or 1)
            f.status:ClearAllPoints(); f.status:SetPoint("TOPLEFT",isError and 62 or 24,-126-introOffset)
            f.status:SetWidth(isError and 434 or 472)
            f.status:SetText(text)
            -- Long translated guidance must fit above the request field even
            -- with the larger error font.
            local height=f.status:GetStringHeight()
            local extra=type(height)=="number" and math.max(0,math.ceil(height)-144) or 0
            f.status:SetHeight(144+extra); f:SetHeight(382+extra+introOffset)
            f.requestLabel:ClearAllPoints(); f.requestLabel:SetPoint("TOPLEFT",24,-276-extra-introOffset)
            inputClip:ClearAllPoints(); inputClip:SetPoint("TOPLEFT",24,-294-extra-introOffset)
        end
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
                        f.setStatus(L["Не удалось активировать ввод. Щёлкните в поле запроса, затем Ctrl+C или Ctrl+V."],true)
                    end
                end
            end)
        end
        f.focusInput=focusInput
        inputClip:SetScript("OnMouseDown",focusInput)
        edit:SetScript("OnMouseUp",focusInput)
        local function setText(text)
            f.capturePaste=false; f.capturedReply=false; f.charBuffer=false
            edit:SetMaxBytes(type(f.importTest)=="table" and f.importTest.captureChars and 1 or 0)
            f.programmatic=true; edit:SetText(text); f.programmatic=false
            focusInput()
        end
        f.begin=function()
            f.quotaError=nil
            if type(f.importTest)=="table" and f.importTest.replay then
                f.phase="waiting"; f.request=""
                f.steps:SetText(MPL.locale=="ruRU" and "Повторная вставка — без запросов WCL" or "Replay paste — no WCL requests")
                f.setStatus(MPL.locale=="ruRU" and "В Companion нажмите «Скопировать последний ответ».\nВернитесь сюда и нажмите Ctrl+V.\nМожно повторять тот же ответ без Ctrl+C и без загрузки данных."
                    or "In Companion, copy the last reply.\nReturn here and press Ctrl+V.\nRepeat the same reply without Ctrl+C or loading data.")
                setText(""); return
            end
            local spec=MPL.SelectedSpec(f.name,f.realm) or (f.profile and f.profile.spec) or "All specs"
            if spec=="All specs" then spec="" end
            local id,request,skipped,total
            if f.searchResultID then
                id,request=MPL.BeginSearchGroupRequest(f.forceSearch)
                local group=MPL.searchGroupWindow
                if not id or not request or not group or type(group.requestPlayers)~="table" then
                    f.setStatus(L["Group member data is unavailable; try again shortly"],true); return
                end
                f.character:SetText(L["Нужно загрузить: "]..#group.requestPlayers)
            elseif f.batch then
                local players,err
                if type(f.batch)=="table" then players=f.batch else players,err=MPL.CollectApplicants() end
                if err then f.setStatus(err,true); return end
                total=#players
                if f.importTest then skipped=0 else players,skipped=MPL.FilterFreshProfiles(players,f.refresh) end
                if total>0 and #players==0 then
                    f.character:SetText(L["Нужно загрузить: "].."0 / "..total)
                    f.status:SetText(L["Все кандидаты уже имеют актуальные логи."])
                    if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
                    return
                end
                id,request=MPL.SendBatchRequest(players,f.refresh)
                if id and type(f.batch)=="table" then MPL.pendingReply.groupPlayers=f.batch end
                f.character:SetText(L["Нужно загрузить: "]..#players.." / "..total)
            else id,request=MPL.SendRequest(f.name,f.realm,f.requestedMetric or (f.profile and f.profile.metric) or "dps",spec,f.applicant,false,f.refresh) end
            if not id then f.setStatus(request,true); return end
            f.phase="copy"; f.request=request
            f.steps:SetText(L["|cffffd1001. Отправка запроса|r    /    |cff8888882. Получение логов|r"])
            f.setStatus(L["Запрос: Ctrl+A выделить, Ctrl+C скопировать"]
                ..(skipped and skipped>0 and ("\n"..L["Актуальные данные: "]..skipped..L[" из "]..total) or ""))
            setText(request)
        end
        edit:SetScript("OnEscapePressed",function() f:Hide() end)
        f:SetScript("OnHide",function()
            edit:ClearFocus(); f.revision=f.revision+1; f.quotaError=nil
            f.charBuffer=false; f.capturedReply=false; f.capturePaste=false
        end)
        f:SetScript("OnUpdate",function(_,elapsed)
            if not f.quotaError then return end
            f.quotaElapsed=(f.quotaElapsed or 0)+elapsed
            if f.quotaElapsed>=1 then
                f.quotaElapsed=0
                f.setStatus(companionError(f.quotaError),true)
            end
        end)
        local function copied(key)
            if key=="V" and f.phase=="waiting" and not MPL.CompanionHasHistory() then
                local revision=f.revision
                C_Timer.After(0.15,function()
                    if f:IsShown() and revision==f.revision and edit:GetText()==f.request
                        and not MPL.CompanionHasHistory() then
                        f.setStatus(L["MPlusLogs Companion пока не ответил.\nЕсли программа ещё не установлена — скачайте её. Если установлена — откройте её и проверьте вход в Warcraft Logs."],true)
                    end
                end)
            end
            if key=="C" and f.phase=="copy" then
                f.phase="waiting"
                f.steps:SetText(L["|cff8888881. Отправка запроса|r    /    |cffffd1002. Получение логов|r"])
                f.setStatus(L["Подождите немного и нажмите |cffffd100Ctrl+V|r.\nCompanion должен быть запущен, а вход выполнен. После настройки сначала введите /reload."])
                edit:HighlightText()
            end
        end
        edit:SetScript("OnKeyDown",function(_,key)
            if IsControlKeyDown() then
                if key=="V" and f.importTest then MPL.BeginImportTestPaste(f) end
                if key=="V" and not (type(f.importTest)=="table" and f.importTest.replay) then
                    f.capturePaste=true; f.capturedReply=false; f.charBuffer=false
                    f.programmatic=true; edit:SetText(""); edit:SetMaxBytes(1); f.programmatic=false
                end
                -- Native clipboard shortcuts act on the selection. Replace the
                -- entire request on paste, even after a mouse click moved it.
                if key=="C" or key=="V" then edit:HighlightText() end
                copied(key)
            end
        end)
        local function textChanged()
            if (f.capturePaste or (type(f.importTest)=="table" and f.importTest.captureChars)) and not f.capturedReply then return end
            if f.importTest then MPL.ImportTestTextChanged(f) end
            f.revision=f.revision+1
            local revision=f.revision
            if f.programmatic or f.phase=="idle" then return end
            C_Timer.After(0.15,function()
                if revision~=f.revision or f.programmatic or not f:IsShown() then return end
                local text=f.capturedReply or edit:GetText()
                if text==f.request then
                    if f.phase=="waiting" and not MPL.CompanionHasHistory() then
                        f.setStatus(L["MPlusLogs Companion пока не ответил.\nЕсли программа ещё не установлена — скачайте её. Если установлена — откройте её и проверьте вход в Warcraft Logs."],true)
                    end
                    setText(f.request)
                    return
                end
                local count,err
                if type(f.importTest)=="table" and f.importTest.replay then
                    local prepared
                    prepared,err=MPL.PrepareImportTestReplay(f,text)
                    if not prepared then f.setStatus(err,true); return end
                end
                local testStarted=f.importTest and MPL.ImportTestClock()
                if f.searchResultID then count,err=MPL.ReceiveSearchGroupReply(text)
                else count,err=MPL.ReceiveReply(text,true) end
                if f.importTest then MPL.FinishImportTest(f,count,err,text,testStarted) end
                if count then
                    local panel=MPL.panel
                    if f.requestedMetric and panel and panel.name==f.name and panel.realm==f.realm and panel.profile then
                        panel.viewMetric=f.requestedMetric; MPL.RenderProfileStats(panel); MPL.UpdateProfileLoadButton()
                    end
                    f.phase="done"; f.status:SetText(L["Логи получены."])
                    f.programmatic=true; edit:SetText(""); f.programmatic=false
                    f:Hide()
                else
                    f.quotaError=err and err:find("API reset at ",1,true) and err or nil
                    f.setStatus(companionError(err or L["Ответ ещё не получен. Нажмите Ctrl+V позже."]),true)
                    setText(f.request)
                end
            end)
        end
        edit:SetScript("OnTextChanged",textChanged)
        -- Keep the native EditBox buffer constant-sized. WoW dispatches OnChar
        -- for pasted characters even when they exceed its display byte limit.
        -- Assemble once after the paste, rather than growing native text.
        edit:SetScript("OnChar",function(_,character)
            if not f.capturePaste and not (type(f.importTest)=="table" and f.importTest.captureChars) then return end
            if f.programmatic or (f.phase~="waiting" and f.phase~="copy") then return end
            if not f.charBuffer then
                f.charBuffer={}; f.charBufferBytes=0; f.charBufferOverflow=false
                local buffer,revision=f.charBuffer,f.revision
                C_Timer.After(0,function()
                    if revision~=f.revision or not f:IsShown() or f.charBuffer~=buffer then return end
                    f.charBuffer=false
                    if f.charBufferOverflow then
                        f.setStatus(MPL.L["Слишком большой импорт (максимум 500 КБ)"],true); return
                    end
                    f.capturedReply=table.concat(buffer)
                    textChanged()
                end)
            end
            if f.charBufferOverflow then return end
            f.charBufferBytes=f.charBufferBytes+#character
            if f.charBufferBytes>1600000 then f.charBufferOverflow=true; return end
            f.charBuffer[#f.charBuffer+1]=character
        end)
        MPL.downloadWindow=f
    end
    local f=MPL.downloadWindow
    MPL.pendingReply=nil
    f.revision=f.revision+1
    f.name=name; f.realm=server; f.profile=profile or false; f.phase="idle"; f.request=""
    f.batch=batch or false
    f.importTest=importTest or false; f.importTestPaste=false
    f.capturedReply=false; f.charBuffer=false; f.capturePaste=false
    f.searchResultID=searchResultID or false
    local replay=type(importTest)=="table" and importTest.replay
    f.edit:SetMaxLetters(replay and importTest.noLetterCount and 0 or (searchResultID and 1600000 or 500000))
    f.edit:SetMaxBytes(replay and importTest.captureChars and 1 or (replay and 1600000 or 0))
    f.refresh=refresh or false
    f.requestedMetric=requestedMetric or false; f.forceSearch=forceSearch or false
    f.title:SetText(L["M+ логи / Warcraft Logs"])
    f.applicant=context or false
    f.character:SetText(name.." — "..server)
    f.steps:SetText(L["|cff8888881. Отправка запроса    /    2. Получение логов|r"])
    f.setStatus(L["Подготовка запроса…"])
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
        local f=window("MPlusLogsBatchResults",L["Логи кандидатов"],660,420)
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
    local rowOffset=0
    for index,player in ipairs(players) do
        local key=MPL.Key(player.name,player.realm)
        local row=f.rows[index]
        if not row then
            row=CreateFrame("Frame",nil,f.content); row:SetSize(590,88); row:SetPoint("TOPLEFT",0,-(index-1)*90)
            row.name=label(row,0,-2,425,"","GameFontHighlight")
            row.status=label(row,0,-22,425); row.status:SetHeight(64); row.status:SetJustifyV("TOP")
            row.open=button(row,L["Показать"],450,20,135,function() MPL.ShowProfile(row.player.name,row.player.realm,row.player) end)
            f.rows[index]=row
        end
        row:ClearAllPoints(); row:SetPoint("TOPLEFT",0,-rowOffset)
        row.player=player
        row.name:SetText(player.name.." — "..player.realm)
        local failure=failures[key]
        row.status:SetText(failure and ((profiles[key] and L["Сохранён кеш. "] or L["Не загружено. "])..companionError(MPL.T(failure.error),failure.errorCode,failure.retryAt)) or L["Логи загружены: доступны DPS и HPS"])
        local measured=row.status:GetStringHeight()
        local height=type(measured)=="number" and math.max(64,math.ceil(measured)) or 64
        row.status:SetHeight(height); row:SetHeight(height+24)
        rowOffset=rowOffset+height+26
        if MPL.GetProfile(player.name,player.realm) then row.open:Enable() else row.open:Disable() end
        row:Show()
    end
    f.content:SetHeight(math.max(1,rowOffset)); f:Show(); MPL.UpdatePanelScroll(f)
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
        GameTooltip:AddLine("M+ "..MPL.PrimaryPercentileLabel()..L[" по уровню ключа"])
        GameTooltip:AddLine(L["DPS/HPS: в соответствии с настройками."],1,1,1)
        GameTooltip:AddLine(L["Серый процент: данные устарели."],0.7,0.7,0.7)
        GameTooltip:Show()
    end)
    f:SetScript("OnLeave",function() GameTooltip:Hide() end)
    f.headers=headers; f.original={}; f.compact=false; f.viewer=viewer; f.expanded=false
    f.raiderExport=false
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

local function raiderExportLayout(f,active)
    -- Raider.IO anchors its export icon beside the native bottom-center
    -- buttons. Our wider applicant panel leaves space before Edit instead.
    local b=active and _G.RaiderIO_ExportButton or f.raiderExport
    if not b or b:GetNumPoints()~=1 then return end
    local point,parent,relative,x,y=b:GetPoint(1)
    -- Anchor offsets round after UI scaling, just like frame widths.
    local function near(value,target) return type(value)=="number" and math.abs(value-target)<0.1 end
    if point~="BOTTOMRIGHT" or parent~=LFGListFrame or not near(y,7) then return end
    if active and relative=="BOTTOM" and near(x,-12) then
        b:ClearAllPoints(); b:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOMRIGHT",-112,7)
        f.raiderExport=b
    elseif not active and f.raiderExport then
        -- Do not overwrite a position another addon changed in the meantime.
        if relative=="BOTTOMRIGHT" and near(x,-112) then
            b:ClearAllPoints(); b:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOM",-12,7)
        end
        f.raiderExport=false
    end
end

local function applicantLogLayout(forceInactive)
    local f=MPL.logColumn
    if not f then return false end
    local active=not forceInactive and LFGListFrame and LFGListFrame.activePanel==f.viewer
        and f.viewer:IsVisible() and MPL.GroupLogsEnabled()
        and (not C_LFGList.HasActiveEntryInfo or C_LFGList.HasActiveEntryInfo())
    if not InCombatLockdown() then
        raiderExportLayout(f,active)
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
            f:ClearAllPoints()
            f:SetPoint("LEFT",f.headers[f.headers[4]:IsShown() and 4 or 3],"RIGHT",0,0)
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
    local ratingShown=MPL.logColumn.headers[4]:IsShown()
    local name,class,_,_,_,_,_,_,_,role,_,_,_,_,_,specID=C_LFGList.GetApplicantMemberInfo(appID,index)
    MPL.RecordApplicant(name,role,specID,class)
    if not cell then
        cell=CreateFrame("Button",nil,member); cell:SetSize(56,20)
        cell:SetPoint("LEFT",member,"LEFT",280,0)
        cell.text=label(cell,0,-4,56,"","GameFontHighlightSmall"); cell.text:SetJustifyH("CENTER")
        cell:SetScript("OnClick",function()
            if not MPL.GroupLogsEnabled() then return end
            for _,player in ipairs(MPL.CollectApplicants()) do
                if player.applicantID==cell.appID and player.memberIndex==cell.index
                    and MPL.Key(player.name,player.realm)==cell.key then
                    MPL.ShowProfile(player.name,player.realm,player); return
                end
            end
        end)
        cell:SetScript("OnEnter",function()
            GameTooltip:SetOwner(cell,"ANCHOR_RIGHT"); GameTooltip:ClearLines()
            local caption=MPL.PrimaryPercentileLabel(cell.metric)
            if MPL.GetOption("percentile")~="dungeon_dps" then caption=cell.metric:upper().." "..caption end
            GameTooltip:AddLine(caption..L[" по уровню ключа"])
            GameTooltip:AddLine(cell.detail,0.8,0.8,0.8,true)
            if cell.profile then MPL.AddDungeonTooltip(GameTooltip,cell.profile,cell.metric,cell.stale,MPL.ListedDungeon()) end
            GameTooltip:AddLine(L["Нажмите для полной сводки"],1,1,1); GameTooltip:Show()
        end)
        cell:SetScript("OnLeave",function() GameTooltip:Hide() end)
        cells[member]=cell
    end
    cell.appID=appID; cell.index=index; cell.key=false; cell.metric="dps"; cell.detail=L["Логи не загружены"]; cell.profile=false
    cell:ClearAllPoints(); cell:SetPoint("LEFT",member,"LEFT",ratingShown and 280 or 226,0)
    cell.text:SetText("—")
    local row=member:GetParent()
    if row then row:SetWidth(309+(active and applicantExtraWidth or 0)) end
    member:SetWidth((ratingShown and 256 or 200)+(active and applicantExtraWidth or 0))
    member.Name:SetPoint("RIGHT",member,"LEFT",active and 115 or 95,0)
    member.RoleIcon1:ClearAllPoints(); member.RoleIcon1:SetPoint("LEFT",active and 124 or 104,0)
    member.ItemLevel:ClearAllPoints(); member.ItemLevel:SetPoint("CENTER",member,"LEFT",active and 204 or 177,0)
    member.Rating:ClearAllPoints(); member.Rating:SetPoint("CENTER",member,"LEFT",active and 253 or 218,0)
    if not active or not MPL.SafeString(name) or not MPL.SafeString(status) or status~="applied" then cell:Hide(); return end
    local shortName,realm=MPL.Identity(name)
    if not MPL.SafeString(shortName) or not MPL.SafeString(realm) then cell:Hide(); return end
    cell.key=MPL.Key(shortName,realm)
    local knownRole=MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] and role or nil
    if knownRole then
        MPL.roles=MPL.roles or {}; MPL.roles[cell.key]=role
    end
    cell.metric=MPL.PrimaryMetric(nil,shortName,realm,knownRole)
    local profile=MPL.GetProfile(shortName,realm)
    if profile then
        local stale,lastDate=MPL.IsProfileStale(profile)
        cell.profile=profile; cell.stale=stale
        cell.metric=MPL.PrimaryMetric(profile,shortName,realm)
        cell.text:SetText(MPL.PrimaryStatistic(profile,cell.metric,nil,stale))
        cell.detail=MPL.SpecLabel(profile.spec).." / "..L["Последняя загрузка: "]..lastDate..(stale and L[" / Обновите логи"] or "")
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

function MPL.CopyURL(name, realm, profile, url, title)
    MPL.copy = MPL.copy or window("MPlusLogsCopyWindow",L["Ссылка Warcraft Logs"],650,150)
    local f = MPL.copy
    if not f.edit then
        f.copyHint=label(f,20,-48,610,L["Ctrl+C — скопировать и закрыть, Esc — закрыть"])
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
    f.title:SetText(title or L["Ссылка Warcraft Logs"])
    f.copyHint:SetText(title and L["Скопируйте ссылку (Ctrl+C) и откройте её в браузере:"] or L["Ctrl+C — скопировать и закрыть, Esc — закрыть"])
    f.revision=f.revision+1
    f:Show(); f.edit:SetText(url or MPL.URL(name,realm,profile)); f.edit:SetFocus(); f.edit:HighlightText()
end

function MPL.ShowImport()
    if not MPL.importWindow then
        local f = window("MPlusLogsImportWindow",L["Импорт данных MPlusLogs"],700,430)
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
        local function setImportStatus(text)
            f.status:SetText(text)
            local measured=f.status:GetStringHeight()
            local extra=type(measured)=="number" and math.max(0,math.ceil(measured)-40) or 0
            f:SetHeight(430+extra)
            scroll:SetPoint("BOTTOMRIGHT",-42,85+extra)
        end
        local function receive()
            if f.handling then return end
            f.handling=true
            local text=edit:GetText()
            -- WoW can notify OnTextChanged after programmatic SetText has
            -- returned. A request is outgoing text, never an importable reply.
            -- Keep it selected so a premature paste cannot destroy the request.
            if text:match("^MPLS1\r?\n[^\r\n]+\r?\nMPLQ1") then
                setImportStatus(L["Запрос в поле. Ctrl+C: отправить помощнику. Затем Ctrl+V: вставить ответ."])
                edit:HighlightText()
                f.handling=false
                return
            end
            local count, err = MPL.ReceiveReply(text)
            setImportStatus(count and (L["Загружено профилей: "]..count) or companionError(err or L["Ошибка импорта"]))
            f.programmatic=true
            if count then
                edit:SetText(""); edit:ClearFocus()
                if MPL.panel and MPL.panel:IsShown() then MPL.ShowProfile(MPL.panel.name,MPL.panel.realm,MPL.panel.applicant) end
                f:Hide()
            else
                -- Display readable feedback in the main field, not an encoded
                -- transport envelope. Ctrl+V can replace it on another attempt.
                if not text:match("^MPLS1\r?\n[^\r\n]+\r?\nMPL[1B]") and not text:match("^MPL1\r?\n") then
                    edit:SetText(companionError(err or L["Не удалось обработать ответ"]))
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
