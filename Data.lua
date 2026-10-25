local _, MPL = ...
local L = MPL.L
MPlusLogs = MPL
MPL.zone = 55
MPL.maxProfileAge = 24 * 60 * 60
local defaults={healerHpsFirst=false,percentile="best",freshHours=24,tooltips=true,stalePopup=true,
    showInRaids=false,showInPvp=false,showInOtherGroups=false,mainSpec="current",hideLogSettings=false,hideTutorial=false}

function MPL.GetOption(key)
    local options=MPlusLogsDB and MPlusLogsDB.options
    if options and options[key]~=nil then return options[key] end
    if key=="tooltips" and MPlusLogsDB and MPlusLogsDB.tooltips~=nil then return MPlusLogsDB.tooltips end
    return defaults[key]
end

function MPL.SetOption(key,value)
    if defaults[key]==nil then return false end
    if key=="percentile" then
        if not ({best=true,median=true,dungeon_dps=true,dungeon_median=true,dungeon_best=true})[value] then return false end
    elseif key=="mainSpec" then
        if value~="current" and value~="logs" then return false end
    elseif key=="freshHours" then
        if not ({[6]=true,[12]=true,[24]=true,[48]=true})[value] then return false end
    elseif type(value)~="boolean" then return false end
    MPlusLogsDB=MPlusLogsDB or {}; MPlusLogsDB.options=MPlusLogsDB.options or {}
    MPlusLogsDB.options[key]=value
    if key=="tooltips" then MPlusLogsDB.tooltips=value end
    if MPL.RefreshSettingsDisplays then MPL.RefreshSettingsDisplays() end
    return true
end

function MPL.OrderPercentiles(best,median)
    local option=MPL.GetOption("percentile")
    if option=="median" or option=="dungeon_median" then return median,best end
    return best,median
end

function MPL.PercentileCaption()
    local option=MPL.GetOption("percentile")
    return (option=="median" or option=="dungeon_median") and "Median / Best" or "Best / Median"
end

function MPL.PrimaryPercentileLabel(metric)
    local option=MPL.GetOption("percentile")
    if option=="dungeon_dps" then
        if metric=="hps" then return L["HPS (текущий данж)"] end
        if metric=="dps" then return L["DPS (текущий данж)"] end
        return L["DPS / HPS (текущий данж)"]
    end
    if option=="dungeon_median" then return L["Median (текущий данж)"] end
    if option=="dungeon_best" then return L["Best (текущий данж)"] end
    return MPL.GetOption("percentile")=="median" and L["Median %"] or L["Best %"]
end

function MPL.UsesDungeonMetric()
    return MPL.GetOption("percentile"):match("^dungeon_")~=nil
end

local function formatRate(value)
    if value==nil then return "—" end
    -- Promote rounded thousands at the boundary instead of displaying 1000K.
    if value>=999500 then
        local text=string.format("%.2f",value/1000000):gsub("0+$",""):gsub("%.$","")
        return text.."M"
    end
    if value>=1000 then return string.format("%.0fK",value/1000) end
    return string.format("%.0f",value)
end

function MPL.PrimaryStatistic(profile,metric,dungeon,stale,compactRate)
    local option=MPL.GetOption("percentile")
    local row
    if MPL.UsesDungeonMetric() then
        dungeon=dungeon or (MPL.ListedDungeon and MPL.ListedDungeon())
        for _,candidate in ipairs(profile.dungeons or {}) do
            if candidate.name==dungeon then row=candidate; break end
        end
        if not row then return "—" end
    end
    local _,amount,best,median=MPL.MetricValues(profile,row,metric)
    if option=="dungeon_dps" then
        if not amount then return "—" end
        local text=compactRate and formatRate(amount) or string.format("%.0f",amount)
        return stale and ("|cff888888"..text.."|r") or text
    end
    local value=best
    if option=="median" or option=="dungeon_median" then value=median end
    return MPL.Percent(value,stale)
end

function MPL.ProfileDate(profile)
    local y,m,d,h,n=(profile.updated or ""):match("^(%d%d%d%d)%-(%d%d)%-(%d%d) (%d%d):(%d%d) UTC$")
    y,m,d,h,n=tonumber(y),tonumber(m),tonumber(d),tonumber(h),tonumber(n)
    if not y or y<1970 or not m or m<1 or m>12 or h>23 or n>59 then return nil,L["дата неизвестна"] end
    local leap=y%4==0 and (y%100~=0 or y%400==0)
    local lengths={31,leap and 29 or 28,31,30,31,30,31,31,30,31,30,31}
    if d<1 or d>lengths[m] then return nil,L["дата неизвестна"] end
    local prior=y-1
    local days=365*(y-1970)+math.floor(prior/4)-math.floor(1969/4)
        -math.floor(prior/100)+math.floor(1969/100)+math.floor(prior/400)-math.floor(1969/400)+d-1
    for month=1,m-1 do days=days+lengths[month] end
    return days*86400+h*3600+n*60,string.format("%02d.%02d.%04d",d,m,y)
