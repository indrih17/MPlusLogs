local _, MPL = ...
-- Classic keeps the historical typography and density with the modern header,
-- footer and full grid. Original retains the older header and alternating grid.
local classic=MPL.CopyAppearanceValue(MPL.AppearanceDefaults)
for key,value in pairs({compactSummary=false,levelDigits="natural",legacyLayout=true,legacyCenteredHeadings=true}) do
    classic[key]=value
end
local function preset(name,overrides)
    local values=MPL.CopyAppearanceValue(classic)
    for key,value in pairs(overrides or {}) do values[key]=value end
    return {name=name,values=MPL.NormalizeAppearance(values)}
end
MPL.AppearancePresetOrder={"classic","clean","table","compact","large","minimal","original"}
MPL.AppearancePresets={
    classic=preset("Classic"),
    original=preset("Original layout",{headerLayout="original",gridMode="legacy"}),
    clean=preset("Clean",{gridMode="horizontal"}),
    ["table"]=preset("Full table",{gridMode="full",tableBorder=true}),
    compact=preset("Compact",{rowHeight=22,iconSize=16,cellPadding=4,compactSummary=true}),
    large=preset("Large text",{fontSize=14}),
    minimal=preset("Minimal",{showNotes=false,showSource=false,showSeason=false,showSpecRanks=false,showGroupHeaders=false,column_time_visible=false,column_runs_visible=false,column_rank_visible=false,column_points_visible=false}),
}

-- Color palettes are independent of the layout presets above. Each palette is
-- complete so switching never leaves colors from the previous palette behind.
local function hexColor(hex)
    return {tonumber(hex:sub(1,2),16)/255,tonumber(hex:sub(3,4),16)/255,tonumber(hex:sub(5,6),16)/255,1}
end
local function colorPreset(name,overrides)
    local colors={}
    for _,field in ipairs(MPL.AppearanceFields) do
        if field.kind=="color" then colors[field.key]=MPL.CopyAppearanceValue(MPL.AppearanceDefaults[field.key]) end
    end
    for key,hex in pairs(overrides or {}) do colors[key]=hexColor(hex) end
    return {name=name,colors=colors}
end
local function darkPalette(name,c)
    return colorPreset(name,{
        backgroundColor=c[1],titleBackgroundColor=c[2],headerColor="121212",buttonColor=c[4],
        accentColor=c[5],textColor=c[6],mutedColor=c[7],borderColor=c[8],stripeColor=c[9],hoverColor=c[10],
        rowColor=c[1],numberColor=c[6],buttonTextColor=c[6],dungeonColor=c[5],
        selectedColor=c[10],gridColor=c[3],missingColor=c[7],
    })
end
MPL.AppearanceColorPresetOrder={"classic","graphite","midnight","emerald","copper","amethyst","contrast"}
MPL.AppearanceColorPresets={
    classic=colorPreset("Classic"),
    -- Black remains dominant; hue is confined to quiet surface contrasts and accents.
    graphite=darkPalette("Graphite",{"000000","121314","1C1E20","202326","ADB4BC","E1F2F5","BCC2C8","454A50","08090A","2B2F33"}),
    midnight=darkPalette("Midnight blue",{"000000","111317","1A1E24","1D232B","9DAFC4","E1F2F5","BCC2CC","424B58","08090C","292F38"}),
    emerald=darkPalette("Emerald",{"000000","111512","1B201D","1E2521","A0B8AA","E1F2F5","BCC7C1","434F48","080B09","29322D"}),
    copper=darkPalette("Warm copper",{"000000","161310","221E19","28221C","C0AD98","E1F2F5","C9C2BA","544A40","0C0A08","352D25"}),
    amethyst=darkPalette("Amethyst",{"000000","151217","201C24","241F29","B5A8C4","E1F2F5","C5BFCC","4D4456","0B090D","312A38"}),
    contrast=darkPalette("High contrast",{"000000","111213","202224","26292C","C4CCD3","FFFFFF","D8DCDF","8A8F94","090A0B","363B40"}),
}
-- Preserve WCL tier hues while making dim results readable on solid surfaces.
-- These remain ordinary palette swatches so copies and exports retain them.
local contrast=MPL.AppearanceColorPresets.contrast.colors
contrast.semanticLowColor=hexColor("B8BCC4")
contrast.semanticRareColor=hexColor("71A7FF")
contrast.semanticEpicColor=hexColor("C68EFF")
-- Stronger separators remain visible without competing with the text.
MPL.AppearanceColorPresets.contrast.colors.gridColor=hexColor("5A5E63")
