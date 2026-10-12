local _, MPL = ...
local locale = GetLocale and GetLocale() or "enUS"
if locale == "enGB" then locale = "enUS" end
local supported = {enUS=true,ruRU=true,deDE=true,esES=true,esMX=true,frFR=true,itIT=true,koKR=true,ptBR=true,zhCN=true,zhTW=true}
MPL.locale = supported[locale] and locale or "enUS"
MPL.L = setmetatable({}, {__index=function(_, key) return key end})

-- Translate known metadata/helper messages without changing imported records.
function MPL.T(text)
    return text and MPL.L[text] or ""
end