end

function MPL.IsProfileStale(profile, now)
    local timestamp,display=MPL.ProfileDate(profile)
    return not timestamp or (now or GetServerTime())-timestamp>=MPL.GetOption("freshHours")*3600,display
end

function MPL.ProfileRefreshRemaining(profile)
    local timestamp=profile and MPL.ProfileDate(profile)
    return timestamp and math.max(0,timestamp+5*60-GetServerTime()) or 0
end

local function profileDisplayMetadata(profile)
    if not profile then return end
    if profile.displayMetadata then return profile.displayMetadata end
    -- Saved API profiles from before the display extension have no transport
    -- marker. Actual extension fields confirm support; missing API percentiles
    -- alone never override the explicit marker on newer replies.
    if type(profile.source)~="string" or not profile.source:find("^WCL API:") then return end
    for _,rank in ipairs(profile.specRanks or {}) do if rank.rankPercent~=nil then return end end
    for _,row in ipairs(profile.dungeons or {}) do
        if row.rankPercent~=nil or row.flagged~=nil or row.otherFlagged~=nil then return end
    end
    return "companion"
end

function MPL.ProfileNeedsDisplayRefresh(profile)
    local state=profileDisplayMetadata(profile)
    return state=="refresh" or (state=="companion" and MPL.CompanionSupports and MPL.CompanionSupports("rankcolors")==true) or false
end

function MPL.ProfileDisplayWarning(profile)
    local state=profileDisplayMetadata(profile)
    if state~="companion" and state~="refresh" then return end
    if MPL.ProfileNeedsDisplayRefresh(profile) then return L["Некоторые данные отсутствуют. Обновите логи."] end
    return L["Некоторые данные отсутствуют. Обновите MPlusLogs Companion."]
end

function MPL.SetProfileDisplayMetadata(profiles,requested,supported)
    for _,profile in pairs(profiles) do
        profile.displayMetadata=supported and (requested and "complete" or "refresh") or "companion"
    end
end

function MPL.GetProfileState(name,realm,spec)
    local key=MPL.Key(name,realm)
    local state=MPL.profileStates and MPL.profileStates[key]
    if state and state.expires and state.expires<=GetServerTime() then state=nil end
    if not state then
        local saved=MPlusLogsDB and MPlusLogsDB.profileStates and MPlusLogsDB.profileStates[key]
        if saved and (saved.expires or 0)>GetServerTime() then state=saved end
    end
    -- Access is character-wide, including legacy saved states with a spec.
    if state and state.reason~="hidden" and state.spec and state.spec~="" and state.spec~=spec then return end
    return state
end

