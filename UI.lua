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
    local reset=tonumber(errorText:match("API reset at (%d+); ")) or (retryAt and retryAt>0 and retryAt)
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
    for _,key in ipairs({L["Неверный формат ответа логов"],L["Пустой или незавершённый импорт"],
        L["Отсутствует обязательное поле"],L["Некорректное число"],L["Некорректная запись профиля"],
        L["Некорректная запись данжа"],L["Некорректное завершение профиля"],L["Некорректный результат загрузки"],
        L["Некорректное описание ошибки"],L["Неполная запись DPS/HPS"],L["Неизвестный регион"],
        L["Неизвестная метрика"],L["Неизвестная роль"],L["Метрика не соответствует роли"],
        L["Дублирующийся профиль"],L["Повторный результат загрузки"],L["Слишком большой импорт (максимум 500 КБ)"],
        L["Слишком много профилей"],L["Слишком много данжей"],L["Ошибка импорта"],L["Не удалось обработать ответ"]}) do
        if errorText==L[key] then return details(L["Ошибка чтения данных"]) end
    end
    if errorText:find(L["Неизвестная строка импорта; строка "],1,true) then
        return details(L["Ошибка чтения данных"])
    end
    return errorText
end
MPL.CompanionError=companionError
local function readableFont(field)
    -- Latin clients use Friz Quadrata without Cyrillic glyphs. Player/realm
    -- names can still be Russian; use WoW's matching Cyrillic face locally.
    -- Keep Asian, Russian and addon-customized fonts and all text styling.
    local font,size,flags=field:GetFont()
    if font and font:lower():gsub("/","\\")=="fonts\\frizqt__.ttf" then
        field:SetFont("Fonts\\FRIZQT___CYR.TTF",size,flags)
    end
end
local function label(parent, x, y, width, text, template)
    local f = parent:CreateFontString(nil, "OVERLAY", template or "GameFontHighlightSmall")
    readableFont(f)
    f:SetPoint("TOPLEFT", x, y); f:SetWidth(width); f:SetJustifyH("LEFT"); f:SetText(text or "")
    return f
end
local function button(parent, text, x, y, width, callback)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetSize(width, 24); b:SetPoint("BOTTOMLEFT", x, y); b:SetText(text); b:SetScript("OnClick", callback)
    return b
end
local function flatButton(parent,text,width,height,callback,primary)
    local b=CreateFrame("Button",nil,parent,"BackdropTemplate")
    b:SetSize(width,height)
    b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    b:SetBackdropColor(primary and 0.24 or 0.12,primary and 0.13 or 0.10,primary and 0.32 or 0.16,1)
    b:SetBackdropBorderColor(0.40,0.29,0.51,1)
    local caption=label(b,0,0,width,text,"GameFontHighlightSmall")
    caption:ClearAllPoints(); caption:SetPoint("LEFT",8,0); caption:SetPoint("RIGHT",-8,0)
    caption:SetJustifyH("CENTER"); caption:SetWordWrap(false)
    b:SetFontString(caption)
    b.caption=caption
    b:SetNormalFontObject("GameFontHighlightSmall")
    b:SetHighlightFontObject("GameFontHighlightSmall"); b:SetDisabledFontObject("GameFontDisableSmall")
    b:SetText(text); b:SetScript("OnClick",callback)
    b.hover=b:CreateTexture(nil,"HIGHLIGHT"); b.hover:SetAllPoints()
    b.hover:SetColorTexture(1,1,1,0.08)
    return b
end
local function profileButton(parent,text,x,y,width,callback,primary)
    local b=flatButton(parent,text,width,26,callback,primary)
    b:SetPoint("BOTTOMLEFT",x,y)
    return b
end
local function layoutProfileActions(f)
    local applicant=type(f.applicant)=="table"
    if applicant then f.lookupExpanded=false end
    local expanded=f.lookupExpanded==true
    local drawer=expanded and 44 or 0
    f.lookup:SetShown(expanded); f.lookupButton:SetShown(expanded); f.lookupDivider:SetShown(expanded)
    if not expanded then f.lookup:ClearFocus() end
    f.searchButton:SetShown(not applicant)
    f.searchButton:SetText(expanded and L["Свернуть поиск"] or L["Найти персонажа…"])
    f.wclButton:ClearAllPoints(); f.wclButton:SetPoint("BOTTOMLEFT",20,20+drawer)
    f.searchButton:ClearAllPoints(); f.searchButton:SetPoint("LEFT",f.wclButton,"RIGHT",10,0)
    if not f.centerLoadButton then
        f.loadButton:ClearAllPoints(); f.loadButton:SetPoint("BOTTOMRIGHT",-40,applicant and 56 or 20+drawer)
    end
    return drawer
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
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart",function(self)
        if self.mplProfileWindow==true and MPL.AppearanceValue and MPL.AppearanceValue("locked",false) then return end
        self:StartMoving()
    end)
    f:SetScript("OnDragStop",function(self)
        self:StopMovingOrSizing()
        if self.mplProfileWindow==true and not self.appearanceSample and MPL.SaveAppearanceWindowPosition then MPL.SaveAppearanceWindowPosition(self) end
    end)
    f.title=label(f, 20, -16, width-60, title, "GameFontNormalLarge")
    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -2, -2)
    f.closeButton=close
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
    if MPL.FormatAppearancePercent then return MPL.FormatAppearancePercent(value,stale) end
    local text=MPL.Percent(value,stale):gsub("%%|r$","|r")
    return text
end
local function percentileRGB(value)
    local color=(MPL.AppearancePercentColor or MPL.PercentColor)(value)
    if not color then return 225/255,242/255,245/255 end
    return tonumber(color:sub(1,2),16)/255,tonumber(color:sub(3,4),16)/255,tonumber(color:sub(5,6),16)/255
end
local function emphasizeNumber(field,r,g,b,enabled)
    -- A small same-color stroke adds weight without changing the game font.
    field:SetShadowColor(r,g,b,enabled and 1 or 0)
    field:SetShadowOffset(enabled and 0.5 or 0,0)
end
local function dungeonNameFont(field)
    local font,size,flags=field:GetFont()
    -- Enlarge only dungeon names, keeping the original client font and flags.
    if font and type(size)=="number" then
        field:SetFont(font,size+2,flags)
    end
