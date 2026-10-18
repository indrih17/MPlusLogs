local _, MPL = ...
-- Opt-in bulk reproduction, using the production request and paste window.
local function text(ru,en) return MPL.locale=="ruRU" and ru or en end
local function clock()
    if debugprofilestop then return debugprofilestop() end
    return (GetTimePreciseSec and GetTimePreciseSec() or GetTime and GetTime() or 0)*1000
end

function MPL.SampleImportTestPlayers()
    local pool,seen={},{}
    local function add(profile)
        if type(profile)~="table" or profile.zone~=MPL.zone or profile.region~=MPL.Region()
            or not MPL.SafeString(profile.name) or not MPL.SafeString(profile.realm) then return end
        local key=MPL.Key(profile.name,profile.realm,profile.region)
        local updated=MPL.ProfileDate(profile) or 0
        if seen[key] then
            -- A stale variant must not hide a more recent copy of this character.
            seen[key].updatedAt=math.max(seen[key].updatedAt,updated)
            return
        end
        local state=MPL.GetProfileState(profile.name,profile.realm,"")
        if state and state.reason=="hidden" then return end
        -- Request the aggregate once per character, regardless of stored specs.
        local player={name=profile.name,realm=profile.realm,spec="",updatedAt=updated,key=key}
        seen[key]=player
        pool[#pool+1]=player
    end
    local function flat(profiles) for _,profile in pairs(profiles or {}) do add(profile) end end
    local function nested(profiles) for _,variants in pairs(profiles or {}) do flat(variants) end end
    flat(MPlusLogsDB and MPlusLogsDB.profiles)
    nested(MPlusLogsDB and MPlusLogsDB.specProfiles)
    flat(MPL.bundled); nested(MPL.bundledSpecs); flat(MPL.snapshots)
    local total=#pool
    -- Unknown dates first; use identity to make equal-date selection repeatable.
    table.sort(pool,function(a,b)
        if a.updatedAt~=b.updatedAt then return a.updatedAt<b.updatedAt end
        return a.key<b.key
    end)
    local selected={}
    for index=1,math.min(100,total) do
        selected[#selected+1]=pool[index]
    end
    return selected,total
end

local function label(parent,y,height)
    local value=parent:CreateFontString(nil,"OVERLAY","GameFontHighlight")
    value:SetPoint("TOPLEFT",24,y); value:SetWidth(552); value:SetHeight(height)
    value:SetJustifyH("LEFT"); value:SetJustifyV("TOP")
    return value
end

local function blocked()
    if InCombatLockdown() then
        print("MPlusLogs: "..text("тест доступен вне боя.","test is available outside combat.")); return true
    end
    if MPL.pendingReply then
        print("MPlusLogs: "..text("сначала завершите текущую загрузку.",
            "finish the current exchange first.")); return true
    end
end

function MPL.ShowImportTest()
    if blocked() then return end
    local f=MPL.importTestWindow
    if not f then
        f=CreateFrame("Frame","MPlusLogsImportTest",UIParent,"BackdropTemplate")
        f:SetSize(600,470); f:SetPoint("CENTER"); f:SetFrameStrata("DIALOG")
        f:SetMovable(true); f:EnableMouse(true); f:RegisterForDrag("LeftButton")
        f:SetScript("OnDragStart",f.StartMoving); f:SetScript("OnDragStop",f.StopMovingOrSizing)
        f:SetBackdrop({bgFile="Interface\\DialogFrame\\UI-DialogBox-Background",
            edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",tile=true,tileSize=16,edgeSize=16,
            insets={left=4,right=4,top=4,bottom=4}})
        local close=CreateFrame("Button",nil,f,"UIPanelCloseButton"); close:SetPoint("TOPRIGHT",-4,-4)
        close:SetScript("OnClick",function() f:Hide() end)
        f.title=label(f,-22,25); f.title:SetText(text("Тест массового импорта","Bulk import test"))
        f.summary=label(f,-57,46)
        f.help=label(f,-108,86)
        f.help:SetText(text("Самые старые данные в базе; неизвестные даты — первыми.\nОткроется обычное окно: Ctrl+C → дождитесь Companion → Ctrl+V.\nЗапрос обновляет базу. Кэш последних 5 минут и лимиты API сохраняются.",
            "Oldest saved data first; unknown dates come first.\nUses the normal window: Ctrl+C → wait for Companion → Ctrl+V.\nUpdates stored profiles. The 5-minute cache and API limits still apply."))
        f.result=label(f,-198,116)
        f.replayCaptured=CreateFrame("Button",nil,f,"UIPanelButtonTemplate")
        f.replayCaptured:SetPoint("BOTTOMLEFT",24,90); f.replayCaptured:SetSize(552,28)
        f.replayCaptured:SetText(text("Повтор: сбор символов отдельно от поля","Replay: capture characters outside the input"))
        f.replayCaptured:SetScript("OnClick",function() MPL.ShowImportReplay(false,true) end)
        f.replay=CreateFrame("Button",nil,f,"UIPanelButtonTemplate")
        f.replay:SetPoint("BOTTOMLEFT",24,54); f.replay:SetSize(230,28)
        f.replay:SetText(text("Повтор: обычное поле","Replay: normal input"))
        f.replay:SetScript("OnClick",function() MPL.ShowImportReplay(false) end)
        f.replayNoCount=CreateFrame("Button",nil,f,"UIPanelButtonTemplate")
        f.replayNoCount:SetPoint("BOTTOMRIGHT",-24,54); f.replayNoCount:SetSize(290,28)
        f.replayNoCount:SetText(text("Повтор: без подсчёта символов","Replay: no letter counting"))
        f.replayNoCount:SetScript("OnClick",function() MPL.ShowImportReplay(true) end)
        f.shuffle=CreateFrame("Button",nil,f,"UIPanelButtonTemplate")
        f.shuffle:SetPoint("BOTTOMLEFT",24,18); f.shuffle:SetSize(230,28)
        f.shuffle:SetText(text("Пересобрать список старых","Rebuild oldest list"))
        f.shuffle:SetScript("OnClick",function() MPL.ShowImportTest() end)
        f.start=CreateFrame("Button",nil,f,"UIPanelButtonTemplate")
        f.start:SetPoint("BOTTOMRIGHT",-24,18); f.start:SetSize(290,28)
        f.start:SetText(text("Перезапросить через Companion","Request again via Companion"))
        f.start:SetScript("OnClick",function()
            if blocked() or #f.players==0 then return end
            -- Copy the sample; transport normalizes request fields in place.
            local players={}
            for _,player in ipairs(f.players) do players[#players+1]={name=player.name,realm=player.realm,spec=""} end
            MPL.ShowDownload(text("Тест импорта","Import test"),GetNormalizedRealmName(),nil,nil,players,true,nil,true)
            if MPL.downloadWindow and MPL.downloadWindow.importTest then f:Hide() end
        end)
        UISpecialFrames[#UISpecialFrames+1]="MPlusLogsImportTest"
        MPL.importTestWindow=f
    end
    f.players,f.available=MPL.SampleImportTestPlayers()
    f.summary:SetText(string.format(text("В базе доступно: %d. Выбрано: %d из 100.\nРегион: %s. Свежие профили тоже включены.",
        "Available in database: %d. Selected: %d of 100.\nRegion: %s. Fresh profiles are included."),f.available,#f.players,MPL.Region():upper()))
    f.start:SetEnabled(#f.players>0)
    f.result:SetText(text("Результат и замеры появятся здесь после вставки ответа.",
        "Results and timings will appear here after you paste the reply."))
    f:Show()
end

function MPL.ShowImportReplay(noLetterCount,captureChars)
    if blocked() then return end
    MPL.ShowDownload(text("Повторная вставка без WCL","Replay paste without WCL"),GetNormalizedRealmName(),
        nil,nil,{},false,nil,{replay=true,noLetterCount=noLetterCount==true,captureChars=captureChars==true})
    if MPL.importTestWindow then MPL.importTestWindow:Hide() end
end

function MPL.PrepareImportTestReplay(f,reply)
    local id,payload=reply:match("^MPLS1\r?\n(%d+%-%d+)\r?\n(.*)")
    if not id then return nil,text("Скопируйте последний ответ в Companion.","Copy the last reply in Companion.") end
    if payload:match("^MPLV1 ") then payload=payload:match("^[^\r\n]+\r?\n(.*)") end
    local encoded=payload and payload:match("^MPLB1\r?\n(.*)")
    if not encoded then return nil,text("Нужен сохранённый ответ массовой загрузки.","A saved batch reply is required.") end
    local body=encoded:gsub("%%(%x%x)",function(hex) return string.char(tonumber(hex,16)) end)
    local parsed,err=MPL.Parse(body,true)
    if not parsed then return nil,err end
    local players,expected={},{}
    local function add(key,p)
        if key~=MPL.Key(p.name,p.realm) then return false end
        if not expected[key] then
            local player={name=p.name,realm=p.realm,spec=p.spec~="All specs" and p.spec or "",role=p.role}
            players[#players+1]=player; expected[key]=player
        end
        return true
    end
    for key,p in pairs(parsed.profiles) do
        if not add(key,p) then return nil,text("Ответ относится к другому региону.","Reply belongs to a different region.") end
    end
    for key,p in pairs(parsed.failures) do
        if not add(key,p) then return nil,text("Ответ относится к другому региону.","Reply belongs to a different region.") end
    end
    if #players>250 then return nil,MPL.L["Слишком много кандидатов (максимум 250)"] end
    -- Explicit diagnostic replay derives its expected roster from the validated
    -- saved batch. Ordinary requests keep their original identity checks.
    MPL.pendingReply={id=id,batch=true,expected=expected,players=players}
    f.batch=players
    return true
end

function MPL.BeginImportTestPaste(f)
    if not f.importTest then return end
    local paste={started=clock(),events=0}
    f.importTestPaste=paste
    C_Timer.After(0,function()
        if f.importTestPaste==paste then paste.nextFrameMs=clock()-paste.started end
    end)
end

function MPL.ImportTestTextChanged(f)
    if f.importTest and not f.programmatic and f.importTestPaste then
        local paste=f.importTestPaste
        paste.events=paste.events+1
        if not paste.changed then paste.changed=clock() end
    end
end

function MPL.ImportTestClock() return clock() end

function MPL.FinishImportTest(f,count,err,body,started)
    if not f.importTest then return end
    local finished=clock()
    local paste=f.importTestPaste
    local result={count=count,error=err,bytes=#body,processingMs=finished-started,
        noLetterCount=type(f.importTest)=="table" and f.importTest.noLetterCount==true or false,
        captureChars=f.capturePaste==true or (type(f.importTest)=="table" and f.importTest.captureChars==true) or false,
        nextFrameMs=paste and paste.nextFrameMs,events=paste and paste.events,
        textChangedMs=paste and paste.changed and paste.changed-paste.started,
        totalMs=paste and finished-paste.started}
    MPL.lastImportTest=result
    if count==nil then return end
    local checksum=0
    for index=1,#body do checksum=(checksum*31+body:byte(index))%2147483647 end
    result.checksum=checksum
    local delivery=result.textChangedMs and string.format("%.1f",result.textChangedMs) or "—"
    local total=result.totalMs and string.format("%.1f",result.totalMs) or "—"
    local message=string.format(text("Импортировано: %d. Ответ: %d байт.\nCtrl+V → изменение поля: %s мс. Обработка ответа: %.1f мс.\nВсего после Ctrl+V: %s мс (включая ожидание 150 мс).",
        "Imported: %d. Reply: %d bytes.\nCtrl+V → text change: %s ms. Reply processing: %.1f ms.\nTotal after Ctrl+V: %s ms (includes 150 ms debounce)."),
        count,result.bytes,delivery,result.processingMs,total)
    local mode=result.captureChars and text("отдельный сбор символов","separate character capture")
        or result.noLetterCount and text("без подсчёта символов","no letter counting") or text("обычное","normal")
    message=message.."\n"..text("Поле: ","Input: ")..mode
    message=message.."\n"..text("Контрольная сумма ответа: ","Reply checksum: ")..string.format("%.0f",checksum)
    if MPL.importTestWindow then
        MPL.importTestWindow.result:SetText(message); MPL.importTestWindow:Show()
    end
    print("MPlusLogs: "..message)
end
