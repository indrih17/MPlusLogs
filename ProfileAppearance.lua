local _, MPL = ...
local L=MPL.L
local ids={"dungeon","level","time","runs","points","rank","rate","best","median"}
local windowPadding,blockSpacing=20,8
local function option(key,fallback)
    local value=MPL.AppearanceValue and MPL.AppearanceValue(key)
    if value==nil then return fallback end
    return value
end
local function legacyLayout()
    return option("legacyLayout",false) and not option("compactSummary",false)
        and not option("verticalLayout",false)
end
local function windowScale(f)
    local configured=option("scale",1)
    -- BlizzMove can restore or change the frame scale after opening. A data
    -- refresh must only reapply our scale when the appearance setting changes.
    if f.appearanceConfiguredScale~=configured then
        f:SetScale(configured)
        f.appearanceConfiguredScale=configured
    end
    local current=f:GetScale()
    return type(current)=="number" and current>0 and current or configured
end
local function color(key,fallback)
    local value=option(key,fallback)
    local default=MPL.AppearanceDefaults and MPL.AppearanceDefaults[key]
    if default and fallback then
        local same=true
        for i=1,4 do if value[i]~=default[i] then same=false; break end end
        if same then value=fallback end
    end
    return value[1] or 0,value[2] or 0,value[3] or 0,value[4] or 1
end
local function fill(texture,key,fallback,opacity)
    local r,g,b,a=color(key,fallback)
    texture:SetColorTexture(r,g,b,a*(opacity or 1))
    -- Adjacent surface tiles must share their exact edges at fractional UI
    -- scales. Independent texel snapping can leave seams at odd offsets.
    if opacity~=nil then
        texture:SetSnapToPixelGrid(false)
        texture:SetTexelSnappingBias(0)
    end
end
local function textColor(field,key,fallback)
    field:SetTextColor(color(key,fallback))
end
local function manualOrder()
    if option("columnOrderMode","auto")=="manual" then return true end
    local order=option("columnOrder",ids)
    for i,id in ipairs(ids) do if order[i]~=id then return true end end
    return false
end
function MPL.OrderAppearancePercentiles(best,median)
    if manualOrder() then return best,median end
    return MPL.OrderPercentiles(best,median)
end
function MPL.ProfileColumnID(index)
    if not manualOrder() and MPL.GetOption("percentile"):find("median",1,true) then
        if index==8 then return "median" elseif index==9 then return "best" end
    end
    return ids[index]
end
function MPL.ProfileColumnIndex(id)
    for i=1,9 do if MPL.ProfileColumnID(i)==id then return i end end
end

local baseSizes={title=16,character=16,summary=10,rating=30,header=10,dungeon=12,numbers=10,secondary=10,button=10,warning=12}
function MPL.StyleProfileFont(field,role)
    if not field then return end
    local native=field.mplNativeFont
    if not native then
        local path,size,flags=field:GetFont()
        native={path=path,size=size or baseSizes[role] or 10,flags=flags or ""}
        field.mplNativeFont=native
    end
    local path,size,flags
    if MPL.ResolveAppearanceFont then path,size,flags=MPL.ResolveAppearanceFont(role) end
    path=path or native.path
    local configured=option("size_"..role,0)
    size=MPL.GetAppearanceFontSize and MPL.GetAppearanceFontSize(role,native.size)
        or (configured>0 and configured or native.size+(option("fontSize",10)-10))
    local outline=option("fontOutline","inherit")
    flags=outline=="inherit" and native.flags or outline
    if flags=="none" then flags="" end
    if type(path)=="string" then
        local ok,result=pcall(field.SetFont,field,path,math.max(8,size),flags or "")
        if not ok or result==false then
            if native.path then field:SetFont(native.path,math.max(8,size),native.flags) end
        end
    end
    field:SetHeight(math.max(20,size+4))
    field.mplAppliedFontSize=size
    if not option("fontShadow",true) then field:SetShadowColor(0,0,0,0); field:SetShadowOffset(0,0) end
end
local buttonFontSerial=0
function MPL.StyleAppearanceButton(button,muted)
    if not button or not button.caption then return end
    button.appearanceMuted=muted==true
    MPL.StyleProfileFont(button.caption,"button")
    local path,size,flags=button.caption:GetFont()
    if not CreateFont or type(path)~="string" then
        button:SetNormalFontObject(muted and "GameFontDisableSmall" or "GameFontHighlightSmall")
        return
    end
    if type(button.appearanceFonts)~="table" then
        buttonFontSerial=buttonFontSerial+1
        local prefix="MPlusLogsAppearanceButton"..buttonFontSerial
        button.appearanceFonts={normal=CreateFont(prefix.."Normal"),highlight=CreateFont(prefix.."Highlight"),disabled=CreateFont(prefix.."Disabled")}
    end
    for state,font in pairs(button.appearanceFonts) do
        font:SetFont(path,size,flags or "")
        font:SetTextColor(color(state=="disabled" and "mutedColor" or "buttonTextColor",state=="disabled" and {.5,.5,.5,1} or {1,1,1,1}))
    end
    button:SetNormalFontObject(muted and button.appearanceFonts.disabled or button.appearanceFonts.normal)
    button:SetHighlightFontObject(button.appearanceFonts.highlight)
    button:SetDisabledFontObject(button.appearanceFonts.disabled)
end
function MPL.ApplyProfileFonts(f)
    local fields={title={f.title},character={f.character},summary={f.summary,f.medianSummary,f.runSummary},
        rating={f.scoreValue},header={f.primaryGroup,f.secondaryGroup,f.scoreLabel},
        secondary={f.context,f.source,f.note,f.footer,f.specRanks,f.inviteInfo,f.specButton.detail,f.currentSpec.caption},
        button={f.specButton.caption},warning={f.staleBanner.message,f.currentSpec.name}}
    for role,list in pairs(fields) do for _,field in ipairs(list) do MPL.StyleProfileFont(field,role) end end
    for _,heading in ipairs(f.headings) do MPL.StyleProfileFont(heading,"header") end
    for _,entry in ipairs(f.specRankEntries) do MPL.StyleProfileFont(entry.number,"numbers"); MPL.StyleProfileFont(entry.specLabel,"secondary") end
    for _,button in ipairs({f.closeButton,f.settingsButton or f.closeButton,f.appearanceButton or f.closeButton,f.wclButton,f.loadButton,f.searchButton,f.lookupButton,f.inviteButton}) do
        if button.caption then
            MPL.StyleAppearanceButton(button,button.appearanceMuted==true)
            if button~=f.closeButton then button:SetHeight(math.max((button==f.settingsButton or button==f.appearanceButton) and 22 or 26,button.caption.mplAppliedFontSize+10)) end
        end
    end
    for _,tab in pairs(f.metricTabs) do MPL.StyleAppearanceButton(tab,false); tab:SetHeight(math.max(28,tab.caption.mplAppliedFontSize+14)) end
    for _,tab in ipairs(type(f.playerTabs)=="table" and f.playerTabs or {}) do
        if tab.caption then MPL.StyleAppearanceButton(tab,false) end
    end
    for _,row in ipairs(f.rows) do
        for i,cell in ipairs(row.cells) do MPL.StyleProfileFont(cell,i==1 and "dungeon" or "numbers") end
        for _,digit in ipairs(row.levelDigits or {}) do MPL.StyleProfileFont(digit,"numbers") end
    end
