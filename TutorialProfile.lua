local _, MPL = ...
local function t(ru,en) return MPL.locale=="ruRU" and ru or en end

local function sample(spec)
    local healer=spec=="Restoration"
    local profile={name="Tutorial",realm="Example",region="eu",class="DRUID",
        spec=spec,role=healer and "HEALER" or "TANK",metric="dps",dual=true,
        score=0,best=0,median=0,otherBest=0,otherMedian=0,runs=0,dungeons={}}
    for i,name in ipairs({"Kings' Rest","Murder Row","Ruby Life Pools","Temple of Sethraliss",
        "Altar of Fangs","Den of Nalorakk","The Blinding Vale","Voidscar Arena"}) do
        profile.dungeons[i]={name=name,level=12+i%2,time="28:42",runs=10+i,
            points=348+i*8,rank=125+i*17,amount=(healer and 80000 or 420000)+i*1200,
            best=96-i*2,median=84-i*3,otherLevel=12+i%2,
            otherAmount=(healer and 950000 or 125000)+i*1500,
            otherBest=healer and 98-i or 72-i*3,otherMedian=healer and 90-i or 60-i*2}
        local row=profile.dungeons[i]
        profile.score=profile.score+row.points; profile.runs=profile.runs+row.runs
        profile.best=profile.best+row.best; profile.median=profile.median+row.median
        profile.otherBest=profile.otherBest+row.otherBest; profile.otherMedian=profile.otherMedian+row.otherMedian
    end
    local count=#profile.dungeons
    profile.best=profile.best/count; profile.median=profile.median/count
    profile.otherBest=profile.otherBest/count; profile.otherMedian=profile.otherMedian/count
    return profile
end

local function render(f,spec)
    f.profile=sample(spec or f.selectedSpec or "Guardian")
    f.selectedSpec=f.profile.spec
    f.specButton:SetText(MPL.SpecLabel(f.selectedSpec,"DRUID"))
    f.specButton.detail:SetText(t("Выбрать специализацию логов","Choose log specialization"))
    local texture=f.selectedSpec=="Restoration" and "Interface/Icons/Spell_Nature_HealingTouch"
        or "Interface/Icons/Ability_Racial_BearForm"
    f.specButton.icon:SetTexture(texture)
    f.currentSpec.name:SetText(MPL.SpecLabel(f.selectedSpec,"DRUID"))
    f.currentSpec.icon:SetTexture(texture); f.currentSpec.icon:Show()
    MPL.RenderProfileStats(f)
    -- Dungeon links cannot lead to a fictional character on the real website.
    for _,row in ipairs(f.rows) do
        row.url=nil
        row:SetScript("OnMouseUp",nil)
        row.scoreSpecIcon:SetScript("OnMouseUp",nil)
    end
end

function MPL.ShowTutorialProfile()
    if InCombatLockdown() then return nil end
    local f=MPL.tutorialProfile
    if not f then
        f=MPL.CreateTutorialProfileFrame()
        MPL.tutorialProfile=f
        f.sortRefresh=render
        f.name,f.realm,f.class="Tutorial","Example","DRUID"
        f.viewMetric="dps"; f.stale=false
        f.title:SetText(t("MPlusLogs / Учебный профиль","MPlusLogs / Tutorial profile"))
        f.character:SetText(t("Учебный друид / вымышленные данные","Tutorial druid / fictional data"))
        f.context:SetText("Midnight M+ Season 2")
        f.source:SetText(t("Учебные данные: внешний вид настоящего профиля MPlusLogs.",
            "Sample data in the actual MPlusLogs profile layout."))
        f.note:SetText(t("Переключайте DPS / HPS и специализацию. Запросы Warcraft Logs не отправляются.",
            "Switch DPS / HPS and specializations. No Warcraft Logs requests are sent."))
        f.footer:SetText(t("Закройте профиль, чтобы вернуться к обучению.",
            "Close the profile to return to the tutorial."))
        f.emptyMessage:Hide(); f.staleBanner:Hide(); f.inviteButton:Hide(); f.inviteInfo:Hide()
        f.lookup:SetText("Tutorial-Example"); f.lookup:EnableMouse(false)
        f.lookup:SetScript("OnEnterPressed",nil)
        f.lookupButton:Disable(); f.lookupButton:SetScript("OnClick",nil)
        f.wclButton:Disable(); f.wclButton:SetScript("OnClick",nil)
        f.loadButton:SetScript("OnUpdate",nil)
        f.loadButton:SetScript("OnClick",function()
            f.footer:SetText(t("Это учебный профиль. Для настоящей загрузки откройте профиль игрока.",
                "This is a sample profile. Open a player's profile to load actual logs."))
        end)
        for metric,tab in pairs(f.metricTabs) do
            local selectedMetric=metric
            tab:SetScript("OnClick",function() f.viewMetric=selectedMetric; render(f) end)
        end
        f.specButton.canSelectSpecs=true
        f.specButton:SetScript("OnClick",function()
            if MenuUtil and MenuUtil.CreateContextMenu then
                MenuUtil.CreateContextMenu(f.specButton,function(_,root)
                    for _,spec in ipairs({"Guardian","Restoration"}) do
                        local selectedSpec=spec
                        root:CreateRadio(MPL.SpecLabel(spec,"DRUID"),
                            function() return f.selectedSpec==selectedSpec end,
                            function() render(f,selectedSpec) end)
                    end
                end)
            else render(f,f.selectedSpec=="Guardian" and "Restoration" or "Guardian") end
        end)
    end
    if not f:IsShown() then f.sortColumn=false; f.sortAscending=false end
    f.viewMetric="dps"
    render(f,"Guardian")
    f:Show()
    return f
end
