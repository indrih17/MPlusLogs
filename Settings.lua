local _, MPL = ...
local L = MPL.L

function MPL.RefreshSettingsDisplays()
    if GameTooltip then GameTooltip.mplKey=nil; GameTooltip:Hide() end
    if not MPL.GetOption("stalePopup") and MPL.staleWindow then MPL.staleWindow:Hide() end
    local f=MPL.panel
    if f and f:IsShown() then
        local sent=f.inviteSent
        MPL.ShowProfile(f.name,f.realm,f.applicant,true)
        if sent then f.inviteSent=true; MPL.UpdateProfileInvite() end
    end
    if MPL.UpdateBatchButton then MPL.UpdateBatchButton() end
end

function MPL.RegisterSettings()
    if MPL.settingsCategory or not Settings or not Settings.RegisterVerticalLayoutCategory then return end
    local category,layout=Settings.RegisterVerticalLayoutCategory("MPlusLogs")
    local function setting(key,kind,title,default)
        return Settings.RegisterProxySetting(category,"MPLUSLOGS_"..key,kind,title,default,
            function() return MPL.GetOption(key) end,function(value) MPL.SetOption(key,value) end)
    end
    Settings.CreateCheckbox(category,setting("healerHpsFirst",Settings.VarType.Boolean,L["HPS первым для хилов"],false),
        L["Для хилов показывать HPS перед DPS в заявках, тултипе и полной сводке."])
    Settings.CreateDropdown(category,setting("percentile",Settings.VarType.String,L["Основной процентиль"],"best"),function()
        local options=Settings.CreateControlTextContainer()
        options:Add("best","Best avg"); options:Add("median","Median")
        options:Add("dungeon_dps",L["DPS / HPS (текущий данж)"])
        options:Add("dungeon_median",L["Median (текущий данж)"])
        options:Add("dungeon_best",L["Best (текущий данж)"])
        return options:GetData()
    end,L["В заявках показывается выбранный показатель; в сводке и тултипе он идёт первым."].."\n"..L["Текущий данж — подземелье вашей группы в поиске. При отсутствии его логов показывается «—»."])
    Settings.CreateDropdown(category,setting("freshHours",Settings.VarType.Number,L["Срок актуальности логов"],24),function()
        local options=Settings.CreateControlTextContainer()
        for _,hours in ipairs({6,12,24,48}) do options:Add(hours,string.format(L["%d ч."],hours)) end
        return options:GetData()
    end,L["Более старые данные считаются устаревшими и обновляются при общей загрузке."])
    Settings.CreateCheckbox(category,setting("tooltips",Settings.VarType.Boolean,L["Показывать логи в тултипах"],true),
        L["Добавлять показатели M+ при наведении на персонажей и заявки."])
    Settings.CreateCheckbox(category,setting("stalePopup",Settings.VarType.Boolean,L["Предупреждать об устаревших логах"],true),
        L["Показывать окно обновления при открытии устаревшего профиля. Серый цвет данных сохраняется."])
    Settings.CreateDropdown(category,setting("mainSpec",Settings.VarType.String,L["Основной спек"],"current"),function()
        local options=Settings.CreateControlTextContainer()
        options:Add("current",L["Текущий"]); options:Add("logs",L["По логам"])
        return options:GetData()
    end,L["Текущий — специализация из данных заявки или группы. По логам — специализация по сохранённой истории WCL; может отличаться от текущей."])
    layout:AddInitializer(CreateSettingsListSectionHeaderInitializer(L["Где ещё показывать логи М+"]))
    Settings.CreateCheckbox(category,setting("showInRaids",Settings.VarType.Boolean,L["Показывать логи М+ в рейдах"],false),
        L["Показывать логи M+ в заявках и поиске рейдовых групп."])
    Settings.CreateCheckbox(category,setting("showInPvp",Settings.VarType.Boolean,L["Показывать логи М+ в PvP"],false),
        L["Показывать логи M+ в заявках и поиске групп для арен и полей боя."])
    Settings.CreateCheckbox(category,setting("showInOtherGroups",Settings.VarType.Boolean,L["Показывать логи М+ в других группах"],false),
        L["Все остальные группы: мировые боссы, обычные подземелья, вылазки и произвольные сборы."])
    Settings.RegisterAddOnCategory(category)
    MPL.settingsCategory=category
end

function MPL.OpenSettings()
    MPL.RegisterSettings()
    if MPL.settingsCategory then Settings.OpenToCategory(MPL.settingsCategory:GetID()) end
end
