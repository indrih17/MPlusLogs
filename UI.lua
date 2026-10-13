local _, MPL = ...
local L = MPL.L
-- Match Russian Companion diagnostics as UTF-8 bytes so addon localization
-- cannot translate these protocol strings before they are compared.
local ruSessionExpired=string.char(208,161,208,181,209,129,209,129,208,184,209,143,32,87,97,114,99,114,97,102,116,32,76,111,103,115,32,208,184,209,129,209,130,208,181,208,186,208,187,208,176)
local ruApiAccess=string.char(208,180,208,190,209,129,209,130,209,131,208,191,32,208,186,32)
local ruNoPublicLogs=string.char(208,159,209,131,208,177,208,187,208,184,209,135,208,189,209,139,208,181,32,208,187,208,190,208,179,208,184,32,77,43,32,208,189,208,181,32,208,189,208,176,208,185,208,180,208,181,208,189,209,139)
local function companionError(errorText)
    if not errorText then return "" end
    local personal=errorText:find("Personal API; ",1,true)
    local reset=tonumber(errorText:match("API reset at (%d+); "))
    errorText=errorText:gsub("Personal API; ",""):gsub("Shared API; ","")
    errorText=errorText:gsub("API reset at %d+; ","")
    local lower=string.lower(errorText)
    if lower:find("http 401",1,true) or lower:find("unauthor",1,true)
        or lower:find("authentication",1,true) or lower:find("authorization",1,true)
        or lower:find("access token",1,true) or lower:find("session expired",1,true)
        or errorText:find(ruSessionExpired,1,true) then
        return errorText..L["\nОткройте MPlusLogs Companion, войдите в Warcraft Logs, затем введите /reload и повторите загрузку."]
    elseif lower:find("http 403",1,true) or lower:find("forbidden",1,true)
        or lower:find("permission",1,true) or errorText:find(ruApiAccess,1,true) then
        return errorText..L["\nПроверьте вход в Warcraft Logs и доступ к API в Companion, затем повторите загрузку."]
    elseif lower:find("http 429",1,true) or lower:find("rate limit",1,true)
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
        return errorText..hint
    elseif lower:find("rankings hidden",1,true) then
        return L["Логи этого персонажа скрыты в Warcraft Logs. Доступ к ним не разрешён для текущего аккаунта."]
    elseif lower:find("no public logs",1,true) or lower:find("character not found",1,true)
        or lower:find("rankings hidden",1,true) or errorText:find(ruNoPublicLogs,1,true) then
        return errorText..L["\nПроверьте имя персонажа и игровой мир. Возможно, у него нет открытых логов M+; отсутствие данных не означает нулевой результат."]
    elseif lower:find("unknown ",1,true) and lower:find(" shape",1,true)
        or lower:find("throughputrankings missing",1,true)
        or lower:find("graphql error",1,true) then
        return errorText..L["\nCompanion не распознал формат ответа Warcraft Logs. Обновите MPlusLogs Companion; если ошибка повторится, сообщите об этой ошибке."]
    elseif lower:find("could not connect",1,true) or lower:find("timed out",1,true)
        or lower:find("name resolution",1,true) or lower:find("getaddrinfo",1,true)
        or lower:find("http 5",1,true) then
        return errorText..L["\nПроверьте подключение к интернету и попробуйте снова."]
    elseif lower:find("clipboard is busy",1,true) or lower:find("clipboard write failed",1,true) then
        return errorText..L["\nОсвободите буфер обмена, снова скопируйте запрос через Ctrl+C, дождитесь Companion и нажмите Ctrl+V."]
    elseif lower:find("unknown/ambiguous realm",1,true) or lower:find("unknown realm",1,true) then
        return errorText..L["\nПроверьте регион и название игрового мира персонажа, затем повторите запрос."]
    elseif lower:find("too many",1,true) or lower:find("queue is too large",1,true) then
        return errorText..L["\nУменьшите число персонажей в запросе и повторите загрузку."]
    elseif errorText==L["Это ответ на другой запрос; повторите загрузку нужного игрока"]
        or errorText==L["В буфере нет ответа MPlusLogs для этого запроса. Нажмите Ctrl+V позже; проверьте помощник."]
        or errorText==L["Ответ ещё не получен. Попробуйте Ctrl+V чуть позже; проверьте, что помощник запущен."]
        or errorText==L["Ответ не содержит выбранного персонажа"]
        or errorText==L["Ответ содержит данные другого персонажа"]
        or errorText==L["Ответ содержит другую метрику логов"]
        or errorText==L["Ответ содержит другую роль персонажа"]
        or errorText==L["Ответ содержит другую специализацию"]
        or errorText==L["Не получен результат для всех кандидатов"] then
        return errorText..L["\nСкопируйте текущий запрос заново (Ctrl+C), дождитесь Companion и вставьте ответ (Ctrl+V). Если ошибка повторится, сообщите о ней."]
    end
    return errorText
