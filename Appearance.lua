local _, MPL = ...

-- Appearance is deliberately independent of log options and profile navigation.
local defaults, fields, byKey = {}, {}, {}
local columns = {"dungeon","level","time","runs","points","rank","rate","best","median"}
MPL.AppearanceColumns=columns
MPL.AppearanceDefaults=defaults
MPL.AppearanceFields=fields
local function copy(value,depth)
    if type(value)~="table" then return value end
    if (depth or 0)>10 then return nil end
    local result={}
    for key,item in pairs(value) do
        if type(key)=="string" or type(key)=="number" then result[key]=copy(item,(depth or 0)+1) end
    end
    return result
end
MPL.CopyAppearanceValue=copy
local function add(key,label,section,kind,value,min,max,options,advanced)
    local field={key=key,label=label,section=section,kind=kind,min=min,max=max,step=kind=="number" and 1 or nil,options=options,advanced=advanced}
    fields[#fields+1]=field; byKey[key]=field; defaults[key]=copy(value)
    return field
end
local function opts(...)
    local values={...}; local result={}
    for i=1,#values,2 do result[#result+1]={value=values[i],label=values[i+1]} end
    return result
end
add("scale","Window scale","window","number",1,0.65,1.5).step=0.05
-- The season has eight dungeons; this is a fixed baseline, not an editor field.
defaults.maxRows=8
add("locked","Lock window position","window","boolean",false)
add("compactSummary","Compact summary","window","boolean",true)
add("verticalLayout","Vertical layout","window","boolean",false)
add("headerLayout","Profile header layout","window","select","modern",nil,nil,opts("modern","Modern header","original","Original header"))
add("showRealm","Show character realm","window","boolean",true,nil,nil,nil,true)
add("compactAge","Compact data age warning","window","boolean",false,nil,nil,nil,true)
for _,entry in ipairs({{"showRating","Show Mythic+ rating"},{"showSummary","Show summary"},{"showSpecRanks","Show specialization ranks"},{"showSeason","Show season"},{"showNotes","Show explanations"},{"showSource","Show source and update date"}}) do
    add(entry[1],entry[2],"window","boolean",true)
end
add("rowHeight","Row height","table","number",26,20,48)
add("headerHeight","Table header height","table","number",40,24,72,nil,true)
add("cellPadding","Cell padding","table","number",6,0,20)
add("iconSize","Dungeon icon size","table","number",20,12,36,nil,true)
add("scoreIconSize","Specialization icon size","table","number",16,10,30,nil,true)
add("showDungeonIcons","Show dungeon icons","table","boolean",true)
add("showScoreIcons","Show specialization icons","table","boolean",true)
add("showGroupHeaders","Show grouped headings","table","boolean",true)
add("showHover","Highlight hovered row","table","boolean",true)
add("striped","Alternate row backgrounds","table","boolean",true)
add("gridMode","Grid lines","table","select","full",nil,nil,opts("legacy","Classic alternating grid","none","None","horizontal","Horizontal","vertical","Vertical","full","All table dividers"))
add("gridThickness","Grid thickness","table","number",1,1,3,nil,true)
add("tableBorder","Outer table border","table","boolean",false,nil,nil,nil,true)
add("font","Font","fonts","select","native",nil,nil,opts("native","Game interface font"))
add("fontSize","Base font size","fonts","number",10,9,24)
add("fontOutline","Font outline","fonts","select","inherit",nil,nil,opts("inherit","Original","none","None","OUTLINE","Outline","THICKOUTLINE","Thick outline"))
add("fontShadow","Emphasize numeric text","fonts","boolean",true,nil,nil,nil,true)
local roles={"title","character","summary","rating","header","dungeon","numbers","secondary","button","warning"}
local roleLabels={title="Window title",character="Character name",summary="Summary",rating="Mythic+ rating",header="Table headings",dungeon="Dungeon names",numbers="Numbers",secondary="Secondary text",button="Buttons",warning="Data age warning"}
for _,role in ipairs(roles) do
    add("font_"..role,roleLabels[role].." font","fonts","select","inherit",nil,nil,opts("inherit","Inherit base font","native","Game interface font"),true)
    add("size_"..role,roleLabels[role].." size (0 = inherit)","fonts","number",0,0,40,nil,true)
end
add("levelDigits","Key level digits","fonts","select","natural",nil,nil,opts("natural","Natural spacing","aligned","Aligned decimal places"))
add("digitGap","Extra digit spacing","fonts","number",0,0,4,nil,true)
add("numericFormat","DPS / HPS format","fonts","select","compact",nil,nil,opts("compact","Compact K / M","full","Full number"))
add("numericPrecision","DPS / HPS decimal places","fonts","number",2,0,2)
add("pointsPrecision","Points decimal places","fonts","number",0,0,2,nil,true)
add("percentPrecision","Percentile decimal places","fonts","number",1,0,1,nil,true)
add("showPercentSign","Show percent sign in table","fonts","boolean",false,nil,nil,nil,true)
add("thousandsSeparator","Thousands separator","fonts","select","none",nil,nil,opts("none","None","space","Space","comma","Comma"),true)
add("decimalSeparator","Decimal separator","fonts","select","dot",nil,nil,opts("dot","Dot","comma","Comma","locale","Game language"),true)
add("timeFormat","Duration format","fonts","select","clock",nil,nil,opts("clock","29:26","words","29m 26s"),true)
add("surfaceOpacity","Background opacity","colors","number",0.9,0,1).step=0.05
add("borderThickness","Window border thickness","colors","number",1,0,3,nil,true)
add("semanticColors","Use Warcraft Logs percentile colors","colors","boolean",true)
local colorDefs={
    {"backgroundColor","Window background",0,0,0,1},{"titleBackgroundColor","Title background",0.105,0.06,0.12,1},
    {"headerColor","Table header background",18/255,18/255,18/255,1},{"rowColor","Row background",0,0,0,1},
    {"stripeColor","Alternate row background",0.018,0.018,0.018,1},{"hoverColor","Row hover",0.055,0.055,0.055,1},
    {"gridColor","Grid color",0.20,0.20,0.20,1},{"borderColor","Window border",0.27,0.27,0.27,1},
    {"textColor","Primary text",225/255,242/255,245/255,1},{"mutedColor","Secondary text",225/255,242/255,245/255,1},
    {"dungeonColor","Dungeon names",0.72,0.78,1,1},{"numberColor","Numbers",225/255,242/255,245/255,1},
    {"semanticLowColor","Percentiles below 25",102/255,102/255,102/255,1},
    {"semanticRareColor","Percentiles from 50 to 74",0,112/255,1,1},
    {"semanticEpicColor","Percentiles from 75 to 94",163/255,53/255,238/255,1},
    {"rateColor","DPS / HPS values",0.82,0.96,0.65,1},{"accentColor","Accent",0.64,0.45,0.83,1},
    {"buttonColor","Button background",0.12,0.10,0.16,1},{"buttonTextColor","Button text",1,1,1,1},
    {"warningColor","Data age warning background",0.12,0.075,0.015,1},{"warningTextColor","Data age warning text",1,196/255,64/255,1},
    {"ratingColor","Mythic+ rating color",226/255,104/255,168/255,1},{"missingColor","Missing values",0.5,0.5,0.5,1},
    {"selectedColor","Selected tab",0.28,0.13,0.40,1},{"disabledColor","Disabled controls",0.35,0.35,0.38,1},
}
for _,c in ipairs(colorDefs) do add(c[1],c[2],"colors","color",{c[3],c[4],c[5],c[6]},nil,nil,nil,true) end
add("dungeonLanguage","Dungeon language","names","select","enUS",nil,nil,opts("client","Game language","enUS","English"))
add("dungeonFormat","Dungeon name format","names","select","full",nil,nil,opts("full","Full names","short","Short names","abbreviation","Abbreviations","custom","Personal names"))
local columnLabels={dungeon="Dungeon",level="Key level",time="Time",runs="Runs",points="Points",rank="Rank",rate="Best DPS / HPS",best="Best %",median="Median %"}
local visibleLabels={time="Duration column",runs="Runs column",rank="Leaderboard place",best="Best percentile",median="Median percentile"}
for _,id in ipairs(columns) do
    add("column_"..id.."_visible",visibleLabels[id] or columnLabels[id],"table","boolean",true)
    add("column_"..id.."_align",columnLabels[id].." alignment","table","select",id=="dungeon" and "LEFT" or "RIGHT",nil,nil,opts("LEFT","Left","CENTER","Center","RIGHT","Right"),true)
    add("column_"..id.."_padding",columnLabels[id].." padding (-1 = inherit)","table","number",-1,-1,30,nil,true)
    add("column_"..id.."_label",columnLabels[id].." custom heading","table","string","",nil,nil,nil,true)
end
-- Player-facing explanations are presentation metadata, never saved settings.
local help={
    headerLayout="Use the original profile header with the addon title, character name, specialization selector and large rating, or the compact modern header.",
    scale="Scales the entire log window, including text. 1 is normal size; 1.5 is 150%.",
    locked="Prevents dragging the log window. Turn this off to move it again.",
    compactSummary="Uses shorter summary wording. Results and specialization ranks sit below the table in the modern header and above it in the original header. Blocks wrap when space is limited.",
    verticalLayout="In the modern header, places specialization, Mythic+ rating and DPS/HPS controls on separate rows, and stacks each summary block below the table.",
    showRealm="Shows the realm next to the character name. This only changes the display, not which character is loaded.",
    compactAge="Shortens the wording of the outdated logs warning. The warning and last update date remain visible.",
    showRating="Shows the Mythic+ rating above the table.",
    showSummary="Shows log summaries. In the modern header this controls the whole block below the table, including logged runs and specialization ranks. Best and Median follow the table column order, including hidden columns.",
    showSpecRanks="Shows specialization ranks when available. In the modern header they belong to the results summary and are hidden together with it.",
    showSeason="Shows the season below the table in the modern header or above the table in the original header.",
    showNotes="Shows an explanation of Best and Median percentiles below the table. This explanation can remain visible when the results summary is hidden.",
    showSource="Shows where the logs came from and when they were last loaded.",
    rowHeight="Minimum row height in interface units. Rows grow automatically if larger text or icons need more space.",
    headerHeight="Minimum height of the two-level table headings, in interface units. Hiding column group headings halves this height. Large text can increase it.",
    cellPadding="Space between text and the left or right edge of a table cell, in interface units. Individual columns can override it.",
    iconSize="Dungeon icon size in interface units. The row grows if needed to fit the icon.",
    scoreIconSize="Size of specialization icons next to dungeon points, in interface units.",
    showDungeonIcons="Shows an icon next to each dungeon name.",
    showScoreIcons="Shows which specialization earned the displayed dungeon points, when known.",
    showGroupHeaders="Shows the shared headings above groups of related table columns.",
    showHover="Highlights the table row under the mouse pointer.",
    striped="Uses alternating backgrounds to make neighboring rows easier to follow.",
    gridMode="Choose lines between rows, between columns, or both. The classic option draws borders on alternate rows.",
    gridThickness="Thickness of the table dividers in interface units. Visible only when dividers are enabled.",
    tableBorder="Draws a border around the entire dungeon table.",
    font="Main font for the log window. Individual text elements can use a different font below.",
    fontSize="Adjusts text throughout the window while preserving the relative sizes of headings and other elements. Explicit sizes below override it.",
    fontOutline="Adds an outline around letters and digits to improve contrast against the background.",
    fontShadow="Allows text shadows for contrast. This does not make the font bold.",
    levelDigits="Normal digits use the font's spacing. Equal-width digits align key levels by digit position.",
    digitGap="Extra space between key level digits, in interface units. Only applies when equal-width digits are selected.",
    numericFormat="Shortens large values using K for thousands and M for millions, or writes the full number.",
    numericPrecision="Decimal places in shortened K/M values. Zero hides the fractional part. Full numbers are always shown without a fractional part.",
    pointsPrecision="Digits after the decimal separator in dungeon points. This does not change the underlying result.",
    percentPrecision="Maximum digits after the decimal separator in percentiles. Trailing zeroes may be omitted.",
    showPercentSign="Adds a percent sign to best and median percentile values, including the compact summary.",
    thousandsSeparator="Groups long numbers for readability, for example 1234567 or 1 234 567.",
    decimalSeparator="Choose a dot, a comma, or the separator used by the game language.",
    timeFormat="Changes only how the dungeon duration is written: 29:26 or 29m 26s.",
    surfaceOpacity="0 makes background surfaces transparent; 1 makes them fully opaque. Text remains visible. Each color can also have its own opacity.",
    borderThickness="Window border thickness in interface units. Zero hides the border.",
    semanticColors="Uses the Warcraft Logs result color scale instead of the chosen text colors for those results.",
    semanticLowColor="RGB color for percentiles below 25 when percentile colors are enabled. Contrast depends on the background and its transparency.",
    semanticRareColor="RGB color for percentiles from 50 to 74 when percentile colors are enabled. Contrast depends on the background and its transparency.",
    semanticEpicColor="RGB color for percentiles from 75 to 94 when percentile colors are enabled. Contrast depends on the background and its transparency.",
    dungeonLanguage="Chooses the language for dungeon names. If a translation is unavailable, the original name is used.",
    dungeonFormat="Choose full names, short names, abbreviations, or your own names. Enter your own names in the fields below; leave a field blank to use the normal name.",
    font_role="Uses the main font unless you choose a separate font for this element.",
    size_role="Zero chooses this element's normal size, adjusted by the overall text size. A positive number sets an exact size in interface units.",
    color="Choose this element's color and opacity. A six-character code specifies the color; an eight-character code also specifies opacity.",
    visible="Shows or hides this table column. The dungeon column always remains visible.",
    align="Positions the text against the left edge, the right edge, or the center of this column.",
    padding="Text inset from the cell edge, in interface units. -1 uses the shared cell spacing setting.",
    label="Replaces this column's heading. Leave blank to restore the standard heading.",
}
for _,field in ipairs(fields) do
    local role=field.key:match("^font_") and "font_role" or field.key:match("^size_") and "size_role"
    local column=field.key:match("^column_[^_]+_(.+)$")
    field.help=help[field.key] or help[role] or help[column] or (field.kind=="color" and help.color)
end

defaults.columnOrder=copy(columns)
-- Preset layout identity is retained by copies and exports, not exposed as a
-- second player-facing layout switch. Missing values keep existing themes.
defaults.legacyLayout=false
defaults.legacyCenteredHeadings=false
local function finite(value) return type(value)=="number" and value==value and value~=math.huge and value~=-math.huge end
local function plain(text,limit)
    return type(text)=="string" and #text<=(limit or 160) and not text:find("[%z\1-\31\127|]")
end
local function normalizeOrder(value)
    local result,seen={},{}
    if type(value)=="table" then
        for i=1,math.min(#value,32) do
            local id=value[i]
            if columnLabels[id] and not seen[id] then result[#result+1]=id; seen[id]=true end
        end
    end
    for _,id in ipairs(columns) do if not seen[id] then result[#result+1]=id end end
    return result
end
local function normalizeField(field,value)
    if field.key=="dungeonLanguage" and value=="ruRU" then return "client" end
    if field.kind=="boolean" then if type(value)=="boolean" then return value end; return defaults[field.key] end
    if field.kind=="number" then
        if not finite(value) then return defaults[field.key] end
        value=math.max(field.min,math.min(field.max,value))
        if field.step==1 then value=math.floor(value+0.5) end
        return value
    end
    if field.kind=="color" then
        if type(value)~="table" then return copy(defaults[field.key]) end
        local color={}
        for i=1,4 do color[i]=finite(value[i]) and math.max(0,math.min(1,value[i])) or defaults[field.key][i] end
        return color
    end
    if field.key=="font" or field.key:match("^font_") then return plain(value,160) and value~="" and value or defaults[field.key] end
    if field.kind=="select" then
        for _,option in ipairs(field.options or {}) do if option.value==value then return value end end
        return defaults[field.key]
    end
    return plain(value,120) and value or defaults[field.key]
end
local function normalizeTheme(value)
    value=type(value)=="table" and value or {}
    local result={}
    result.maxRows=8
    for _,field in ipairs(fields) do result[field.key]=normalizeField(field,value[field.key]) end
    result.columnOrder=normalizeOrder(value.columnOrder)
    result.legacyLayout=value.legacyLayout==true
    result.legacyCenteredHeadings=value.legacyCenteredHeadings==true
    result.column_dungeon_visible=true
    return result
end
MPL.NormalizeAppearance=normalizeTheme
local function styleValues(values)
    local result={}
    for _,field in ipairs(fields) do
        if field.kind~="color" and field.key~="surfaceOpacity" and field.key~="semanticColors" then result[field.key]=copy(values[field.key]) end
    end
    for _,key in ipairs({"columnOrder","legacyLayout","legacyCenteredHeadings"}) do result[key]=copy(values[key]) end
    return result
end
local function paletteValues(values)
    local result={}
    for _,field in ipairs(fields) do if field.kind=="color" then result[field.key]=copy(values[field.key]) end end
    return result
end
local function normalizeAliases(value)
    local result={}
    if type(value)=="table" then
        for id,alias in pairs(value) do
            if (type(id)=="number" or type(id)=="string") and #tostring(id)<=80 and plain(alias,120) then result[tostring(id)]=alias end
        end
    end
    return result
end
local function newState()
    return {schemaVersion=2,activeTheme="classic",themes={},styles={},palettes={},aliases={},profileAliases={},profileSelections={},legacyProfiles={},characterThemes={}}
end
local function characterKey()
    local name,realm
    if UnitFullName then name,realm=UnitFullName("player") end
    realm=realm or (GetNormalizedRealmName and GetNormalizedRealmName())
    return type(name)=="string" and name.."-"..(realm or "") or "player"
end
local function normalizeState(value)
    local result=newState()
    if type(value)~="table" then return result end
    if plain(value.activeTheme,80) then result.activeTheme=value.activeTheme end
    result.aliases=normalizeAliases(value.aliases)
    local count=0
    if type(value.themes)=="table" then
        for id,theme in pairs(value.themes) do
            if count<30 and plain(id,80) and type(theme)=="table" then
                result.themes[id]={name=plain(theme.name,80) and theme.name or id,values=normalizeTheme(theme.values or theme),
                    aliases=normalizeAliases(type(theme.aliases)=="table" and theme.aliases or result.aliases)}
                count=count+1
            end
        end
    end
    if type(value.profileAliases)=="table" then
        for id,aliases in pairs(value.profileAliases) do
            if plain(id,80) then result.profileAliases[id]=normalizeAliases(aliases) end
        end
    end
    for _,kind in ipairs({"styles","palettes"}) do
        local entries=value[kind]
        local saved=0
        if type(entries)=="table" then
            for id,entry in pairs(entries) do
                if saved<30 and plain(id,80) and type(entry)=="table" then
                    local normalized=normalizeTheme(entry.values or entry.colors or {})
                    result[kind][id]={name=plain(entry.name,80) and entry.name or id,
                        values=kind=="styles" and styleValues(normalized) or paletteValues(normalized)}
                    saved=saved+1
                end
            end
        end
    end
    if type(value.characterThemes)=="table" then
        for id,theme in pairs(value.characterThemes) do if plain(id,160) and plain(theme,80) then result.characterThemes[id]=theme end end
    end
    if type(value.profileSelections)=="table" then
        for id,selection in pairs(value.profileSelections) do
            if plain(id,80) and type(selection)=="table" then
                result.profileSelections[id]={style=plain(selection.style,80) and selection.style or nil,
                    palette=plain(selection.palette,80) and selection.palette or nil}
            end
        end
    end
    if type(value.legacyProfiles)=="table" then
        for id,enabled in pairs(value.legacyProfiles) do if plain(id,80) and enabled==true then result.legacyProfiles[id]=true end end
    end
    if value.schemaVersion~=2 then
        if not result.themes[result.activeTheme] then result.legacyProfiles[result.activeTheme]=true end
        for _,id in pairs(result.characterThemes) do if not result.themes[id] then result.legacyProfiles[id]=true end end
    end
    return result
end
local store,storeOwner,draft,undo,actionSnapshot,requested=false,false,nil,{},nil,false
function MPL.InitAppearance()
    MPlusLogsDB=MPlusLogsDB or {}
    if storeOwner==MPlusLogsDB and store==MPlusLogsDB.appearance then return store end
    local raw=MPlusLogsDB.appearance
    if type(raw)=="table" and raw.schemaVersion and raw.schemaVersion~=1 and raw.schemaVersion~=2 then
        MPlusLogsDB.appearanceFuture=raw
    end
    store=normalizeState(type(raw)=="table" and (not raw.schemaVersion or raw.schemaVersion==1 or raw.schemaVersion==2) and raw or nil)
    MPlusLogsDB.appearance=store; storeOwner=MPlusLogsDB
    return store
end
function MPL.GetAppearanceState() return draft or MPL.InitAppearance() end
function MPL.GetAppearanceThemeID()
    local state=MPL.GetAppearanceState()
    return state.characterThemes[characterKey()] or state.activeTheme or "classic"
end
local function currentAliases(state)
    state=state or MPL.GetAppearanceState()
    local id=MPL.GetAppearanceThemeID()
    local profile=state.themes[id]
    return profile and profile.aliases or state.profileAliases[id] or state.aliases
end
local function preferredTemplate(kind)
    local state=MPL.GetAppearanceState()
    local selection=state.profileSelections[MPL.GetAppearanceThemeID()]
    return selection and selection[kind]
end
local function selectTemplate(kind,id)
    local state=MPL.GetAppearanceState(); local profileID=MPL.GetAppearanceThemeID()
    state.profileSelections[profileID]=state.profileSelections[profileID] or {}
    state.profileSelections[profileID][kind]=id
end
local function builtin(id)
    local entry=MPL.AppearancePresets and MPL.AppearancePresets[id]
    return entry and (entry.values or entry)
end
function MPL.GetAppearance()
    local state=MPL.GetAppearanceState(); local id=MPL.GetAppearanceThemeID()
    local theme=state.themes[id]
    if theme then return theme.values end
    return builtin(id) or defaults
end
function MPL.AppearanceValue(key,fallback)
    local value=MPL.GetAppearance()[key]
    if value==nil then return fallback end
    return value
end
function MPL.AppearancePercentColor(value)
    if type(value)~="number" or value~=value then return nil end
    local key
    if not MPL.AppearanceValue("semanticColors",true) then key="numberColor"
    elseif value<25 then key="semanticLowColor"
    elseif value>=50 and value<75 then key="semanticRareColor"
    elseif value>=75 and value<95 then key="semanticEpicColor"
    else return MPL.PercentColor(value) end
    local color=MPL.AppearanceValue(key,defaults[key])
    -- FontString color escapes carry RGB only; saved swatches retain alpha.
    return string.format("%02x%02x%02x",math.floor(color[1]*255+.5),math.floor(color[2]*255+.5),math.floor(color[3]*255+.5))
end
function MPL.RequestAppearanceRefresh()
    if requested then return end
    requested=true
    local function apply()
        requested=false
        if MPL.ApplyAppearanceToViews then MPL.ApplyAppearanceToViews() end
        if MPL.ApplyAppearanceToEditor then MPL.ApplyAppearanceToEditor() end
    end
    if C_Timer and C_Timer.After then C_Timer.After(0,apply) else apply() end
end
local function remember()
    if not draft then MPL.BeginAppearanceEdit() end
    if actionSnapshot then return end
    undo[#undo+1]=copy(draft)
    if #undo>20 then table.remove(undo,1) end
end
function MPL.BeginAppearanceEdit()
    if draft then return true end
    draft=copy(MPL.InitAppearance()); undo={}; return true
end
function MPL.IsAppearanceEditing() return draft~=nil end
function MPL.BeginAppearanceAction()
    if not draft then MPL.BeginAppearanceEdit() end
    if not actionSnapshot then actionSnapshot=copy(draft); undo[#undo+1]=copy(draft); if #undo>20 then table.remove(undo,1) end end
end
function MPL.EndAppearanceAction() actionSnapshot=nil end
function MPL.SaveAppearanceEdit(skipRefresh)
    if not draft then return false end
    store=normalizeState(draft); MPlusLogsDB=MPlusLogsDB or {}; MPlusLogsDB.appearance=store; storeOwner=MPlusLogsDB
    draft=nil; undo={}; actionSnapshot=nil
    if not skipRefresh then MPL.RequestAppearanceRefresh() end
    return true
end
function MPL.CancelAppearanceEdit()
    if not draft then return false end
    draft=nil; undo={}; actionSnapshot=nil; MPL.RequestAppearanceRefresh(); return true
end
function MPL.UndoAppearanceEdit()
    if not draft or #undo==0 then return false,"Nothing to undo" end
    draft=table.remove(undo); actionSnapshot=nil; MPL.RequestAppearanceRefresh(); return true
end
local function uniqueID(state)
    local i=1
    while state.themes["custom"..i] do i=i+1 end
    return "custom"..i
end
local function editableTheme()
    local state=MPL.GetAppearanceState(); local id=MPL.GetAppearanceThemeID()
    if not state.themes[id] then
        local values=copy(MPL.GetAppearance())
        local newID=uniqueID(state)
        state.themes[newID]={name=MPL.L and MPL.L["Custom profile"] or "Custom profile",values=values,aliases=copy(currentAliases(state))}
        state.profileSelections[newID]=copy(state.profileSelections[id])
        if state.characterThemes[characterKey()] then state.characterThemes[characterKey()]=newID else state.activeTheme=newID end
        id=newID
    end
    return state.themes[id].values
end
local function canEditTheme()
    local state=MPL.GetAppearanceState()
    if state.themes[MPL.GetAppearanceThemeID()] then return true end
    local count=0; for _ in pairs(state.themes) do count=count+1 end
    return count<30
end
function MPL.SetAppearanceValue(key,value)
    local field=byKey[key]
    if key~="columnOrder" and not field then return false,"Unknown appearance setting" end
    if field and field.kind=="boolean" and type(value)~="boolean" then return false,"Expected a boolean" end
    if field and field.kind=="number" and not finite(value) then return false,"Expected a finite number" end
    if field and field.kind=="color" and type(value)~="table" then return false,"Expected a color" end
    if field and (field.kind=="select" or field.kind=="string") and type(value)~="string" then return false,"Expected text" end
    if field and (field.kind=="select" or field.kind=="string") and not plain(value,field.kind=="string" and 120 or 160) then return false,"Invalid appearance text" end
    if field and field.kind=="select" and field.key~="font" and not field.key:match("^font_") then
        local valid=false
        for _,option in ipairs(field.options or {}) do if option.value==value then valid=true; break end end
        if not valid then return false,"Invalid appearance choice" end
    end
    if key=="column_dungeon_visible" and value==false then return false,"Dungeon identity must remain visible" end
    if not canEditTheme() then return false,"Too many themes" end
    remember()
    local sourceStyle=MPL.GetAppearanceStyleID()
    local theme=editableTheme()
    if sourceStyle then selectTemplate("style",sourceStyle) end
    theme[key]=key=="columnOrder" and normalizeOrder(value) or normalizeField(field,value)
    -- An explicit alignment edit takes precedence over the historical preset.
    if key:match("^column_.*_align$") then theme.legacyCenteredHeadings=false end
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.SetAppearanceColumnOrder(order) return MPL.SetAppearanceValue("columnOrder",order) end
local function sortNamedEntries(entries)
    table.sort(entries,function(a,b)
        if a.builtin~=b.builtin then return not a.builtin end
        if a.name==b.name then return a.id<b.id end
        return a.name<b.name
    end)
    return entries
end
local function equalValue(a,b)
    if type(a)~=type(b) then return false end
    if type(a)=="number" then return math.abs(a-b)<=1e-9 end
    if type(a)~="table" then return a==b end
    for key,value in pairs(a) do if not equalValue(value,b[key]) then return false end end
    for key in pairs(b) do if a[key]==nil then return false end end
    return true
end
function MPL.GetAppearanceStyles()
    local result={}
    for _,id in ipairs(MPL.AppearancePresetOrder or {}) do
        local entry=MPL.AppearancePresets[id]
        result[#result+1]={id=id,name=entry.name,builtin=true,values=styleValues(entry.values)}
    end
    for id,entry in pairs(MPL.GetAppearanceState().styles) do
        result[#result+1]={id=id,name=entry.name,builtin=false,values=copy(entry.values)}
    end
    return sortNamedEntries(result)
end
function MPL.GetAppearanceStyleID()
    local values=styleValues(MPL.GetAppearance())
    local entries=MPL.GetAppearanceStyles(); local preferred=preferredTemplate("style")
    for _,entry in ipairs(entries) do if entry.id==preferred and equalValue(values,entry.values) then return entry.id end end
    for _,entry in ipairs(entries) do if equalValue(values,entry.values) then return entry.id end end
end
function MPL.GetAppearanceStyleSourceID()
    return MPL.GetAppearanceStyleID() or preferredTemplate("style") or "classic"
end
function MPL.ApplyAppearanceStyle(id)
    local selected
    for _,entry in ipairs(MPL.GetAppearanceStyles()) do if entry.id==id then selected=entry; break end end
    if not selected then return false,"Unknown appearance style" end
    if MPL.GetAppearanceStyleID()==id then return true end
    if not canEditTheme() then return false,"Too many themes" end
    remember(); local theme=editableTheme()
    for key,value in pairs(selected.values) do theme[key]=copy(value) end
    selectTemplate("style",id)
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.GetAppearancePalettes()
    local result={}
    -- Keep the authored builtin order after custom palettes.
    local custom={}
    for id,entry in pairs(MPL.GetAppearanceState().palettes) do
        custom[#custom+1]={id=id,name=entry.name,builtin=false,colors=copy(entry.values)}
    end
    for _,entry in ipairs(sortNamedEntries(custom)) do result[#result+1]=entry end
    for _,id in ipairs(MPL.AppearanceColorPresetOrder or {}) do
        local entry=MPL.AppearanceColorPresets[id]
        result[#result+1]={id=id,name=entry.name,builtin=true,colors=copy(entry.colors)}
    end
    return result
end
local function createTemplate(kind,name)
    if not plain(name,80) or not name:match("%S") then return nil,"Enter a template name" end
    local entries=MPL.GetAppearanceState()[kind]
    local count=0; for _ in pairs(entries) do count=count+1 end
    if count>=30 then return nil,"Too many templates" end
    local values=kind=="styles" and styleValues(MPL.GetAppearance()) or paletteValues(MPL.GetAppearance())
    remember(); entries=MPL.GetAppearanceState()[kind]
    local prefix=kind=="styles" and "style" or "palette"
    local i=1; while entries[prefix..i] do i=i+1 end
    local id=prefix..i; entries[id]={name=name,values=values}
    selectTemplate(kind=="styles" and "style" or "palette",id)
    MPL.RequestAppearanceRefresh(); return id
end
local function renameTemplate(kind,id,name)
    if not MPL.GetAppearanceState()[kind][id] then return false,"Built-in templates cannot be renamed" end
    if not plain(name,80) or not name:match("%S") then return false,"Enter a template name" end
    remember(); MPL.GetAppearanceState()[kind][id].name=name
    MPL.RequestAppearanceRefresh(); return true
end
local function deleteTemplate(kind,id)
    if not MPL.GetAppearanceState()[kind][id] then return false,"Built-in templates cannot be deleted" end
    remember(); MPL.GetAppearanceState()[kind][id]=nil
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.CreateAppearanceStyle(name) return createTemplate("styles",name) end
function MPL.RenameAppearanceStyle(id,name) return renameTemplate("styles",id,name) end
function MPL.DeleteAppearanceStyle(id) return deleteTemplate("styles",id) end
function MPL.CreateAppearancePalette(name) return createTemplate("palettes",name) end
function MPL.RenameAppearancePalette(id,name) return renameTemplate("palettes",id,name) end
function MPL.DeleteAppearancePalette(id) return deleteTemplate("palettes",id) end
function MPL.GetAppearanceColorPresetID()
    local theme=MPL.GetAppearance()
    local entries=MPL.GetAppearancePalettes(); local preferred=preferredTemplate("palette")
    local matched
    for _,palette in ipairs(entries) do
        local same=true
        for key,color in pairs(palette.colors) do
            local actual=theme[key]
            for i=1,4 do
                -- Theme exports round numbers through Lua's tostring.
                if not actual or math.abs(actual[i]-color[i])>1e-9 then same=false; break end
            end
            if not same then break end
        end
        if same and palette.id==preferred then return palette.id end
        if same and not matched then matched=palette.id end
    end
    return matched
end
function MPL.ApplyAppearanceColorPreset(id)
    local palette
    for _,entry in ipairs(MPL.GetAppearancePalettes()) do if entry.id==id then palette=entry; break end end
    if not palette then return false,"Unknown color palette" end
    if MPL.GetAppearanceColorPresetID()==id then return true end
    if not canEditTheme() then return false,"Too many themes" end
    remember()
    local theme=editableTheme()
    for _,field in ipairs(fields) do
        if field.kind=="color" then theme[field.key]=copy(palette.colors[field.key]) end
    end
    selectTemplate("palette",id)
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.MoveAppearanceColumn(id,direction)
    local order=copy(MPL.GetAppearance().columnOrder)
    for i,value in ipairs(order) do
        if value==id then
            local target=i+(direction<0 and -1 or 1)
            if target<1 or target>#order then return false end
            order[i],order[target]=order[target],order[i]
            return MPL.SetAppearanceColumnOrder(order)
        end
    end
    return false
end
function MPL.ResetAppearance(section)
    if not canEditTheme() then return false,"Too many themes" end
    remember(); local theme=editableTheme()
    local baseline=builtin("classic") or defaults
    if not section or section=="quick" then
        for key,value in pairs(baseline) do theme[key]=copy(value) end
    else
        for _,field in ipairs(fields) do if field.section==section then theme[field.key]=copy(baseline[field.key]) end end
        if section=="table" then theme.columnOrder=copy(columns); theme.legacyCenteredHeadings=baseline.legacyCenteredHeadings end
        if section=="window" then theme.legacyLayout=baseline.legacyLayout end
    end
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.GetAppearanceThemes()
    local result={}
    for _,id in ipairs(MPL.AppearancePresetOrder or {"classic"}) do
        local entry=MPL.AppearancePresets and MPL.AppearancePresets[id]
        result[#result+1]={id=id,name=entry and entry.name or "Classic",builtin=true}
    end
    for id,entry in pairs(MPL.GetAppearanceState().themes) do result[#result+1]={id=id,name=entry.name,builtin=false} end
    table.sort(result,function(a,b)
        if a.builtin~=b.builtin then return not a.builtin end
        if a.name==b.name then return a.id<b.id end
        return a.name<b.name
    end)
    return result
end
function MPL.GetAppearancePresets()
    local result={}
    for _,entry in ipairs(MPL.GetAppearanceThemes()) do if entry.builtin then result[#result+1]=entry end end
    return result
end
function MPL.GetAppearanceProfiles()
    local state=MPL.GetAppearanceState()
    local result={}
    local used={classic=true,[MPL.GetAppearanceThemeID()]=true}
    for id in pairs(state.legacyProfiles) do used[id]=true end
    for _,id in pairs(state.characterThemes) do used[id]=true end
    for id,entry in pairs(state.themes) do result[#result+1]={id=id,name=entry.name,builtin=false} end
    for id in pairs(used) do
        if not state.themes[id] and builtin(id) then
            result[#result+1]={id=id,name=id=="classic" and "Default profile" or MPL.AppearancePresets[id].name,builtin=true}
        end
    end
    return sortNamedEntries(result)
end
function MPL.GetAppearanceProfileID() return MPL.GetAppearanceThemeID() end
function MPL.SelectAppearanceTheme(id)
    local state=MPL.GetAppearanceState()
    if not (builtin(id) or id=="classic" or state.themes[id]) then return false,"Unknown theme" end
    remember(); state=MPL.GetAppearanceState()
    if state.characterThemes[characterKey()] then state.characterThemes[characterKey()]=id else state.activeTheme=id end
    MPL.RequestAppearanceRefresh(); return true
end
MPL.SelectAppearancePreset=MPL.SelectAppearanceTheme
function MPL.CreateAppearanceTheme(name)
    if not plain(name,80) or not name:match("%S") then return nil,"Enter a theme name" end
    local state=MPL.GetAppearanceState(); local count=0; for _ in pairs(state.themes) do count=count+1 end
    if count>=30 then return nil,"Too many themes" end
    local values=copy(MPL.GetAppearance()); remember(); state=MPL.GetAppearanceState()
    local aliases=copy(currentAliases(state))
    local selection=copy(state.profileSelections[MPL.GetAppearanceThemeID()])
    local id=uniqueID(state); state.themes[id]={name=name,values=values,aliases=aliases}; state.profileSelections[id]=selection
    if state.characterThemes[characterKey()] then state.characterThemes[characterKey()]=id else state.activeTheme=id end
    MPL.RequestAppearanceRefresh(); return id
end
function MPL.RenameAppearanceTheme(id,name)
    local state=MPL.GetAppearanceState()
    if not state.themes[id] then return false,"Built-in themes cannot be renamed" end
    if not plain(name,80) or not name:match("%S") then return false,"Enter a theme name" end
    remember(); MPL.GetAppearanceState().themes[id].name=name; return true
end
function MPL.DeleteAppearanceTheme(id)
    local state=MPL.GetAppearanceState()
    if not state.themes[id] then return false,"Built-in themes cannot be deleted" end
    remember(); state=MPL.GetAppearanceState(); state.themes[id]=nil; state.profileAliases[id]=nil; state.profileSelections[id]=nil
    if state.activeTheme==id then state.activeTheme="classic" end
    for key,value in pairs(state.characterThemes) do if value==id then state.characterThemes[key]=nil end end
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.SelectAppearanceProfile(id)
    if id~="classic" and not MPL.GetAppearanceState().themes[id] and id~=MPL.GetAppearanceThemeID() then
        local known=false
        for _,entry in ipairs(MPL.GetAppearanceProfiles()) do if entry.id==id then known=true; break end end
        if not known then return false,"Unknown appearance profile" end
    end
    return MPL.SelectAppearanceTheme(id)
end
function MPL.CreateAppearanceProfile(name) return MPL.CreateAppearanceTheme(name) end
function MPL.RenameAppearanceProfile(id,name) return MPL.RenameAppearanceTheme(id,name) end
function MPL.DeleteAppearanceProfile(id) return MPL.DeleteAppearanceTheme(id) end
function MPL.SetAppearanceCharacterTheme(enabled)
    remember(); local state=MPL.GetAppearanceState(); local key=characterKey()
    state.characterThemes[key]=enabled and MPL.GetAppearanceThemeID() or nil
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.GetAppearanceCharacterBinding()
    return MPL.GetAppearanceState().characterThemes[characterKey()] and "character" or "account"
end
function MPL.SetAppearanceCharacterBinding(scope)
    if scope~="character" and scope~="account" then return false,"Invalid theme scope" end
    return MPL.SetAppearanceCharacterTheme(scope=="character")
end
function MPL.GetDungeonAlias(id) return currentAliases()[tostring(id)] end
function MPL.SetDungeonAlias(id,value)
    if not plain(value,120) or (type(id)~="string" and type(id)~="number") or #tostring(id)>80 then return false,"Invalid dungeon name" end
    remember(); local state=MPL.GetAppearanceState(); local profileID=MPL.GetAppearanceThemeID()
    if not state.themes[profileID] and not state.profileAliases[profileID] then state.profileAliases[profileID]=copy(currentAliases(state)) end
    currentAliases(state)[tostring(id)]=value~="" and value or nil
    MPL.RequestAppearanceRefresh(); return true
end
function MPL.ResetAppearanceForCharacter()
    -- Close the editor first: its OnHide invalidates outstanding picker/text
    -- callbacks before they can revive the draft that recovery discards.
    if MPL.appearanceEditor and MPL.appearanceEditor:IsShown() then MPL.appearanceEditor:Hide() end
    draft=nil; undo={}; actionSnapshot=nil; local state=MPL.InitAppearance()
    state.characterThemes[characterKey()]="classic"
    if MPL.ResetAppearanceWindowPosition then MPL.ResetAppearanceWindowPosition() end
    MPL.RequestAppearanceRefresh(); return true
end

-- A bounded, data-only wire format: each field has a length prefix. No Lua
-- parser, loadstring, deserializer callbacks, executable text or source data.
local function encodeString(value) return tostring(#value)..":"..value end
local function encode(value,depth)
    if (depth or 0)>4 then error("Appearance nesting limit") end
    if type(value)=="boolean" then return value and "t" or "f" end
    if type(value)=="number" then return "n"..encodeString(tostring(value)) end
    if type(value)=="string" then return "s"..encodeString(value) end
    if type(value)=="table" then
        local parts,keys={},{}
        for key in pairs(value) do keys[#keys+1]=key end
        table.sort(keys,function(a,b) return tostring(a)<tostring(b) end)
        for _,key in ipairs(keys) do parts[#parts+1]=encode(tostring(key),(depth or 0)+1)..encode(value[key],(depth or 0)+1) end
        return "m"..tostring(#keys)..":"..table.concat(parts)
    end
    error("Invalid appearance value")
end
local function decode(text)
    local index,nodes=1,0
    local function length()
        local colon=text:find(":",index,true)
        if not colon or colon-index>7 then error("Invalid length") end
        local raw=text:sub(index,colon-1)
        if not raw:match("^%d+$") then error("Invalid length") end
        local count=tonumber(raw); if count>65536 then error("Field too large") end
        index=colon+1; return count
    end
    local read
    read=function(depth)
        nodes=nodes+1; if nodes>2500 or depth>4 then error("Appearance data too complex") end
        local tag=text:sub(index,index); index=index+1
        if tag=="t" then return true end
        if tag=="f" then return false end
        if tag=="s" or tag=="n" then
            local count=length(); if index+count-1>#text then error("Truncated value") end
            local value=text:sub(index,index+count-1); index=index+count
            if tag=="n" then value=tonumber(value); if not finite(value) then error("Invalid number") end end
            return value
        end
        if tag=="m" then
            local count=length(); if count>500 then error("Too many fields") end
            local result={}
            for _=1,count do
                local key=read(depth+1); if type(key)~="string" or #key>160 then error("Invalid key") end
                result[key]=read(depth+1)
            end
            return result
        end
        error("Invalid appearance token")
    end
    local result=read(0); if index~=#text+1 then error("Trailing appearance data") end
    return result
end
local function wireArray(value)
    local result={}
    if type(value)=="table" then for i=1,32 do result[i]=value[tostring(i)] end end
    return result
end
function MPL.ExportAppearance(includeAliases)
    local payload={schemaVersion=1,theme=copy(MPL.GetAppearance()),styleID=MPL.GetAppearanceStyleSourceID(),paletteID=MPL.GetAppearanceColorPresetID()}
    if includeAliases then payload.aliases=copy(currentAliases()) end
    return "MPLA1:"..encode(payload,0)
end
function MPL.ImportAppearance(text)
    if type(text)~="string" or #text>65536 or text:sub(1,6)~="MPLA1:" then return false,"Invalid appearance import" end
    local ok,payload=pcall(decode,text:sub(7))
    if not ok or type(payload)~="table" or payload.schemaVersion~=1 or type(payload.theme)~="table" then return false,"Invalid appearance import" end
    if not canEditTheme() then return false,"Too many themes" end
    for _,field in ipairs(fields) do if field.kind=="color" then payload.theme[field.key]=wireArray(payload.theme[field.key]) end end
    payload.theme.columnOrder=wireArray(payload.theme.columnOrder)
    remember(); local values=normalizeTheme(payload.theme); local target=editableTheme()
    for key,value in pairs(values) do target[key]=value end
    selectTemplate("style",plain(payload.styleID,80) and payload.styleID or nil)
    selectTemplate("palette",plain(payload.paletteID,80) and payload.paletteID or nil)
    if type(payload.aliases)=="table" then
        -- An included alias table is the source profile's complete snapshot;
        -- absence means "keep local names", while an empty table clears them.
        MPL.GetAppearanceState().themes[MPL.GetAppearanceThemeID()].aliases=normalizeAliases(payload.aliases)
    end
    MPL.RequestAppearanceRefresh(); return true
end

local lsm,lsmBound
local function mediaChanged(_,mediaType)
    if mediaType and mediaType~="font" then return end
    MPL.RequestAppearanceRefresh()
    if MPL.RefreshAppearanceFontList then MPL.RefreshAppearanceFontList() end
end
local function discoverMedia()
    if not LibStub then return end
    local ok,library=pcall(function() return LibStub("LibSharedMedia-3.0",true) end)
    if ok and library then
        lsm=library
        if not lsmBound and lsm.RegisterCallback then
            lsm.RegisterCallback(MPL,"LibSharedMedia_Registered",mediaChanged)
            lsm.RegisterCallback(MPL,"LibSharedMedia_SetGlobal",mediaChanged)
            lsmBound=true
        end
    end
end
function MPL.GetAppearanceFonts()
    discoverMedia(); local result={{value="native",label="Game interface font"}}
    if lsm and lsm.List then
        for _,key in ipairs(lsm:List("font") or {}) do result[#result+1]={value=key,label=key} end
    end
    return result
end
function MPL.GetAppearanceFontSize(role,nativeSize)
    local theme=MPL.GetAppearance()
    local size=theme["size_"..tostring(role)]
    local bases={title=16,character=16,summary=10,rating=22,header=10,dungeon=12,numbers=10,secondary=10,button=10,warning=12}
    if not size or size==0 then
        local base=nativeSize or bases[role] or 10
        if role=="rating" then
            if theme.headerLayout=="original" then base=30
            elseif not theme.verticalLayout then base=16 end
        end
        size=base+theme.fontSize-10
    end
    return math.max(8,size)
end
function MPL.ResolveAppearanceFont(role)
    discoverMedia()
    local theme=MPL.GetAppearance(); local key=theme["font_"..tostring(role)]
    if not key or key=="inherit" then key=theme.font end
    local size=MPL.GetAppearanceFontSize(role)
    local flags
    if theme.fontOutline~="inherit" then flags=theme.fontOutline=="none" and "" or theme.fontOutline end
    if key=="native" then return nil,size,flags,key end
    local path
    if lsm and lsm.IsValid and lsm:IsValid("font",key) then path=lsm:Fetch("font",key,true)
    elseif lsm and lsm.GetGlobal and lsm:GetGlobal("font") then path=lsm:Fetch("font",key,true) end
    return path,size,flags,key
end
function MPL.GetAppearanceFontInfo(role)
    local path,size,flags,key=MPL.ResolveAppearanceFont(role or "numbers")
    local override=lsm and lsm.GetGlobal and lsm:GetGlobal("font")
    local available=key=="native" or (lsm and lsm.IsValid and lsm:IsValid("font",key)) or false
    return {requested=key,actual=path and (override or key) or "native",available=available,
        path=path,size=size,flags=flags,overridden=path~=nil and override~=nil and override~=key}
end
if CreateFrame then
    local events=CreateFrame("Frame")
    events:RegisterEvent("ADDON_LOADED")
    events:RegisterEvent("PLAYER_LOGOUT")
    events:SetScript("OnEvent",function(_,event,name)
        if event=="PLAYER_LOGOUT" then
            -- /reload also serializes SavedVariables after this event. Keep
            -- the live editor draft without rebuilding UI during shutdown.
            MPL.SaveAppearanceEdit(true)
            return
        end
        if name=="MPlusLogs" then MPL.InitAppearance() end
        local before=lsm; discoverMedia()
        if lsm and not before then mediaChanged() end
    end)
end
