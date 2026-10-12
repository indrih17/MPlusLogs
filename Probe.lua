local _, MPL = ...
local L = MPL.L
local A, B = "MPlusLogsProbe_A", "MPlusLogsProbe_B"
local state = {prepared=false}
MPL.probeState = state

local function loaded(name)
    return C_AddOns.IsAddOnLoaded(name)
end
local function payload(slot)
    return MPlusLogsProbePayloads and MPlusLogsProbePayloads[slot]
end
local function value(slot)
    local p = payload(slot)
    return p and p.value or L["(не загружен)"]
end
local function count(slot)
    return MPlusLogsProbeLoads and MPlusLogsProbeLoads[slot] or 0
end
local function load(name)
    local ok, result, reason = pcall(C_AddOns.LoadAddOn,name)
    if not ok then return nil,tostring(result) end
    return result,reason
end

function MPL.ProbeReport()
    local version,build,_,interface = GetBuildInfo()
    return table.concat({
        "MPlusLogs LoadOnDemand probe",
        "Client: "..tostring(version).." build "..tostring(build).." Interface "..tostring(interface),
        "Prepared: "..tostring(state.prepared),
        "A loaded: "..tostring(loaded(A)),
        "A value: "..value("A").."; executions: "..count("A"),
        "B loaded: "..tostring(loaded(B)),
        "B value: "..value("B").."; executions: "..count("B"),
        "Result: "..(state.result or L["ещё не проверен"]),
    },"\n")
end

local function refresh()
    if MPL.probeWindow then
        MPL.probeWindow.report:SetText(MPL.ProbeReport())
        MPL.probeWindow.message:SetText(state.message or L["Сначала нажмите «1. Подготовить»."])
    end
end

function MPL.ProbePrepare()
    if InCombatLockdown() then state.message=L["Выйдите из боя перед проверкой."]; refresh(); return end
    if loaded(A) then
        state.message=L["A уже загружен. Для нового опыта сначала восстановите BASELINE-файлы, затем /reload."]
        refresh(); return
    end
    local ok,reason = load(B)
    if not ok then
        state.message=L["Не удалось загрузить контроль B: "]..tostring(reason)..L[". Проверьте установку модулей и перезапуск WoW."]
        refresh(); return
    end
    if value("B") ~= "BASELINE-B" or count("B") ~= 1 then
        state.message=L["B не содержит исходный BASELINE-B. Восстановите исходные файлы и повторите после /reload."]
        refresh(); return
    end
    state.prepared=true
    state.message=L["Подготовлено: B загружен, A не загружен. Напишите в чат Codex «Готово»; файл изменит помощник."]
    refresh()
end

function MPL.ProbeRead()
    if InCombatLockdown() then state.message=L["Выйдите из боя перед проверкой."]; refresh(); return end
    if not state.prepared then state.message=L["Сначала подготовьте тест."]; refresh(); return end
    if loaded(A) then state.message=L["A уже проверен в этой сессии. Повторная загрузка не является новым опытом."]; refresh(); return end
    local ok,reason = load(A)
    if not ok then state.message=L["Ошибка загрузки A: "]..tostring(reason); refresh(); return end
    load(B) -- Control: an already loaded module should retain its old payload.
    if value("A"):match("^UPDATED%-A%-%x+$") and count("A") == 1 and value("B") == "BASELINE-B" and count("B") == 1 then
        state.result=L["PASS: A прочитал новый файл; B остался в памяти"]
    elseif value("A") == "BASELINE-A" then
        state.result=L["BASELINE: A прочитал исходное содержимое. Сверьте файл/момент обновления с Codex."]
    else state.result=L["INCONCLUSIVE: неожиданное значение или число выполнений; скопируйте отчёт"] end
    state.message=L["Скопируйте отчёт (нажмите поле, Ctrl+A, Ctrl+C) и отправьте в чат Codex."]
    refresh()
end

function MPL.ShowProbe()
    if not MPL.probeWindow then
        local f = CreateFrame("Frame","MPlusLogsProbeWindow",UIParent,"BackdropTemplate")
        f:SetSize(760,390); f:SetPoint("CENTER"); f:SetFrameStrata("DIALOG")
        f:SetBackdrop({bgFile="Interface/Tooltips/UI-Tooltip-Background",edgeFile="Interface/Tooltips/UI-Tooltip-Border",edgeSize=16,insets={left=4,right=4,top=4,bottom=4}})
        f:SetBackdropColor(0.025,0.025,0.04,0.98)
        local title=f:CreateFontString(nil,"OVERLAY","GameFontNormalLarge")
        title:SetPoint("TOPLEFT",20,-18); title:SetText(L["MPlusLogs: тест чтения файла без /reload"])
        local close=CreateFrame("Button",nil,f,"UIPanelCloseButton"); close:SetPoint("TOPRIGHT",-2,-2)
        local report=CreateFrame("EditBox",nil,f,"InputBoxTemplate")
        report:SetMultiLine(true); report:SetFontObject(ChatFontNormal); report:SetAutoFocus(false)
        report:SetSize(700,230); report:SetPoint("TOPLEFT",25,-55)
        report:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
        f.report=report
        f.message=f:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall")
        f.message:SetPoint("BOTTOMLEFT",20,60); f.message:SetWidth(715); f.message:SetJustifyH("LEFT")
        for i,entry in ipairs({{L["1. Подготовить"],MPL.ProbePrepare},{L["2. Прочитать обновлённый A"],MPL.ProbeRead},{L["Обновить отчёт"],refresh}}) do
            local b=CreateFrame("Button",nil,f,"UIPanelButtonTemplate")
            b:SetSize(i==2 and 270 or 180,26); b:SetPoint("BOTTOMLEFT",i==1 and 20 or i==2 and 210 or 490,20)
            b:SetText(entry[1]); b:SetScript("OnClick",entry[2])
        end
        UISpecialFrames[#UISpecialFrames+1]="MPlusLogsProbeWindow"
        MPL.probeWindow=f
    end
    refresh(); MPL.probeWindow:Show()
end