end
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
    f.title=label(f, 20, -16, width-60, title, "GameFontNormalLarge")
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
local function metricTab(f,metric,x)
    local b=CreateFrame("Button",nil,f,"BackdropTemplate")
    b:SetSize(86,28); b:SetPoint("TOPLEFT",x,-112)
    b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    b:SetBackdropBorderColor(0.27,0.27,0.27,1)
    b.caption=label(b,8,-7,70,metric:upper()); b.caption:SetJustifyH("CENTER")
    b:SetScript("OnClick",function()
        f.viewMetric=metric; MPL.RenderProfileStats(f)
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
    f.character = label(f,20,-48,900,"","GameFontHighlightLarge")
    panelFill(f,20,-80,880,26,0.105,0.06,0.12)
    f.context = label(f,30,-87,860)
    f.specButton=specSelector(f,function()
        if not f.specButton.canSelectSpecs then return end
        if InCombatLockdown() or not MenuUtil or not MenuUtil.CreateContextMenu then return end
        local role=MPL.roles and MPL.roles[MPL.Key(f.name,f.realm)]
        MenuUtil.CreateContextMenu(f.specButton,function(_,root)
            root:CreateTitle(L["Выбрать специализацию логов"])
            local main=MPL.MainProfileSpec(f.name,f.realm,role)
            for _,spec in ipairs(MPL.ProfileSpecs(f.name,f.realm)) do
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
                    if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
                end)
            end
        end)
    end)
    f.context:SetWidth(540)
    f.metricTabs={dps=metricTab(f,"dps",20),hps=metricTab(f,"hps",112)}
    f.filter = label(f,218,-120,680)
    f.scoreLabel=label(f,64,-163,310,L["Рейтинг Mythic+"],"GameFontHighlight")
    f.scoreLabel:SetJustifyH("CENTER")
    f.scoreValue=label(f,64,-189,310,"","GameFontHighlightLarge")
    f.scoreValue:SetJustifyH("CENTER"); f.scoreValue:SetHeight(36)
    local font=f.scoreValue:GetFont()
    if font then f.scoreValue:SetFont(font,30,"") end
    f.summary=label(f,520,-159,370)
    f.medianSummary=label(f,520,-181,370)
    f.runSummary=label(f,520,-203,370)
    f.source = label(f,20,-566,900)
    f.note = label(f,20,-586,900)
    local headings = {L["Подземелье"],L["Уровень"],L["Время"],L["Прохождения"],L["Очки"],L["Место"],L["Лучший DPS"],L["Best %"],L["Median %"]}
    f.columns={0,242,292,358,414,484,554,684,768}
    f.widths={242,50,66,56,70,70,130,84,112}
    f.headings={}
    f.tableDecor={panelFill(f,20,-254,880,52,34/255,34/255,34/255)}
    f.primaryGroup=label(f,434,-261,140,L["Рейтинг"]); f.primaryGroup:SetJustifyH("CENTER")
    f.secondaryGroup=label(f,574,-261,326,"DPS"..L[" / по уровню ключа"]); f.secondaryGroup:SetJustifyH("CENTER")
    for _,y in ipairs({-254,-280,-306}) do f.tableDecor[#f.tableDecor+1]=gridLine(f,20,y,880,1) end
    for i, text in ipairs(headings) do
        local heading=label(f,24+f.columns[i],-282,f.widths[i]-8,text)
        heading:SetHeight(22); heading:SetJustifyV("MIDDLE"); heading:SetWordWrap(true); heading:SetNonSpaceWrap(true)
        heading:SetJustifyH("CENTER"); heading:SetTextColor(0.93,0.93,0.93)
        f.headings[i]=heading
        f.tableDecor[#f.tableDecor+1]=gridLine(f,20+f.columns[i],-280,1,26)
    end
    f.tableDecor[#f.tableDecor+1]=gridLine(f,434,-254,1,26)
    f.tableDecor[#f.tableDecor+1]=gridLine(f,574,-254,1,26)
    f.tableDecor[#f.tableDecor+1]=gridLine(f,900,-254,1,52)
    local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT",20,-306); scroll:SetPoint("BOTTOMRIGHT",-40,145)
    scroll:SetSize(880,249)
    local content = CreateFrame("Frame", nil, scroll); content:SetSize(880,1); scroll:SetScrollChild(content)
    f.content, f.scroll, f.rows = content, scroll, {}
    scroll:HookScript("OnScrollRangeChanged",function() MPL.UpdatePanelScroll(f) end)
    scroll:HookScript("OnSizeChanged",function() MPL.UpdatePanelScroll(f) end)
    f.metricHeading=f.headings[7]
    f.tableElements={f.primaryGroup,f.secondaryGroup,f.scoreLabel,f.scoreValue,f.summary,f.medianSummary,f.runSummary,f.filter}
    f.footer = label(f,20,-606,900)
    button(f,L["Ссылка WCL"],20,20,120,function() MPL.CopyURL(f.name,f.realm,f.profile) end)
    f.loadButton=button(f,L["Обновить M+ логи"],730,53,170,function() MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant) end)
    button(f,L["Local history"],490,53,220,function() MPL.ShowHistory(f.name,f.realm) end)
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

local dungeonIcons={
    ["Altar of Fangs"]="12993",["Den of Nalorakk"]="12825",["Kings' Rest"]="11762",["Murder Row"]="12813",
    ["Ruby Life Pools"]="12521",["Temple of Sethraliss"]="11877",["The Blinding Vale"]="12859",["Voidscar Arena"]="12923",
}
function MPL.RenderProfileStats(f)
    local profile,stale=type(f.profile)=="table" and f.profile or nil,f.stale
    local metric=f.viewMetric or "dps"
    for _,heading in ipairs(f.headings) do heading:SetShown(profile~=nil) end
    for _,element in ipairs(f.tableElements) do element:SetShown(profile~=nil) end
    for _,texture in ipairs(f.tableDecor) do texture:SetShown(profile~=nil) end
    for key,tab in pairs(f.metricTabs) do
        tab:SetShown(profile~=nil)
        tab:SetBackdropColor(key==metric and 0.16 or 0.04,key==metric and 0.10 or 0.04,key==metric and 0.18 or 0.04,1)
        tab.caption:SetTextColor(key==metric and 0.85 or 0.65,key==metric and 0.95 or 0.65,key==metric and 0.75 or 0.65)
    end
    for _,row in ipairs(f.rows) do row:Hide() end
    f.metricHeading:SetText(L["Лучший "]..metric:upper())
    local firstHeading,secondHeading=MPL.OrderPercentiles(L["Best %"],L["Median %"])
    f.headings[8]:SetText(firstHeading); f.headings[9]:SetText(secondHeading)
    f.secondaryGroup:SetText(metric:upper()..L[" / по уровню ключа"])
    if not profile then return end
    f.filter:SetText(metric:upper()..L[" / по уровню ключа"].."  /  "..MPL.SpecLabel(profile.spec,f.class))
    f.scoreValue:SetText(profile.score and string.format("%.0f",profile.score) or "—")
    f.scoreValue:SetTextColor(stale and 0.53 or 226/255,stale and 0.53 or 104/255,stale and 0.53 or 168/255)
    local _,_,best,median=MPL.MetricValues(profile,nil,metric)
    local first,second=MPL.OrderPercentiles(best,median)
    local firstLabel,secondLabel=MPL.OrderPercentiles(L["Лучший % в среднем:"],L["Медианный % в среднем:"])
    f.summary:SetText(metric:upper().." "..firstLabel.."  "..tablePercent(first,stale))
    if MPL.UsesDungeonMetric() then
        f.summary:SetText(MPL.PrimaryPercentileLabel(metric)..": "..MPL.PrimaryStatistic(profile,metric,nil,stale))
    end
    f.medianSummary:SetText(metric:upper().." "..secondLabel.."  "..tablePercent(second,stale))
    f.runSummary:SetText(L["Прохождения"]..":  "..(profile.runs or "—"))
    for index,dungeon in ipairs(profile.dungeons) do
        local row=f.rows[index]
        if not row then
            row=CreateFrame("Frame",nil,f.content); row:SetSize(880,30); row:SetPoint("TOPLEFT",0,-(index-1)*30)
            row.background=panelFill(row,0,0,880,30,index%2==0 and 0.018 or 0,index%2==0 and 0.018 or 0,index%2==0 and 0.018 or 0)
            row.shade=index%2==0 and 0.018 or 0
            row:EnableMouse(true)
            row:SetScript("OnEnter",function(self) self.background:SetColorTexture(0.055,0.055,0.055,1) end)
            row:SetScript("OnLeave",function(self) self.background:SetColorTexture(self.shade,self.shade,self.shade,1) end)
            row.cells={}
            for i=1,9 do
                row.cells[i]=label(row,f.columns[i]+6,-8,f.widths[i]-12)
                row.cells[i]:SetJustifyH(i==1 and "LEFT" or "RIGHT")
                gridLine(row,f.columns[i],0,1,30)
            end
            gridLine(row,880,0,1,30); gridLine(row,0,-29,880,1)
            row.icon=row:CreateTexture(nil,"ARTWORK"); row.icon:SetPoint("TOPLEFT",6,-4); row.icon:SetSize(22,22)
            row.cells[1]:ClearAllPoints(); row.cells[1]:SetPoint("TOPLEFT",34,-8); row.cells[1]:SetWidth(f.widths[1]-40)
            f.rows[index]=row
        end
        local icon=dungeonIcons[dungeon.name]
        row.icon:SetTexture(icon and ("Interface\\AddOns\\MPlusLogs\\assets\\dungeons\\"..icon..".tga") or "Interface\\Icons\\INV_Misc_Map_01")
        local level,amount,best,median=MPL.MetricValues(profile,dungeon,metric)
        local first,second=MPL.OrderPercentiles(tablePercent(best,stale)..(dungeon.flagged and profile.metric==metric and "*" or ""),tablePercent(median,stale))
        local metadata=profile.metric==metric
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
            row.cells[i]:SetTextColor(stale and 0.53 or r,stale and 0.53 or g,stale and 0.53 or b)
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
    local players=type(f.groupPlayers)=="table" and f.groupPlayers or {}
    if #players<2 then return end
    local width=880/#players
    for i,player in ipairs(players) do
        local tab=f.playerTabs[i]
        if not tab then
            tab=button(f,"",0,0,width-4,function() end)
            tab:SetScript("OnClick",function()
                local p=tab.player
                MPL.ShowProfile(p.name,p.realm,p.applicantID and p or nil,true,true)
            end)
            tab:SetScript("OnEnter",function(self)
                GameTooltip:SetOwner(self,"ANCHOR_TOP")
                GameTooltip:AddLine(self.player.name.."-"..self.player.realm)
                GameTooltip:Show()
            end)
            tab:SetScript("OnLeave",function() GameTooltip:Hide() end)
            f.playerTabs[i]=tab
        end
        tab.player=player; tab:ClearAllPoints()
        tab:SetPoint("BOTTOMLEFT",f,"TOPLEFT",20+(i-1)*width,-2)
        tab:SetSize(width-4,26)
        local selected=MPL.Key(player.name,player.realm)==MPL.Key(f.name,f.realm)
        tab:SetText((selected and "|cffffd100" or "|cffffffff")..player.name.."|r")
        tab:Show()
    end
end

function MPL.ShowGroupProfiles(players,selected)
    if #players==0 then return end
    local first=players[1]
    if selected then
        for _,player in ipairs(players) do
            if MPL.Key(player.name,player.realm)==MPL.Key(selected.name,selected.realm) then first=player; break end
        end
    end
    MPL.panel=MPL.panel or buildPanel()
    MPL.panel.groupPlayers=players
    MPL.panel.groupFailures=nil
    MPL.ShowProfile(first.name,first.realm,first.applicantID and first or nil,true,true)
    local pending=MPL.FilterFreshProfiles(players)
    if #pending>0 then
        MPL.ShowDownload(first.name,first.realm,nil,nil,players)
    end
end

function MPL.ShowProfile(fullName, realm,context,suppressNotice,keepGroup)
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
    if unitName then MPL.RefreshCharacterSpec(unitName,unitRealm) end
    local profile, name, server = MPL.GetProfile(fullName, realm)
    if not name then return end
    local stateKey=MPL.Key(name,server)
    local state=MPL.profileStates and MPL.profileStates[stateKey]
    if state and state.expires and state.expires<=GetServerTime() then state=nil end
    if not state and MPlusLogsDB.profileStates then
        local saved=MPlusLogsDB.profileStates[stateKey]
        if saved and (saved.expires or 0)>GetServerTime() then state=saved end
    end
    local requestedSpec=MPL.SelectedSpec(name,server) or (profile and profile.spec) or "All specs"
    if state and state.spec and state.spec~="" and state.spec~=requestedSpec then state=nil end
    if state and (state.reason=="hidden" or state.reason=="empty") then profile=nil end
    MPL.Remember(name,server)
    MPL.panel = MPL.panel or buildPanel()
    local f = MPL.panel
    if not keepGroup and not suppressNotice then f.groupPlayers=nil; f.groupFailures=nil end
    f.applicant=type(context)=="table" and MPL.Key(context.name,context.realm)==MPL.Key(name,server) and context or false
    f.inviteSent=false
    if MPL.staleWindow then MPL.staleWindow:Hide() end
    local stale,lastDate=false,nil
    if profile then stale,lastDate=MPL.IsProfileStale(profile) end
    local primary=profile and MPL.PrimaryMetric(profile,name,server) or "dps"
    local secondary=primary=="hps" and "dps" or "hps"
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
        or state.reason=="retry" and L["Повторный запрос логов отложен. Его можно отправить позже."]
        or L["Для этого персонажа нет доступных логов M+."])
    f.specButton:SetText(MPL.SpecLabel(displayed,f.class))
    f.specButton.detail:SetText(not profile and L["Профиль не загружен"] or L["Выбрать специализацию логов"])
    local canSelectSpecs=#MPL.ProfileSpecs(name,server)>1
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
    f.character:SetText(name .. " — " .. server..(current and ("  /  "..L["Текущая специализация"]..": "..MPL.SpecLabel(current[1],current[3])) or ""))
    f.lookup:SetText(name .. "-" .. server)
    f.scroll:SetVerticalScroll(0)
    for _, row in ipairs(f.rows) do row:Hide() end
    f.viewMetric=primary; f.stale=stale
    f.context:SetText(profile and (profile.season.."  /  "..MPL.SpecLabel(profile.spec,f.class)) or "Midnight M+ Season 2")
    f.loadButton:ClearAllPoints()
    if profile then
        f.scroll:Show(); f.emptyMessage:Hide()
        f.loadButton:SetPoint("BOTTOMLEFT",730,53); f.loadButton:SetSize(170,24)
        f.loadButton:SetText(L["Обновить M+ логи"])
        f.source:SetText(MPL.T(profile.source)..L["  /  Последняя загрузка: "]..lastDate..(stale and L[" / Обновите логи"] or ""))
        f.note:SetText(L["Процентиль урона/исцеления не оценивает выживание, прерывания и механику."])
        f.footer:SetText(profile.characterID == 81818678 and profile.source == "Снимок со скриншота пользователя" and L["* Пометка WCL сохранена со скриншота. Общие 162 лога и строки показаны как в источнике."] or L["Логи: только прохождения, доступные WCL; отсутствие данных не означает плохую игру."])
    else
        f.scroll:Hide(); f.emptyMessage:Show()
        f.emptyMessage:SetText(f.selectedSpec~="All specs" and (L["Профиль не загружен"]..": "..MPL.SpecLabel(f.selectedSpec,f.class))
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
            f.specButton.detail:SetText(state.reason=="retry" and L["Повторный запрос отложен"] or L["Нет доступных логов"])
        end
        f.content:SetHeight(1)
    end
    if profile and stateText then f.footer:SetText(stateText) end
    local failure=type(f.groupFailures)=="table" and f.groupFailures[stateKey]
    if failure then f.footer:SetText(companionError(MPL.T(failure.error))) end
    MPL.RenderProfileStats(f)
    for _,text in ipairs({f.character,f.context,f.source,f.note,f.footer}) do
        text:SetTextColor(stale and 0.53 or 0.88,stale and 0.53 or 0.95,stale and 0.53 or 0.96)
    end
    f:Show()
    MPL.UpdateProfileInvite()
    MPL.UpdatePanelScroll(f)
    MPL.RenderPlayerTabs(f)
    if stale and not suppressNotice then MPL.ShowStaleNotice(name,server,profile,lastDate) end
end

function MPL.ShowStaleNotice(name,realm,profile,lastDate)
    if not MPL.GetOption("stalePopup") then return end
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
    f.message:SetText(name.." — "..realm..L["\nПоследняя дата загрузки - "]..lastDate..L[".\nПревышен срок актуальности или дата неизвестна."])
    f:Show()
end

function MPL.ShowCompanionUpdates()
    if not MPL.companionUpdateWindow then
        local f=window("MPlusLogsCompanionUpdates",L["Обновления Companion"],600,290,true)
        local message=label(f,24,-48,552,L["Один раз установите Companion с проверкой обновлений. Дальше он сам предложит обновление; читать changelog аддона не нужно. Если Companion уже проверяет обновления, повторная установка не нужна."])
        message:SetHeight(76); message:SetJustifyV("TOP")
        label(f,24,-130,552,L["Скопируйте ссылку (Ctrl+C) и откройте её в браузере:"])
        f.edit=CreateFrame("EditBox",nil,f,"InputBoxTemplate")
        f.edit:SetSize(548,28); f.edit:SetPoint("TOPLEFT",28,-158); f.edit:SetAutoFocus(false)
        f.edit:SetScript("OnEscapePressed",function() f:Hide() end)
        f:SetScript("OnHide",function() f.edit:ClearFocus() end)
        button(f,L["Понятно"],390,24,186,function()
            MPlusLogsDB=MPlusLogsDB or {}
            MPlusLogsDB.companionUpdaterNoticeSeen=true
            f:Hide()
        end)
        MPL.companionUpdateWindow=f
    end
    local f=MPL.companionUpdateWindow
    f:Show()
    f.edit:SetText("https://github.com/indrih17/MPlusLogs/releases/tag/companion-channel")
    f.edit:SetFocus(); f.edit:HighlightText()
end

function MPL.ShowDownload(fullName, realm, profile,context,batch,history)
    local name, server = MPL.Identity(fullName,realm)
    if not name then return end
    if not MPL.downloadWindow then
        local f=window("MPlusLogsDownloadWindow",L["M+ логи / Warcraft Logs"],520,382,true)
        f.programmatic=false; f.revision=0; f.phase="idle"; f.request=""; f.quotaElapsed=0
        f.character=label(f,24,-53,472,"","GameFontHighlightLarge")
        f.steps=label(f,24,-84,472,L["1. Отправка запроса    /    2. Получение логов"],"GameFontNormal")
        local divider=f:CreateTexture(nil,"ARTWORK")
        divider:SetColorTexture(0.55,0.48,0.28,0.35)
        divider:SetPoint("TOPLEFT",24,-108); divider:SetSize(472,1)
        f.status=label(f,24,-126,472,"","GameFontHighlight")
        f.status:SetHeight(144); f.status:SetJustifyV("TOP")
        label(f,24,-276,472,L["Запрос: Ctrl+A выделить, Ctrl+C скопировать"],"GameFontDisableSmall")
        local inputClip=CreateFrame("Frame",nil,f,"BackdropTemplate")
        inputClip:SetPoint("TOPLEFT",24,-294); inputClip:SetSize(472,64)
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
        edit:SetScript("OnMouseUp",focusInput)
        local function setText(text)
            f.programmatic=true; edit:SetText(text); f.programmatic=false
            focusInput()
        end
        f.begin=function()
            f.quotaError=nil
            local spec=MPL.SelectedSpec(f.name,f.realm) or (f.profile and f.profile.spec) or "All specs"
            if spec=="All specs" then spec="" end
            local id,request,skipped,total
            if f.history then
                id,request=MPL.SendHistoryRequest(f.name,f.realm)
            elseif f.batch then
                local players,err
                if type(f.batch)=="table" then players=f.batch else players,err=MPL.CollectApplicants() end
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
                if id and type(f.batch)=="table" then MPL.pendingReply.groupPlayers=f.batch end
                f.character:SetText(L["Нужно загрузить: "]..#players.." / "..total)
            else id,request=MPL.SendRequest(f.name,f.realm,f.profile and f.profile.metric or "dps",spec,f.applicant,true) end
            if not id then f.status:SetText(request); return end
            f.phase="copy"; f.request=request
            f.steps:SetText(L["|cffffd1001. Отправка запроса|r    /    |cff8888882. Получение логов|r"])
            f.status:SetText(L["Запрос: Ctrl+A выделить, Ctrl+C скопировать"]
                ..(skipped and skipped>0 and ("\n"..L["Актуальные данные: "]..skipped..L[" из "]..total) or ""))
            setText(request)
        end
        edit:SetScript("OnEscapePressed",function() f:Hide() end)
        f:SetScript("OnHide",function() edit:ClearFocus(); f.revision=f.revision+1; f.quotaError=nil end)
        f:SetScript("OnUpdate",function(_,elapsed)
            if not f.quotaError then return end
            f.quotaElapsed=(f.quotaElapsed or 0)+elapsed
            if f.quotaElapsed>=1 then
                f.quotaElapsed=0
                f.status:SetText(companionError(f.quotaError))
            end
        end)
        local function copied(key)
            if key=="C" and f.phase=="copy" then
                f.phase="waiting"
                f.steps:SetText(L["|cff8888881. Отправка запроса|r    /    |cffffd1002. Получение логов|r"])
                f.status:SetText(L["Подождите немного и нажмите |cffffd100Ctrl+V|r.\nCompanion должен быть запущен, а вход выполнен. После настройки сначала введите /reload."])
                edit:HighlightText()
            end
        end
        edit:SetScript("OnKeyDown",function(_,key)
            if IsControlKeyDown() then
                -- Native clipboard shortcuts act on the selection. Replace the
                -- entire request on paste, even after a mouse click moved it.
                if key=="C" or key=="V" then edit:HighlightText() end
                copied(key)
            end
        end)
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
                    f.quotaError=err and err:find("API reset at ",1,true) and err or nil
                    f.status:SetText(companionError(err or L["Ответ ещё не получен. Нажмите Ctrl+V позже."]))
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
    f.history=history or false
    f.title:SetText(history and L["Local combat history"] or L["M+ логи / Warcraft Logs"])
    f.applicant=context or false
    f.character:SetText(name.." — "..server)
    f.steps:SetText(L["|cff8888881. Отправка запроса    /    2. Получение логов|r"])
    f.status:SetText(L["Подготовка запроса…"])
    f.programmatic=true; f.edit:SetText(""); f.programmatic=false; f.edit:ClearFocus()
    if MPL.importWindow then MPL.importWindow:Hide() end
    f:Show()
    f.begin()
end

function MPL.ShowBatchDownload()
    MPL.ShowDownload(L["Кандидаты"],GetNormalizedRealmName(),nil,nil,true)
end

function MPL.ShowHistory(fullName,realm)
    if not MPL.SafeString(fullName) then fullName,realm=UnitFullName("player") end
    local name,server=MPL.Identity(fullName,realm)
    if not name then return end
    if not MPL.historyWindow then
        local f=window("MPlusLogsHistoryWindow",L["Local combat history"],960,660,true)
        f.character=label(f,20,-48,900,"","GameFontHighlightLarge")
        f.summary=label(f,20,-80,900); f.summary:SetHeight(42)
        f.scroll=CreateFrame("ScrollFrame",nil,f,"UIPanelScrollFrameTemplate")
        f.scroll:SetPoint("TOPLEFT",20,-140); f.scroll:SetPoint("BOTTOMLEFT",20,96); f.scroll:SetSize(408,420)
        f.content=CreateFrame("Frame",nil,f.scroll); f.content:SetSize(388,1); f.scroll:SetScrollChild(f.content); f.rows={}
        f.scroll:HookScript("OnScrollRangeChanged",function() MPL.UpdatePanelScroll(f) end)
        f.empty=label(f,20,-154,400,L["No local observations for this character. Choose a combat log in Companion."])
        f.empty:SetHeight(100)
        label(f,470,-145,220,L["Player"])
        label(f,690,-145,75,L["Interrupts"])
        label(f,775,-145,65,L["Deaths"])
        label(f,850,-145,70,L["Dispels"])
        f.party={}
        for i=1,5 do
            local y=-175-(i-1)*52
            f.party[i]={name=label(f,470,y,210),spec=label(f,470,y-18,210),
                interrupts=label(f,690,y,70),deaths=label(f,775,y,65),dispels=label(f,850,y,70)}
        end
        f.source=label(f,470,-448,450); f.source:SetHeight(58)
        f.coverage=label(f,470,-510,450); f.coverage:SetHeight(60)
        label(f,20,-580,900,L["Raw event counts from local files, separate from WCL percentiles. Partial logs are not complete-run totals."]):SetHeight(32)
        button(f,L["Refresh history"],20,20,230,function() MPL.ShowDownload(f.name,f.realm,nil,nil,false,true) end)
        button(f,L["Закрыть"],790,20,140,function() f:Hide() end)
        MPL.historyWindow=f
    end
    local f=MPL.historyWindow
    f.name,f.realm=name,server
    f.character:SetText(name.." — "..server)
    local runs,observations,totals=MPL.HistoryRuns(name,server)
    f.runs=runs
    f.summary:SetText(string.format(L["Local runs: %d / Complete observations: %d"],#runs,observations).."\n"
        ..L["Interrupts"]..": "..(observations>0 and totals.interrupts or "—").." / "
        ..L["Deaths"]..": "..(observations>0 and totals.deaths or "—").." / "..L["Dispels"]..": "..(observations>0 and totals.dispels or "—"))
    local function select(run)
        f.selected=run
        for i,row in ipairs(f.party) do
            local p=run and run.players[i]
            for _,cell in pairs(row) do cell:SetText("") end
            if p then
                row.name:SetText(p.name~="" and (p.name.."-"..p.realm) or p.guid)
                local info=MPL.specInfo[p.specID]
                row.spec:SetText(info and MPL.SpecLabel(info[1]) or "—")
                row.interrupts:SetText(p.interrupts); row.deaths:SetText(p.deaths); row.dispels:SetText(p.dispels)
            end
        end
        f.source:SetText(run and (L["Combat log"]..": "..run.source.."\n"..string.format(L["Source lines: %d-%d"],run.firstLine,run.lastLine)) or "")
        f.coverage:SetText(run and (L[run.coverage=="complete" and "Complete" or "Partial"]
            .." / "..L[run.status=="completed" and "Completed" or run.status=="in_progress" and "In progress" or "Incomplete"]
            .."\n"..L["Includes owned pets/totems; dispels include spellsteals."]
            ..(run.yearInferred and ("\n"..L["Year inferred from file date."]) or "")) or "")
    end
    for _,row in ipairs(f.rows) do row:Hide() end
    for i,run in ipairs(runs) do
        local row=f.rows[i]
        if not row then
            row=CreateFrame("Button",nil,f.content); row:SetSize(388,52)
            row.caption=label(row,4,-5,380); row.caption:SetHeight(44)
            row:SetScript("OnClick",function() select(row.run) end)
            f.rows[i]=row
        end
        row.run=run
        -- Rebind each time the window changes character; avoid a stale selection closure.
        row:SetScript("OnClick",function() select(row.run) end)
        row:SetPoint("TOPLEFT",0,-(i-1)*54)
        row.caption:SetText("+"..run.level.." "..run.dungeon.."\n"..run.started:gsub("T"," "):sub(1,19).." / "..L[run.coverage=="complete" and "Complete" or "Partial"])
        row:Show()
    end
    f.content:SetHeight(math.max(1,#runs*54)); f.scroll:SetVerticalScroll(0)
    f.empty:SetShown(#runs==0)
    select(runs[1]); f:Show(); MPL.UpdatePanelScroll(f)
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
            row=CreateFrame("Frame",nil,f.content); row:SetSize(590,88); row:SetPoint("TOPLEFT",0,-(index-1)*90)
            row.name=label(row,0,-2,425,"","GameFontHighlight")
            row.status=label(row,0,-22,425); row.status:SetHeight(64); row.status:SetJustifyV("TOP")
            row.open=button(row,L["Показать"],450,20,135,function() MPL.ShowProfile(row.player.name,row.player.realm,row.player) end)
            f.rows[index]=row
        end
        row.player=player
        row.name:SetText(player.name.." — "..player.realm)
        local failure=failures[key]
        row.status:SetText(failure and ((profiles[key] and L["Сохранён кеш. "] or L["Не загружено. "])..companionError(MPL.T(failure.error))) or L["Логи загружены: доступны DPS и HPS"])
        if MPL.GetProfile(player.name,player.realm) then row.open:Enable() else row.open:Disable() end
        row:Show()
    end
    f.content:SetHeight(math.max(1,#players*90)); f:Show(); MPL.UpdatePanelScroll(f)
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
    local name,class,_,_,_,_,_,_,_,role,_,_,_,_,_,specID=C_LFGList.GetApplicantMemberInfo(appID,index)
    MPL.RecordApplicant(name,role,specID,class)
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
