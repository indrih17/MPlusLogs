local _, MPL = ...
local L = MPL.L
MPlusLogs = MPL
MPL.zone = 55
MPL.maxProfileAge = 24 * 60 * 60
local defaults={healerHpsFirst=false,percentile="best",freshHours=24,tooltips=true,stalePopup=true}

function MPL.GetOption(key)
    local options=MPlusLogsDB and MPlusLogsDB.options
    if options and options[key]~=nil then return options[key] end
    if key=="tooltips" and MPlusLogsDB and MPlusLogsDB.tooltips~=nil then return MPlusLogsDB.tooltips end
    return defaults[key]
end

function MPL.SetOption(key,value)
    if defaults[key]==nil then return false end
    if key=="percentile" then
        if value~="best" and value~="median" then return false end
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
    if MPL.GetOption("percentile")=="median" then return median,best end
    return best,median
end

function MPL.PercentileCaption()
    return MPL.GetOption("percentile")=="median" and "Median / Best" or "Best / Median"
end

function MPL.PrimaryPercentileLabel()
    return MPL.GetOption("percentile")=="median" and L["Median %"] or L["Best %"]
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

function MPL.FilterFreshProfiles(players)
    local pending,skipped={},0
    for _,player in ipairs(players) do
        local profile=MPL.GetProfile(player.name,player.realm,player.spec,player.role)
        local metric=MPL.PrimaryMetric(profile,player.name,player.realm,player.role)
        local usable=profile and (profile.dual or profile.metric==metric)
        if usable and not MPL.IsProfileStale(profile) then skipped=skipped+1
        else pending[#pending+1]=player end
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
    local name, suffix = fullName:match("^([^%-]+)%-(.+)$")
    name = name or fullName
    realm = suffix or (MPL.SafeString(realm) and realm) or GetNormalizedRealmName()
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

function MPL.SpecLabel(spec)
    if GetSpecializationInfoByID then
        for id,info in pairs(MPL.specInfo) do
            if info[1]==spec then
                local _,name=GetSpecializationInfoByID(id)
                if MPL.SafeString(name) then return name end
            end
        end
    end
    return MPL.T(spec)
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
    local info=MPL.specs and MPL.specs[key]
    if info and (role=="" or info[2]==role) then return info[1] end
    if role~="" then return "All specs" end
end

function MPL.SelectSpec(name,realm,spec,role)
    MPlusLogsDB=MPlusLogsDB or {}
    MPlusLogsDB.selectedSpecs=MPlusLogsDB.selectedSpecs or {}
    role=role or (MPL.roles and MPL.roles[MPL.Key(name,realm)]) or ""
    MPlusLogsDB.selectedSpecs[MPL.Key(name,realm)..":"..role]=spec
end

function MPL.RecordApplicant(fullName,role,specID,class)
    local name,realm=MPL.Identity(fullName)
    if not name then return end
    local key=MPL.Key(name,realm)
    MPL.roles=MPL.roles or {}; MPL.specs=MPL.specs or {}; MPL.classes=MPL.classes or {}
    MPL.roles[key]=MPL.SafeString(role) and ({HEALER=true,TANK=true,DAMAGER=true})[role] and role or nil
    local info=not (issecretvalue and issecretvalue(specID)) and MPL.specInfo[specID]
    MPL.specs[key]=info or nil
    MPL.classes[key]=MPL.SafeString(class) and class or nil
    return MPL.SelectedSpec(name,realm,MPL.roles[key])
end

function MPL.GetProfile(fullName, realm, spec, role)
    local name, server = MPL.Identity(fullName, realm)
    if not name then return end
    local key = MPL.Key(name, server)
    role=role or (MPL.roles and MPL.roles[key])
    spec=spec or MPL.SelectedSpec(name,server,role)
    if spec=="" then spec="All specs" end
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

function MPL.ProfileSpecs(name,realm,role)
    local result,seen={"All specs"},{["All specs"]=true}
    local key=MPL.Key(name,realm)
    local class=MPL.classes and MPL.classes[key]
    local function add(spec)
        if spec and not seen[spec] then result[#result+1]=spec; seen[spec]=true end
    end
    for _,info in pairs(MPL.specInfo) do
        if (not class or info[3]==class) and (not role or info[2]==role) then add(info[1]) end
    end
    local profile=MPL.GetProfile(name,realm)
    if profile then add(profile.spec) end
    for _,p in pairs(MPlusLogsDB and MPlusLogsDB.specProfiles and MPlusLogsDB.specProfiles[key] or {}) do
        local profileRole=MPL.ProfileRole(p)
        if not role or not profileRole or profileRole==role then add(p.spec) end
    end
    table.sort(result,function(a,b) if a==b then return false elseif a=="All specs" then return true elseif b=="All specs" then return false end; return a<b end)
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

function MPL.Percent(value, stale)
    if value == nil then return "—" end
    local color = value >= 99 and "ffe268a8" or value >= 95 and "ffff8000" or value >= 75 and "ffa335ee" or value >= 50 and "ff0070dd" or value >= 25 and "ff1eff00" or "ff999999"
    if stale then color="ff888888" end
    local text = string.format("%.1f", value):gsub("%.0$", "")
    return "|c" .. color .. text .. "%|r"
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
                        if current or (#f ~= 16 and #f ~= 19) then error(L["Некорректная запись профиля"]) end
                        if not ({eu=true,us=true,kr=true,tw=true,cn=true})[f[2]] then error(L["Неизвестный регион"]) end
                        if number(f[5], 10000, true) ~= MPL.zone then error(L["Этот импорт относится к другому сезону/zoneID"]) end
                        if f[8] ~= "dps" and f[8] ~= "hps" then error(L["Неизвестная метрика"]) end
                        count = count + 1
                        if count > 1000 then error(L["Слишком много профилей"]) end
                        current = {region=f[2], realm=required(f[3]), name=required(f[4]), zone=MPL.zone,
                            season=required(f[6]), spec=required(f[7]), metric=f[8], score=number(f[9]),
                            best=number(f[10],100), median=number(f[11],100), runs=number(f[12],10000000,true),
                            updated=required(f[13]), source=required(f[14]), characterID=number(f[15],1000000000,true),
                            realmSlug=f[16], dungeons={}}
                        if #f==19 then
                            if not ({HEALER=true,TANK=true,DAMAGER=true})[f[17]] then error(L["Неизвестная роль"]) end
                            current.dual=true; current.role=f[17]
                            if current.metric~=(current.role=="HEALER" and "hps" or "dps") then error(L["Метрика не соответствует роли"]) end
                            current.otherBest=number(f[18],100); current.otherMedian=number(f[19],100)
                        end
                    elseif f[1] == "D" then
                        if not current or (#f ~= 10 and #f ~= 14) or (#f==14 and not current.dual) then error(L["Некорректная запись данжа"]) end
                        if current.dual and #f~=14 then error(L["Неполная запись DPS/HPS"]) end
                        if #current.dungeons >= 32 then error(L["Слишком много данжей"]) end
                        current.dungeons[#current.dungeons+1] = {name=required(f[2]), level=number(f[3],100,true),
                            time=f[4], runs=number(f[5],10000000,true), amount=number(f[6]), best=number(f[7],100),
                            median=number(f[8],100), points=number(f[9]), rank=number(f[10],100000000,true)}
                        if #f==14 then
                            local row=current.dungeons[#current.dungeons]
                            row.otherLevel=number(f[11],100,true); row.otherAmount=number(f[12])
                            row.otherBest=number(f[13],100); row.otherMedian=number(f[14],100)
                        end
                    elseif f[1]=="F" and batch then
                        if current or #f~=5 or not ({eu=true,us=true,kr=true,tw=true,cn=true})[f[2]] then error(L["Некорректный результат загрузки"]) end
                        local name,realm=required(f[4]),required(f[3])
                        if #f[5]>500 or f[5]=="" then error(L["Некорректное описание ошибки"]) end
                        local key=MPL.Key(name,realm,f[2])
                        if failures[key] then error(L["Повторный результат загрузки"]) end
                        failures[key]={name=name,realm=realm,error=f[5]}
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
        if old then variants[MPL.VariantKey(old)]=old end
        variants[MPL.VariantKey(profile)]=profile
        MPlusLogsDB.specProfiles[key]=variants
        MPlusLogsDB.profiles[key]=profile
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
function MPL.URL(name, realm, profile)
    if profile and profile.characterID then return "https://www.warcraftlogs.com/character/id/" .. profile.characterID .. "?zone=" .. MPL.zone end
    -- The website accepts localized realm names; API sync requires a WCL realm slug.
    return "https://www.warcraftlogs.com/character/" .. MPL.Region() .. "/" .. encode(profile and profile.realmSlug ~= "" and profile.realmSlug or realm) .. "/" .. encode(name) .. "?zone=" .. MPL.zone
end