end
function MPL.ProfileAppearanceStyle()
    local fontSize=option("fontSize",10)
    local icon=option("showDungeonIcons",true) and option("iconSize",20) or 0
    local rowHeight=math.max(option("rowHeight",26),fontSize+10,option("size_numbers",0)+8,option("size_dungeon",0)+8,icon+6,option("showScoreIcons",true) and option("scoreIconSize",16)+6 or 0)
    local headerHeight=math.max(option("headerHeight",40),fontSize*2+16,option("size_header",0)*2+16)
    if not option("showGroupHeaders",true) then headerHeight=math.max(24,headerHeight/2) end
    return {rowHeight=rowHeight,headerHeight=headerHeight,headerBand=option("showGroupHeaders",true) and headerHeight/2 or 0,
        iconSize=icon,scoreIconSize=option("scoreIconSize",16),nameInset=icon>0 and icon+10 or 6,
        namePadding=icon>0 and icon+16 or 12,scorePadding=option("scoreIconSize",16)+14,titleY=5}
end

local function numberText(value,precision,grouped)
    if type(value)~="number" then return tostring(value) end
    local text=string.format("%."..precision.."f",value)
    local integer,fraction=text:match("^([%-]?%d+)%.?(%d*)$")
    if grouped and option("thousandsSeparator","none")~="none" then
        local group=option("thousandsSeparator","none")=="comma" and "," or " "
        integer=integer:reverse():gsub("(%d%d%d)","%1"..group):reverse():gsub("^[ ,]",""):gsub("%-[ ,]","-")
    end
    local separator=option("decimalSeparator","dot")
    if separator=="locale" then separator=(MPL.locale=="ruRU" or MPL.locale=="deDE" or MPL.locale=="frFR") and "comma" or "dot" end
    return integer..(fraction~="" and ((separator=="comma" and "," or ".")..fraction) or "")
end
function MPL.FormatAppearancePercent(value,stale)
    if type(value)~="number" then return "—" end
    local precision=option("percentPrecision",0)
    local factor=10^precision
    local rounded=math.floor(value*factor+.5)/factor
    if value<100 then rounded=math.min(rounded,100-1/factor) end
    local text=numberText(rounded,precision,false):gsub("[.,]0$","")..(option("showPercentSign",false) and "%" or "")
    local hex=option("semanticColors",true) and MPL.PercentColor(value) or nil
    if not hex then
        local r,g,b=color("numberColor",{225/255,242/255,245/255,1})
        hex=string.format("%02x%02x%02x",math.floor(r*255+.5),math.floor(g*255+.5),math.floor(b*255+.5))
    end
    return "|cff"..hex..text.."|r"
end
function MPL.FormatAppearanceCell(index,value,dungeon,profile,metric)
    if value=="—" then return value end
    if index==4 or index==6 then return option("thousandsSeparator","none")=="none" and value or numberText(tonumber(value),0,true) end
    if index==5 and type(dungeon.points)=="number" then
        local precision=option("pointsPrecision",0)
        return numberText(precision==0 and math.floor(dungeon.points) or dungeon.points,precision,true)
    end
    if index==7 then
        local _,amount=MPL.MetricValues(profile,dungeon,metric)
        if not amount then return "—" end
        if option("numericFormat","compact")=="full" then return numberText(amount,0,true) end
        if amount>=1000000 then return numberText(amount/1000000,option("numericPrecision",2),false).."M" end
        return numberText(amount/1000,option("numericPrecision",2),false).."K"
    end
    if index==3 and option("timeFormat","clock")=="words" then
        local hours,hminutes,hseconds=tostring(value):match("^(%d+):(%d+):(%d+)$")
        if hours then return hours..L["h"].." "..hminutes..L["m"].." "..hseconds..L["s"] end
        local minutes,seconds=tostring(value):match("^(%d+):(%d+)$")
        if minutes then return minutes..L["m"].." "..seconds..L["s"] end
    end
    return value
end

local function widthOf(field)
    local width=field:GetUnboundedStringWidth()
    return type(width)=="number" and math.ceil(width) or 0
end
local function groupFor(id)
    if id=="points" or id=="rank" then return 1 end
    if id=="rate" or id=="best" or id=="median" then return 2 end
end
local function columnPadding(id)
    local padding=option("column_"..id.."_padding",-1)
    return padding>=0 and padding or option("cellPadding",6)