end
local profileTableLayout={
    rowHeight=26,headerHeight=40,headerBand=20,nameInset=30,namePadding=36,
    iconSize=20,scoreIconSize=16,scorePadding=30,titleY=5,
}
local function renderLevelDigits(row,value,r,g,b)
    local cell=row.cells[2]
    local text=tostring(value)
    if type(row.levelDigits)~="table" then row.levelDigits={} end
    for _,digit in ipairs(row.levelDigits) do digit:Hide() end
    row.levelDigitWidth=nil
    cell:Show()
    -- Use the font's native spacing unless decimal-place alignment was selected.
    if not MPL.AppearanceValue or MPL.AppearanceValue("levelDigits","natural")~="aligned" then cell:SetAlpha(1); return end
    if not text:match("^%d+$") then cell:SetAlpha(1); return end
    local function digitAt(index)
        local digit=row.levelDigits[index]
        if not digit then
            digit=label(row,0,-3,1)
            digit:SetHeight(20); digit:SetJustifyV("MIDDLE"); digit:SetJustifyH("LEFT")
            digit:SetWordWrap(false); digit:SetNonSpaceWrap(false)
            row.levelDigits[index]=digit
        end
        if MPL.StyleProfileFont then MPL.StyleProfileFont(digit,"numbers") end
        return digit
    end
    -- Keep the native game font, but give every decimal place the width of
    -- its widest digit. A narrow "1" can no longer move the preceding "2".
    local measure=digitAt(1)
    local step=0
    for digit=0,9 do
        measure:SetText(tostring(digit))
        local width=measure:GetUnboundedStringWidth()
        if type(width)=="number" then step=math.max(step,width) end
    end
    local _,fontSize=cell:GetFont()
    step=math.max(1,math.ceil(step>0 and step or (fontSize or 10)*0.6))+(MPL.AppearanceValue and MPL.AppearanceValue("digitGap",0) or 0)
    row.levelDigitWidth=#text*step
    for index=1,#text do
        local digit=digitAt(index)
        digit:SetText(text:sub(index,index)); digit:SetWidth(step)
        digit:ClearAllPoints(); digit:SetPoint("TOPRIGHT",cell,"TOPRIGHT",-(#text-index)*step,0)
        -- Narrow glyphs such as "1" must not acquire a second colored stroke.
        digit:SetTextColor(r,g,b); emphasizeNumber(digit,r,g,b,false); digit:Show()
    end
    -- Retain the full value for measurement, but remove both its glyphs and
    -- shadow. Alpha alone leaves a second text representation below the slots.
    emphasizeNumber(cell,r,g,b,false)
    cell:SetAlpha(0)
    cell:Hide()
end
local function gridLine(parent,x,y,width,height)
    local texture=parent:CreateTexture(nil,"ARTWORK")
    texture:SetPoint("TOPLEFT",x,y); texture:SetSize(width,height)
    texture:SetColorTexture(0.20,0.20,0.20,1)
    return texture
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
local layoutProfileBanner
local function setProfileFooter(f,text)
    f.footer:SetText(text)
    if layoutProfileBanner then
        layoutProfileBanner(f,type(f.profile)=="table" and f.profile or nil)
    end
end
MPL.SetProfileFooter=setProfileFooter
local function metricTab(f,metric,x)
    local b=CreateFrame("Button",nil,f,"BackdropTemplate")
    b:SetSize(86,28); b:SetPoint("TOPLEFT",x,-112)
    b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    b:SetBackdropBorderColor(0.27,0.27,0.27,1)
    b.caption=label(b,8,-7,70,metric:upper()); b.caption:SetJustifyH("CENTER")
    b.caption:ClearAllPoints(); b.caption:SetPoint("LEFT",8,0); b.caption:SetPoint("RIGHT",-8,0)
    b.caption:SetJustifyV("MIDDLE")
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
            f.metricNoticeFooter=f.metricNoticeFooter or f.footer:GetText() or ""
            setProfileFooter(f,metric=="hps" and L["Healing data loads on request. Click Load HPS."]
                or L["Damage data loads on request. Click Load DPS."])
        elseif f.metricNoticeFooter then
            setProfileFooter(f,f.metricNoticeFooter); f.metricNoticeFooter=nil
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
    b.arrow=CreateFrame("Frame",nil,b); b.arrow:SetSize(16,16); b.arrow:SetPoint("RIGHT",-10,0)
    -- A plain chevron, matching the flat selector rather than a framed Blizzard icon.
    for i=1,4 do
        local stripe=b.arrow:CreateTexture(nil,"ARTWORK")
        stripe:SetColorTexture(0.9,0.85,0.96,1); stripe:SetSize(10-i*2,1)
        stripe:SetPoint("TOP",0,-4-i)
    end
    b:SetScript("OnClick",callback)
    b:SetScript("OnEnter",function(self)
        if not self.canSelectSpecs then return end
        if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(self,true)
        else self:SetBackdropColor(0.22,0.15,0.31,1); self:SetBackdropBorderColor(0.86,0.67,1,1) end
        GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
        GameTooltip:AddLine(L["Выбрать специализацию логов"],1,1,1)
        GameTooltip:AddLine(L["Основной спек отмечен в списке. Переключение использует сохранённые логи; отсутствующий профиль можно загрузить."],0.85,0.85,0.85,true)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave",function(self)
        if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(self,false)
        else self:SetBackdropColor(0.12,0.09,0.18,1); self:SetBackdropBorderColor(0.64,0.45,0.83,1) end
        GameTooltip:Hide()
    end)
    return b
end
local function toggleSpecializationMenu(f,anchor,builder)
    local menu=f.specMenu
    if menu and menu:IsShown() and menu.activeAnchor==anchor then menu:Hide(); return end
    if not menu then
        menu=CreateFrame("Frame",nil,f,"BackdropTemplate")
        menu:Hide(); f.specMenu=menu; menu.rows={}
        menu:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
        menu:SetFrameStrata("DIALOG"); menu:SetClampedToScreen(true); menu:EnableMouse(true)
        menu.title=label(menu,12,-10,280,"", "GameFontHighlightSmall")
        menu.divider=menu:CreateTexture(nil,"ARTWORK")
        menu:SetScript("OnShow",function(self)
            self:RegisterEvent("GLOBAL_MOUSE_DOWN"); self:RegisterEvent("PLAYER_REGEN_DISABLED")
        end)
        menu:SetScript("OnHide",function(self)
            self:UnregisterEvent("GLOBAL_MOUSE_DOWN"); self:UnregisterEvent("PLAYER_REGEN_DISABLED")
        end)
        menu:SetScript("OnEvent",function(self,event)
            if event=="PLAYER_REGEN_DISABLED" or (not self:IsMouseOver() and not self.activeAnchor:IsMouseOver()) then self:Hide() end
        end)
        menu:EnableKeyboard(true); menu:SetPropagateKeyboardInput(true)
        menu:SetScript("OnKeyDown",function(self,key)
            self:SetPropagateKeyboardInput(key~="ESCAPE")
            if key=="ESCAPE" then self:Hide() end
        end)
        f:HookScript("OnHide",function() menu:Hide() end)
    end
    for _,row in ipairs(menu.rows) do row:Hide() end
    menu.title:Hide(); menu.divider:Hide(); menu.entries={}; menu.activeAnchor=anchor
    local function palette(key,fallback)
        local c=MPL.AppearanceValue and MPL.AppearanceValue(key) or fallback
        return c[1],c[2],c[3],c[4] or 1
    end
    menu:SetBackdropColor(palette("buttonColor",{.12,.10,.16,1}))
    menu:SetBackdropBorderColor(palette("borderColor",{.4,.29,.51,1}))
    local rowIndex=0
    local root={}
    function root:CreateTitle(text)
        menu.entries[#menu.entries+1]={kind="title",text=text,field=menu.title}
        menu.title:SetText(text); menu.title:Show()
        if MPL.StyleProfileFont then MPL.StyleProfileFont(menu.title,"button") end
        menu.title:SetTextColor(palette("textColor",{.9,.94,.96,1}))
    end
    local function item(kind,text,selected,callback)
        rowIndex=rowIndex+1
        local row=menu.rows[rowIndex]
        if not row then
            row=flatButton(menu,"",280,30,nil); menu.rows[rowIndex]=row
            row.caption:ClearAllPoints(); row.caption:SetPoint("LEFT",14,0); row.caption:SetPoint("RIGHT",-10,0)
            row.caption:SetJustifyH("LEFT"); row.caption:SetWordWrap(true)
            row.marker=row:CreateTexture(nil,"OVERLAY")
            row.marker:SetPoint("TOPLEFT",4,-6); row.marker:SetPoint("BOTTOMLEFT",4,6); row.marker:SetWidth(3)
        end
        local entry={kind=kind,text=text,selected=selected,callback=callback,button=row}
        menu.entries[#menu.entries+1]=entry
        row:SetEnabled(true); row:SetAlpha(1)
        row:SetText(text); row.caption:SetText(text)
        if MPL.StyleAppearanceButton then MPL.StyleAppearanceButton(row,false) end
        local checked=selected and selected() or false
        row.marker:SetColorTexture(palette("accentColor",{.64,.45,.83,1})); row.marker:SetShown(checked)
        row.caption:SetTextColor(palette("buttonTextColor",{1,1,1,1}))
        local function paint(hover)
            if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(row,hover,checked) end
        end
        row:SetScript("OnEnter",function()
            paint(true)
            if entry.tooltip and MPL.GetOption("tooltips") then
                GameTooltip:SetOwner(row,"ANCHOR_RIGHT")
                GameTooltip:AddLine(entry.tooltip,.85,.85,.85,true); GameTooltip:Show()
            end
        end)
        row:SetScript("OnLeave",function()
            paint(false)
            if entry.tooltip then GameTooltip:Hide() end
        end)
        row:SetScript("OnClick",function()
            if row:IsEnabled()==false then return end
            menu:Hide(); callback()
        end)
        function entry:SetEnabled(enabled)
            row:SetEnabled(enabled)
            row:SetAlpha(enabled and 1 or .65)
            if MPL.StyleAppearanceButton then MPL.StyleAppearanceButton(row,not enabled) end
            row.caption:SetTextColor(palette(enabled and "buttonTextColor" or "mutedColor",enabled and {1,1,1,1} or {.5,.5,.5,1}))
            paint(false)
        end
        paint(false); row:Show()
        return entry
    end
    function root:CreateRadio(text,selected,callback) item("radio",text,selected,callback) end
    function root:CreateButton(text,callback) return item("button",text,nil,callback) end
    function root:CreateDivider()
        menu.entries[#menu.entries+1]={kind="divider",field=menu.divider}
        menu.divider:SetColorTexture(palette("borderColor",{.4,.29,.51,1})); menu.divider:Show()
    end
    builder(nil,root)
    local width=260
    for _,entry in ipairs(menu.entries) do
        local caption=entry.button and entry.button.caption or (entry.kind=="title" and entry.field)
        if caption then width=math.max(width,(caption:GetUnboundedStringWidth() or 0)+32) end
    end
    local scale=menu:GetEffectiveScale() or f:GetScale() or 1
    width=math.min(width,math.max(180,UIParent:GetWidth()/scale-24))
    local y=10
    for _,entry in ipairs(menu.entries) do
        if entry.button then
            local row=entry.button
            local _,size=row.caption:GetFont()
            local line=math.max(18,(size or 10)+4)
            local height=math.max(30,math.ceil((row.caption:GetUnboundedStringWidth() or 0)/(width-48))*line+12)
            row:ClearAllPoints(); row:SetPoint("TOPLEFT",8,-y); row:SetSize(width-16,height)
            y=y+height+4
        elseif entry.kind=="title" then
            local size=type(entry.field.mplAppliedFontSize)=="number" and entry.field.mplAppliedFontSize or 10
            local line=math.max(18,size+4)
            local height=math.ceil((entry.field:GetUnboundedStringWidth() or 0)/(width-24))*line
            entry.field:SetWidth(width-24); entry.field:SetHeight(height); y=y+height+8
        else
            entry.field:ClearAllPoints(); entry.field:SetPoint("TOPLEFT",8,-y-2); entry.field:SetSize(width-16,1); y=y+9
        end
    end
    menu:SetSize(width,y+6); menu:SetFrameLevel(f:GetFrameLevel()+30)
    menu:ClearAllPoints(); menu:SetPoint("TOPLEFT",anchor,"BOTTOMLEFT",0,-4); menu:Show()
end

local function buildPanel(frameName)
    local f = window(frameName or "MPlusLogsWindow", "MPlusLogs — Warcraft Logs", 940, 700)
    f.profileWindowTitle="MPlusLogs — Warcraft Logs"
    f.mplProfileWindow=true
    f:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1,insets={left=1,right=1,top=1,bottom=1}})
    f:SetBackdropColor(0,0,0,1); f:SetBackdropBorderColor(0.27,0.27,0.27,1)
    f.closeButton:Hide()
    f.closeButton=flatButton(f,"",24,24,function() f:Hide() end)
    f.closeButton:SetPoint("TOPRIGHT",-5,-5)
    for _,angle in ipairs({math.pi/4,-math.pi/4}) do
        local stroke=f.closeButton:CreateTexture(nil,"ARTWORK")
        stroke:SetColorTexture(0.94,0.92,0.98,1)
        stroke:SetSize(19,2); stroke:SetPoint("CENTER")
        stroke:SetRotation(angle)
    end
    f.lookupExpanded=false; f.centerLoadButton=false; f.specMenu=false
    f.titleFill=panelFill(f,1,-1,938,36,0.105,0.06,0.12)
    f.title:SetTextColor(0.9,0.94,0.96)
    if not frameName then
        local settings=flatButton(f,L["Settings"],104,22,function() MPL.OpenSettings() end)
        settings:SetSize(104,22); settings:SetPoint("TOPRIGHT",-38,-7)
        settings:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
        settings:SetBackdropColor(0.16,0.10,0.21,1)
        settings:SetBackdropBorderColor(0.40,0.29,0.51,1)
        settings.caption:ClearAllPoints(); settings.caption:SetPoint("CENTER"); settings.caption:SetJustifyH("CENTER")
        settings:SetScript("OnEnter",function()
            if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(settings,true)
            else settings:SetBackdropBorderColor(0.75,0.55,0.96,1) end
            settings.caption:SetTextColor(1,0.82,0)
        end)
        settings:SetScript("OnLeave",function()
            if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(settings,false)
            else settings:SetBackdropBorderColor(0.40,0.29,0.51,1) end
            settings.caption:SetTextColor(1,1,1)
        end)
        settings:SetShown(not MPL.GetOption("hideLogSettings"))
        f.settingsButton=settings
        f.appearanceButton=flatButton(f,L["Appearance"],120,22,function()
            if MPL.OpenAppearanceSettings then MPL.OpenAppearanceSettings() end
        end)
        f.appearanceButton:SetPoint("TOPRIGHT",-150,-7)
        f.appearanceButton:Show()
        f.appearanceButton:SetScript("OnEnter",function(self)
            if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(self,true) end
            if GameTooltip then
                GameTooltip:SetOwner(self,"ANCHOR_BOTTOM")
                GameTooltip:SetText(L["Customize window appearance…"])
                GameTooltip:AddLine(L["Choose styles and colors, adjust fonts and table columns, and preview changes before saving."],1,1,1,true)
                GameTooltip:Show()
            end
        end)
        f.appearanceButton:SetScript("OnLeave",function(self)
            if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(self,false) end
            if GameTooltip then GameTooltip:Hide() end
        end)
        if MPL.CreateTutorialHelpButton then
            f.tutorialButton=MPL.CreateTutorialHelpButton(f,function()
                if f.profile then return "profile" end
                return MPL.NeedsCompanionIntro() and "companion" or "exchange"
            end,"header")
            f.tutorialButton:SetPoint("TOPRIGHT",-278,-7)
        end
        f.title:SetWidth(460)
    end
    f.character = label(f,20,-48,400,"","GameFontHighlightLarge")
    f.character:SetWordWrap(false)
    f.currentSpec=CreateFrame("Frame",nil,f,"BackdropTemplate")
    f.currentSpec:SetPoint("TOPRIGHT",-40,-39); f.currentSpec:SetSize(460,32)
    f.currentSpec:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    f.currentSpec:SetBackdropColor(0,0,0,0)
    f.currentSpec:SetBackdropBorderColor(0,0,0,0)
    f.currentSpec.icon=f.currentSpec:CreateTexture(nil,"ARTWORK")
    f.currentSpec.icon:SetPoint("TOPLEFT",5,-4); f.currentSpec.icon:SetSize(24,24)
    f.currentSpec.caption=label(f.currentSpec,37,-3,415,L["Текущая специализация"],"GameFontHighlight")
    f.currentSpec.caption:SetTextColor(0.72,0.72,0.75)
    f.currentSpec.caption:SetWordWrap(false)
    f.currentSpec.name=label(f.currentSpec,37,-16,415,"","GameFontHighlightLarge")
    local specNameFont,_,specNameFlags=f.currentSpec.name:GetFont()
    if specNameFont then f.currentSpec.name:SetFont(specNameFont,14,specNameFlags) end
    f.currentSpec.name:SetTextColor(225/255,242/255,245/255)
    f.currentSpec.name:SetWordWrap(false)
    f.logSpec=label(f.currentSpec,28,-28,300,"","GameFontHighlight")
    f.logSpec:SetWordWrap(true); f.logSpec:SetNonSpaceWrap(true); f.logSpec:Hide()
    f.contextFill=panelFill(f,20,-80,880,26,0.105,0.06,0.12)
    f.context = label(f,30,-87,860)
    f.extraLogsButton=flatButton(f,"",24,24,function(self)
        if GameTooltip then GameTooltip:Hide() end
        local open=f.specButton:GetScript("OnClick")
        if open then open(self or f.extraLogsButton) end
    end)
    f.extraLogsButton:SetScript("OnEnter",function(self)
        if not GameTooltip then return end
        GameTooltip:SetOwner(self,"ANCHOR_BOTTOM")
        GameTooltip:SetText(L["Other specialization logs"])
        GameTooltip:AddLine(L["Выбрать специализацию логов"],1,1,1,true)
        GameTooltip:Show()
    end)
    f.extraLogsButton:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
    f.extraLogsButton.arrow={}
    for i=1,4 do
        local stroke=f.extraLogsButton:CreateTexture(nil,"ARTWORK")
        stroke:SetColorTexture(.85,.82,.9,1); stroke:SetSize(1,9-i*2)
        f.extraLogsButton.arrow[i]=stroke
    end
    f.specButton=specSelector(f,function(anchor)
        if not f.specButton.canSelectSpecs then return end
        if InCombatLockdown() then return end
        local role=MPL.roles and MPL.roles[MPL.Key(f.name,f.realm)]
        toggleSpecializationMenu(f,anchor or f.specButton,function(_,root)
            root:CreateTitle(L["Выбрать специализацию логов"])
            local main=MPL.MainProfileSpec(f.name,f.realm,role)
            local specs={"All specs"}
            for _,spec in ipairs(MPL.ProfileSpecs(f.name,f.realm)) do specs[#specs+1]=spec end
            for _,spec in ipairs(specs) do
                local caption=MPL.SpecLabel(spec,f.class)
                if spec==main then caption=caption..L[" — основной"] end
                local stored=MPL.GetProfile(f.name,f.realm,spec)
                if stored then caption=caption..L[" — загружено"] else caption=caption..L[" — not loaded"] end
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
            local state=MPL.SpecDiscoveryState(f.name,f.realm,f.viewMetric)
            local aggregate=MPL.GetProfile(f.name,f.realm,"All specs")
            -- Older replies already carried an explicit available-spec list,
            -- even though the old discovery action did not retain a receipt.
            if (not state or state=="stale") and aggregate and type(aggregate.availableSpecs)=="table"
                and aggregate.metric==f.viewMetric and not MPL.IsProfileStale(aggregate) then state="complete" end
            local caption=state=="pending" and L["Checking specializations..."]
                or state=="complete" and (#specs>2 and L["Specialization list loaded"] or L["No other specializations found"])
                or state=="stale" and L["Refresh specialization list"] or L["Find other specializations"]
            local action=root:CreateButton(caption,function()
                -- A targeted spec discovery must not expand back into the
                -- party batch or change the user's selected log filter.
                MPL.ShowDownload(f.name,f.realm,aggregate,f.applicant,false,true,nil,nil,f.viewMetric,nil,nil,true)
            end)
            action:SetEnabled(state~="pending" and state~="complete")
            if state=="complete" then action.tooltip=L["Other specializations were checked. Only recorded specializations are listed."] end
        end)
    end)
    f.context:SetWidth(540)
    f.metricTabs={dps=metricTab(f,"dps",20),hps=metricTab(f,"hps",112)}
    f.scoreLabel=label(f,64,-163,310,L["Рейтинг Mythic+"],"GameFontHighlight")
    f.scoreLabel:SetJustifyH("CENTER")
    f.scoreValue=label(f,64,-189,310,"","GameFontHighlightLarge")
    f.scoreValue:SetJustifyH("CENTER"); f.scoreValue:SetHeight(36)
    f.ratingGroup=CreateFrame("Frame",nil,f,"BackdropTemplate")
    f.ratingGroup:SetBackdrop({edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    f.ratingGroup:SetBackdropBorderColor(.30,.24,.34,1)
    local font=f.scoreValue:GetFont()
    if font then f.scoreValue:SetFont(font,22,"") end
    f.summary=label(f,520,-159,370)
    f.medianSummary=label(f,520,-181,370)
    f.runSummary=label(f,520,-203,370)
    f.summaryLabels={}; f.summaryHelp={}; f.summarySeparators={}
    for i=1,3 do
        f.summaryLabels[i]=label(f,20,0,260)
        f.summaryLabels[i]:SetWordWrap(false)
        f.summaryLabels[i]:Hide()
        local help=CreateFrame("Frame",nil,f)
        help:SetFrameLevel(f:GetFrameLevel()+2); help:EnableMouse(true); help:Hide()
        help:SetScript("OnEnter",function(self)
            if not MPL.GetOption("tooltips") then return end
            GameTooltip:SetOwner(self,"ANCHOR_TOP")
            GameTooltip:SetText(self.tooltipTitle or L["Summary details"],1,1,1)
            GameTooltip:AddLine(self.tooltipDetail or "",.85,.85,.85,true)
            GameTooltip:Show()
        end)
        help:SetScript("OnLeave",function() GameTooltip:Hide() end)
        help:SetScript("OnHide",function(self) if GameTooltip:IsOwned(self) then GameTooltip:Hide() end end)
        f.summaryHelp[i]=help
    end
    f.specRanks=label(f,20,-233,880); f.specRanks:SetJustifyH("CENTER")
    f.specRanks:SetHeight(18); f.specRanks:SetJustifyV("MIDDLE")
    f.specRankEntries={}
    f.staleBanner=CreateFrame("Frame",nil,f,"BackdropTemplate")
    f.staleBanner:SetPoint("TOPLEFT",20,-254); f.staleBanner:SetSize(880,28)
    f.staleBanner:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    f.staleBanner:SetBackdropColor(0.12,0.075,0.015,1)
    f.staleBanner:SetBackdropBorderColor(0.65,0.40,0.06,1)
    f.staleBanner.icon=f.staleBanner:CreateTexture(nil,"ARTWORK")
    f.staleBanner.icon:SetSize(20,20); f.staleBanner.icon:SetPoint("LEFT",10,0)
    f.staleBanner.icon:SetTexture("Interface/AddOns/MPlusLogs/assets/stale-clock.tga")
    f.staleBanner.message=label(f.staleBanner,40,-7,828,"","GameFontHighlight")
    f.staleBanner.message:SetWordWrap(true)
    f.staleBanner.message:SetJustifyV("TOP")
    f.staleBanner:Hide()
    f.source = label(f,20,-566,900)
    f.note = label(f,20,-586,900)
    local headings = {L["Подземелье"],L["Уровень"],L["Время"],L["Runs"],L["Очки"],L["Rank"],L["Best DPS"],L["Best %"],L["Median %"]}
    f.columns={0,242,292,358,414,484,554,684,768}
    f.widths={242,50,66,56,70,70,130,84,112}
    f.headings={}; f.sortButtons={}
    f.sortColumn=false; f.sortAscending=false; f.sortRefresh=false
    f.tableHeader=CreateFrame("Frame",nil,f)
    f.tableHeader:SetPoint("TOPLEFT",20,-254); f.tableHeader:SetSize(880,40)
    f.tableDecor={panelFill(f.tableHeader,0,0,880,40,18/255,18/255,18/255)}
    f.primaryGroup=label(f.tableHeader,414,-5,140,L["Score"]); f.primaryGroup:SetJustifyH("CENTER")
    f.secondaryGroup=label(f.tableHeader,554,-5,326,L["DPS by Level"]); f.secondaryGroup:SetJustifyH("CENTER")
    f.primaryGroup:SetWordWrap(false); f.secondaryGroup:SetWordWrap(false)
    for i, text in ipairs(headings) do
        local column=i
        local sortButton=CreateFrame("Button",nil,f.tableHeader)
        sortButton:SetPoint("TOPLEFT",f.columns[i]+1,-21); sortButton:SetSize(f.widths[i]-2,18)
        local hover=sortButton:CreateTexture(nil,"HIGHLIGHT")
        hover:SetAllPoints(); hover:SetColorTexture(1,1,1,0.08)
        sortButton:SetScript("OnClick",function()
            if type(f.profile)~="table" then return end
            f.sortAscending=f.sortColumn==column and not f.sortAscending or false
            f.sortColumn=column
            if MPL.ProfileColumnID then f.sortId=MPL.ProfileColumnID(column) end
            if f.sortRefresh then f.sortRefresh(f) else MPL.RenderProfileStats(f) end
        end)
        local heading=label(sortButton,3,-1,f.widths[i]-8,text)
        heading:SetHeight(18); heading:SetJustifyV("MIDDLE"); heading:SetWordWrap(false); heading:SetNonSpaceWrap(false)
        heading:SetJustifyH("CENTER"); heading:SetTextColor(0.93,0.93,0.93)
        sortButton.arrow=CreateFrame("Frame",nil,sortButton)
        sortButton.arrow:SetPoint("TOPLEFT",f.widths[i]-11,-7); sortButton.arrow:SetSize(7,4)
        sortButton.arrow.stripes={}
        for stripe=1,4 do
            local texture=sortButton.arrow:CreateTexture(nil,"OVERLAY")
            texture:SetColorTexture(1,0.82,0,1); texture:SetSize(9-stripe*2,1)
            sortButton.arrow.stripes[stripe]=texture
        end
        sortButton.arrow:Hide()
        f.sortButtons[i]=sortButton
        f.headings[i]=heading
        if MPL.AppearanceValue then
            sortButton:SetScript("OnEnter",function(self)
                GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
                GameTooltip:AddLine(heading:GetText(),1,1,1,true)
                GameTooltip:Show()
            end)
            sortButton:SetScript("OnLeave",function() GameTooltip:Hide() end)
        end
    end
    local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT",20,-294); scroll:SetPoint("BOTTOMRIGHT",-40,145)
    scroll:SetSize(880,217)
    local content = CreateFrame("Frame", nil, scroll); content:SetSize(880,1); scroll:SetScrollChild(content)
    f.content, f.scroll, f.rows = content, scroll, {}
    scroll:HookScript("OnScrollRangeChanged",function() MPL.UpdatePanelScroll(f) end)
    scroll:HookScript("OnSizeChanged",function() MPL.UpdatePanelScroll(f) end)
    f.metricHeading=f.headings[7]
    f.tableElements={f.primaryGroup,f.secondaryGroup,f.scoreLabel,f.scoreValue,f.summary,f.medianSummary,f.runSummary}
    f.footer = label(f,20,-606,900)
    f.wclButton=profileButton(f,L["Ссылка WCL"],20,20,120,function() MPL.CopyURL(f.name,f.realm,f.profile) end)
    f.loadButton=profileButton(f,L["Обновить M+ логи"],730,20,170,function()
        if type(f.searchMember)=="table" and IsShiftKeyDown and IsShiftKeyDown() then
            MPL.ShowSearchGroupLogs(f.searchMember.searchResultID,true); return
        end
        -- Recover a missed redraw from saved logs before cooldowns or another
        -- exchange can prevent this tab from displaying an imported profile.
        if not f.searchMember then
            local cached=MPL.GetProfile(f.name,f.realm)
            if cached and cached~=f.profile then
                local metric=f.viewMetric
                MPL.ShowProfile(f.name,f.realm,f.applicant,true,true)
                if f.profile then
                    f.viewMetric=metric; MPL.RenderProfileStats(f); MPL.UpdateProfileLoadButton()
                    return
                end
            end
        end
        if missingMetric(f.profile,f.viewMetric) then
            MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant,false,false,nil,nil,f.viewMetric); return
        end
        if type(f.searchMember)=="table" and (not f.searchMember.loaded
            or MPL.SearchGroupHasPendingProfiles(f.searchMember.searchResultID)) then
            MPL.ShowSearchGroupLogs(f.searchMember.searchResultID); return
        end
        if type(f.searchMember)=="table" and MPL.ProfileNeedsDisplayRefresh(f.profile) then
            MPL.ShowSearchGroupLogs(f.searchMember.searchResultID,false,true); return
        end
        local state=MPL.GetProfileState(f.name,f.realm,f.selectedSpec)
        if state and state.reason=="hidden" then return end
        if MPL.ProfileNeedsDisplayRefresh(f.profile) then
            -- Fetch the missing presentation fields from the Companion cache;
            -- this is not a forced WCL refresh and needs no five-minute wait.
            MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant,nil,false,nil,nil,nil,nil,true); return
        end
        local cooling,remaining=MPL.UpdateProfileLoadButton()
        if cooling then
            f.cooldownNotice=true
            local grouped=type(f.groupPlayers)=="table" and #f.groupPlayers>1
            local key=grouped and L["Обновить логи группы можно через %d мин. %d сек."] or L["Обновить логи можно через %d мин. %d сек."]
            setProfileFooter(f,string.format(L[key],math.floor(remaining/60),remaining%60))
            return
        end
        MPL.ShowDownload(f.name,f.realm,f.profile,f.applicant,nil,true)
    end,true)
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
                    local key=grouped and L["Обновить логи группы можно через %d мин. %d сек."] or L["Обновить логи можно через %d мин. %d сек."]
                    setProfileFooter(f,string.format(L[key],math.floor(remaining/60),remaining%60))
                else
                    f.cooldownNotice=false; setProfileFooter(f,"")
                end
            end
        end
    end)
    f.emptyMessage=label(f,80,-300,780,L["Данные этого персонажа ещё не загружены."],"GameFontHighlightLarge")
    f.emptyMessage:SetJustifyH("CENTER")
    f.lookupDivider=f:CreateTexture(nil,"ARTWORK")
    f.lookupDivider:SetColorTexture(0.27,0.22,0.32,1); f.lookupDivider:SetHeight(1)
    f.lookupDivider:SetPoint("BOTTOMLEFT",20,55); f.lookupDivider:SetPoint("BOTTOMRIGHT",-40,55)
    f.lookup = CreateFrame("EditBox", nil, f, "BackdropTemplate")
    f.lookup:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    f.lookup:SetBackdropColor(0.06,0.05,0.08,1); f.lookup:SetBackdropBorderColor(0.40,0.29,0.51,1)
    f.lookup:SetFontObject("GameFontHighlightSmall"); f.lookup:SetTextInsets(8,8,0,0)
    f.lookup:SetSize(680,26); f.lookup:SetPoint("BOTTOMLEFT",20,20); f.lookup:SetAutoFocus(false)
    f.lookup:SetScript("OnEscapePressed",function(self)
        self:ClearFocus(); f.lookupExpanded=false; MPL.RenderProfileStats(f)
    end)
    local function lookup() MPL.ShowProfile(strtrim(f.lookup:GetText())); f.lookup:ClearFocus() end
    f.lookup:SetScript("OnEnterPressed",lookup)
    f.lookupButton=profileButton(f,L["Показать профиль"],710,20,190,lookup)
    f.lookupButton:ClearAllPoints(); f.lookupButton:SetPoint("BOTTOMRIGHT",-40,20)
    f.lookupButton:SetScript("OnEnter",function(self)
        GameTooltip:SetOwner(self,"ANCHOR_TOP")
        GameTooltip:AddLine(L["Профиль персонажа"],1,0.82,0)
        GameTooltip:AddLine(L["Введите Имя-Сервер в поле слева.\nЕсли профиль уже открыт, таблица останется прежней."],1,1,1,true)
        GameTooltip:Show()
    end)
    f.lookupButton:SetScript("OnLeave",function() GameTooltip:Hide() end)
    f.searchButton=profileButton(f,L["Найти персонажа…"],150,20,210,function()
        f.lookupExpanded=not f.lookupExpanded
        MPL.RenderProfileStats(f)
        if f.lookupExpanded then f.lookup:SetFocus(); f.lookup:HighlightText() end
    end)
    f:HookScript("OnHide",function()
        f.lookupExpanded=false; f.lookup:ClearFocus()
        if not frameName and MPL.downloadWindow then MPL.downloadWindow:Hide() end
    end)
    f.applicant=false; f.inviteSent=false
    f.inviteInfo=label(f,150,-660,530)
    f.inviteInfo:ClearAllPoints(); f.inviteInfo:SetPoint("BOTTOMLEFT",150,30)
    f.inviteButton=profileButton(f,L["Пригласить"],710,20,190,function()
        local ok,err=MPL.InviteFromProfile(f.applicant)
        if ok then f.inviteSent=true; MPL.UpdateProfileInvite()
        else f.inviteInfo:SetText(err); f.inviteButton:Disable() end
    end)
    f.inviteButton:ClearAllPoints(); f.inviteButton:SetPoint("BOTTOMRIGHT",-40,20)
    -- Optional scaling via BlizzMove; keep our existing drag handlers.
    if not frameName and BlizzMoveAPI and type(BlizzMoveAPI.RegisterAddOnFrames)=="function" then
        BlizzMoveAPI:RegisterAddOnFrames({MPlusLogs={
            MPlusLogsWindow={FrameReference=f,NonDraggable=true},
        }})
    end
    if MPL.RegisterAppearanceView then MPL.RegisterAppearanceView(f) end
    if not frameName and MPL.RestoreAppearanceWindowPosition then MPL.RestoreAppearanceWindowPosition(f) end
    return f
end

-- The walkthrough uses the real layout in an isolated window. It replaces all
-- request/navigation handlers before showing it; MPL.panel remains untouched.
function MPL.CreateTutorialProfileFrame(frameName)
    return buildPanel(frameName or "MPlusLogsTutorialProfile")
end

local function loadButtonFont(f,muted)
    if MPL.StyleAppearanceButton then MPL.StyleAppearanceButton(f.loadButton,muted)
    else f.loadButton:SetNormalFontObject(muted and "GameFontDisableSmall" or "GameFontHighlightSmall") end
end
function MPL.UpdateProfileLoadButton()
    local f=MPL.panel
    if not f then return false end
    if missingMetric(f.profile,f.viewMetric) then
        f.loadButton:Show(); f.loadButton:SetAlpha(1)
        loadButtonFont(f,false)
        f.loadButton:SetText(f.viewMetric=="hps" and L["Load HPS"] or L["Load DPS"])
        return false,0
    end
    f.loadButton:SetText(f.profile and L["Обновить M+ логи"] or L["Загрузить M+ логи"])
    if MPL.ProfileNeedsDisplayRefresh(f.profile) then
        f.loadButton:Show(); f.loadButton:SetAlpha(1)
        loadButtonFont(f,false)
        return false,0
    end
    if type(f.searchMember)=="table" and (not f.searchMember.loaded
        or MPL.SearchGroupHasPendingProfiles(f.searchMember.searchResultID)) then
        f.loadButton:Show(); f.loadButton:SetAlpha(1)
        loadButtonFont(f,false)
        return false,0
    end
    local state=MPL.GetProfileState(f.name,f.realm,f.selectedSpec)
    f.loadButton:SetShown(not (state and state.reason=="hidden"))
    local remaining=math.max(math.ceil(MPL.ProfileRefreshRemaining(f.profile or nil)),MPL.ProfileRetryRemaining(f.name,f.realm,f.selectedSpec))
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
                    remaining=math.min(remaining,math.max(math.ceil(MPL.ProfileRefreshRemaining(profile)),MPL.ProfileRetryRemaining(player.name,player.realm,spec)))
                end
            end
            if remaining==math.huge then remaining=0 end
        end
    end
    -- Keep mouse clicks so the muted button can explain the cooldown.
    f.loadButton:SetAlpha(cooling and 0.5 or 1)
    loadButtonFont(f,cooling)
    return cooling,remaining
end

function MPL.UpdateProfileInvite()
    local f=MPL.panel
    if not f then return end
    local fromApplicant=type(f.applicant)=="table"
    layoutProfileActions(f)
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
local function durationSeconds(value)
    if not value or value=="" then return nil end
    local hours,minutes,seconds=value:match("^(%d+):(%d%d):(%d%d)$")
    if hours then return tonumber(hours)*3600+tonumber(minutes)*60+tonumber(seconds) end
    minutes,seconds=value:match("^(%d+):(%d%d)$")
    if minutes then return tonumber(minutes)*60+tonumber(seconds) end
end
local function textWidth(field)
    local width=field:GetUnboundedStringWidth()
    return type(width)=="number" and math.ceil(width) or 0
end
local function layoutSpecRanks(f,total)
    if not f.specRanks:IsShown() then return end
    local function measuredWidth(field)
        local width=textWidth(field)
        return width>0 and width or #field:GetText()*6
    end
    local captionWidth=measuredWidth(f.specRanks)
    local width=captionWidth
    for _,entry in ipairs(f.specRankEntries) do
        if entry:IsShown() then
            local numberWidth=measuredWidth(entry.number)+1
            local symbolWidth=entry.hasIcon and 18 or measuredWidth(entry.specLabel)
            entry.number:SetWidth(numberWidth); entry.specLabel:SetWidth(symbolWidth)
            entry:SetWidth(numberWidth+4+symbolWidth)
            width=width+8+entry:GetWidth()
        end
    end
    local x=20+(total-width)/2
    f.specRanks:ClearAllPoints(); f.specRanks:SetPoint("TOPLEFT",x,-229); f.specRanks:SetWidth(captionWidth)
    x=x+captionWidth
    for _,entry in ipairs(f.specRankEntries) do
        if entry:IsShown() then
            entry:ClearAllPoints(); entry:SetPoint("TOPLEFT",x+8,-229)
            x=x+8+entry:GetWidth()
        end
    end
end
local function layoutProfileTable(f)
    if MPL.LayoutAppearanceTable then return MPL.LayoutAppearanceTable(f) end
    local style=profileTableLayout
    local widths={220,40,40,40,58,40,92,60,60}
    for i,heading in ipairs(f.headings) do
        -- Reserve room for the sort indicator even while it is hidden.
        local headingWidth=textWidth(heading)
        widths[i]=math.max(widths[i],headingWidth+24)
    end
    for _,row in ipairs(f.rows) do
        if row:IsShown() then
            for i,cell in ipairs(row.cells) do
                local padding=i==1 and style.namePadding or (i==5 and row.scoreSpecIcon:IsShown() and style.scorePadding or 12)
                widths[i]=math.max(widths[i],textWidth(cell)+padding)
                if i==2 and type(row.levelDigitWidth)=="number" then
                    widths[i]=math.max(widths[i],row.levelDigitWidth+padding)
                end
            end
        end
    end
    widths[6]=widths[6]+math.max(0,textWidth(f.primaryGroup)+16-widths[5]-widths[6])
    widths[9]=widths[9]+math.max(0,textWidth(f.secondaryGroup)+16-widths[7]-widths[8]-widths[9])
    -- Give spare space to names, keeping numeric columns compact.
    local minimum=0
    for _,width in ipairs(widths) do minimum=minimum+width end
    widths[1]=widths[1]+math.max(0,780-minimum)
    local total=0
    for i,width in ipairs(widths) do f.columns[i]=total; total=total+width end
    f.widths=widths; f.tableWidth=total
    f:SetWidth(total+60)
    f.titleFill:SetWidth(total+58); f.contextFill:SetWidth(total)
    f.tableHeader:SetSize(total,style.headerHeight); f.tableDecor[1]:SetSize(total,style.headerHeight)
    f.content:SetWidth(total); f.scroll:SetWidth(total)
    f.staleBanner:SetWidth(total); f.staleBanner.message:SetWidth(total-52)
    for _,field in ipairs({f.source,f.note,f.footer}) do field:SetWidth(total) end
    layoutSpecRanks(f,total)
    for i,field in ipairs({f.summary,f.medianSummary,f.runSummary}) do
        field:ClearAllPoints(); field:SetPoint("TOPLEFT",total-360,-137-i*22)
    end
    f.lookup:SetWidth(total-210); f.inviteInfo:SetWidth(total-350)
    for i,sortButton in ipairs(f.sortButtons) do
        sortButton:ClearAllPoints(); sortButton:SetPoint("TOPLEFT",f.columns[i]+1,-style.headerBand-1)
        sortButton:SetSize(widths[i]-2,style.headerBand-2)
        f.headings[i]:SetSize(widths[i]-8,style.headerBand-2)
        f.headings[i]:SetWordWrap(false); f.headings[i]:SetNonSpaceWrap(false)
        sortButton.arrow:ClearAllPoints(); sortButton.arrow:SetPoint("TOPLEFT",widths[i]-11,-math.floor((style.headerBand-6)/2))

    end
    for i,group in ipairs({f.primaryGroup,f.secondaryGroup}) do
        local column=i==1 and 5 or 7
        local width=i==1 and widths[5]+widths[6] or widths[7]+widths[8]+widths[9]
        group:ClearAllPoints(); group:SetPoint("TOPLEFT",f.columns[column]+4,-style.titleY); group:SetWidth(width-8)
    end
    for index,row in ipairs(f.rows) do
        -- The old background-layer grid disappeared beneath shaded rows and
        -- the header. Reproduce that visible pattern explicitly and reliably.
        local showGrid=index%2==1
        row:ClearAllPoints(); row:SetPoint("TOPLEFT",0,-(index-1)*style.rowHeight)
        row:SetSize(total,style.rowHeight); row.background:SetSize(total,style.rowHeight)
        row.shade=index%2==0 and 0.018 or 0
        row.background:SetColorTexture(row.shade,row.shade,row.shade,1)
        row.bottomLine:ClearAllPoints(); row.bottomLine:SetPoint("TOPLEFT",0,1-style.rowHeight); row.bottomLine:SetWidth(total)
        row.bottomLine:SetShown(showGrid)
        row.icon:ClearAllPoints(); row.icon:SetPoint("TOPLEFT",6,-(style.rowHeight-style.iconSize)/2)
        row.icon:SetSize(style.iconSize,style.iconSize); row.scoreSpecIcon:SetSize(style.scoreIconSize,style.scoreIconSize)
        for i,cell in ipairs(row.cells) do
            local padding=i==1 and style.namePadding or (i==5 and row.scoreSpecIcon:IsShown() and style.scorePadding or 12)
            cell:ClearAllPoints(); cell:SetPoint("TOPLEFT",f.columns[i]+(i==1 and style.nameInset or 6),-(style.rowHeight-20)/2)
            cell:SetWidth(widths[i]-padding)
            local line=row.columnLines[i]
            line:ClearAllPoints(); line:SetPoint("TOPLEFT",f.columns[i],0)
            line:SetHeight(style.rowHeight)
            line:SetShown(showGrid)
        end
        row.rightLine:ClearAllPoints(); row.rightLine:SetPoint("TOPLEFT",total-1,0)
        row.rightLine:SetHeight(style.rowHeight)
        row.rightLine:SetShown(showGrid)
    end
    if type(f.playerTabs)=="table" then MPL.RenderPlayerTabs(f) end
end
local function sortedDungeons(f,profile,metric)
    if not f.sortColumn then return profile.dungeons end
    -- Sort a view so cached profiles and other windows retain their source order.
    local entries={}
    for index,dungeon in ipairs(profile.dungeons) do
        local level,amount,best,median=MPL.MetricValues(profile,dungeon,metric)
        local first,second=(MPL.OrderAppearancePercentiles or MPL.OrderPercentiles)(best,median)
        local primary=profile.metric==metric
        local values={MPL.DungeonDisplayName and MPL.DungeonDisplayName(dungeon.name) or dungeon.name,level,primary and durationSeconds(dungeon.time) or nil,
            dungeon.runs,primary and dungeon.points or nil,primary and dungeon.rank or nil,
            amount,first,second}
        local sortColumn=f.sortColumn
        if f.sortId and MPL.ProfileColumnIndex then sortColumn=MPL.ProfileColumnIndex(f.sortId) or sortColumn end
        entries[#entries+1]={dungeon=dungeon,index=index,value=values[sortColumn]}
    end
    table.sort(entries,function(a,b)
        if a.value==b.value then return a.index<b.index end
        -- Missing data stays at the bottom in either direction; zero is data.
        if a.value==nil then return false end
        if b.value==nil then return true end
        if f.sortAscending then return a.value<b.value end
        return a.value>b.value
    end)
    local result={}
    for i,entry in ipairs(entries) do result[i]=entry.dungeon end
    return result
end
layoutProfileBanner=function(f,profile)
    local style=MPL.ProfileAppearanceStyle and MPL.ProfileAppearanceStyle() or profileTableLayout
    local messages={}
    local showStale=profile~=nil and f.stale==true
    if showStale then
        local _,lastDate=MPL.ProfileDate(profile)
        if MPL.AppearanceValue and MPL.AppearanceValue("compactAge",false) then
            messages[#messages+1]=L["Данные устарели"].." — "..lastDate
        else messages[#messages+1]="|cffffc440"..L["Данные устарели"].."|r    "..L["Последняя загрузка: "]..lastDate end
    end
    local warning=MPL.ProfileDisplayWarning(profile)
    if warning then messages[#messages+1]=warning end
    f.staleBanner.message:SetText(table.concat(messages,"\n"))
    local textHeight=f.staleBanner.message:GetStringHeight()
    local height=math.max(28,math.max(#messages*14,type(textHeight)=="number" and textHeight or 0)+14)
    local offset=#messages>0 and height+4 or 0
    f.staleBanner:SetShown(#messages>0); f.staleBanner:SetHeight(height)
    f.staleBanner.message:SetHeight(height-14)
    local footerHeight=f.footer:GetStringHeight()
    local extra=type(footerHeight)=="number" and math.max(0,math.ceil(footerHeight)-20) or 0
    local drawer=layoutProfileActions(f)
    if MPL.LayoutAppearanceBanner then return MPL.LayoutAppearanceBanner(f,profile,offset,extra,drawer) end
    f:SetHeight((profile and 656 or 700)+offset+extra+drawer)
    f.tableHeader:ClearAllPoints(); f.tableHeader:SetPoint("TOPLEFT",20,-254-offset)
    f.scroll:ClearAllPoints()
    f.scroll:SetPoint("TOPLEFT",20,-254-style.headerHeight-offset); f.scroll:SetPoint("BOTTOMRIGHT",-40,145+extra+drawer)
    for i,text in ipairs({f.source,f.note,f.footer}) do
        text:ClearAllPoints(); text:SetPoint("TOPLEFT",20,-(profile and 502 or 546)-i*20-offset)
    end
end
function MPL.RenderProfileStats(f)
    if f.specMenu then f.specMenu:Hide() end
    local profile=type(f.profile)=="table" and f.profile or nil
    local metric=f.viewMetric or "dps"
    if not f.appearanceSample then
        f.note:SetText(profile and L["Best % is the best logged percentile; Median % is the median. Percentiles do not measure survival, interrupts or mechanics."] or "")
    end
    f.headerSummaryData=nil
    for _,field in ipairs(f.summaryLabels or {}) do field:Hide() end
    local style=MPL.ProfileAppearanceStyle and MPL.ProfileAppearanceStyle() or profileTableLayout
    if MPL.ApplyProfileFonts then MPL.ApplyProfileFonts(f) end
    if f.sortColumn and type(f.sortId)=="string" and MPL.ProfileColumnIndex then f.sortColumn=MPL.ProfileColumnIndex(f.sortId) or f.sortColumn end
    f.headings[1]:SetText(L["Подземелье"]); f.headings[2]:SetText(L["Уровень"]); f.headings[3]:SetText(L["Время"])
    for _,heading in ipairs(f.headings) do heading:SetShown(profile~=nil) end
    for i,sortButton in ipairs(f.sortButtons) do
        local selected=f.sortColumn==i
        sortButton:SetShown(profile~=nil)
        sortButton.arrow:SetShown(profile~=nil and selected)
        -- Reflect the same triangle vertically so both directions have identical dimensions.
        for stripe,texture in ipairs(sortButton.arrow.stripes) do
            texture:ClearAllPoints()
            texture:SetPoint("TOPLEFT",stripe-1,-(f.sortAscending and 4-stripe or stripe-1))
        end
        f.headings[i]:SetTextColor(selected and 1 or 0.93,selected and 0.82 or 0.93,selected and 0 or 0.93)
    end
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
    f.headings[4]:SetText(L["Runs"])
    f.headings[6]:SetText(L["Rank"])
    f.primaryGroup:SetText(L["Score"])
    f.metricHeading:SetText(metric=="hps" and L["Best HPS"] or L["Best DPS"])
    local firstHeading,secondHeading=(MPL.OrderAppearancePercentiles or MPL.OrderPercentiles)(L["Best %"],L["Median %"])
    f.headings[8]:SetText(firstHeading); f.headings[9]:SetText(secondHeading)
    f.secondaryGroup:SetText(metric=="hps" and L["HPS by Level"] or L["DPS by Level"])
    f.specRanks:SetText(""); f.specRanks:Hide()
    for _,entry in ipairs(f.specRankEntries) do entry:Hide() end
    if not profile then
        layoutProfileTable(f); layoutProfileBanner(f,profile)
        f.content:SetHeight(1); f.scroll:SetVerticalScroll(0); MPL.UpdatePanelScroll(f)
        return
    end
    for index,rank in ipairs(profile.specRanks or {}) do
        local entry=f.specRankEntries[index]
        if not entry then
            entry=CreateFrame("Frame",nil,f); entry:SetHeight(18)
            entry.number=label(entry,0,0,1)
            entry.number:SetHeight(18); entry.number:SetJustifyV("MIDDLE"); entry.number:SetWordWrap(false)
            entry.icon=entry:CreateTexture(nil,"ARTWORK"); entry.icon:SetSize(18,18)
            entry.icon:SetPoint("LEFT",entry.number,"RIGHT",4,0)
            entry.specLabel=label(entry,0,0,1)
            entry.specLabel:ClearAllPoints(); entry.specLabel:SetPoint("LEFT",entry.number,"RIGHT",4,0)
            entry.specLabel:SetHeight(18); entry.specLabel:SetJustifyV("MIDDLE"); entry.specLabel:SetWordWrap(false)
            f.specRankEntries[index]=entry
        end
        local texture=specTexture(rank.spec,f.class)
        entry.hasIcon=texture~=nil
        entry.number:SetText(tostring(rank.rank))
        local r,g,b=percentileRGB(rank.rankPercent)
        entry.number:SetTextColor(r,g,b); emphasizeNumber(entry.number,r,g,b,true)
        entry.icon:SetTexture(texture); entry.icon:SetShown(entry.hasIcon)
        entry.specLabel:SetText(entry.hasIcon and "" or MPL.SpecLabel(rank.spec,f.class))
        entry.specLabel:SetShown(not entry.hasIcon)
        entry:Show()
    end
    if #(profile.specRanks or {})>0 then
        f.specRanks:SetText("Spec Ranks:")
        f.specRanks:SetTextColor(225/255,242/255,245/255)
        f.specRanks:Show()
    end
    f.scoreValue:SetText(profile.score and string.format("%.0f",profile.score) or "—")
    f.scoreValue:SetTextColor(226/255,104/255,168/255)
    local _,_,best,median=MPL.MetricValues(profile,nil,metric)
    local summaryOrder=MPL.OrderSummaryPercentiles or MPL.OrderPercentiles
    local first,second=summaryOrder(best,median)
    local firstLabel,secondLabel=summaryOrder(L["Лучший % в среднем:"],L["Медианный % в среднем:"])
    local firstShort,secondShort=summaryOrder(L["Best % (avg)"],L["Median % (avg)"])
    local firstHelp,secondHelp=summaryOrder(L["Average of the best logged percentiles across dungeons. This is not the best single run."],L["Average of the median logged percentiles across dungeons."])
    f.summary:SetText(metric:upper().." "..firstLabel.."  "..tablePercent(first))
    if MPL.UsesDungeonMetric() then
        f.summary:SetText(MPL.PrimaryPercentileLabel(metric)..": "..MPL.PrimaryStatistic(profile,metric))
    end
    f.medianSummary:SetText(metric:upper().." "..secondLabel.."  "..tablePercent(second))
    f.runSummary:SetText(L["Прохождения"]..":  "..(profile.runs or "—"))
    f.headerSummaryData={
        {label=metric:upper().." "..firstShort,value=tablePercent(first),help=firstHelp},
        {label=metric:upper().." "..secondShort,value=tablePercent(second),help=secondHelp},
        {label=L["Прохождения"],value=tostring(profile.runs or "—"),help=L["Number of logged runs in this profile."]},
    }
    if MPL.UsesDungeonMetric() then
        f.headerSummaryData[1]={label=MPL.PrimaryPercentileLabel(metric),value=MPL.PrimaryStatistic(profile,metric),help=L["Result for the currently listed dungeon, using the selected main metric."]}
    end
    for index,dungeon in ipairs(sortedDungeons(f,profile,metric)) do
        local row=f.rows[index]
        if not row then
            row=CreateFrame("Frame",nil,f.content); row:SetSize(880,26); row:SetPoint("TOPLEFT",0,-(index-1)*26)
            row.shade=index%2==0 and 0.018 or 0
            row.background=panelFill(row,0,0,880,26,row.shade,row.shade,row.shade)
            row:EnableMouse(true)
            row:SetScript("OnEnter",function(self)
                if MPL.ColorAppearanceRow then MPL.ColorAppearanceRow(self,true)
                else self.background:SetColorTexture(0.055,0.055,0.055,1) end
                if self.url or (MPL.DungeonDisplayName and self.dungeonName) then
                    GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
                    local displayName=MPL.DungeonDisplayName and MPL.DungeonDisplayName(self.dungeonName) or self.dungeonName
                    GameTooltip:AddLine((self.url and (L["Ссылка WCL"].." — ") or "")..displayName,1,1,1)
                    if MPL.DungeonTooltipNames then
                        local full,canonical=MPL.DungeonTooltipNames(self.dungeonName)
                        if full~=displayName then GameTooltip:AddLine(full,1,1,1) end
                        if canonical~=displayName and canonical~=full then GameTooltip:AddLine(canonical,.8,.8,.8) end
                    end
                    for i,cell in ipairs(self.cells) do
                        local width=cell:GetUnboundedStringWidth()
                        if i>1 and cell:IsShown() and type(width)=="number" and width>cell:GetWidth() then
                            GameTooltip:AddDoubleLine(f.headings[i]:GetText(),cell:GetText(),1,1,1,1,1,1)
                        end
                    end
                    GameTooltip:Show()
                end
            end)
            row:SetScript("OnLeave",function(self)
                if MPL.ColorAppearanceRow then MPL.ColorAppearanceRow(self,false)
                else self.background:SetColorTexture(self.shade,self.shade,self.shade,1) end
                GameTooltip:Hide()
            end)
            local function copyDungeonURL(_,mouseButton)
                if mouseButton=="LeftButton" and row.url then
                    GameTooltip:Hide()
                    MPL.CopyURL(f.name,f.realm,f.profile,row.url)
                end
            end
            row:SetScript("OnMouseUp",copyDungeonURL)
            row.cells={}; row.columnLines={}
            for i=1,9 do
                row.cells[i]=label(row,f.columns[i]+6,-3,math.max(1,f.widths[i]-12))
                if i==1 then dungeonNameFont(row.cells[i]) end
                -- Keep the text box explicit and centered inside each row.
                row.cells[i]:SetHeight(20); row.cells[i]:SetJustifyV("MIDDLE")
                row.cells[i]:SetJustifyH(i==1 and "LEFT" or "RIGHT")
                row.cells[i]:SetWordWrap(false); row.cells[i]:SetNonSpaceWrap(false)
                row.columnLines[i]=gridLine(row,f.columns[i],0,1,26)
            end
            row.rightLine=gridLine(row,880,0,1,26); row.bottomLine=gridLine(row,0,-25,880,1)
            row.icon=row:CreateTexture(nil,"ARTWORK"); row.icon:SetPoint("TOPLEFT",6,-3); row.icon:SetSize(20,20)
            row.scoreSpecIcon=CreateFrame("Frame",nil,row)
            row.scoreSpecIcon:SetSize(16,16)
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
            row.cells[1]:ClearAllPoints(); row.cells[1]:SetPoint("TOPLEFT",30,-3); row.cells[1]:SetWidth(f.widths[1]-36)
            f.rows[index]=row
        end
        row.dungeonName=dungeon.name
        row.url=MPL.DungeonURL(f.name,f.realm,profile,dungeon.name,metric)
        if f.appearanceSample==true then row.url=nil end
        local icon=dungeonIcons[dungeon.name]
        row.icon:SetTexture(icon and ("Interface\\AddOns\\MPlusLogs\\assets\\dungeons\\"..icon..".tga") or "Interface\\Icons\\INV_Misc_Map_01")
        local level,amount,best,median=MPL.MetricValues(profile,dungeon,metric)
        local lowParses=(profile.metric==metric and dungeon.flagged)
            or (profile.metric~=metric and dungeon.otherFlagged)
        local bestText=tablePercent(best)
        if best~=nil and lowParses then bestText=bestText:gsub("|r$","*|r") end
        local first,second=(MPL.OrderAppearancePercentiles or MPL.OrderPercentiles)(bestText,tablePercent(median))
        local metadata=profile.metric==metric
        local scoreSpec=metadata and dungeon.points and (dungeon.scoreSpec or (profile.spec~="All specs" and profile.spec))
        local scoreTexture=specTexture(scoreSpec,f.class)
        row.scoreSpecIcon.spec=scoreSpec
        row.scoreSpecIcon.texture:SetTexture(scoreTexture)
        row.hasScoreIcon=scoreTexture~=nil
        row.scoreSpecIcon:SetShown(scoreTexture~=nil)
        row.scoreSpecIcon:SetAlpha(1)
        row.cells[5]:SetWidth(math.max(1,f.widths[5]-(scoreTexture and 30 or 12)))
        local time=metadata and dungeon.time or nil
        local values={MPL.DungeonDisplayName and MPL.DungeonDisplayName(dungeon.name) or dungeon.name,level or "—",time and time~="" and time or "—",dungeon.runs or "—",
            metadata and dungeon.points and string.format("%.0f",math.floor(dungeon.points)) or "—",
            metadata and dungeon.rank or "—",amount and string.format("%.2fK",amount/1000) or "—",first,second}
        for i,value in ipairs(values) do
            if MPL.FormatAppearanceCell then value=MPL.FormatAppearanceCell(i,value,dungeon,profile,metric) end
            row.cells[i]:SetText(value)
            if MPL.StyleProfileFont then MPL.StyleProfileFont(row.cells[i],i==1 and "dungeon" or "numbers") end
            local r,g,b=225/255,242/255,245/255
            if i==1 then r,g,b=0.72,0.78,1 end
            if i==5 then r,g,b=226/255,104/255,168/255 end
            if i==6 and metadata and dungeon.rank and dungeon.rank>0 then r,g,b=percentileRGB(dungeon.rankPercent) end
            if i==7 then r,g,b=0.82,0.96,0.65 end
            row.cells[i]:SetTextColor(r,g,b)
            local sr,sg,sb=r,g,b
            if i==8 or i==9 then
                local firstValue,secondValue=(MPL.OrderAppearancePercentiles or MPL.OrderPercentiles)(best,median)
                sr,sg,sb=percentileRGB(i==8 and firstValue or secondValue)
            end
            -- Keep dungeon names regular; a colored stroke adds unwanted weight.
            emphasizeNumber(row.cells[i],sr,sg,sb,value~="—" and i~=1 and i~=2)
            if i==2 then renderLevelDigits(row,value,r,g,b) end
        end
        row:Show()
    end
    layoutProfileTable(f)
    layoutProfileBanner(f,profile)
    f.content:SetHeight(math.max(1,#profile.dungeons*style.rowHeight))
    if f.appearancePreserveScroll~=true then f.scroll:SetVerticalScroll(0) end
    MPL.UpdatePanelScroll(f)
end

function MPL.RenderPlayerTabs(f)
    f.playerTabs=type(f.playerTabs)=="table" and f.playerTabs or {}
    for _,tab in ipairs(f.playerTabs) do tab:Hide() end
    local players=type(f.searchPlayers)=="table" and f.searchPlayers or
        (type(f.groupPlayers)=="table" and f.groupPlayers or {})
    if #players<2 then return end
    local width=(type(f.viewportWidth)=="number" and f.viewportWidth or f.tableWidth or 880)/#players
    for i,player in ipairs(players) do
        local tab=f.playerTabs[i]
        if not tab then
            tab=CreateFrame("Button",nil,f,"BackdropTemplate")
            tab:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
            local caption=tab:CreateFontString(nil,"OVERLAY","GameFontNormal")
            readableFont(caption)
            caption:SetPoint("LEFT",10,0); caption:SetPoint("RIGHT",-10,0)
            caption:SetJustifyH("CENTER"); caption:SetWordWrap(false)
            tab:SetFontString(caption)
            tab.caption=caption
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
                if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(self,true,self.selected)
                elseif not self.selected then self:SetBackdropColor(0.40,0.07,0.07,1) end
                GameTooltip:SetOwner(self,"ANCHOR_TOP")
                GameTooltip:AddLine(self.player.name..(self.player.realm and "-"..self.player.realm or ""))
                if self.player.error then GameTooltip:AddLine(self.player.error,1,.3,.2,true) end
                if self.player.candidates then GameTooltip:AddLine(L["Choose the character's realm"],1,.82,0,true) end
                GameTooltip:Show()
            end)
            tab:SetScript("OnLeave",function(self)
                if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(self,false,self.selected)
                elseif not self.selected then self:SetBackdropColor(0.27,0.035,0.035,1) end
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
        if MPL.StyleAppearanceButton then MPL.StyleAppearanceButton(tab,false) end
        if MPL.StyleProfileFont then tab:SetHeight(math.max(selected and 32 or 26,tab.caption.mplAppliedFontSize+10)) end
        if MPL.ColorAppearanceControl then MPL.ColorAppearanceControl(tab,false,selected) end
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
    if not f:IsShown() then f.sortColumn=false; f.sortAscending=false end
    f.searchMember=false
    if type(f.searchChoices)=="table" then for _,b in ipairs(f.searchChoices) do b:Hide() end end
    f.specButton:Show(); f.currentSpec:Show()
    f.emptyMessage:ClearAllPoints(); f.emptyMessage:SetPoint("TOPLEFT",80,-300)
    if not keepGroup and not suppressNotice then f.groupPlayers=nil; f.groupFailures=nil; f.searchPlayers=nil end
    if not keepGroup and not suppressNotice then f.partyTracked=false end
    f.applicant=type(context)=="table" and MPL.Key(context.name,context.realm)==MPL.Key(name,server) and context or false
    f.inviteSent=false
    local stale,lastDate=false,nil
    if profile then stale,lastDate=MPL.IsProfileStale(profile) end
    local notice=MPL.staleWindow
    if notice then
        -- Inspect/spec events redraw the same profile. Keep its open notice
        -- until dismissal, navigation, or replacement of the displayed logs.
        local sameNotice=stale and profile and notice.profile and notice.name
            and MPL.Key(notice.name,notice.realm)==stateKey
            and notice.profile.updated==profile.updated and notice.profile.spec==profile.spec
        if sameNotice and MPL.GetOption("stalePopup") then
            notice.profile=profile; notice.applicant=f.applicant
        else notice:Hide() end
    end
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
    local stateText=state and (state.error and companionError(state.error,state.errorCode,state.expires)
        or state.reason=="hidden" and L["Логи скрыты в Warcraft Logs."]
        or state.reason=="missing" and L["Персонаж не найден"]
        or state.reason=="retry" and L["Повторный запрос логов отложен. Его можно отправить позже."]
        or L["Для этого персонажа нет доступных логов M+."])
    if stateText and state and state.error and state.errorCode~="auth" and state.expires then stateText=stateText.."\n"..MPL.RetryDelayText(state.expires) end
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
    f.title:SetText(name .. " — " .. server)
    f.currentSpec.name:SetText(current and MPL.SpecLabel(current[1],current[3]) or "—")
    local currentTexture=current and specTexture(current[1],current[3])
    f.currentSpec.icon:SetTexture(currentTexture or nil)
    f.currentSpec.icon:SetShown(currentTexture~=nil and currentTexture~=false)
    f.currentSpec:SetAlpha(1)
    f.currentSpec.caption:SetAlpha(current and 1 or 0.55)
    f.currentSpec.name:SetAlpha(current and 1 or 0.55)
    f.lookup:SetText(name .. "-" .. server:gsub(" ",""))
    f.scroll:SetVerticalScroll(0)
    for _, row in ipairs(f.rows) do row:Hide() end
    f.viewMetric=primary; f.stale=stale
    f.context:SetText(profile and profile.season or "Midnight M+ Season 2")
    f.loadButton:ClearAllPoints()
    f.centerLoadButton=not profile and not stateText
    if profile then
        f.scroll:Show(); f.emptyMessage:Hide()
        f.loadButton:SetSize(170,26)
        f.loadButton:SetText(L["Обновить M+ логи"])
        f.source:SetText(MPL.T(profile.source)..L["  /  Последняя загрузка: "]..lastDate)
        f.note:SetText(""); f.footer:SetText("")
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
            f.loadButton:SetSize(170,26)
            f.loadButton:SetText(L["Обновить M+ логи"])
            f.footer:SetText("")
            f.specButton.detail:SetText(hidden and L["Логи скрыты"]
                or state.errorCode=="auth" and L["Профиль не загружен"]
                or state.reason=="retry" and L["Повторный запрос отложен"] or L["Нет доступных логов"])
        end
        f.content:SetHeight(1)
    end
    if profile and stateText then f.footer:SetText(stateText) end
    local failure=type(f.groupFailures)=="table" and f.groupFailures[stateKey]
    if failure then f.footer:SetText(companionError(MPL.T(failure.error),failure.errorCode,failure.retryAt)) end
    if profile and profile.realmInferred then
        local previous=f.footer:GetText() or ""
        f.footer:SetText((previous~="" and previous.."\n" or "")..L["Match based on name and class; realm not confirmed in game."])
    end
    MPL.RenderProfileStats(f)
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

function MPL.ShowDownload(fullName, realm, profile,context,batch,refresh,searchResultID,importTest,requestedMetric,forceSearch,displayRefresh,includeSpecs)
    local name, server = MPL.Identity(fullName,realm)
    if not name then return end
    local state=MPL.GetProfileState(name,server,includeSpecs and "All specs" or MPL.SelectedSpec(name,server))
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
        local details={}
        local pending=MPL.FilterFreshProfiles(batch,refresh,displayRefresh,details)
        if #pending==0 and (details.waiting or 0)==0 then return end
    elseif batch==true then
        local players,err=MPL.CollectApplicants()
        local details={}
        local pending=not err and MPL.FilterFreshProfiles(players,refresh,displayRefresh,details)
        if pending and #players>0 and #pending==0 and (details.waiting or 0)==0 then
            -- Keep the existing all-fresh message, but never offer a request
            -- when the only missing profiles are known to be hidden.
            for _,player in ipairs(players) do
                local playerState=MPL.GetProfileState(player.name,player.realm,player.spec)
                if playerState and playerState.reason=="hidden" then return end
            end
        end
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
        if MPL.CreateTutorialHelpButton then
            f.tutorialButton=MPL.CreateTutorialHelpButton(f,function()
                return (f.previewCompanionIntro or MPL.NeedsCompanionIntro()) and "companion" or "exchange"
            end,"icon")
            f.tutorialButton:SetSize(f.closeButton:GetWidth(),f.closeButton:GetHeight())
            f.tutorialButton:SetPoint("RIGHT",f.closeButton,"LEFT",-12,0)
            f.title:SetWidth(420)
        end
        f.companionHint=CreateFrame("Frame",nil,f)
        f.companionHint:SetPoint("TOPLEFT",24,-126); f.companionHint:SetSize(472,80)
        f.companionHint.text=label(f.companionHint,0,0,472,L["Первый раз загружаете логи? Сначала установите и запустите MPlusLogs Companion."])
        f.companionHint.text:SetJustifyV("TOP")
        f.companionHint.download=button(f.companionHint,L["Скачать MPlusLogs Companion"],0,12,270,MPL.ShowCompanionDownload)
        f.companionHint.continue=button(f.companionHint,L["Уже установлен"],282,12,190,function()
            -- Acknowledging setup does not confirm a Companion response.
            MPlusLogsDB=MPlusLogsDB or {}
            MPlusLogsDB.companionIntroDismissed=true
            f.previewCompanionIntro=false
            f.setStatus(f.status:GetText(),f.statusIsError)
            f.focusInput()
        end)
        f.setStatus=function(text,isError)
            f.statusIsError=isError==true
            local showHint=f.previewCompanionIntro or MPL.NeedsCompanionIntro()
            f.companionHint:SetShown(showHint)
            local measured=f.companionHint.text:GetStringHeight()
            local introOffset=showHint and math.max(80,type(measured)=="number" and math.ceil(measured)+48 or 80) or 0
            if type(measured)=="number" then f.companionHint.text:SetHeight(math.ceil(measured)) end
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
            if MPL.TutorialCoversWindow and MPL.TutorialCoversWindow(f) then return end
            edit:SetFocus(); edit:HighlightText()
            local revision=f.revision
            -- Button release can change focus after OnClick has returned.
            C_Timer.After(0,function()
                if f:IsShown() and revision==f.revision and (f.phase=="copy" or f.phase=="waiting")
                    and not (MPL.TutorialCoversWindow and MPL.TutorialCoversWindow(f)) then
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
                f.steps:SetText(MPL.locale=="ruRU" and L["Повторная вставка — без запросов WCL"] or "Replay paste — no WCL requests")
                f.setStatus(MPL.locale=="ruRU" and L["В Companion нажмите «Скопировать последний ответ».\nВернитесь сюда и нажмите Ctrl+V.\nМожно повторять тот же ответ без Ctrl+C и без загрузки данных."]
                    or "In Companion, copy the last reply.\nReturn here and press Ctrl+V.\nRepeat the same reply without Ctrl+C or loading data.")
                setText(""); return
            end
            local spec=f.includeSpecs and "All specs" or MPL.SelectedSpec(f.name,f.realm) or (f.profile and f.profile.spec) or "All specs"
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
                local details={}
                if f.importTest then skipped=0 else players,skipped=MPL.FilterFreshProfiles(players,f.refresh,f.displayRefresh,details) end
                if total>0 and #players==0 then
                    f.character:SetText(L["Нужно загрузить: "].."0 / "..total)
                    if (details.waiting or 0)>0 then
                        f.waitingRetryAt=details.retryAt
                        f.setStatus(L["Все оставшиеся запросы временно отложены."].."\n"..MPL.RetryDelayText(details.retryAt),true)
                    else f.status:SetText(L["Все кандидаты уже имеют актуальные логи."]) end
                    if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
                    return
                end
                id,request=MPL.SendBatchRequest(players,f.refresh)
                if id and type(f.batch)=="table" then MPL.pendingReply.groupPlayers=f.batch end
                f.character:SetText(L["Нужно загрузить: "]..#players.." / "..total)
            else id,request=MPL.SendRequest(f.name,f.realm,f.requestedMetric or (f.profile and f.profile.metric) or "dps",spec,f.applicant,f.includeSpecs,f.refresh) end
            if not id then f.setStatus(request,true); return end
            f.phase="copy"; f.request=request
            f.steps:SetText(L["|cffffd1001. Отправка запроса|r    /    |cff8888882. Получение логов|r"])
            f.setStatus(L["Запрос: Ctrl+A выделить, Ctrl+C скопировать"]
                .."\n"..L["Подождите немного и нажмите |cffffd100Ctrl+V|r.\nCompanion должен быть запущен, а вход выполнен. После настройки сначала введите /reload."]
                ..(skipped and skipped>0 and ("\n"..L["Актуальные данные: "]..skipped..L[" из "]..total) or ""))
            setText(request)
        end
        edit:SetScript("OnEscapePressed",function() f:Hide() end)
        f:SetScript("OnHide",function()
            edit:ClearFocus(); f.revision=f.revision+1; f.quotaError=nil; f.waitingRetryAt=false
            f.charBuffer=false; f.capturedReply=false; f.capturePaste=false
            f.previewCompanionIntro=false
        end)
        f:SetScript("OnUpdate",function(_,elapsed)
            if not f.quotaError and not f.waitingRetryAt then return end
            f.quotaElapsed=(f.quotaElapsed or 0)+elapsed
            if f.quotaElapsed>=1 then
                f.quotaElapsed=0
                if f.waitingRetryAt then
                    if f.waitingRetryAt<=GetServerTime() then f.waitingRetryAt=false; f.begin()
                    else f.setStatus(L["Все оставшиеся запросы временно отложены."].."\n"..MPL.RetryDelayText(f.waitingRetryAt),true) end
                else f.setStatus(companionError(f.quotaError),true) end
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
                local wasBatch=MPL.pendingReply and MPL.pendingReply.batch
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
                    f.phase="done"
                    local result=wasBatch and MPL.lastBatchResult
                    if result then f.status:SetText(L["Загружено: "]..result.loaded..L[" из "]..#result.players..L[". Ошибки обновления: "]..result.errorCount)
                    else f.status:SetText(count>0 and L["Логи получены."] or L["Логи не загружены"]) end
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
    f.previewCompanionIntro=false
    MPL.pendingReply=nil
    f.revision=f.revision+1
    f.name=name; f.realm=server; f.profile=profile or false; f.phase="idle"; f.request=""
    f.batch=batch or false
    f.waitingRetryAt=false
    f.importTest=importTest or false; f.importTestPaste=false
    f.capturedReply=false; f.charBuffer=false; f.capturePaste=false
    f.searchResultID=searchResultID or false
    local replay=type(importTest)=="table" and importTest.replay
    f.edit:SetMaxLetters(replay and importTest.noLetterCount and 0 or (searchResultID and 1600000 or 500000))
    f.edit:SetMaxBytes(replay and importTest.captureChars and 1 or (replay and 1600000 or 0))
    f.refresh=refresh or false
    f.includeSpecs=includeSpecs==true
    f.displayRefresh=displayRefresh==true
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

function MPL.ShowCompanionIntroPreview()
    if InCombatLockdown() then return end
    local f=MPL.downloadWindow
    if not f or (f.phase~="copy" and f.phase~="waiting") then
        local name,realm=UnitFullName("player")
        MPL.ShowDownload(name,realm,nil,nil,nil,true)
        f=MPL.downloadWindow
    end
    if not f then return end
    -- Preview the real inline hint without resetting saved installation history
    -- or replacing a request that is already being copied/pasted.
    f.previewCompanionIntro=true
    f.setStatus(f.status:GetText(),f.statusIsError)
    f:Show(); f.focusInput()
end

function MPL.ShowBatchDownload()
    MPL.ShowDownload(L["Кандидаты"],GetNormalizedRealmName(),nil,nil,true)
end

function MPL.ShowBatchResults(players,profiles,failures,count,open)
    local errorCount,loaded,retryAt=0,0
    for _,player in ipairs(players) do
        local key=MPL.Key(player.name,player.realm)
        local failure=failures[key]
        if failure then
            errorCount=errorCount+1
            if failure.errorCode~="auth" and failure.retryAt and failure.retryAt>GetServerTime() then retryAt=math.min(retryAt or failure.retryAt,failure.retryAt) end
        elseif profiles[key] then loaded=loaded+1 end
    end
    if not open then
        MPL.lastBatchResult={players=players,profiles=profiles,failures=failures,count=count,loaded=loaded,errorCount=errorCount}
        if MPL.batchResultsWindow then MPL.batchResultsWindow:Hide() end
        if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
        -- A valid response may contain no loaded profiles. Show the failures
        -- instead of silently dismissing them as a completed clipboard exchange.
        if errorCount==0 then return end
    end
    if not MPL.batchResultsWindow then
        local f=window("MPlusLogsBatchResults",L["Логи кандидатов"],660,420)
        f.summary=label(f,24,-52,610,"","GameFontHighlight")
        f.scroll=CreateFrame("ScrollFrame",nil,f,"UIPanelScrollFrameTemplate")
        f.scroll:SetPoint("TOPLEFT",24,-94); f.scroll:SetPoint("BOTTOMRIGHT",-42,58)
        f.content=CreateFrame("Frame",nil,f.scroll); f.content:SetSize(590,1)
        f.scroll:SetScrollChild(f.content); f.rows={}
        f.retryElapsed=0
        f:SetScript("OnUpdate",function(_,elapsed)
            f.retryElapsed=(f.retryElapsed or 0)+elapsed
            if f.retryElapsed>=1 then
                f.retryElapsed=0
                local nextRetry
                for _,failure in pairs(f.resultFailures) do
                    if failure.errorCode~="auth" and failure.retryAt and failure.retryAt>GetServerTime() then nextRetry=math.min(nextRetry or failure.retryAt,failure.retryAt) end
                end
                f.retryAt=nextRetry or false
                f.summary:SetText(f.resultSummary..(f.retryAt and f.retryAt>GetServerTime() and ("\n"..MPL.RetryDelayText(f.retryAt)) or ""))
            end
        end)
        f.scroll:HookScript("OnScrollRangeChanged",function() MPL.UpdatePanelScroll(f) end)
        button(f,L["Закрыть"],24,20,140,function() f:Hide() end)
        MPL.batchResultsWindow=f
    end
    local f=MPL.batchResultsWindow
    for _,row in ipairs(f.rows) do row:Hide() end
    f.retryAt=retryAt or false
    f.resultFailures=failures
    f.resultSummary=L["Загружено: "]..loaded..L[" из "]..#players..L[". Ошибки обновления: "]..errorCount
    f.summary:SetText(f.resultSummary..(retryAt and ("\n"..MPL.RetryDelayText(retryAt)) or ""))
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
        cell.text:SetText(MPL.PrimaryStatistic(profile,cell.metric,nil,stale,true))
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
