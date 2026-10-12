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
    local category=Settings.RegisterVerticalLayoutCategory("MPlusLogs")
    local function setting(key,kind,title,default)
        return Settings.RegisterProxySetting(category,"MPLUSLOGS_"..key,kind,title,default,
            function() return MPL.GetOption(key) end,function(value) MPL.SetOption(key,value) end)
    end
    Settings.CreateCheckbox(category,setting("healerHpsFirst",Settings.VarType.Boolean,L["HPS первым для хилов"],false),
        L["Для хилов показывать HPS перед DPS в заявках, тултипе и полной сводке."])
    Settings.CreateDropdown(category,setting("percentile",Settings.VarType.String,L["Основной процентиль"],"best"),function()
        local options=Settings.CreateControlTextContainer()
        options:Add("best","Best avg"); options:Add("median","Median")
        return options:GetData()
    end,L["В заявках показывается выбранный показатель; в сводке и тултипе он идёт первым."])
    Settings.CreateDropdown(category,setting("freshHours",Settings.VarType.Number,L["Срок актуальности логов"],24),function()
        local options=Settings.CreateControlTextContainer()
        for _,hours in ipairs({6,12,24,48}) do options:Add(hours,string.format(L["%d ч."],hours)) end
        return options:GetData()
    end,L["Более старые данные считаются устаревшими и обновляются при общей загрузке."])
    Settings.CreateCheckbox(category,setting("tooltips",Settings.VarType.Boolean,L["Показывать логи в тултипах"],true),
        L["Добавлять показатели M+ при наведении на персонажей и заявки."])
    Settings.CreateCheckbox(category,setting("stalePopup",Settings.VarType.Boolean,L["Предупреждать об устаревших логах"],true),
        L["Показывать окно обновления при открытии устаревшего профиля. Серый цвет данных сохраняется."])
    Settings.RegisterAddOnCategory(category)
    MPL.settingsCategory=category
end

function MPL.OpenSettings()
    MPL.RegisterSettings()
    if MPL.settingsCategory then Settings.OpenToCategory(MPL.settingsCategory:GetID()) end
end