end
local function columnOrder()
    local order=option("columnOrder",ids)
    -- In automatic mode retain the old main-percentile order while visibility
    -- and widths still refer to semantic ids rather than physical positions.
    local result={}
    for _,id in ipairs(order) do
        if not manualOrder() and (id=="best" or id=="median") then
            local index=id=="best" and 8 or 9
            result[#result+1]=MPL.ProfileColumnID(index)
        else result[#result+1]=id end
    end
    return result
end
local function groupLabels(f,visible)
    f.appearanceGroups=f.appearanceGroups or {f.primaryGroup,f.secondaryGroup}
    for _,group in ipairs(f.appearanceGroups) do group:Hide() end
    local segments={}
    for _,id in ipairs(visible) do
        local group=groupFor(id)
        local last=segments[#segments]
        if group and last and last.group==group then last.ids[#last.ids+1]=id
        else segments[#segments+1]={group=group,ids={id}} end
    end
    local slot=0
    for _,segment in ipairs(segments) do
        if segment.group then
            slot=slot+1
            local label=f.appearanceGroups[slot]
            if not label then
                label=f.tableHeader:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall")
                label:SetJustifyH("CENTER"); label:SetWordWrap(false)
                f.appearanceGroups[slot]=label
            end
            MPL.StyleProfileFont(label,"header")
            local full=segment.group==1 and L["Score"] or ((f.viewMetric=="hps") and L["HPS by Level"] or L["DPS by Level"])
            label:SetText(#segment.ids==1 and "" or full)
            segment.label=label
        end
    end
    return segments
end
local function createHeaderViewport(f)
    if f.headerViewport then return end
    f.headerViewport=CreateFrame("ScrollFrame",nil,f)
    f.tableHeader:SetParent(f.headerViewport)
    f.headerViewport:SetScrollChild(f.tableHeader)
    f.horizontalBar=CreateFrame("Slider",nil,f)
    f.horizontalBar:SetOrientation("HORIZONTAL"); f.horizontalBar:SetHeight(12)
    f.horizontalBar:SetMinMaxValues(0,0); f.horizontalBar:SetValueStep(1)
    f.horizontalBar:SetThumbTexture("Interface/Buttons/UI-ScrollBar-Knob")
    f.horizontalBar:SetScript("OnValueChanged",function(_,value)
        f.appearanceHorizontalOffset=value
        f.scroll:SetHorizontalScroll(value); f.headerViewport:SetHorizontalScroll(value)
    end)
    f.horizontalBar:Hide()
end
function MPL.LayoutAppearanceTable(f)
    local style=MPL.ProfileAppearanceStyle()
    MPL.ApplyProfileFonts(f)
    local visible={}
    for _,id in ipairs(columnOrder()) do
        if id=="dungeon" or option("column_"..id.."_visible",true) then visible[#visible+1]=id end
    end
    f.visibleColumnIds=visible
    local segments=groupLabels(f,visible)
    local minima={220,40,40,40,58,40,92,60,60}
    local widths={0,0,0,0,0,0,0,0,0}
    local widthById={}
    -- Measure hidden columns too, so their former space can be released from
    -- the historical minimum rather than reassigned to the dungeon column.
    for _,id in ipairs(columnOrder()) do
        local i=MPL.ProfileColumnIndex(id)
        local custom=option("column_"..id.."_label","")
        if custom~="" then f.headings[i]:SetText(custom) end
        local pad=columnPadding(id)
        local width=math.max(minima[i],widthOf(f.headings[i])+24)
        for _,row in ipairs(f.rows) do
            if row:IsShown() then
                local inset=i==1 and style.namePadding or (i==5 and row.scoreSpecIcon:IsShown() and option("showScoreIcons",true) and style.scorePadding or pad*2)
                width=math.max(width,widthOf(row.cells[i])+inset)
                if i==2 and row.levelDigitWidth then width=math.max(width,row.levelDigitWidth+inset) end
            end
        end
        widthById[id]=width
    end
    for _,segment in ipairs(segments) do
        if segment.label and #segment.ids>1 and option("showGroupHeaders",true) then
            local sum=0; for _,id in ipairs(segment.ids) do sum=sum+widthById[id] end
            -- Preserve the legacy group measurement; split singleton groups
            -- never expand a numeric column just to fit a group caption.
            local last=segment.ids[#segment.ids]
            widthById[last]=widthById[last]+math.max(0,widthOf(segment.label)+16-sum)
        end
    end
    local total=0
    for _,id in ipairs(visible) do total=total+widthById[id] end
    local outer=windowPadding*2+20
    -- Reserve room for the profile controls when only a few columns are shown.
    -- The horizontal header needs room even when the theme hides columns.
    -- Only an explicit preference may switch it to the stacked layout.
    local vertical=option("verticalLayout",false)
    local hiddenWidth=0
    for _,id in ipairs(ids) do
        if id~="dungeon" and not option("column_"..id.."_visible",true) then
            hiddenWidth=hiddenWidth+(widthById[id] or 0)
        end
    end
    local minimum=vertical and 460 or math.max(620,(legacyLayout() and 880 or 820)-hiddenWidth)
    widthById.dungeon=widthById.dungeon+math.max(0,minimum-total)
    total=0
    for _,id in ipairs(visible) do
        local i=MPL.ProfileColumnIndex(id)
        f.columns[i]=total; widths[i]=widthById[id]; total=total+widths[i]
    end
    f.widths=widths; f.tableWidth=total
    local screen=UIParent:GetWidth()
    local scale=windowScale(f)
    local maxWidth=type(screen)=="number" and screen>500 and screen/scale-20 or total+outer
    local viewport=math.min(total,math.max(300,maxWidth-outer))
    f.viewportWidth=viewport; f.appearanceCompact=vertical
    f:SetWidth(viewport+outer)
    f.titleFill:SetWidth(viewport+outer-2); f.contextFill:SetWidth(viewport)
    createHeaderViewport(f)
    f.headerViewport:SetShown(type(f.profile)=="table")
    f.tableHeader:SetSize(total,style.headerHeight); f.tableDecor[1]:SetSize(total,style.headerHeight)
    f.content:SetWidth(total); f.scroll:SetWidth(viewport)
    f.staleBanner:SetWidth(viewport); f.staleBanner.message:SetWidth(math.max(1,viewport-52))
    for _,field in ipairs({f.source,f.note,f.footer}) do field:SetWidth(viewport) end
    f.lookup:SetWidth(math.max(80,viewport-210)); f.inviteInfo:SetWidth(math.max(80,viewport-350))
    f.title:SetWidth(math.max(100,viewport-180))
    if not f.tableOutline then
        f.tableOutline=CreateFrame("Frame",nil,f,"BackdropTemplate")
        f.tableOutline:SetBackdrop({edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
        f.tableOutline:EnableMouse(false)
    end
    f.tableOutline:SetBackdropBorderColor(color("gridColor",{.2,.2,.2,1}))
    f.tableOutline:SetShown(option("tableBorder",false) and type(f.profile)=="table")
    for i,sortButton in ipairs(f.sortButtons) do
        local id=MPL.ProfileColumnID(i)
        local shown=widths[i]>0 and type(f.profile)=="table"
        sortButton:SetShown(shown); f.headings[i]:SetShown(shown)
        if shown then
            sortButton:ClearAllPoints(); sortButton:SetPoint("TOPLEFT",f.columns[i]+1,-style.headerBand-1)
            sortButton:SetSize(widths[i]-2,style.headerHeight-style.headerBand-2)
            f.headings[i]:SetSize(widths[i]-8,style.headerHeight-style.headerBand-2)
            f.headings[i]:SetJustifyH(option("legacyCenteredHeadings",false) and "CENTER" or option("column_"..id.."_align",i==1 and "LEFT" or "RIGHT"))
            sortButton.arrow:ClearAllPoints(); sortButton.arrow:SetPoint("TOPLEFT",widths[i]-11,-math.floor((style.headerHeight-style.headerBand-6)/2))
        end
    end
    for _,segment in ipairs(segments) do
        if segment.label then
            local start=MPL.ProfileColumnIndex(segment.ids[1])
            local sum=0; for _,id in ipairs(segment.ids) do sum=sum+widthById[id] end
            segment.label:ClearAllPoints(); segment.label:SetPoint("TOPLEFT",f.columns[start]+4,-style.titleY)
            segment.label:SetWidth(math.max(1,sum-8))
            segment.label:SetShown(type(f.profile)=="table" and option("showGroupHeaders",true) and #segment.ids>1)
        end
    end
    local grid=option("gridMode","legacy")
    local thickness=option("gridThickness",1)
    f.appearanceHeaderLines=f.appearanceHeaderLines or {}
    for i=1,12 do
        local line=f.appearanceHeaderLines[i]
        if not line then line=f.tableHeader:CreateTexture(nil,"ARTWORK"); f.appearanceHeaderLines[i]=line end
        line:Hide(); fill(line,"gridColor",{.2,.2,.2,1})
    end
    if type(f.profile)=="table" and (grid=="full" or grid=="horizontal" or grid=="vertical") then
        for slot,offset in ipairs({0,style.headerHeight-thickness,style.headerBand}) do
            local line=f.appearanceHeaderLines[9+slot]
            line:ClearAllPoints(); line:SetPoint("TOPLEFT",0,-offset); line:SetSize(total,thickness)
            line:SetShown((grid=="full" or grid=="horizontal") and (slot~=3 or style.headerBand>0))
        end
        if grid=="full" or grid=="vertical" then
            for _,id in ipairs(visible) do
                local i=MPL.ProfileColumnIndex(id)
                local line=f.appearanceHeaderLines[i]
                line:ClearAllPoints(); line:SetPoint("TOPLEFT",f.columns[i],-style.headerBand)
                line:SetSize(thickness,style.headerHeight-style.headerBand); line:Show()
            end
        end
    end
    for index,row in ipairs(f.rows) do
        row.appearanceIndex=index
        local legacy=grid=="legacy" and index%2==1
        local horizontal=grid=="full" or grid=="horizontal" or legacy
        local vertical=grid=="full" or grid=="vertical" or legacy
        row:ClearAllPoints(); row:SetPoint("TOPLEFT",0,-(index-1)*style.rowHeight)
        row:SetSize(total,style.rowHeight); row.background:SetSize(total,style.rowHeight)
        row.shade=index%2==0 and .018 or 0
        MPL.ColorAppearanceRow(row,false)
        row.bottomLine:ClearAllPoints(); row.bottomLine:SetPoint("TOPLEFT",0,thickness-style.rowHeight)
        row.bottomLine:SetSize(total,thickness); row.bottomLine:SetShown(horizontal)
        fill(row.bottomLine,"gridColor",{.2,.2,.2,1})
        row.icon:ClearAllPoints(); row.icon:SetPoint("TOPLEFT",6,-(style.rowHeight-style.iconSize)/2)
        row.icon:SetSize(style.iconSize,style.iconSize); row.icon:SetShown(option("showDungeonIcons",true))
        row.scoreSpecIcon:SetSize(style.scoreIconSize,style.scoreIconSize)
        row.scoreSpecIcon:SetShown(widths[5]>0 and row.hasScoreIcon==true and option("showScoreIcons",true))
        for i,cell in ipairs(row.cells) do
            local id=MPL.ProfileColumnID(i)
            local pad=columnPadding(id)
            local inset=i==1 and style.nameInset or pad
            local reserve=i==1 and style.namePadding or (i==5 and row.scoreSpecIcon:IsShown() and style.scorePadding or pad*2)
            local height=math.max(20,option("size_"..(i==1 and "dungeon" or "numbers"),0)+4,option("fontSize",10)+4)
            cell:ClearAllPoints(); cell:SetPoint("TOPLEFT",(f.columns[i] or 0)+inset,-(style.rowHeight-height)/2)
            cell:SetSize(math.max(1,widths[i]-reserve),height)
            cell:SetJustifyH(option("column_"..id.."_align",i==1 and "LEFT" or "RIGHT"))
            cell:SetShown(widths[i]>0 and not (i==2 and type(row.levelDigitWidth)=="number"))
            local line=row.columnLines[i]
            line:ClearAllPoints(); line:SetPoint("TOPLEFT",f.columns[i] or 0,0)
            line:SetSize(thickness,style.rowHeight); line:SetShown(widths[i]>0 and vertical)
            fill(line,"gridColor",{.2,.2,.2,1})
        end
        local levelAlign=option("column_level_align","RIGHT")
        local digitStart=math.max(0,row.cells[2]:GetWidth()-(row.levelDigitWidth or 0))
        if levelAlign=="LEFT" then digitStart=0
        elseif levelAlign=="CENTER" then digitStart=digitStart/2 end
        for _,digit in ipairs(row.levelDigits or {}) do
            if widths[2]==0 then digit:Hide()
            elseif type(row.levelDigitWidth)=="number" then
                digit:ClearAllPoints(); digit:SetPoint("TOPLEFT",row.cells[2],"TOPLEFT",digitStart,0)
                digitStart=digitStart+digit:GetWidth()
            end
        end
        row.rightLine:ClearAllPoints(); row.rightLine:SetPoint("TOPLEFT",total-thickness,0)
        row.rightLine:SetSize(thickness,style.rowHeight); row.rightLine:SetShown(vertical)
        fill(row.rightLine,"gridColor",{.2,.2,.2,1})
    end
    local horizontalRange=type(f.profile)=="table" and math.max(0,total-viewport) or 0
    f.horizontalBar:SetMinMaxValues(0,horizontalRange)
    f.horizontalBar:SetValue(math.min(f.appearanceHorizontalOffset or 0,horizontalRange))
    f.horizontalBar:SetShown(horizontalRange>1)
    if type(f.playerTabs)=="table" then MPL.RenderPlayerTabs(f) end
end

function MPL.ColorAppearanceRow(row,hover)
    local key=hover and option("showHover",true) and "hoverColor" or ((row.appearanceIndex or 1)%2==0 and option("striped",true) and "stripeColor" or "rowColor")
    local br,bg,bb,ba=color("backgroundColor",{0,0,0,1})
    br,bg,bb,ba=color("rowColor",{br,bg,bb,ba})
    local offset=key=="hoverColor" and .055 or (key=="stripeColor" and .018 or 0)
    local fallback={math.min(1,br+offset),math.min(1,bg+offset),math.min(1,bb+offset),ba}
    fill(row.background,key,fallback,option("surfaceOpacity",1))
end

local function positioned(field,x,y,width)
    field:ClearAllPoints(); field:SetPoint("TOPLEFT",x,-y)
    if width then field:SetWidth(math.max(1,width)) end
end
local function visible(field,key,hasProfile)
    field:SetShown(hasProfile and option(key,true))
end
local function compactSummaryText(f)
    local profile=f.profile
    local metric=f.viewMetric or "dps"
    local _,_,best,median=MPL.MetricValues(profile,nil,metric)
    local first,second=MPL.OrderPercentiles(best,median)
    local result=metric:upper().." "..MPL.PercentileCaption()..": "..MPL.FormatAppearancePercent(first).." / "..MPL.FormatAppearancePercent(second)
    if MPL.UsesDungeonMetric() then result=f.summary:GetText() end
    return result.."    "..L["Runs"]..": "..(profile.runs or "—")
end
-- Pack whole information groups onto a shared row, wrapping only when the
-- user's typography really exceeds the available width.
local function layoutCompactRow(f,left,total,y,gap,ranksWidth)
    local groups={}
    if f.scoreValue:IsShown() then
        local labelWidth=widthOf(f.scoreLabel)+2
        local valueWidth=widthOf(f.scoreValue)+2
        groups[#groups+1]={width=labelWidth+gap+valueWidth,height=math.max(f.scoreLabel:GetHeight(),f.scoreValue:GetHeight()),
            place=function(x,top,height)
                positioned(f.scoreLabel,x,top+(height-f.scoreLabel:GetHeight())/2,labelWidth)
                positioned(f.scoreValue,x+labelWidth+gap,top+(height-f.scoreValue:GetHeight())/2,valueWidth)
            end}
    end
    if f.summary:IsShown() then
        local width=math.min(total,widthOf(f.summary)+2)
        f.summary:SetWidth(width); f.summary:SetWordWrap(true); f.summary:SetNonSpaceWrap(true)
        local line=math.max(22,(f.summary.mplAppliedFontSize or 10)+6)
        local height=math.max(line,math.ceil(widthOf(f.summary)/width)*line,f.summary:GetStringHeight()+4)
        f.summary:SetHeight(height)
        groups[#groups+1]={width=width,height=height,place=function(x,top,rowHeight)
            positioned(f.summary,x,top+(rowHeight-height)/2,width)
        end}
    end
    if f.specRanks:IsShown() then
        local ranksHeight=math.max(18,f.specRanks:GetHeight())
        for _,entry in ipairs(f.specRankEntries) do
            if entry:IsShown() then
                entry:SetHeight(math.max(18,entry.number:GetHeight(),entry.hasIcon and 18 or entry.specLabel:GetHeight()))
                ranksHeight=math.max(ranksHeight,entry:GetHeight())
            end
        end
        groups[#groups+1]={width=ranksWidth,height=ranksHeight,place=function(x,top,height)
            local rankY=top+(height-18)/2
            positioned(f.specRanks,x,top+(height-f.specRanks:GetHeight())/2,widthOf(f.specRanks)); x=x+widthOf(f.specRanks)
            for _,entry in ipairs(f.specRankEntries) do
                if entry:IsShown() then positioned(entry,x+8,top+(height-entry:GetHeight())/2); x=x+8+entry:GetWidth() end
            end
            f.appearanceRanksY=rankY
        end}
    end
    local row,width,height={},0,0
    local function flush()
        local x=left
        for _,group in ipairs(row) do group.place(x,y,height); x=x+group.width+gap end
        y=y+height+gap; row={}; width=0; height=0
    end
    for _,group in ipairs(groups) do
        if #row>0 and width+gap+group.width>total then flush() end
        width=width+(#row>0 and gap or 0)+group.width
        row[#row+1]=group; height=math.max(height,group.height)
    end
    if #row>0 then flush() end
    return y
end
local function layoutHeader(f,hasProfile)
    local total=f.viewportWidth
    local compact=f.appearanceCompact
    local left=windowPadding
    local right=left+20
    local gap=blockSpacing
    local titleSize=f.title.mplAppliedFontSize or 16
    local characterSize=f.character.mplAppliedFontSize or 16
    local controls={}
    local controlsWidth=0
    for _,key in ipairs({"settingsButton","appearanceButton","tutorialButton"}) do
        local button=f[key]
        if button and button:IsShown() then
            local minimum=key=="settingsButton" and 104 or (key=="appearanceButton" and 120 or 160)
            local width=math.min(total,math.max(minimum,button.caption and widthOf(button.caption)+20 or minimum))
            button:SetWidth(width)
            controls[#controls+1]=button
            controlsWidth=controlsWidth+width+8
        end
    end
    -- Narrow windows keep the title on its own row and wrap header actions.
    local wrapped=controlsWidth>total-216
    local rowY=wrapped and math.max(36,titleSize+20) or 7
    local rowWidth,rowHeight=0,0
    for _,button in ipairs(controls) do
        if rowWidth>0 and rowWidth+button:GetWidth()>total then
            rowY=rowY+rowHeight+8; rowWidth=0; rowHeight=0
        end
        button:ClearAllPoints(); button:SetPoint("TOPRIGHT",-38-rowWidth,-rowY)
        rowWidth=rowWidth+button:GetWidth()+8
        rowHeight=math.max(rowHeight,button:GetHeight())
    end
    local titleBand=math.max(36,titleSize+20,rowY+rowHeight+7)
    local characterY=titleBand+12
    local characterHeight=math.max(24,characterSize+4)
    local specY=compact and characterY+characterHeight+4 or titleBand+3
    f.appearanceTitleBand=titleBand
    f.titleFill:SetHeight(titleBand)
    f.title:SetWidth(math.max(80,total-(wrapped and 0 or controlsWidth)-76))
    local character=f.character:GetText()
    if not f.appearanceCharacterOriginal or f.appearanceCharacterLast~=character then f.appearanceCharacterOriginal=character end
    local display=option("showRealm",true) and f.appearanceCharacterOriginal or f.appearanceCharacterOriginal:match("^(.-) — ") or f.appearanceCharacterOriginal
    f.character:SetText(display); f.appearanceCharacterLast=display
    positioned(f.character,left,characterY,compact and total or math.max(100,total-480))
    local captionHeight=math.max(12,option("size_secondary",0)>0 and option("size_secondary",0)+2 or option("fontSize",10)+2)
    local specNameHeight=math.max(14,option("size_warning",0)>0 and option("size_warning",0)+2 or option("fontSize",10)+4)
    local specHeight=captionHeight+specNameHeight+6
    local specWidth=math.min(460,math.max(100,total-160))
    positioned(f.currentSpec.caption,37,3); f.currentSpec.caption:SetHeight(captionHeight)
    positioned(f.currentSpec.name,37,captionHeight+4); f.currentSpec.name:SetHeight(specNameHeight)
    f.currentSpec:SetHeight(specHeight)
    f.currentSpec:ClearAllPoints()
    if compact then f.currentSpec:SetPoint("TOPLEFT",left,-specY); f.currentSpec:SetWidth(total)
    else f.currentSpec:SetPoint("TOPRIGHT",-right,-specY); f.currentSpec:SetWidth(specWidth) end
    f.currentSpec.caption:SetWidth((compact and total or specWidth)-45)
    f.currentSpec.name:SetWidth((compact and total or specWidth)-45)
    local seasonY=compact and (specY+specHeight+4) or math.max(titleBand+44,specY+specHeight+8,characterY+characterHeight+8)
    local seasonHeight=math.max(26,(f.context.mplAppliedFontSize or 10)+14)
    local metricHeight=math.max(28,(f.metricTabs.dps.caption.mplAppliedFontSize or 10)+14)
    local selectorCaptionHeight=math.max(16,(f.specButton.caption.mplAppliedFontSize or 10)+4)
    local selectorDetailHeight=math.max(12,(f.specButton.detail.mplAppliedFontSize or 10)+2)
    local selectorHeight=math.max(44,selectorCaptionHeight+selectorDetailHeight+16)
    f.specButton:SetHeight(selectorHeight)
    positioned(f.specButton.caption,48,7); f.specButton.caption:SetHeight(selectorCaptionHeight)
    positioned(f.specButton.detail,48,selectorCaptionHeight+9); f.specButton.detail:SetHeight(selectorDetailHeight)
    f.appearanceSeasonY=seasonY
    f.appearanceSeasonHeight=seasonHeight
    positioned(f.context,left+10,seasonY+7,compact and total-20 or math.max(160,total-340))
    f.contextFill:ClearAllPoints(); f.contextFill:SetPoint("TOPLEFT",left,-seasonY)
    f.contextFill:SetHeight(seasonHeight)
    f.contextFill:SetShown(option("showSeason",true)); f.context:SetShown(option("showSeason",true))
    local summaryLine=math.max(22,(f.summary.mplAppliedFontSize or 10)+6)
    local ratingHeight=math.max(36,option("size_rating",0)+6,option("fontSize",10)+26)
    local ratingLabelHeight=math.max(24,(f.scoreLabel.mplAppliedFontSize or 12)+4)
    f.summary:SetWordWrap(false); f.summary:SetNonSpaceWrap(false)
    local tableTop
    if compact then
        local cursor=option("showSeason",true) and seasonY+seasonHeight+math.max(0,gap-2) or seasonY+2
        local x=left
        for _,metric in ipairs({"dps","hps"}) do
            f.metricTabs[metric]:ClearAllPoints(); f.metricTabs[metric]:SetPoint("TOPLEFT",x,-cursor); x=x+92
        end
        cursor=cursor+metricHeight+math.max(0,gap-2)
        f.specButton:ClearAllPoints(); f.specButton:SetPoint("TOPLEFT",left,-cursor); f.specButton:SetWidth(total)
        f.specButton.caption:SetWidth(total-78); f.specButton.detail:SetWidth(total-78)
        cursor=cursor+selectorHeight+gap+2
        f.appearanceCompactRowY=cursor
        local infoTop=cursor
        local ratingWidth=math.max(widthOf(f.scoreLabel),widthOf(f.scoreValue))+4
        local summaryWidth=math.max(widthOf(f.summary),widthOf(f.medianSummary),widthOf(f.runSummary))+4
        local sideBySide=hasProfile and option("showRating",true) and option("showSummary",true)
            and not option("compactSummary",false) and ratingWidth+summaryWidth+gap*2<=total
        if hasProfile and option("showRating",true) then
            local width=sideBySide and ratingWidth or total
            positioned(f.scoreLabel,left,cursor,width); positioned(f.scoreValue,left,cursor+ratingLabelHeight+2,width)
            cursor=cursor+ratingLabelHeight+2+ratingHeight+((not sideBySide and option("showSummary",true)) and gap or 0)
        end
        if hasProfile and option("showSummary",true) then
            if option("compactSummary",false) then
                f.summary:SetText(compactSummaryText(f))
                positioned(f.summary,left,cursor,total); cursor=cursor+summaryLine
            else
                local summaryTop=sideBySide and infoTop or cursor
                local x=sideBySide and left+total-summaryWidth or left
                for i,field in ipairs({f.summary,f.medianSummary,f.runSummary}) do
                    positioned(field,x,summaryTop+(i-1)*summaryLine,sideBySide and summaryWidth or total)
                end
                cursor=math.max(cursor,summaryTop+3*summaryLine)
            end
        end
        f.appearanceRanksY=cursor
        if hasProfile and option("showSpecRanks",true) and #(f.profile.specRanks or {})>0 then cursor=cursor+24 end
        tableTop=cursor+gap
    else
        local selectorY=titleBand+36
        f.specButton:ClearAllPoints(); f.specButton:SetPoint("TOPRIGHT",-right,-selectorY); f.specButton:SetWidth(310)
        f.specButton.caption:SetWidth(232); f.specButton.detail:SetWidth(232)
        local metricY=seasonY+(option("showSeason",true) and seasonHeight+6 or 2)
        local summaryY=math.max(metricY+metricHeight+19,selectorY+selectorHeight+15)
        local ratingY=summaryY+(option("compactSummary",false) and -4 or 4)
        local ratingValueY=ratingY+ratingLabelHeight+2
        positioned(f.metricTabs.dps,left,metricY); positioned(f.metricTabs.hps,left+92,metricY)
        local summaryWidth=math.min(370,total/2)
        local ratingWidth=math.max(1,math.min(310,total-summaryWidth-64))
        positioned(f.scoreLabel,left+44,ratingY,ratingWidth); positioned(f.scoreValue,left+44,ratingValueY,ratingWidth)
        for i,field in ipairs({f.summary,f.medianSummary,f.runSummary}) do positioned(field,left+total-summaryWidth-10,summaryY+(i-1)*summaryLine,summaryWidth) end
        local contentBottom=math.max(metricY+metricHeight,selectorY+selectorHeight)
        f.appearanceCompactRowY=contentBottom+gap
        if hasProfile and option("showRating",true) then
            contentBottom=math.max(contentBottom,ratingValueY+ratingHeight)
        end
        if hasProfile and option("showSummary",true) then
            if option("compactSummary",false) then
                f.summary:SetText(compactSummaryText(f))

            else
                contentBottom=math.max(contentBottom,summaryY+3*summaryLine)
            end
        end
        f.appearanceRanksY=contentBottom+(legacyLayout() and 4 or gap)
        if hasProfile and option("showSpecRanks",true) and #(f.profile.specRanks or {})>0 then
            contentBottom=f.appearanceRanksY+18
        end
        tableTop=contentBottom+(legacyLayout() and 7 or gap)
        -- 0.5.X reserved the ranks line even when no ranks were available.
        if legacyLayout() and option("showRating",true) and option("showSummary",true) and option("showSpecRanks",true) then
            tableTop=math.max(tableTop,summaryY+95)
        end
    end
    visible(f.scoreLabel,"showRating",hasProfile); visible(f.scoreValue,"showRating",hasProfile)
    for _,field in ipairs({f.summary,f.medianSummary,f.runSummary}) do visible(field,"showSummary",hasProfile) end
    if option("compactSummary",false) then f.medianSummary:Hide(); f.runSummary:Hide() end
    if not option("showSpecRanks",true) then f.specRanks:Hide(); for _,entry in ipairs(f.specRankEntries) do entry:Hide() end end
    local ranksWidth=widthOf(f.specRanks)
    for _,entry in ipairs(f.specRankEntries) do
        if entry:IsShown() then
            local numberWidth=widthOf(entry.number)+1
            local symbolWidth=entry.hasIcon and 18 or widthOf(entry.specLabel)
            entry:SetHeight(18)
            entry.number:SetWidth(numberWidth); entry.specLabel:SetWidth(symbolWidth); entry:SetWidth(numberWidth+4+symbolWidth)
            ranksWidth=ranksWidth+8+entry:GetWidth()
        end
    end
    local x=math.max(left,left+(total-ranksWidth)/2)
    positioned(f.specRanks,x,f.appearanceRanksY,widthOf(f.specRanks)); x=x+widthOf(f.specRanks)
    for _,entry in ipairs(f.specRankEntries) do
        if entry:IsShown() then positioned(entry,x+8,f.appearanceRanksY); x=x+8+entry:GetWidth() end
    end
    if option("compactSummary",false) then
        tableTop=layoutCompactRow(f,left,total,f.appearanceCompactRowY,gap,ranksWidth)
    end
    return tableTop
end

-- Disjoint background tiles keep a 50% surface at 50%, instead of painting
-- a second 50% table/header layer over a full-window background (75%).
local function backdropTiles(f,tableTop,tableBottom,seasonY,hasProfile)
    f.appearanceBackdropParts=f.appearanceBackdropParts or {}
    local left=windowPadding
    local right=left+20
    local titleEnd=(f.appearanceTitleBand or 36)+1
    local seasonHeight=f.appearanceSeasonHeight or 26
    local rectangles={{1,titleEnd,f:GetWidth()-2,math.max(0,seasonY-titleEnd)},
        {1,seasonY,left-1,seasonHeight},{f:GetWidth()-right,seasonY,right-1,seasonHeight},
        {1,seasonY+seasonHeight,f:GetWidth()-2,math.max(0,tableTop-seasonY-seasonHeight)},
        {1,tableTop,left-1,tableBottom-tableTop},{f:GetWidth()-right,tableTop,right-1,tableBottom-tableTop},
        {1,tableBottom,f:GetWidth()-2,math.max(0,f:GetHeight()-tableBottom-1)}}
    if not option("showSeason",true) then rectangles[2]={1,seasonY,f:GetWidth()-2,seasonHeight}; rectangles[3]={0,0,0,0} end
    if not hasProfile then
        rectangles[5]={1,tableTop,f:GetWidth()-2,tableBottom-tableTop}
        rectangles[6]={0,0,0,0}
    end
    f:SetBackdropColor(0,0,0,0)
    for i,rect in ipairs(rectangles) do
        local texture=f.appearanceBackdropParts[i]
        if not texture then texture=f:CreateTexture(nil,"BACKGROUND"); f.appearanceBackdropParts[i]=texture end
        texture:ClearAllPoints(); texture:SetPoint("TOPLEFT",rect[1],-rect[2]); texture:SetSize(math.max(0,rect[3]),math.max(0,rect[4]))
        texture:SetShown(rect[3]>0 and rect[4]>0)
        fill(texture,"backgroundColor",{0,0,0,1},option("surfaceOpacity",1))
    end
end
function MPL.LayoutAppearanceBanner(f,profile,offset,extra,drawer)
    local style=MPL.ProfileAppearanceStyle()
    local total=f.viewportWidth or f.tableWidth
    local left=windowPadding
    local right=left+20
    local top=layoutHeader(f,profile~=nil)
    local count=profile and #profile.dungeons or 8
    local rows=legacyLayout() and 8 or math.max(1,math.min(count,8))
    local scrollHeight=rows*style.rowHeight+(legacyLayout() and not profile and 44 or 0)
    local horizontal=profile and (f.tableWidth or total)>total+1 and 16 or 0
    local buttonHeight=math.max(26,f.loadButton:GetHeight(),f.wclButton:GetHeight(),f.searchButton:GetHeight())
    local compactActions=f.appearanceCompact and buttonHeight+10 or (type(f.applicant)=="table" and 36 or 0)
    local secondaryLine=math.max(20,option("size_secondary",0)+6,option("fontSize",10)+6)
    local fields={}
    if option("showSource",true) then fields[#fields+1]=f.source end
    if option("showNotes",true) then fields[#fields+1]=f.note end
    fields[#fields+1]=f.footer
    local textHeight=#fields*secondaryLine
    -- Size the lower area from its contents rather than the old fixed reserve.
    local textGap,actionGap=legacyLayout() and 20 or 8,legacyLayout() and 28 or 8
    local bottom=textGap+textHeight+extra+actionGap+buttonHeight+20+drawer+compactActions+horizontal
    f:SetHeight(top+offset+style.headerHeight+scrollHeight+bottom+((profile or legacyLayout()) and 0 or 44))
    positioned(f.staleBanner,left,top,total)
    positioned(f.headerViewport,left,top+offset,total); f.headerViewport:SetHeight(style.headerHeight)
    f.tableHeader:ClearAllPoints(); f.tableHeader:SetPoint("TOPLEFT",0,0)
    f.scroll:ClearAllPoints(); f.scroll:SetPoint("TOPLEFT",left,-top-offset-style.headerHeight)
    f.scroll:SetPoint("BOTTOMRIGHT",-right,bottom)
    f.scroll:SetSize(total,scrollHeight)
    local bodyBottom=top+offset+style.headerHeight+scrollHeight
    f.horizontalBar:ClearAllPoints(); f.horizontalBar:SetPoint("TOPLEFT",left,-bodyBottom-2); f.horizontalBar:SetWidth(total)
    local textY=bodyBottom+textGap+horizontal
    for i,field in ipairs(fields) do positioned(field,left,textY+(i-1)*secondaryLine,total) end
    f.source:SetShown(option("showSource",true)); f.note:SetShown(option("showNotes",true))
    if f.appearanceCompact then
        f.searchButton:SetWidth(math.max(100,math.min(210,total-130)))
        f.loadButton:ClearAllPoints(); f.loadButton:SetPoint("BOTTOMRIGHT",-right,20+buttonHeight+10+drawer)
    else f.searchButton:SetWidth(210) end
    local scale=windowScale(f)
    local screenHeight=UIParent:GetHeight()
    if type(screenHeight)=="number" and screenHeight>500 and f:GetHeight()*scale>screenHeight-60 then
        local reduction=f:GetHeight()-(screenHeight-60)/scale
        local available=math.max(style.rowHeight,scrollHeight-reduction)
        f:SetHeight(f:GetHeight()-(scrollHeight-available)); f.scroll:SetHeight(available)
        bodyBottom=top+offset+style.headerHeight+available
        f.horizontalBar:ClearAllPoints(); f.horizontalBar:SetPoint("TOPLEFT",left,-bodyBottom-2)
        for i,field in ipairs(fields) do positioned(field,left,bodyBottom+textGap+horizontal+(i-1)*secondaryLine,total) end
    end
    f.tableOutline:ClearAllPoints(); f.tableOutline:SetPoint("TOPLEFT",left,-top-offset)
    f.tableOutline:SetSize(total,bodyBottom-top-offset)
    f.wclButton:ClearAllPoints(); f.wclButton:SetPoint("BOTTOMLEFT",left,20+drawer)
    if not f.appearanceCompact and not f.centerLoadButton then
        f.loadButton:ClearAllPoints(); f.loadButton:SetPoint("BOTTOMRIGHT",-right,f.applicant and 56 or 20+drawer)
    end
    f.lookup:ClearAllPoints(); f.lookup:SetPoint("BOTTOMLEFT",left,20)
    f.lookupButton:ClearAllPoints(); f.lookupButton:SetPoint("BOTTOMRIGHT",-right,20)
    f.inviteButton:ClearAllPoints(); f.inviteButton:SetPoint("BOTTOMRIGHT",-right,20)
    backdropTiles(f,top+offset,bodyBottom,f.appearanceSeasonY,profile~=nil)
    if not f.appearanceEmptyFill then f.appearanceEmptyFill=f.scroll:CreateTexture(nil,"BACKGROUND") end
    local blank=math.max(0,f.scroll:GetHeight()-count*style.rowHeight)
    f.appearanceEmptyFill:ClearAllPoints(); f.appearanceEmptyFill:SetPoint("BOTTOMLEFT",0,0); f.appearanceEmptyFill:SetSize(total,blank)
    f.appearanceEmptyFill:SetShown(profile~=nil and blank>0); fill(f.appearanceEmptyFill,"backgroundColor",{0,0,0,1},option("surfaceOpacity",1))
    MPL.ApplyAppearancePalette(f)
end

function MPL.ApplyAppearancePalette(f)
    local opacity=option("surfaceOpacity",1)
    local border=option("borderThickness",1)
    if f.appearanceBorderThickness~=border then
        -- A tiny substitute edge produces enormous tiled UVs and can abort
        -- SetBackdrop before its default white fill is made transparent.
        f:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile=border>0 and "Interface/Buttons/WHITE8X8" or nil,edgeSize=math.max(1,border),insets={left=1,right=1,top=1,bottom=1}})
        f:SetBackdropColor(0,0,0,0); f.appearanceBorderThickness=border
    end
    f:SetBackdropBorderColor(color("borderColor",{.27,.27,.27,1}))
    if border==0 then f:SetBackdropBorderColor(0,0,0,0) end
    fill(f.titleFill,"titleBackgroundColor",{.105,.06,.12,1},opacity)
    -- Keep labels readable over the world while the main surface fades. This
    -- reaches zero with the global opacity and retains each color's own alpha.
    local headingOpacity=1-(1-opacity)^2
    fill(f.contextFill,"titleBackgroundColor",{.105,.06,.12,1},headingOpacity)
    fill(f.tableDecor[1],"headerColor",{18/255,18/255,18/255,1},headingOpacity)
    textColor(f.title,"textColor",{.9,.94,.96,1}); textColor(f.character,"textColor",{.9,.94,.96,1})
    for _,field in ipairs({f.context,f.source,f.note,f.footer,f.summary,f.medianSummary,f.runSummary,f.specRanks}) do textColor(field,"textColor",{225/255,242/255,245/255,1}) end
    textColor(f.note,"mutedColor",{225/255,242/255,245/255,1})
    textColor(f.scoreValue,"ratingColor",{226/255,104/255,168/255,1})
    f.staleBanner:SetBackdropColor(color("warningColor",{.12,.075,.015,1}))
    -- Inline warning color codes otherwise override the chosen text color.
    local warning=f.staleBanner.message:GetText() or ""
    local wr,wg,wb=color("warningTextColor",{1,196/255,64/255,1})
    local warningHex=string.format("|cff%02x%02x%02x",math.floor(wr*255+.5),math.floor(wg*255+.5),math.floor(wb*255+.5))
    f.staleBanner.message:SetText(warning:gsub("|c%x%x%x%x%x%x%x%x",warningHex))
    textColor(f.staleBanner.message,"warningTextColor",{1,1,1,1})
    for _,button in ipairs({f.wclButton,f.searchButton,f.loadButton,f.lookupButton,f.inviteButton,f.closeButton,f.settingsButton or f.closeButton,f.appearanceButton or f.closeButton}) do
        local fallback=button==f.loadButton and {.24,.13,.32,1} or (button==f.settingsButton and {.16,.1,.21,1} or {.12,.10,.16,1})
        button.appearanceDefaultColor=fallback
        button:SetBackdropColor(color("buttonColor",fallback))
        button:SetBackdropBorderColor(color("borderColor",{.4,.29,.51,1}))
        if button.caption then textColor(button.caption,"buttonTextColor",{1,1,1,1}) end
        if button:IsEnabled()==false then
            button:SetBackdropColor(color("disabledColor",{.08,.08,.10,1}))
            if button.caption then textColor(button.caption,"mutedColor",{.5,.5,.5,1}) end
        end
        if not button.appearanceControlHooks then
            button.appearanceControlHooks=true
            button:HookScript("OnEnter",function(self) MPL.ColorAppearanceControl(self,true) end)
            button:HookScript("OnLeave",function(self) MPL.ColorAppearanceControl(self,false) end)
        end
    end
    for key,tab in pairs(f.metricTabs) do
        if key==f.viewMetric then tab:SetBackdropColor(color("selectedColor",{.28,.13,.40,1}))
        else tab:SetBackdropColor(color("buttonColor",{.045,.045,.055,1})) end
        textColor(tab.caption,"buttonTextColor",key==f.viewMetric and {1,.95,.8,1} or {.70,.70,.73,1})
        fill(tab.selectionBar,"accentColor",{1,.78,.30,1})
    end
    f.specButton:SetBackdropColor(color("buttonColor",{.12,.09,.18,1}))
    f.specButton:SetBackdropBorderColor(color("borderColor",{.64,.45,.83,1}))
    textColor(f.scoreLabel,"textColor",{1,1,1,1})
    for _,group in ipairs(f.appearanceGroups or {}) do textColor(group,"textColor",{1,1,1,1}) end
    for i,heading in ipairs(f.headings) do
        if f.sortColumn==i then textColor(heading,"accentColor",{1,.82,0,1})
        else textColor(heading,"textColor",{.93,.93,.93,1}) end
    end
    for _,row in ipairs(f.rows) do
        for i,cell in ipairs(row.cells) do
            local key=i==1 and "dungeonColor" or (i==5 and "ratingColor" or (i==7 and "rateColor" or "numberColor"))
            local fallback=i==1 and {.72,.78,1,1} or (i==5 and {226/255,104/255,168/255,1} or (i==7 and {.82,.96,.65,1} or {225/255,242/255,245/255,1}))
            if i~=6 or not option("semanticColors",true) then textColor(cell,key,fallback) end
            if cell:GetText()=="—" then textColor(cell,"missingColor",{225/255,242/255,245/255,1}) end
            if option("fontShadow",true) and i~=1 and not option("semanticColors",true) then
                local r,g,b=color(key,fallback)
                cell:SetShadowColor(r,g,b,cell:GetText()~="—" and 1 or 0)
            end
            if i==2 or not option("fontShadow",true) then cell:SetShadowColor(0,0,0,0); cell:SetShadowOffset(0,0) end
        end
        for _,digit in ipairs(row.levelDigits or {}) do
            textColor(digit,"numberColor",{225/255,242/255,245/255,1})
            digit:SetShadowColor(0,0,0,0); digit:SetShadowOffset(0,0)
        end
    end
end

function MPL.ColorAppearanceControl(button,hover,selected)
    if button:IsEnabled()==false then button:SetBackdropColor(color("disabledColor",{.08,.08,.1,1})); return end
    local key=hover and "hoverColor" or (selected and "selectedColor" or "buttonColor")
    button:SetBackdropColor(color(key,hover and {.22,.15,.31,1} or (selected and {0,0,0,1} or button.appearanceDefaultColor or {.12,.09,.18,1})))
    button:SetBackdropBorderColor(color(hover and "accentColor" or "borderColor",hover and {.86,.67,1,1} or {.64,.45,.83,1}))
end

local function positionKey()
    local name,realm=UnitFullName("player")
    return tostring(name or "player").."-"..tostring(realm or GetNormalizedRealmName())
end
local function validCoordinate(value) return type(value)=="number" and value==value and math.abs(value)<100000 end
function MPL.SaveAppearanceWindowPosition(f)
    local point,relative,relativePoint,x,y=f:GetPoint(1)
    if type(point)~="string" or type(relativePoint)~="string" or not validCoordinate(x) or not validCoordinate(y) then return end
    if relative and relative~=UIParent then return end
    MPlusLogsDB=MPlusLogsDB or {}
    if type(MPlusLogsDB.appearanceWindowPositions)~="table" then MPlusLogsDB.appearanceWindowPositions={} end
    MPlusLogsDB.appearanceWindowPositions[positionKey()]={point=point,relativePoint=relativePoint,x=x,y=y}
end
function MPL.RestoreAppearanceWindowPosition(f)
    local positions=MPlusLogsDB and MPlusLogsDB.appearanceWindowPositions
    local saved=type(positions)=="table" and positions[positionKey()]
    local anchors={TOP=true,BOTTOM=true,LEFT=true,RIGHT=true,CENTER=true,TOPLEFT=true,TOPRIGHT=true,BOTTOMLEFT=true,BOTTOMRIGHT=true}
    if type(saved)=="table" and anchors[saved.point] and anchors[saved.relativePoint] and validCoordinate(saved.x) and validCoordinate(saved.y) then
        f:ClearAllPoints(); f:SetPoint(saved.point,UIParent,saved.relativePoint,saved.x,saved.y)
    end
end
function MPL.ResetAppearanceWindowPosition()
    local positions=MPlusLogsDB and MPlusLogsDB.appearanceWindowPositions
    if type(positions)=="table" then positions[positionKey()]=nil end
    if MPL.panel then MPL.panel:ClearAllPoints(); MPL.panel:SetPoint("CENTER",UIParent,"CENTER",0,0) end
end

local views=setmetatable({},{__mode="k"})
function MPL.RegisterAppearanceView(f) views[f]=true end
function MPL.ApplyAppearanceToViews()
    for f in pairs(views) do
        if f:IsShown() then
            local scroll=f.scroll:GetVerticalScroll()
            local lookupText=f.lookup:GetText(); local focused=f.lookup:HasFocus()
            f.appearancePreserveScroll=true
            MPL.RenderProfileStats(f)
            f.appearancePreserveScroll=nil
            if type(scroll)=="number" then
                f.scroll:SetVerticalScroll(math.min(scroll,math.max(0,f.content:GetHeight()-f.scroll:GetHeight())))
            end
            if f.lookup:GetText()~=lookupText then f.lookup:SetText(lookupText) end
            if focused then f.lookup:SetFocus() end
        end
    end
end

function MPL.ShowAppearancePreview()
    if InCombatLockdown() then return nil end
    local f=MPL.appearancePreview
    if not f then
        f=MPL.CreateTutorialProfileFrame("MPlusLogsAppearancePreview")
        f.appearanceSample=true
        MPL.appearancePreview=f
        f.name,f.realm,f.class="Preview","Example","DRUID"
        f.title:SetText(L["MPlusLogs — Appearance preview"])
        f.character:SetText(L["Sample character — fictional data"])
        f.context:SetText("Midnight M+ Season 2")
        f.source:SetText(L["Appearance preview: sample data"])
        f.note:SetText(L["No Warcraft Logs requests are sent."])
        f.footer:SetText(L["Changes are applied immediately. Save or cancel in the editor."])
        f.emptyMessage:Hide(); f.inviteButton:Hide(); f.inviteInfo:Hide()
        f.currentSpec.name:SetText(MPL.SpecLabel("Guardian","DRUID"))
        f.currentSpec.icon:SetTexture("Interface/Icons/Ability_Racial_BearForm")
        f.specButton.caption:SetText(MPL.SpecLabel("Guardian","DRUID"))
        f.specButton.icon:SetTexture("Interface/Icons/Ability_Racial_BearForm")
        f.specButton.detail:SetText(L["Appearance preview"])
        f.specButton:SetScript("OnClick",nil)
        for _,button in ipairs({f.loadButton,f.wclButton,f.searchButton,f.lookupButton,f.inviteButton}) do
            button:SetScript("OnClick",nil); button:SetScript("OnUpdate",nil); button:Disable()
        end
        f.lookup:SetScript("OnEnterPressed",nil)
        f.profile={name="Preview",realm="Example",spec="Guardian",metric="dps",dual=true,score=3807,runs=192,best=73.4,median=56.2,
            otherBest=69,otherMedian=48,updated="2026-10-23 12:00 UTC",dungeons={}}
        f.stale=true
        local names={"Altar of Fangs","Den of Nalorakk","Kings' Rest","Murder Row","Ruby Life Pools","Temple of Sethraliss","The Blinding Vale","Voidscar Arena"}
        for i,name in ipairs(names) do
            f.profile.dungeons[i]={name=name,level=i==1 and 20 or (i==2 and 21 or 19),time="29:26",runs=33-i,
                points=485-i,rank=1198+i*127,rankPercent=99-i*3,scoreSpec="Guardian",amount=203830-i*5270,best=99-i*8,median=80-i*7,
                otherLevel=19,otherAmount=146300-i*7170,otherBest=89-i*5,otherMedian=61-i*5}
        end
        f.profile.dungeons[8].amount=nil; f.profile.dungeons[8].best=nil
        f.profile.dungeons[6].flagged=true
        f.sortRefresh=function() MPL.RenderProfileStats(f) end
        for metric,tab in pairs(f.metricTabs) do
            local selected=metric
            tab:SetScript("OnClick",function() f.viewMetric=selected; MPL.RenderProfileStats(f) end)
        end
    end
    f.viewMetric=f.viewMetric or "dps"
    MPL.RenderProfileStats(f)
    for _,row in ipairs(f.rows) do row.url=nil; row:SetScript("OnMouseUp",nil); row.scoreSpecIcon:SetScript("OnMouseUp",nil) end
    f:Show()
    return f
end
