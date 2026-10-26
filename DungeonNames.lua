local _, MPL = ...

-- Canonical WCL names remain data identities. Only displayed labels are resolved.
-- Russian names: Blizzard's current Mythic+ leaderboard, checked 2026-10-25:
-- https://worldofwarcraft.blizzard.com/ru-ru/worldsoul/eu/leaderboards/mythic-dungeon/turalyon/murder-row
-- Map IDs are the challenge-map IDs used by Integration.lua, not instance IDs.
MPL.DungeonCatalog = {
    {id=588,canonical="Altar of Fangs",names={enUS="Altar of Fangs",ruRU="Алтарь Клыков"},
        short={enUS="Altar of Fangs",ruRU="Алтарь Клыков"},abbreviation="AOF",icon="12993"},
    {id=586,canonical="Den of Nalorakk",names={enUS="Den of Nalorakk",ruRU="Берлога Налоракка"},
        short={enUS="Nalorakk",ruRU="Налоракк"},abbreviation="DON",icon="12825"},
    {id=249,canonical="Kings' Rest",names={enUS="Kings' Rest",ruRU="Гробница королей"},
        short={enUS="Kings' Rest",ruRU="Гробница королей"},abbreviation="KR",icon="11762"},
    {id=587,canonical="Murder Row",names={enUS="Murder Row",ruRU="Закоулок душегубов"},
        short={enUS="Murder Row",ruRU="Закоулок"},abbreviation="MR",icon="12813"},
    {id=399,canonical="Ruby Life Pools",names={enUS="Ruby Life Pools",ruRU="Рубиновые Омуты Жизни"},
        short={enUS="Ruby Life Pools",ruRU="Рубиновые Омуты"},abbreviation="RLP",icon="12521"},
    {id=250,canonical="Temple of Sethraliss",names={enUS="Temple of Sethraliss",ruRU="Храм Сетралисс"},
        short={enUS="Sethraliss",ruRU="Сетралисс"},abbreviation="TOS",icon="11877"},
    {id=584,canonical="The Blinding Vale",names={enUS="The Blinding Vale",ruRU="Слепящая долина"},
        short={enUS="Blinding Vale",ruRU="Слепящая долина"},abbreviation="BV",icon="12859"},
    {id=585,canonical="Voidscar Arena",names={enUS="Voidscar Arena",ruRU="Арена Шрама Бездны"},
        short={enUS="Voidscar Arena",ruRU="Арена"},abbreviation="VA",icon="12923"},
}

local byName,byID = {},{}
for _,entry in ipairs(MPL.DungeonCatalog) do
    byName[entry.canonical]=entry
    byID[entry.id]=entry
end

function MPL.DungeonInfo(identity)
    return byName[identity] or byID[tonumber(identity)]
end

local function option(key,default)
    if MPL.AppearanceValue then return MPL.AppearanceValue(key,default) end
    return default
end

local function safeText(text)
    return not (issecretvalue and issecretvalue(text)) and type(text)=="string" and text~=""
end

local function locale()
    local value=option("dungeonLanguage","enUS")
    if value=="client" or value=="auto" then
        value=GetLocale and GetLocale() or MPL.locale or "enUS"
    end
    return value=="enGB" and "enUS" or value
end

local function fullName(entry)
    local selected=option("dungeonLanguage","enUS")
    if (selected=="client" or selected=="auto") and C_ChallengeMode and C_ChallengeMode.GetMapUIInfo then
        local ok,name=pcall(C_ChallengeMode.GetMapUIInfo,entry.id)
        if ok and safeText(name) then return name end
    end
    return entry.names[locale()] or entry.canonical
end

function MPL.DungeonDisplayName(canonical)
    local entry=MPL.DungeonInfo(canonical)
    if not entry then return type(canonical)=="string" and canonical or tostring(canonical or "") end
    local format=option("dungeonFormat","full")
    if format=="custom" or format=="alias" then
        local alias=MPL.GetDungeonAlias and MPL.GetDungeonAlias(entry.id)
        if safeText(alias) then return alias end
    elseif format=="abbreviation" or format=="abbr" then
        return entry.abbreviation
    elseif format=="short" then
        return entry.short[locale()] or fullName(entry)
    end
    return fullName(entry)
end

-- Full localized name plus canonical name for a tooltip. This deliberately
-- ignores shortening/aliases so an icon-only or custom-labeled row stays clear.
function MPL.DungeonTooltipNames(canonical)
    local entry=MPL.DungeonInfo(canonical)
    if not entry then return MPL.DungeonDisplayName(canonical),canonical end
    return fullName(entry),entry.canonical
end

function MPL.GetAppearanceDungeonList()
    local result={}
    for _,entry in ipairs(MPL.DungeonCatalog) do
        result[#result+1]={id=entry.id,name=fullName(entry),canonical=entry.canonical}
    end
    return result
end