function MPL.FilterFreshProfiles(players,refresh,displayRefresh)
    local pending,skipped={},0
    for _,player in ipairs(players) do
        -- Party tabs outlive their initial spec snapshot. Refresh the profile
        -- currently selected in the UI, without mutating an in-flight batch.
        local spec=MPL.SelectedSpec(player.name,player.realm,player.role) or player.spec
        local profile=MPL.GetProfile(player.name,player.realm,spec,player.role)
        local metric=MPL.PrimaryMetric(profile,player.name,player.realm,player.role)
        local usable=profile and (profile.dual or profile.metric==metric)
        local state=MPL.GetProfileState(player.name,player.realm,spec)
        if state and state.reason=="hidden" then
            -- Known access failures are neither pending nor loaded profiles.
        elseif usable and not (displayRefresh and MPL.ProfileNeedsDisplayRefresh(profile)) and ((not refresh and not MPL.IsProfileStale(profile))
            or (refresh and MPL.ProfileRefreshRemaining(profile)>0)) then skipped=skipped+1
        else
            local request={}
            for key,value in pairs(player) do request[key]=value end
            request.spec=spec
            pending[#pending+1]=request
        end
    end
    return pending,skipped
end

function MPL.SafeString(value)
    return not (issecretvalue and issecretvalue(value)) and type(value) == "string" and value ~= ""
end

local upper = {"А","Б","В","Г","Д","Е","Ё","Ж","З","И","Й","К","Л","М","Н","О","П","Р","С","Т","У","Ф","Х","Ц","Ч","Ш","Щ","Ъ","Ы","Ь","Э","Ю","Я"}
local lower = {"а","б","в","г","д","е","ё","ж","з","и","й","к","л","м","н","о","п","р","с","т","у","ф","х","ц","ч","ш","щ","ъ","ы","ь","э","ю","я"}
local letters = {}
for i, letter in ipairs(upper) do letters[letter] = lower[i] end
function MPL.Normalize(value)
    value = value:gsub("[%z\1-\31\127]", ""):gsub("[|]", "")
    value = value:gsub("[\194-\244][\128-\191]+", letters)
    -- Lua 5.1 ctype functions may use a Windows codepage: never lowercase
    -- arbitrary UTF-8 bytes or use locale-dependent whitespace classes here.
    return (value:gsub("[A-Z]", string.lower):gsub("[ \t\r\n%-%']", ""))
end

function MPL.Region()
    return ({[1]="us", [2]="kr", [3]="eu", [4]="tw", [5]="cn"})[GetCurrentRegion()] or "eu"
end

function MPL.Identity(fullName, realm)
    if not MPL.SafeString(fullName) then return end
    -- An unavailable realm is not evidence that this is a local character.
    if issecretvalue and issecretvalue(realm) then return end
    local name, suffix = fullName:match("^([^%-]+)%-(.+)$")
    name = name or fullName
    realm = suffix or (MPL.SafeString(realm) and realm) or GetNormalizedRealmName()
    if not MPL.SafeString(realm) then return end
    return name, realm
end

function MPL.Key(name, realm, region)
    return (region or MPL.Region()) .. ":" .. MPL.Normalize(realm) .. ":" .. MPL.Normalize(name) .. ":" .. MPL.zone
end

-- WCL uses English specialization slugs regardless of the WoW client locale.
MPL.specInfo={
    [250]={"Blood","TANK","DEATHKNIGHT"},[251]={"Frost","DAMAGER","DEATHKNIGHT"},[252]={"Unholy","DAMAGER","DEATHKNIGHT"},
    [577]={"Havoc","DAMAGER","DEMONHUNTER"},[581]={"Vengeance","TANK","DEMONHUNTER"},[1480]={"Devourer","DAMAGER","DEMONHUNTER"},
    [102]={"Balance","DAMAGER","DRUID"},[103]={"Feral","DAMAGER","DRUID"},[104]={"Guardian","TANK","DRUID"},[105]={"Restoration","HEALER","DRUID"},
    [1467]={"Devastation","DAMAGER","EVOKER"},[1468]={"Preservation","HEALER","EVOKER"},[1473]={"Augmentation","DAMAGER","EVOKER"},
    [253]={"BeastMastery","DAMAGER","HUNTER"},[254]={"Marksmanship","DAMAGER","HUNTER"},[255]={"Survival","DAMAGER","HUNTER"},
    [62]={"Arcane","DAMAGER","MAGE"},[63]={"Fire","DAMAGER","MAGE"},[64]={"Frost","DAMAGER","MAGE"},
    [268]={"Brewmaster","TANK","MONK"},[269]={"Windwalker","DAMAGER","MONK"},[270]={"Mistweaver","HEALER","MONK"},
    [65]={"Holy","HEALER","PALADIN"},[66]={"Protection","TANK","PALADIN"},[70]={"Retribution","DAMAGER","PALADIN"},
    [256]={"Discipline","HEALER","PRIEST"},[257]={"Holy","HEALER","PRIEST"},[258]={"Shadow","DAMAGER","PRIEST"},
    [259]={"Assassination","DAMAGER","ROGUE"},[260]={"Outlaw","DAMAGER","ROGUE"},[261]={"Subtlety","DAMAGER","ROGUE"},
    [262]={"Elemental","DAMAGER","SHAMAN"},[263]={"Enhancement","DAMAGER","SHAMAN"},[264]={"Restoration","HEALER","SHAMAN"},
    [265]={"Affliction","DAMAGER","WARLOCK"},[266]={"Demonology","DAMAGER","WARLOCK"},[267]={"Destruction","DAMAGER","WARLOCK"},
    [71]={"Arms","DAMAGER","WARRIOR"},[72]={"Fury","DAMAGER","WARRIOR"},[73]={"Protection","TANK","WARRIOR"},
}

function MPL.VariantKey(profile)
    return profile.spec..":"..(profile.role or "")
end

function MPL.SpecLabel(spec,class)
    if GetSpecializationInfoByID then
        for id,info in pairs(MPL.specInfo) do
            if info[1]==spec and (not class or info[3]==class) then
                local _,name=GetSpecializationInfoByID(id)
                if MPL.SafeString(name) then return name end
            end
        end
    end
    return MPL.T(spec)
end

function MPL.SpecClass(spec)
    local class
    for _,info in pairs(MPL.specInfo) do
        if info[1]==spec then
            if class and class~=info[3] then return end
            class=info[3]
        end
    end
    return class
end

function MPL.ProfileRole(profile)
    if profile.role then return profile.role end
    if profile.spec~="All specs" then
        for _,info in pairs(MPL.specInfo) do if info[1]==profile.spec then return info[2] end end
    end
end

function MPL.SelectedSpec(name,realm,role)
    local key=MPL.Key(name,realm)
    role=role or (MPL.roles and MPL.roles[key]) or ""
    local choices=MPlusLogsDB and MPlusLogsDB.selectedSpecs
    local selected=choices and choices[key..":"..role]
    if selected then return selected end
    return "All specs"
end

function MPL.SelectSpec(name,realm,spec,role)
    MPlusLogsDB=MPlusLogsDB or {}
    MPlusLogsDB.selectedSpecs=MPlusLogsDB.selectedSpecs or {}
    role=role or (MPL.roles and MPL.roles[MPL.Key(name,realm)]) or ""
    MPlusLogsDB.selectedSpecs[MPL.Key(name,realm)..":"..role]=spec
end

-- Background callers only read known data. Opening a profile may request one
-- inspect; INSPECT_READY refreshes the visible badge when the reply arrives.
local lastSpecInspect=-math.huge
function MPL.RefreshCharacterSpec(name,realm,requestInspect)
    local key=MPL.Key(name,realm)
    local inspectUnit
    local units={"player","target","focus","mouseover"}
    for i=1,4 do units[#units+1]="party"..i end
    for i=1,40 do units[#units+1]="raid"..i end
    for _,unit in ipairs(units) do
        if UnitExists(unit) and UnitIsPlayer(unit) then
            local unitName,unitRealm=UnitFullName(unit)
            if MPL.SafeString(unitName) and not (issecretvalue and issecretvalue(unitRealm))
                and (unitRealm==nil or MPL.SafeString(unitRealm)) then
                unitName,unitRealm=MPL.Identity(unitName,unitRealm)
            else unitName=nil end
            if unitName and MPL.Key(unitName,unitRealm)==key then
                MPL.classes=MPL.classes or {}; MPL.specs=MPL.specs or {}
                if UnitClass then
                    local _,class=UnitClass(unit)
                    if MPL.SafeString(class) then MPL.classes[key]=class end
                end
                local api=C_SpecializationInfo or {}
                local specID
                if unit=="player" then
                    local getSpec=api.GetSpecialization or GetSpecialization
                    local getInfo=api.GetSpecializationInfo or GetSpecializationInfo
                    local index=getSpec and getSpec()
                    if index and not (issecretvalue and issecretvalue(index)) and getInfo then specID=getInfo(index) end
                else
                    local getInspect=api.GetInspectSpecialization or GetInspectSpecialization
                    if getInspect then specID=getInspect(unit) end
                    if not inspectUnit and requestInspect and CanInspect and CanInspect(unit,false) then inspectUnit=unit end
                end
                local info=specID and not (issecretvalue and issecretvalue(specID)) and MPL.specInfo[specID]
                if info then
                    MPL.specs[key]=info; MPL.classes[key]=info[3]
                end
                -- A duplicate target token may have no inspect data; keep looking
                -- for the player token or another token with a known spec.
                if info then return info end
            end
        end
    end
    if inspectUnit and NotifyInspect and not InCombatLockdown()
        and not (InspectFrame and InspectFrame:IsShown()) then
        local now=GetTime and GetTime() or GetServerTime()
        if now-lastSpecInspect>=3 then
            lastSpecInspect=now
            NotifyInspect(inspectUnit)
        end
    end
    return MPL.specs and MPL.specs[key]
end

function MPL.RecordApplicant(fullName,role,specID,class)
    local name,realm=MPL.Identity(fullName)
    if not MPL.SafeString(name) or not MPL.SafeString(realm) then return end
    local key=MPL.Key(name,realm)
    MPL.roles=MPL.roles or {}; MPL.specs=MPL.specs or {}; MPL.classes=MPL.classes or {}
    MPL.roles[key]=MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] and role or nil
    local info=not (issecretvalue and issecretvalue(specID)) and MPL.specInfo[specID]
    MPL.specs[key]=info or nil
    MPL.classes[key]=MPL.SafeString(class) and class or (info and info[3]) or nil
    return MPL.SelectedSpec(name,realm,MPL.roles[key])
end

function MPL.GetProfile(fullName, realm, spec, role)
    local explicitRole=role~=nil
    local explicitSpec=spec~=nil
    local name, server = MPL.Identity(fullName, realm)
    if not name then return end
    local key = MPL.Key(name, server)
    role=role or (MPL.roles and MPL.roles[key])
    spec=spec or MPL.SelectedSpec(name,server,role)
    if spec=="" then spec="All specs" end
    local choices=MPlusLogsDB and MPlusLogsDB.selectedSpecs
    local manual=choices and choices[key..":"..(role or "")]
    if not explicitRole and (explicitSpec or manual) and spec and spec~="All specs" then
        role=MPL.ProfileRole({spec=spec})
    end
    local selected
    local function consider(profile)
        if not profile then return end
        if spec and profile.spec~=spec then return end
        local profileRole=MPL.ProfileRole(profile)
        if role and profileRole and role~=profileRole then return end
        local stamp=MPL.ProfileDate(profile)
        local current=selected and MPL.ProfileDate(selected)
        if not selected or (stamp and (not current or stamp>current)) then selected=profile end
    end
    consider(MPlusLogsDB and MPlusLogsDB.profiles and MPlusLogsDB.profiles[key])
    for _,profile in pairs(MPlusLogsDB and MPlusLogsDB.specProfiles and MPlusLogsDB.specProfiles[key] or {}) do consider(profile) end
    consider(MPL.bundled and MPL.bundled[key])
    for _,profile in pairs(MPL.bundledSpecs and MPL.bundledSpecs[key] or {}) do consider(profile) end
    if not selected then consider(MPL.snapshots and MPL.snapshots[key]) end
    return selected, name, server
end

-- Manual log selection does not change the configured main specialization.
function MPL.MainProfileSpec(name,realm,role)
    if MPL.GetOption("mainSpec")=="logs" then return MPL.LoggedProfileSpec(name,realm,role) end
    local current=MPL.specs and MPL.specs[MPL.Key(name,realm)]
    if current and (not role or current[2]==role) then return current[1] end
end

-- Keep the fallback for choosing which saved logs to open when no current
-- specialization is known, without labelling that historical choice as main.
function MPL.DefaultProfileSpec(name,realm,role)
    return MPL.MainProfileSpec(name,realm,role) or MPL.LoggedProfileSpec(name,realm,role)
end

function MPL.LoggedProfileSpec(name,realm,role)
    local key=MPL.Key(name,realm)
    local latest,concrete,available=nil,nil,{}
    local function consider(p)
        if not p or (role and MPL.ProfileRole(p) and MPL.ProfileRole(p)~=role) then return end
        local spec=p.primarySpec or (p.spec~="All specs" and p.spec)
        if not spec then return end
        local stamp=MPL.ProfileDate(p) or 0
        if p.spec~="All specs" then
            available[p.spec]=true
            local last=concrete and (MPL.ProfileDate(concrete) or 0) or -1
            if not concrete or stamp>last or (stamp==last and p.spec<concrete.spec) then concrete=p end
        end
        local previous=latest and (MPL.ProfileDate(latest) or 0) or -1
        if not latest or stamp>previous or (stamp==previous and spec<(latest.primarySpec or latest.spec)) then latest=p end
    end
    consider(MPlusLogsDB and MPlusLogsDB.profiles and MPlusLogsDB.profiles[key])
    for _,p in pairs(MPlusLogsDB and MPlusLogsDB.specProfiles and MPlusLogsDB.specProfiles[key] or {}) do consider(p) end
    consider(MPL.bundled and MPL.bundled[key])
    for _,p in pairs(MPL.bundledSpecs and MPL.bundledSpecs[key] or {}) do consider(p) end
    if latest then
        local main=latest.primarySpec or latest.spec
        if not concrete or available[main] then return main end
    end
    if concrete then return concrete.spec end
end

function MPL.ProfileSpecs(name,realm,role)
    local result,seen={},{}
    local key=MPL.Key(name,realm)
    local function addSpec(spec)
        if not spec or spec=="All specs" or seen[spec] then return end
        if role and MPL.ProfileRole({spec=spec}) and MPL.ProfileRole({spec=spec})~=role then return end
        result[#result+1]=spec; seen[spec]=true
    end
    local function add(p)
        if not p then return end
        addSpec(p.spec)
        addSpec(p.primarySpec)
        for _,entry in ipairs(p.specRanks or {}) do addSpec(entry.spec) end
        for _,row in ipairs(p.dungeons or {}) do addSpec(row.scoreSpec) end
        for _,spec in ipairs(p.availableSpecs or {}) do addSpec(spec) end
    end
    add(MPlusLogsDB and MPlusLogsDB.profiles and MPlusLogsDB.profiles[key])
    for _,p in pairs(MPlusLogsDB and MPlusLogsDB.specProfiles and MPlusLogsDB.specProfiles[key] or {}) do add(p) end
    add(MPL.bundled and MPL.bundled[key])
    for _,p in pairs(MPL.bundledSpecs and MPL.bundledSpecs[key] or {}) do add(p) end
    table.sort(result)
    return result
end

function MPL.LoadBundle()
    if not MPL.bundledText or MPL.bundledText == "" then MPL.bundled = {}; MPL.bundledSpecs={}; return end
    local profiles, err = MPL.Parse(MPL.bundledText)
    if not profiles then print(L["MPlusLogs: ошибка базы: "] .. err); return end
    MPL.bundled = profiles
    MPL.bundledSpecs={}
    for _,profile in pairs(profiles) do
        local key=MPL.Key(profile.name,profile.realm,profile.region)
        MPL.bundledSpecs[key]=MPL.bundledSpecs[key] or {}
        MPL.bundledSpecs[key][MPL.VariantKey(profile)]=profile
    end
end

function MPL.Remember(name, realm)
    if not MPlusLogsDB or not MPL.SafeString(name) or not MPL.SafeString(realm) then return end
    MPlusLogsDB.requests = MPlusLogsDB.requests or {}
    local key = MPL.Key(name,realm)
    if MPlusLogsDB.requests[key] then return end
    local count = 0
    for _ in pairs(MPlusLogsDB.requests) do count = count + 1 end
    if count >= 1000 then return end
    MPlusLogsDB.requests[key] = {name=name, realm=realm, region=MPL.Region()}
end

function MPL.PercentColor(value)
    if value == nil then return nil end
    return value >= 100 and "e5cc80" or value >= 99 and "e268a8" or value >= 95 and "ff8000" or value >= 75 and "a335ee" or value >= 50 and "0070ff" or value >= 25 and "1eff00" or "666666"
end

function MPL.Percent(value, stale)
    if value == nil then return "—" end
    local color = stale and "888888" or MPL.PercentColor(value)
    local text = string.format("%.1f", value):gsub("%.0$", "")
    return "|cff" .. color .. text .. "%|r"
end

function MPL.MetricValues(profile, row, metric)
    row=row or profile
    if profile.metric==metric then return row.level,row.amount,row.best,row.median end
    return row.otherLevel,row.otherAmount,row.otherBest,row.otherMedian
end

function MPL.PrimaryMetric(profile,name,realm,role)
    role=role or (MPL.roles and MPL.roles[MPL.Key(name,realm)]) or (profile and profile.role)
    if MPL.GetOption("healerHpsFirst") and role=="HEALER" then return "hps" end
    return "dps"
end

local function clean(value)
    return value:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end):gsub("[%z\1-\31\127|]", "")
end

function MPL.DecodeCompanionError(message)
    local code,retry,text=message:match("^MPLERR1 ([a-z]+) (%d+):(.*)$")
    local known={hidden=true,missing=true,empty=true,retry=true,budget=true,auth=true,schema=true,network=true,unknown=true}
    retry=tonumber(retry)
    if not code or not known[code] or not retry or retry>253402300799 then return message end
    if code=="budget" and retry>GetServerTime() and not text:find("API reset at ",1,true) then
        text="API reset at "..string.format("%.0f",retry).."; "..text
    end
    return text,code,retry
end
local function fields(line)
    local result = {}
    for part in (line .. "\t"):gmatch("(.-)\t") do result[#result+1] = clean(part) end
    return result
end
local function number(value, max, integer)
    if value == "" then return nil end
    local n = tonumber(value)
    if not n or n ~= n or n < 0 or n > (max or 1000000000000) or (integer and n % 1 ~= 0) then error(L["Некорректное число"]) end
    return n
end
local function required(value)
    if not value or value == "" or #value > 200 then error(L["Отсутствует обязательное поле"]) end
    return value
end

-- Data-only import. Never evaluate pasted Lua or execute imported text.
function MPL.Parse(text, batch)
    if type(text) ~= "string" or #text > 500000 then return nil, L["Слишком большой импорт (максимум 500 КБ)"] end
    local ok, result = pcall(function()
        local profiles, current, header, failures = {}, nil, false, {}
        local count, lineNumber, variants = 0, 0, {}
        local rankStates, rankRows = {}, 0
        for line in (text .. "\n"):gmatch("([^\n]*)\n") do
            lineNumber=lineNumber+1
            line = line:gsub("\r$", "")
            if line ~= "" then
                if not header then
                    if line ~= (batch and "MPL2" or "MPL1") then error(L["Неверный формат ответа логов"]) end
                    header = true
                else
                    local f = fields(line)
                    if f[1] == "P" then
                        if current or (#f ~= 16 and #f ~= 17 and #f ~= 19 and #f ~= 20) then error(L["Некорректная запись профиля"]) end
                        rankStates, rankRows = {}, 0
                        if not ({eu=true,us=true,kr=true,tw=true,cn=true})[f[2]] then error(L["Неизвестный регион"]) end
                        if number(f[5], 10000, true) ~= MPL.zone then error(L["Этот импорт относится к другому сезону/zoneID"]) end
                        if f[8] ~= "dps" and f[8] ~= "hps" then error(L["Неизвестная метрика"]) end
                        count = count + 1
                        if count > 1000 then error(L["Слишком много профилей"]) end
                        current = {region=f[2], realm=required(f[3]), name=required(f[4]), zone=MPL.zone,
                            season=required(f[6]), spec=required(f[7]), metric=f[8], score=number(f[9]),
                            best=number(f[10],100), median=number(f[11],100), runs=number(f[12],10000000,true),
                            updated=required(f[13]), source=required(f[14]), characterID=number(f[15],1000000000,true),
                            realmSlug=f[16], dual=false, dungeons={}}
                        if #f==19 or #f==20 then
                            if not ({HEALER=true,TANK=true,DAMAGER=true})[f[17]] then error(L["Неизвестная роль"]) end
                            current.dual=true; current.role=f[17]
                            if current.metric~=(current.role=="HEALER" and "hps" or "dps") then error(L["Метрика не соответствует роли"]) end
                            current.otherBest=number(f[18],100); current.otherMedian=number(f[19],100)
                        end
                        if #f==17 or #f==20 then
                            current.primarySpec=required(f[#f])
                            if #current.primarySpec>80 then error(L["Некорректная запись профиля"]) end
                        end
                    elseif f[1] == "M" then
                        if not current or #f~=2 or f[2]~="dps" or not current.dual
                            or current.role~="DAMAGER" or current.metric~="dps" or current.secondaryPending
                            or #current.dungeons>0 or current.otherBest or current.otherMedian then
                            error(L["Некорректная запись профиля"])
                        end
                        current.secondaryPending=true
                    elseif f[1] == "A" then
                        if not current or #f~=2 then error(L["Некорректная запись профиля"]) end
                        local spec=required(f[2])
                        current.availableSpecs=current.availableSpecs or {}
                        if #spec>80 or #current.availableSpecs>=16 then error(L["Некорректная запись профиля"]) end
                        local known=false
                        for _,value in ipairs(current.availableSpecs) do if value==spec then known=true; break end end
                        if not known then current.availableSpecs[#current.availableSpecs+1]=spec end
                    elseif f[1] == "R" then
                        if not current or (#f~=3 and #f~=4) then error(L["Некорректная запись профиля"]) end
                        local spec=required(f[2])
                        local rank=number(f[3],100000000,true)
                        local percent=#f==4 and number(f[4],100) or nil
                        if #f==4 and percent==nil then error(L["Некорректная запись профиля"]) end
                        current.specRanks=current.specRanks or {}
                        rankRows=rankRows+1
                        if #spec>80 or not rank or rank<1 or rankRows>64 then error(L["Некорректная запись профиля"]) end
                        local previous=rankStates[spec]
                        if previous==nil then
                            local entry={spec=spec,rank=rank,rankPercent=percent}
                            rankStates[spec]=entry
                            current.specRanks[#current.specRanks+1]=entry
                        elseif previous and previous.rank~=rank then
                            -- Accept older Companions' repeated rows without
                            -- discarding the profile or choosing an uncertain rank.
                            rankStates[spec]=false
                            for i,entry in ipairs(current.specRanks) do
                                if entry==previous then table.remove(current.specRanks,i); break end
                            end
                        elseif previous and previous.rankPercent~=percent then
                            previous.rankPercent=nil
                        end
                    elseif f[1] == "D" then
                        if not current or (#f ~= 10 and #f ~= 11 and #f ~= 12 and #f ~= 13 and #f ~= 14 and #f ~= 15 and #f ~= 16 and #f ~= 17)
                            or (#f>=14 and not current.dual) then error(L["Некорректная запись данжа"]) end
                        if current.dual and #f<14 then error(L["Неполная запись DPS/HPS"]) end
                        if #current.dungeons >= 32 then error(L["Слишком много данжей"]) end
                        current.dungeons[#current.dungeons+1] = {name=required(f[2]), level=number(f[3],100,true),
                            time=f[4], runs=number(f[5],10000000,true), amount=number(f[6]), best=number(f[7],100),
                            median=number(f[8],100), points=number(f[9]), rank=number(f[10],100000000,true)}
                        local annotated=#f==13 or #f==17
                        local extended=#f==12 or #f==16 or annotated
                        local specIndex=current.dual and 15 or 11
                        if #f==11 or #f==15 or (extended and f[specIndex]~="") then
                            local spec=required(f[specIndex])
                            if #spec>80 then error(L["Некорректная запись данжа"]) end
                            current.dungeons[#current.dungeons].scoreSpec=spec
                        end
                        if extended then
                            -- A blank scoreSpec is allowed only in the explicit
                            -- percentile extension; old row shapes stay strict.
                            local percent=number(f[specIndex+1],100)
                            if percent==nil and not annotated then error(L["Некорректная запись данжа"]) end
                            current.dungeons[#current.dungeons].rankPercent=percent
                        end
                        if annotated then
                            local flags=f[#f]
                            if flags~="1" and flags~="2" and flags~="3" then error(L["Некорректная запись данжа"]) end
                            local row=current.dungeons[#current.dungeons]
                            row.flagged=flags=="1" or flags=="3" or nil
                            row.otherFlagged=flags=="2" or flags=="3" or nil
                            if row.otherFlagged and (not current.dual or current.secondaryPending) then
                                error(L["Некорректная запись данжа"])
                            end
                        end
                        if #f>=14 then
                            local row=current.dungeons[#current.dungeons]
                            row.otherLevel=number(f[11],100,true); row.otherAmount=number(f[12])
                            row.otherBest=number(f[13],100); row.otherMedian=number(f[14],100)
                            if current.secondaryPending and (row.otherLevel or row.otherAmount or row.otherBest or row.otherMedian) then
                                error(L["Некорректная запись данжа"])
                            end
                        end
                    elseif f[1]=="F" and batch then
                        if current or #f~=5 or not ({eu=true,us=true,kr=true,tw=true,cn=true})[f[2]] then error(L["Некорректный результат загрузки"]) end
                        local name,realm=required(f[4]),required(f[3])
                        if #f[5]>500 or f[5]=="" then error(L["Некорректное описание ошибки"]) end
                        local key=MPL.Key(name,realm,f[2])
                        if failures[key] then error(L["Повторный результат загрузки"]) end
                        local message,code,retry=MPL.DecodeCompanionError(f[5])
                        failures[key]={name=name,realm=realm,error=message,errorCode=code,retryAt=retry}
                    elseif f[1] == "E" then
                        if not current or #f ~= 1 then error(L["Некорректное завершение профиля"]) end
                        local key = MPL.Key(current.name, current.realm, current.region)
                        local variant=key..":"..MPL.VariantKey(current)
                        if variants[variant] then error(L["Дублирующийся профиль"]) end
                        variants[variant]=true
                        if profiles[key] then key=variant end
                        profiles[key], current = current, nil
                    else
                        local bytes={}
                        for index=1,math.min(12,#line) do bytes[#bytes+1]=string.format("%02X",line:byte(index)) end
                        error(L["Неизвестная строка импорта; строка "]..lineNumber..L[", байты "]..table.concat(bytes," "))
                    end
                end
            end
        end
        if not header or current or (count==0 and not (batch and next(failures))) then error(L["Пустой или незавершённый импорт"]) end
        return batch and {profiles=profiles,failures=failures} or profiles
    end)
    if not ok then return nil, tostring(result):match("[^:]+$") or L["Ошибка импорта"] end
    return result
end

function MPL.Import(text)
    local profiles, err = MPL.Parse(text)
    if not profiles then return nil, err end
    return MPL.StoreProfiles(profiles)
end

function MPL.StoreProfiles(profiles)
    MPlusLogsDB = MPlusLogsDB or {profiles={}}
    MPlusLogsDB.profiles = MPlusLogsDB.profiles or {}
    MPlusLogsDB.specProfiles = MPlusLogsDB.specProfiles or {}
    local count = 0
    for _, profile in pairs(profiles) do
        local key=MPL.Key(profile.name,profile.realm,profile.region)
        local variants=MPlusLogsDB.specProfiles[key] or {}
        -- Migrate a legacy profile before updating the compatibility view.
        local old=MPlusLogsDB.profiles[key]
        if old and old.realmInferred and profile.realmInferred==nil then profile.realmInferred=true end
        if old then variants[MPL.VariantKey(old)]=old end
        variants[MPL.VariantKey(profile)]=profile
        MPlusLogsDB.specProfiles[key]=variants
        MPlusLogsDB.profiles[key]=profile
        if MPL.profileStates then MPL.profileStates[key]=nil end
        if MPlusLogsDB.profileStates then MPlusLogsDB.profileStates[key]=nil end
        count=count+1
    end
    return count
end

local function encode(value)
    return value:gsub("([^A-Za-z0-9%-%._~])", function(c) return string.format("%%%02X", c:byte()) end)
end
function MPL.ExportRequests()
    local rows = {}
    for _, request in pairs(MPlusLogsDB and MPlusLogsDB.requests or {}) do
        rows[#rows+1] = "Q\t" .. encode(request.region) .. "\t" .. encode(request.realm) .. "\t" .. encode(request.name)
    end
    table.sort(rows)
    return "MPLQ1\n" .. table.concat(rows,"\n") .. "\n", #rows
end
function MPL.ExportCharacterRequest(name, realm, metric, spec, role)
    if not MPL.SafeString(name) or not MPL.SafeString(realm) then return end
    -- Character names/realms from WoW can stay readable in the copy field.
    -- The companion accepts UTF-8 as well as the older percent-encoded format.
    local function field(text) return (text:gsub("[%z\1-\31\127|]","")) end
    local text="MPLQ1\nQ\t" .. MPL.Region() .. "\t" .. field(realm) .. "\t" .. field(name)
        .. "\t" .. (metric == "hps" and "hps" or "dps") .. "\t" .. field(spec or "")
    if role then text=text.."\t"..field(role) end
    return text.."\n"
end
-- WCL encounter IDs for Midnight Season 2; these differ from instance/art IDs.
local dungeonEncounters={
    ["Altar of Fangs"]=12993,["Den of Nalorakk"]=12825,["Kings' Rest"]=61762,["Murder Row"]=12813,
    ["Ruby Life Pools"]=112521,["Temple of Sethraliss"]=61877,["The Blinding Vale"]=12859,["Voidscar Arena"]=12923,
}
function MPL.DungeonURL(name,realm,profile,dungeon,metric)
    local encounter=MPL.zone==55 and dungeonEncounters[dungeon]
    if not encounter then return nil end
    return MPL.URL(name,realm,profile).."&boss="..encounter
        .."&metric="..(metric=="hps" and "points_and_healing" or "points_and_damage")
end
function MPL.URL(name, realm, profile)
    if profile and profile.characterID then return "https://www.warcraftlogs.com/character/id/" .. profile.characterID .. "?zone=" .. MPL.zone end
    -- The website accepts localized realm names; API sync requires a WCL realm slug.
    return "https://www.warcraftlogs.com/character/" .. MPL.Region() .. "/" .. encode(profile and profile.realmSlug ~= "" and profile.realmSlug or realm) .. "/" .. encode(name) .. "?zone=" .. MPL.zone
end
