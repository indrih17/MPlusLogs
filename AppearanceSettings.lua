local _, MPL = ...
local L = MPL.L

-- Profile colors are shared; editor typography and geometry stay stable.
local widgets={labels={},buttons={},inputs={},checks={},sliders={},surfaces={}}
local paintButton
local editorFontSize,editorControlHeight=14,32
local editorButtonFonts
local function extraSpacing() return 1.4 end
local function styleEditorFont(field,role)
    field:SetFontObject(role=="title" and "GameFontNormalLarge" or "GameFontHighlightSmall")
    local size=role=="title" and 20 or editorFontSize
    local path,_,flags=field:GetFont()
    if path then field:SetFont(path,size,flags or "") end
    field.mplAppliedFontSize=size
    field:SetHeight(math.max(size+8,field.editorMeasuredHeight or 0))
    if field.editorAutoHeight then
        field:SetHeight(0)
        field:SetHeight(math.max(size+8,field:GetStringHeight() or 0))
    end
end
local function styleEditorButton(b)
    b:SetNormalFontObject("GameFontHighlightSmall")
    b:SetHighlightFontObject("GameFontHighlightSmall")
    b:SetDisabledFontObject("GameFontDisableSmall")
    styleEditorFont(b.caption,"button")
    -- Native button state changes must retain the larger editor font too.
    local path,_,flags=b.caption:GetFont()
    if CreateFont and type(path)=="string" then
        if not editorButtonFonts then
            editorButtonFonts={}
            for _,state in ipairs({"Normal","Highlight","Disabled"}) do
                local font=CreateFont("MPlusLogsEditorButton"..state)
                font:SetFont(path,editorFontSize,flags or "")
                font:SetTextColor(state=="Disabled" and .5 or 1,state=="Disabled" and .5 or 1,state=="Disabled" and .5 or 1)
                editorButtonFonts[state]=font
            end
        end
        b:SetNormalFontObject(editorButtonFonts.Normal)
        b:SetHighlightFontObject(editorButtonFonts.Highlight)
        b:SetDisabledFontObject(editorButtonFonts.Disabled)
    end
    if b.editorMinWidth then
        b:SetWidth(math.max(b.editorMinWidth,(b.caption:GetUnboundedStringWidth() or 0)+(b.editorDisclosure and 48 or 24)))
    end
end
local function rememberLayout(widget,parent,x,y)
    widget.editorLayout={parent=parent,x=x,y=y}
end
local function track(kind,widget,role)
    widgets[kind][#widgets[kind]+1]=widget
    widget.editorFontRole=role
    return widget
end
local sections={
    {id="quick",label="Quick setup"}, {id="window",label="Window and blocks"},
    {id="table",label="Table and columns"}, {id="fonts",label="Fonts and numbers"},
    {id="colors",label="Colors and opacity"}, {id="names",label="Dungeon names and labels"},
    {id="profiles",label="Appearance profiles"},
}
local quick={scale=true,font=true,fontSize=true,surfaceOpacity=true,
    gridMode=true,dungeonLanguage=true,dungeonFormat=true,levelDigits=true,backgroundColor=true}
-- Expose the overall palette, rather than a separate picker for every piece
-- of text and control state. Keep the full schema for existing/imported styles.
local paletteColors={backgroundColor=true,titleBackgroundColor=true,headerColor=true,
    textColor=true,buttonColor=true,accentColor=true,borderColor=true,gridColor=true}
local function translated(text) return L[text or ""] end
local function text(parent,value,x,y,width,template)
    local label=parent:CreateFontString(nil,"OVERLAY",template or "GameFontHighlightSmall")
    label:SetPoint("TOPLEFT",x,y); label:SetWidth(width); label:SetJustifyH("LEFT")
    label:SetText(value or "")
    rememberLayout(label,parent,x,y)
    track("labels",label,"secondary")
    return label
end
local function button(parent,value,x,y,width,callback)
    local b=CreateFrame("Button",nil,parent,"BackdropTemplate")
    b:SetSize(width,editorControlHeight); b:SetPoint("TOPLEFT",x,y); b:SetText(value)
    rememberLayout(b,parent,x,y)
    b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    b.caption=b:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall")
    b.caption:SetPoint("LEFT",b,"LEFT",8,0); b.caption:SetPoint("RIGHT",b,"RIGHT",-8,0)
    b.caption:SetJustifyH("CENTER"); b.caption:SetWordWrap(false)
    b:SetFontString(b.caption); b.caption:SetText(value)
    track("buttons",b)
    b:HookScript("OnEnter",function(self) self.editorHovered=true; if paintButton then paintButton(self) end end)
    b:HookScript("OnLeave",function(self) self.editorHovered=false; if paintButton then paintButton(self) end end)
    b:SetScript("OnClick",callback)
    styleEditorButton(b)
    if paintButton then paintButton(b) end
    return b
end
local function edit(parent,x,y,width)
    local field=CreateFrame("EditBox",nil,parent,"BackdropTemplate")
    field:SetFontObject("GameFontHighlightSmall")
    field:SetTextInsets(6,6,2,2)
    track("inputs",field,"secondary")
    field:SetAutoFocus(false); field:SetSize(width,editorControlHeight); field:SetPoint("TOPLEFT",x,y)
    rememberLayout(field,parent,x,y)
    field:SetMaxLetters(180); field:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
    return field
end
local function checkbox(parent,x,y)
    local b=CreateFrame("CheckButton",nil,parent,"BackdropTemplate")
    b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    b.checkMark=b:CreateTexture(nil,"OVERLAY")
    b.checkMark:SetPoint("TOPLEFT",6,-6); b.checkMark:SetPoint("BOTTOMRIGHT",-6,6)
    b.checkMark:SetTexture("Interface/Buttons/WHITE8X8"); b:SetCheckedTexture(b.checkMark)
    track("checks",b)
    rememberLayout(b,parent,x or 0,y or 0)
    return b
end
local function value(key) return MPL.AppearanceValue and MPL.AppearanceValue(key) end
local function status(message,error)
    local f=MPL.appearanceEditor
    if f then
        f.status:SetText(message and translated(message) or "")
        f.status.editorError=error==true
        if MPL.ApplyAppearanceToEditor then MPL.ApplyAppearanceToEditor(f) end
    end
end
local function normalize(s)
    s=tostring(s or "")
    return MPL.Normalize and MPL.Normalize(s) or s:lower()
end
local function report(ok,message)
    if ok then status("") else status(message or L["Invalid value."],true) end
    return ok
end
local function setValue(key,v)
    return report(MPL.SetAppearanceValue(key,v))
end
local refresh

local function scrollMaximum(scroll,content)
    return math.max(0,content:GetHeight()-math.max(1,scroll:GetHeight()))
end
local function stopScrolling(scroll)
    scroll.editorScrollTarget=nil
    scroll.editorScrollDirection=nil
    if scroll.editorScrollDriver then scroll.editorScrollDriver:SetScript("OnUpdate",nil) end
    local input=scroll.ScrollBar and scroll.ScrollBar.editorInput
    if input then input:SetScript("OnUpdate",nil) end
end
local function updateScroll(f)
    local overflow=f.content:GetHeight()>math.max(1,f.scroll:GetHeight())+1
    if f.scroll.ScrollBar then f.scroll.ScrollBar:SetShown(overflow) end
    f.scroll:EnableMouseWheel(overflow)
    if f.scroll.editorScrollDriver then
        local scroll,bar=f.scroll,f.scroll.ScrollBar
        local maximum=overflow and scrollMaximum(scroll,f.content) or 0
        local position=math.max(0,math.min(maximum,scroll:GetVerticalScroll() or 0))
        -- Range/layout updates must not be mistaken for a manual drag.
        scroll.editorScrollSync=true
        bar:SetMinMaxValues(0,maximum); bar:SetValue(position)
        scroll:SetVerticalScroll(position)
        scroll.editorScrollSync=nil
        local height=math.max(1,scroll:GetHeight())
        f.scrollThumb:SetHeight(math.min(height,math.max(32,height*height/math.max(height,f.content:GetHeight()))))
        if not overflow then stopScrolling(scroll)
        elseif scroll.editorScrollTarget then
            scroll.editorScrollTarget=math.min(maximum,scroll.editorScrollTarget)
        end
    elseif not overflow then f.scroll:SetVerticalScroll(0) end
end

local function setupEditorScroll(f)
    local scroll=f.scroll
    -- Flat rail and solid thumb, matching the tutorial's scroll indicators.
    local bar=CreateFrame("Slider",nil,scroll,"BackdropTemplate")
    scroll.ScrollBar=bar
    bar:SetPoint("TOPLEFT",scroll,"TOPRIGHT",10,0)
    bar:SetPoint("BOTTOMLEFT",scroll,"BOTTOMRIGHT",10,0)
    bar:SetWidth(20); bar:SetOrientation("VERTICAL")
    bar:SetMinMaxValues(0,0); bar:SetValueStep(1); bar:SetObeyStepOnDrag(false)
    bar:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",edgeSize=1})
    f.scrollThumb=bar:CreateTexture(nil,"ARTWORK")
    f.scrollThumb:SetTexture("Interface/Buttons/WHITE8X8")
    f.scrollThumb:SetSize(16,52); bar:SetThumbTexture(f.scrollThumb)
    local driver=CreateFrame("Frame",nil,scroll)
    scroll.editorScrollDriver=driver
    local function setPosition(position)
        scroll.editorScrollSync=true
        scroll:SetVerticalScroll(position); bar:SetValue(position)
        scroll.editorScrollSync=nil
    end
    bar:SetScript("OnValueChanged",function(_,position)
        if scroll.editorScrollSync then return end
        stopScrolling(scroll)
        setPosition(math.max(0,math.min(scrollMaximum(scroll,f.content),position)))
    end)
    scroll:SetScript("OnVerticalScroll",function(_,position)
        if scroll.editorScrollSync then return end
        stopScrolling(scroll)
        scroll.editorScrollSync=true; bar:SetValue(position); scroll.editorScrollSync=nil
    end)
    -- Native Slider track clicks are unreliable with a large proportional thumb.
    -- Keep its rendering, but handle input against the visible thumb boundaries.
    bar:EnableMouse(false)
    local input=CreateFrame("Frame",nil,bar)
    bar.editorInput=input
    input:SetAllPoints(bar); input:EnableMouse(true)
    local function stopDragging() input:SetScript("OnUpdate",nil) end
    local function cursorY()
        local _,y=GetCursorPosition()
        return y/bar:GetEffectiveScale()
    end
    local function moveTo(position)
        setPosition(math.max(0,math.min(scrollMaximum(scroll,f.content),position)))
    end
    input:SetScript("OnMouseDown",function(_,button)
        if button~="LeftButton" then return end
        stopDragging(); stopScrolling(scroll)
        local y=cursorY()
        local top,bottom=f.scrollThumb:GetTop(),f.scrollThumb:GetBottom()
        if not top or not bottom then return end
        local position=scroll:GetVerticalScroll() or 0
        if y>top then
            moveTo(position-scroll:GetHeight())
        elseif y<bottom then
            moveTo(position+scroll:GetHeight())
        else
            -- Retain the grab point: pressing an edge must not centre the thumb.
            local travel=bar:GetHeight()-f.scrollThumb:GetHeight()
            if travel<=0 then return end
            local unitsPerPixel=scrollMaximum(scroll,f.content)/travel
            input:SetScript("OnUpdate",function()
                if not IsMouseButtonDown("LeftButton") then stopDragging(); return end
                moveTo(position+(y-cursorY())*unitsPerPixel)
            end)
        end
    end)
    input:SetScript("OnMouseUp",function(_,button)
        if button=="LeftButton" then stopDragging() end
    end)
    input:SetScript("OnHide",stopDragging)
    bar:HookScript("OnSizeChanged",stopDragging)
    scroll:SetScript("OnMouseWheel",function(_,delta)
        if delta==0 then return end
        stopDragging()
        local position=scroll:GetVerticalScroll() or 0
        local target=scroll.editorScrollTarget or position
        -- Reversing the wheel takes effect immediately, even during animation.
        if scroll.editorScrollDirection and delta*scroll.editorScrollDirection<0 then target=position end
        scroll.editorScrollDirection=delta
        scroll.editorScrollTarget=math.max(0,math.min(scrollMaximum(scroll,f.content),target-delta*40))
        driver:SetScript("OnUpdate",function(_,elapsed)
            local current=scroll:GetVerticalScroll() or 0
            local destination=scroll.editorScrollTarget
            local nextPosition=current+(destination-current)*(1-math.exp(-elapsed/0.055))
            if math.abs(destination-nextPosition)<0.5 then
                setPosition(destination); stopScrolling(scroll)
            else setPosition(nextPosition) end
        end)
    end)
    scroll:HookScript("OnHide",function() stopScrolling(scroll) end)
end

local function hideChoices(f)
    if f.choices then f.choices:Hide() end
end
local function openChoices(f,anchor,options,current,callback)
    local menu=f.choices
    if menu and menu:IsShown() and menu.anchor==anchor then
        menu:Hide()
        return
    end
    if not menu then
        menu=CreateFrame("Frame",nil,f,"BackdropTemplate")
        track("surfaces",menu)
        menu:SetSize(400,280); menu:SetClampedToScreen(true)
        menu:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Tooltips/UI-Tooltip-Border",edgeSize=16,
            insets={left=4,right=4,top=4,bottom=4}})
        menu:SetBackdropColor(0.035,0.035,0.05,1); menu:EnableMouse(true)
        menu.scroll=CreateFrame("ScrollFrame",nil,menu,"UIPanelScrollFrameTemplate")
        menu.scroll:SetPoint("TOPLEFT",10,-12); menu.scroll:SetPoint("BOTTOMRIGHT",-30,12)
        menu.content=CreateFrame("Frame",nil,menu.scroll)
        menu.content:SetSize(350,1); menu.scroll:SetScrollChild(menu.content)
        menu.scroll:HookScript("OnScrollRangeChanged",function() updateScroll(menu) end)
        menu.scroll:HookScript("OnSizeChanged",function() updateScroll(menu) end)
        menu.scroll:HookScript("OnShow",function() updateScroll(menu) end)
        menu.buttons={}
        f.choices=menu
    end
    menu:Hide(); menu:ClearAllPoints(); menu:SetPoint("TOPLEFT",anchor,"BOTTOMLEFT",0,-2)
    menu.anchor=anchor
    menu:SetFrameLevel(f:GetFrameLevel()+30)
    menu.options=options or {}; menu.callback=callback; menu.current=current
    menu.draw=function()
        local count=0
        local itemHeight=editorControlHeight+4
        local inset=12
        menu.scroll:ClearAllPoints(); menu.scroll:SetPoint("TOPLEFT",10,-inset); menu.scroll:SetPoint("BOTTOMRIGHT",-30,12)
        for _,item in ipairs(menu.options) do
            local label=item.label or item.name or tostring(item.value or item.id)
            local caption=item.rawLabel and label or translated(label)
            count=count+1
            local b=menu.buttons[count]
            if not b then
                b=button(menu.content,"",0,0,348,function(self)
                    local selected=self.choice
                    menu:Hide()
                    if selected and menu.callback then menu.callback(selected) end
                end)
                b.selectionMark=b:CreateTexture(nil,"OVERLAY")
                b.selectionMark:SetSize(3,12)
                b.selectionMark:SetPoint("LEFT",7,0)
                b.selectionMark:SetColorTexture(1,0.82,0,1)
                menu.buttons[count]=b
            end
            b.choice=item.value or item.id
            b.editorSelected=b.choice==menu.current
            -- A few swatches make palettes distinguishable before applying one.
            if item.colors and not b.paletteSwatches then
                b.paletteSwatches={}
                for i=1,3 do
                    local swatch=b:CreateTexture(nil,"OVERLAY")
                    swatch:SetSize(12,12); swatch:SetPoint("RIGHT",b,"RIGHT",-12-(3-i)*18,0)
                    b.paletteSwatches[i]=swatch
                end
            end
            for i,swatch in ipairs(b.paletteSwatches or {}) do
                local key=({"backgroundColor","accentColor","textColor"})[i]
                swatch:SetShown(item.colors~=nil)
                if item.colors then swatch:SetColorTexture(unpack(item.colors[key])) end
            end
            b.caption:ClearAllPoints(); b.caption:SetPoint("LEFT",b,"LEFT",8,0)
            b.caption:SetPoint("RIGHT",b,"RIGHT",item.colors and -76 or -8,0)
            b:ClearAllPoints(); b:SetPoint("TOPLEFT",0,-(count-1)*itemHeight)
            b:SetText(caption)
            b.selectionMark:SetShown(b.choice==menu.current)
            b:Show()
        end
        for i=count+1,#menu.buttons do menu.buttons[i]:Hide() end
        local contentHeight=math.max(1,count*itemHeight)
        -- Keep only the list insets, capped for long lists.
        menu:SetHeight(math.min(280,inset+12+contentHeight))
        menu.content:SetHeight(contentHeight); menu.scroll:SetVerticalScroll(0)
        updateScroll(menu)
        if MPL.ApplyAppearanceToEditor then MPL.ApplyAppearanceToEditor(f) end
    end
    menu.draw(); menu:Show()
    if MPL.ApplyAppearanceToEditor then MPL.ApplyAppearanceToEditor(f) end
end

local function colorHex(c)
    if type(c)~="table" then c={1,1,1,1} end
    return string.format("%02X%02X%02X%02X",math.floor((c[1] or 1)*255+0.5),
        math.floor((c[2] or 1)*255+0.5),math.floor((c[3] or 1)*255+0.5),math.floor((c[4] or 1)*255+0.5))
end
local function parseHex(s)
    s=(s or ""):gsub("^#",""):gsub("%s","")
    if (#s~=6 and #s~=8) or not s:match("^%x+$") then return nil end
    return {tonumber(s:sub(1,2),16)/255,tonumber(s:sub(3,4),16)/255,
        tonumber(s:sub(5,6),16)/255,#s==8 and tonumber(s:sub(7,8),16)/255 or 1}
end

function MPL.OpenAppearanceColorPicker(key)
    local f=MPL.appearanceEditor
    if not f or not f:IsShown() then return end
    local picker=ColorPickerFrame
    if not picker then
        -- Some client/UI arrangements leave the Blizzard picker unloaded.
        -- Load only Blizzard's own UI module; never depend on another addon
        -- having opened its picker first.
        local loader=C_AddOns and C_AddOns.LoadAddOn or UIParentLoadAddOn or LoadAddOn
        if loader then pcall(loader,"Blizzard_ColorPicker") end
        picker=ColorPickerFrame
    end
    if not picker then status(L["Use the HEX field to enter a color."],true); return end
    -- Hide the previous singleton picker before assigning this transaction.
    -- SetupColorPickerAndShow may itself hide/show the frame while resetting
    -- its content; an old owner's OnHide must not close the new transaction.
    picker:Hide()
    if f.pendingColor then
        if MPL.EndAppearanceAction then MPL.EndAppearanceAction() end
        f.pendingColor=nil
    end
    local c=value(key) or {1,1,1,1}
    local previous={c[1],c[2],c[3],c[4] or 1}
    local session=f.session
    local owner={key=key,previous=previous,session=session}
    f.pendingColor=owner
    if MPL.BeginAppearanceAction then MPL.BeginAppearanceAction() end
    if not picker.mplAppearanceHooked then
        picker.mplAppearanceHooked=true
        picker:HookScript("OnHide",function(self)
            local editor=self.mplAppearanceOwner
            local transaction=editor and editor.pendingColor
            if editor and transaction then
                -- Blizzard/Ace consumers allow final color/opacity callbacks
                -- after Hide. Keep this owner valid through those callbacks,
                -- including a cancel callback that restores the old color.
                local function complete()
                    if editor.pendingColor==transaction then
                        if MPL.EndAppearanceAction then MPL.EndAppearanceAction() end
                        editor.pendingColor=nil
                        if self.mplAppearanceOwner==editor then self.mplAppearanceOwner=nil end
                    end
                end
                if C_Timer and C_Timer.After then C_Timer.After(0,complete) else complete() end
            end
        end)
    end
    local function active() return f:IsShown() and f.session==session and f.pendingColor==owner end
    local function update()
        if not active() then return end
        local r,g,b=picker:GetColorRGB()
        local a=picker.GetColorAlpha and picker:GetColorAlpha()
        if type(a)~="number" then
            local opacity=OpacitySliderFrame and OpacitySliderFrame:GetValue()
            a=1-(type(opacity)=="number" and opacity or picker.opacity or 0)
        end
        setValue(key,{r,g,b,a}); refresh(f,true)
    end
    local function cancel()
        if not active() then return end
        setValue(key,previous)
        if MPL.EndAppearanceAction then MPL.EndAppearanceAction() end
        f.pendingColor=nil; refresh(f,true)
    end
    picker.mplAppearanceOwner=f
    picker:SetFrameStrata("FULLSCREEN_DIALOG")
    picker:SetFrameLevel(f:GetFrameLevel()+10)
    picker:SetClampedToScreen(true)
    if picker.SetupColorPickerAndShow then
        picker:SetupColorPickerAndShow({r=previous[1],g=previous[2],b=previous[3],
            opacity=previous[4],hasOpacity=true,swatchFunc=update,opacityFunc=update,cancelFunc=cancel})
    else
        picker.hasOpacity=true; picker.opacity=1-previous[4]
        picker.previousValues=previous; picker.func=update; picker.opacityFunc=update; picker.cancelFunc=cancel
        picker:SetColorRGB(previous[1],previous[2],previous[3]); picker:Show()
    end
end

local function optionsFor(field)
    if field.key=="font" or field.key:match("^font_") then
        local result={}
        if field.key~="font" then result[1]={value="inherit",label="Inherit base font"} end
        for _,option in ipairs(MPL.GetAppearanceFonts and MPL.GetAppearanceFonts() or {{value="native",label="Game interface font"}}) do
            result[#result+1]=option
        end
        return result
    end
    return type(field.options)=="function" and field.options() or field.options or {}
end
local function optionLabel(field,current)
    for _,item in ipairs(optionsFor(field)) do
        if item.value==current then return translated(item.label) end
    end
    return tostring(current or "")
end
local function numberValue(field)
    local current=value(field.key)
    local role=field.key:match("^size_(.+)$")
    if role and MPL.GetAppearanceFontSize then
        local preview=MPL.panel and MPL.panel:IsShown() and MPL.panel or MPL.appearancePreview
        local sample
        if preview then
            local names={title="title",character="character",summary="summary",rating="scoreValue",secondary="source"}
            sample=names[role] and preview[names[role]]
            if role=="header" then sample=preview.headings and preview.headings[1]
            elseif role=="dungeon" or role=="numbers" then
                sample=preview.rows and preview.rows[1] and preview.rows[1].cells[role=="dungeon" and 1 or 2]
            elseif role=="button" then sample=preview.loadButton and preview.loadButton.caption
            elseif role=="warning" then sample=preview.staleBanner and preview.staleBanner.message end
        end
        return MPL.GetAppearanceFontSize(role,sample and sample.mplNativeFont and sample.mplNativeFont.size)
    end
    return current or 0
end
local function layoutFieldRow(row)
    local field=row.field
    styleEditorFont(row.label,"secondary")
    row.label:SetHeight(0)
    local labelHeight=math.max(editorFontSize+8,row.label:GetStringHeight() or 0)
    row.label.editorMeasuredHeight=labelHeight
    row.label:SetHeight(labelHeight)
    local top=labelHeight+8
    local control=row.control
    local height=editorControlHeight
    local captionWidth=row.reset.caption:GetUnboundedStringWidth()
    local resetWidth=math.max(100,type(captionWidth)=="number" and math.ceil(captionWidth)+24 or 100)
    local resetX=610-resetWidth
    local x=field.kind=="number" and resetX-92 or (field.kind=="boolean" or field.kind=="select" or field.kind=="color") and 0 or 4
    control:ClearAllPoints(); control:SetPoint("TOPLEFT",x,-top); control:SetHeight(height)
    if field.kind=="boolean" then control:SetWidth(editorControlHeight) end
    if field.kind=="select" or field.kind=="string" then control:SetWidth(math.max(80,resetX-x-12)) end
    row.reset:ClearAllPoints(); row.reset:SetPoint("TOPLEFT",resetX,-top); row.reset:SetSize(resetWidth,height)
    if row.slider then
        row.slider:ClearAllPoints(); row.slider:SetPoint("TOPLEFT",4,-top-6); row.slider:SetHeight(20)
        row.slider:SetWidth(math.max(40,x-20))
    end
    if row.hex then row.hex:ClearAllPoints(); row.hex:SetPoint("TOPLEFT",214,-top); row.hex:SetHeight(height) end
    if row.hint then row.hint:ClearAllPoints(); row.hint:SetPoint("TOPLEFT",field.kind=="boolean" and 40 or 376,-top-5) end
    local bottom=top+height
    if row.sample then
        row.sample:ClearAllPoints(); row.sample:SetPoint("TOPLEFT",4,-bottom-6)
        bottom=bottom+6+math.max(20,(row.sample.mplAppliedFontSize or 10)+4)
        styleEditorFont(row.fontStatus,"secondary")
        row.fontStatus:ClearAllPoints(); row.fontStatus:SetPoint("TOPLEFT",4,-bottom-4)
        bottom=bottom+4+row.fontStatus:GetHeight()
    end
    row:SetHeight(bottom+10)
end
local function addFieldHelp(row,control)
    if not control then return end
    control:HookScript("OnEnter",function(self)
        local field=row.field
        if not field.help or not GameTooltip then return end
        GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
        GameTooltip:SetText(translated(field.label))
        GameTooltip:AddLine(translated(field.help),1,1,1,true)
        GameTooltip.mplAppearanceHelpOwner=self
        GameTooltip.mplAppearanceHelpRow=row
        GameTooltip:Show()
    end)
    control:HookScript("OnLeave",function(self)
        if GameTooltip and GameTooltip.mplAppearanceHelpOwner==self then
            GameTooltip:Hide()
            GameTooltip.mplAppearanceHelpOwner=nil
            GameTooltip.mplAppearanceHelpRow=nil
        end
    end)
end
local function fieldRow(f,field)
    local row=f.rows[field.key]
    if row then row.field=field; return row end
    row=CreateFrame("Frame",nil,f.content)
    row:SetSize(618,58); row.field=field; row.key=field.key
    row.label=text(row,translated(field.label),0,0,590)
    row.label:SetWordWrap(true)
    row.reset=button(row,L["Reset"],472,-22,64,function()
        local default=MPL.AppearanceDefaults and MPL.AppearanceDefaults[field.key]
        if default~=nil then setValue(field.key,default); refresh(f,true) end
    end)
    if field.kind=="boolean" then
        row.control=checkbox(row,0,-18)
        row.control:SetPoint("TOPLEFT",0,-18); row.control:SetSize(28,28)
        row.control:SetScript("OnClick",function(self) setValue(field.key,self:GetChecked()==true) end)
        row.hint=text(row,L["Enabled"],32,-25,390)
    elseif field.kind=="select" then
        row.control=button(row,"",0,-22,450,function(self)
            openChoices(f,self,optionsFor(row.field),value(field.key),function(v)
                setValue(field.key,v); refresh(f,true)
            end)
        end)
        if field.key=="font" or field.key:match("^font_") then
            row:SetHeight(100)
            row.sample=text(row,L["Font sample: Подземелье — 19 20 99.9%"],4,-52,450)
            row.sample.editorFontSample=true
            row.sample:SetWordWrap(false)
            row.fontStatus=text(row,"",4,-76,450)
            row.fontStatus:SetWordWrap(false)
        end
    elseif field.kind=="number" then
        row.control=edit(row,370,-22,80)
        row.control:SetMaxLetters(12)
        local function commit(self)
            local n=tonumber(((self:GetText() or ""):gsub(",",".")))
            if not n or n~=n or n==math.huge or n==-math.huge then status(L["Enter a number."],true); return false
            elseif setValue(field.key,n) then self:ClearFocus(); refresh(f,true); return true end
            return false
        end
        row.commit=commit
        row.control:SetScript("OnEnterPressed",commit)
        row.slider=CreateFrame("Slider",nil,row,"BackdropTemplate")
        row.slider:SetOrientation("HORIZONTAL")
        track("sliders",row.slider)
        row.slider:SetPoint("TOPLEFT",4,-25); row.slider:SetSize(340,16)
        row.slider:SetMinMaxValues(field.min or 0,field.max or 100)
        row.slider:SetValueStep(field.step or 1); row.slider:SetObeyStepOnDrag(true)
        row.slider:SetScript("OnMouseDown",function(self)
            f.draggingSlider=self
            if MPL.BeginAppearanceAction then MPL.BeginAppearanceAction() end
        end)
        row.slider:SetScript("OnMouseUp",function()
            f.draggingSlider=nil
            if MPL.EndAppearanceAction then MPL.EndAppearanceAction() end
            if MPL.ApplyAppearanceToEditor then MPL.ApplyAppearanceToEditor(f) end
            refresh(f,true)
        end)
        row.slider:SetScript("OnValueChanged",function(_,n)
            if f.updating then return end
            local step=field.step or 1
            n=math.floor(n/step+0.5)*step
            if numberValue(field)~=n then setValue(field.key,n); row.control:SetText(tostring(n)) end
        end)
    elseif field.kind=="color" then
        row.control=button(row,L["Choose color…"],0,-22,190,function() MPL.OpenAppearanceColorPicker(field.key) end)
        row.control.caption:ClearAllPoints()
        row.control.caption:SetPoint("LEFT",row.control,"LEFT",8,0)
        row.control.caption:SetPoint("RIGHT",row.control,"RIGHT",-30,0)
        row.swatch=row.control:CreateTexture(nil,"OVERLAY")
        row.swatch:SetSize(18,16); row.swatch:SetPoint("RIGHT",-5,0)
        row.hex=edit(row,214,-22,150); row.hex:SetMaxLetters(9)
        row.commit=function(self)
            local color=parseHex(self:GetText())
            if not color then status(L["Use RRGGBB or RRGGBBAA."],true); return false
            elseif setValue(field.key,color) then self:ClearFocus(); refresh(f,true); return true end
            return false
        end
        row.hex:SetScript("OnEnterPressed",row.commit)
        row.hint=text(row,"RRGGBBAA",376,-27,110)
    else
        row.control=edit(row,4,-22,446)
        row.commit=function(self)
            if setValue(field.key,self:GetText()) then self:ClearFocus(); refresh(f,true); return true end
            return false
        end
        row.control:SetScript("OnEnterPressed",row.commit)
    end
    row:EnableMouse(true)
    addFieldHelp(row,row)
    addFieldHelp(row,row.control)
    addFieldHelp(row,row.reset)
    addFieldHelp(row,row.slider)
    addFieldHelp(row,row.hex)
    row:HookScript("OnHide",function()
        if GameTooltip and GameTooltip.mplAppearanceHelpRow==row then
            GameTooltip:Hide()
            GameTooltip.mplAppearanceHelpOwner=nil
            GameTooltip.mplAppearanceHelpRow=nil
        end
    end)
    f.rows[field.key]=row
    return row
end

local function updateRow(f,row)
    local field=row.field
    local current=value(field.key)
    row.label:SetText(translated(field.label))
    if field.key:match("^size_") then row.label:SetText(translated(field.label):gsub("%s*%b()$","")) end
    if field.kind=="boolean" then row.control:SetChecked(current==true)
    elseif field.kind=="select" then
        row.control:SetText(optionLabel(field,current))
        if row.sample and MPL.ResolveAppearanceFont then
            local role=field.key=="font" and "base" or field.key:match("^font_(.+)$")
            local path,size,flags,key=MPL.ResolveAppearanceFont(role)
            local info=MPL.GetAppearanceFontInfo and MPL.GetAppearanceFontInfo(role)
            row.fontStatus:SetText(info and info.overridden and (L["LSM override:"].." "..info.actual) or "")
            if path then
                local ok,result=pcall(row.sample.SetFont,row.sample,path,math.min(16,size or 12),flags or "")
                if ok and result~=false then row.sample:SetText(L["Font sample: Подземелье — 19 20 99.9%"])
                else
                    row.sample:SetFontObject("GameFontHighlightSmall")
                    row.sample:SetText(L["Unavailable font; using the game interface font."])
                end
            elseif key and key~="native" and key~="inherit" then
                row.sample:SetFontObject("GameFontHighlightSmall")
                row.sample:SetText(L["Unavailable font; using the game interface font."])
            else
                row.sample:SetFontObject("GameFontHighlightSmall")
                row.sample:SetText(L["Font sample: Подземелье — 19 20 99.9%"])
            end
        end
    elseif field.kind=="number" then
        current=numberValue(field)
        if field.key:match("^size_") then row.slider:SetMinMaxValues(8,math.max(field.max or 40,current)) end
        if not row.control:HasFocus() then row.control:SetText(tostring(current or 0)) end
        row.slider:SetValue(current or 0)
    elseif field.kind=="color" then
        local c=type(current)=="table" and current or {1,1,1,1}
        row.swatch:SetColorTexture(c[1],c[2],c[3],c[4] or 1)
        if not row.hex:HasFocus() then row.hex:SetText(colorHex(c)) end
    elseif not row.control:HasFocus() then row.control:SetText(tostring(current or "")) end
end
local function extra(f,key,height)
    local row=f.extras[key]
    if not row then row=CreateFrame("Frame",nil,f.content,"BackdropTemplate"); row:SetWidth(550); f.extras[key]=row end
    row.editorExtra=true; row.editorBaseHeight=height
    row:SetHeight(height*extraSpacing()+2*(row.editorPanelPadding or 0)); return row
end
local function place(row,y)
    row:ClearAllPoints(); row:SetPoint("TOPLEFT",0,-y); row:Show()
    return y+row:GetHeight()+8
end
local function entryCaption(entry)
    return entry.builtin and translated(entry.name) or entry.name
end
local function themeOptions()
    local result={}
    for _,item in ipairs(MPL.GetAppearanceStyles and MPL.GetAppearanceStyles() or {}) do
        result[#result+1]={value=item.id,label=entryCaption(item),rawLabel=true}
    end
    return result
end
local function updateStyleRow(row)
    local id=MPL.GetAppearanceStyleID()
    local source=id or MPL.GetAppearanceStyleSourceID()
    local caption=L["Appearance style"]
    for _,entry in ipairs(themeOptions()) do if entry.value==source then caption=entry.label; break end end
    if not id then caption=string.format(L["%s (modified)"],caption) end
    row.control:SetText(caption)
end
local function disclosureButton(b,expanded)
    b.editorDisclosure=true; b.editorExpanded=expanded==true; b.editorSelected=b.editorExpanded
    b.editorMinWidth=188
    if not b.strokes then
        b.strokes={}
        for _,side in ipairs({-1,1}) do
            local stroke=b:CreateTexture(nil,"OVERLAY")
            stroke:SetSize(9,2); stroke:SetPoint("RIGHT",b,"RIGHT",-16+side*3,0)
            b.strokes[#b.strokes+1]=stroke
        end
        b.caption:ClearAllPoints(); b.caption:SetPoint("LEFT",b,"LEFT",8,0)
        b.caption:SetPoint("RIGHT",b,"RIGHT",-36,0)
    end
    for i,stroke in ipairs(b.strokes) do
        local side=i==1 and -1 or 1
        stroke:SetRotation((b.editorExpanded and -side or side)*math.pi/4)
    end
end
local function themeRow(f,y)
    local row=extra(f,"theme",62)
    if not row.control then
        row.label=text(row,L["Appearance style"],0,0,610)
        row.control=button(row,"",0,-24,410,function(self)
            openChoices(f,self,themeOptions(),MPL.GetAppearanceStyleID(),function(id)
                report(MPL.ApplyAppearanceStyle(id)); refresh(f,true)
            end)
        end)
        row.manage=button(row,L["Manage styles"],422,-24,188,function()
            f.manageStyle=not f.manageStyle; refresh(f,true)
        end)
    end
    disclosureButton(row.manage,f.manageStyle)
    updateStyleRow(row)
    return place(row,y)
end

local function updateProfileRow(row)
    local selected=MPL.GetAppearanceProfileID()
    for _,entry in ipairs(MPL.GetAppearanceProfiles()) do
        if entry.id==selected then row.control:SetText(entryCaption(entry)); break end
    end
end
local function profileRow(f,y)
    local row=extra(f,"profile",62)
    if not row.control then
        row.label=text(row,L["Appearance profile"],0,0,610)
        row.control=button(row,"",0,-24,610,function(self)
            local options={}
            for _,entry in ipairs(MPL.GetAppearanceProfiles()) do
                options[#options+1]={value=entry.id,label=entryCaption(entry),rawLabel=true}
            end
            openChoices(f,self,options,MPL.GetAppearanceProfileID(),function(id)
                report(MPL.SelectAppearanceProfile(id)); refresh(f)
            end)
        end)
    end
    updateProfileRow(row)
    return place(row,y)
end

local function updatePaletteRow(row)
    local id=MPL.GetAppearanceColorPresetID()
    local caption=L["Custom colors"]
    for _,entry in ipairs(MPL.GetAppearancePalettes()) do
        if entry.id==id then caption=entryCaption(entry); break end
    end
    row.control:SetText(caption)
    for _,swatch in ipairs(row.swatches) do swatch.texture:SetColorTexture(unpack(value(swatch.key))) end
end
local function paletteRow(f,y)
    local row=extra(f,"colorPalette",94)
    if not row.control then
        row.label=text(row,L["Color palette"],0,0,610)
        row.control=button(row,"",0,-24,410,function(self)
            local options={}
            for _,preset in ipairs(MPL.GetAppearancePalettes()) do
                options[#options+1]={value=preset.id,label=entryCaption(preset),rawLabel=true,colors=preset.colors}
            end
            openChoices(f,self,options,MPL.GetAppearanceColorPresetID(),function(id)
                report(MPL.ApplyAppearanceColorPreset(id)); refresh(f,true)
            end)
        end)
        row.manage=button(row,L["Manage palettes"],422,-24,188,function()
            f.managePalette=not f.managePalette; refresh(f,true)
        end)
        row.control.caption:ClearAllPoints()
        row.control.caption:SetPoint("LEFT",row.control,"LEFT",8,0)
        row.control.caption:SetPoint("RIGHT",row.control,"RIGHT",-144,0)
        row.swatches={}
        for i,key in ipairs({"backgroundColor","titleBackgroundColor","headerColor","buttonColor","accentColor","textColor"}) do
            local swatch=row.control:CreateTexture(nil,"OVERLAY")
            swatch:SetSize(14,14); swatch:SetPoint("RIGHT",row.control,"RIGHT",-12-(6-i)*20,0)
            row.swatches[i]={texture=swatch,key=key}
        end
        row.description=text(row,L["Choose a palette to change all colors at once. Layout and fonts stay unchanged."],0,-54,610)
        row.description:SetWordWrap(true); row.description.editorAutoHeight=true
    end
    disclosureButton(row.manage,f.managePalette)
    updatePaletteRow(row)
    return place(row,y)
end
local function paletteMatches(query)
    if normalize(L["Color palette"]):find(query,1,true) then return true end
    for _,entry in ipairs(MPL.GetAppearancePalettes()) do
        if normalize(entryCaption(entry)):find(query,1,true) then return true end
    end
    return false
end
local function templateLibrary(f,y,kind)
    local isStyle=kind=="style"
    local row=extra(f,isStyle and "styleLibrary" or "paletteLibrary",88)
    row.editorPanelPadding=12; row:SetWidth(610)
    row:SetHeight(88*extraSpacing()+24)
    if not row.panelAccent then
        row.panelAccent=row:CreateTexture(nil,"ARTWORK")
        row.panelAccent:SetPoint("TOPLEFT",1,-1); row.panelAccent:SetPoint("BOTTOMLEFT",1,1)
        row.panelAccent:SetWidth(3)
    end
    local entries=isStyle and MPL.GetAppearanceStyles() or MPL.GetAppearancePalettes()
    local function selection()
        if isStyle then return MPL.GetAppearanceStyleID() end
        return MPL.GetAppearanceColorPresetID()
    end
    local selected=selection()
    if not row.name then
        row.label=text(row,isStyle and L["Style name"] or L["Palette name"],0,0,586)
        row.name=edit(row,4,-22,400)
        row.create=button(row,isStyle and L["Save style"] or L["Save palette"],0,-56,150,function()
            local create=isStyle and MPL.CreateAppearanceStyle or MPL.CreateAppearancePalette
            local id,err=create(row.name:GetText())
            if report(id~=nil,err) then row.name:SetText(""); refresh(f,true) end
        end)
        row.rename=button(row,L["Rename"],160,-56,120,function()
            local id=selection()
            local rename=isStyle and MPL.RenameAppearanceStyle or MPL.RenameAppearancePalette
            if report(rename(id,row.name:GetText())) then row.name:SetText(""); refresh(f,true) end
        end)
        row.delete=button(row,L["Delete"],290,-56,120,function()
            local id=selection()
            local remove=isStyle and MPL.DeleteAppearanceStyle or MPL.DeleteAppearancePalette
            if report(remove(id)) then refresh(f,true) end
        end)
        for _,b in ipairs({row.create,row.rename,row.delete}) do b.editorMinWidth=b:GetWidth() end
    end
    local personal=false
    for _,entry in ipairs(entries) do if entry.id==selected then personal=not entry.builtin; break end end
    row.rename:SetEnabled(personal); row.delete:SetEnabled(personal)
    return place(row,y)
end
local function profiles(f,y)
    local row=extra(f,"profiles",314)
    if not row.name then
        row.label=text(row,L["Profile name"],0,0,530)
        row.name=edit(row,4,-22,330)
        row.create=button(row,L["Create profile"],0,-56,150,function()
            local id,err=MPL.CreateAppearanceProfile(row.name:GetText())
            if report(id~=nil,err) then row.name:SetText(""); refresh(f) end
        end)
        row.rename=button(row,L["Rename"],160,-56,120,function()
            if report(MPL.RenameAppearanceProfile(MPL.GetAppearanceProfileID(),row.name:GetText())) then refresh(f) end
        end)
        row.delete=button(row,L["Delete"],290,-56,120,function()
            if report(MPL.DeleteAppearanceProfile(MPL.GetAppearanceProfileID())) then refresh(f) end
        end)
        for _,b in ipairs({row.create,row.rename,row.delete}) do b.editorMinWidth=b:GetWidth() end
        row.info=text(row,L["A profile saves all appearance settings. Styles and palettes can be combined independently."],0,-92,610)
        row.info:SetWordWrap(true)
        row.info.editorAutoHeight=true
        row.aliases=checkbox(row,0,-146)
        row.aliases:SetSize(32,32); row.aliases:SetPoint("TOPLEFT",0,-146)
        row.aliasLabel=text(row,L["Include personal dungeon names in export"],40,-153,550)
        row.export=button(row,L["Export"],0,-188,150,function()
            MPL.ShowAppearanceTransfer(false,row.aliases:GetChecked()==true)
        end)
        row.import=button(row,L["Import…"],160,-188,150,function() MPL.ShowAppearanceTransfer(true) end)
        row.bindingLabel=text(row,L["Use this theme for"],0,-230,610)
        row.binding=button(row,"",0,-254,610,function(self)
            if not MPL.SetAppearanceCharacterBinding then return end
            openChoices(f,self,{{value="account",label="All characters"},{value="character",label="This character"}},
                MPL.GetAppearanceCharacterBinding and MPL.GetAppearanceCharacterBinding() or "account",function(scope)
                    report(MPL.SetAppearanceCharacterBinding(scope)); refresh(f,true)
                end)
        end)
    end
    row.binding:SetText(translated(MPL.GetAppearanceCharacterBinding and MPL.GetAppearanceCharacterBinding()=="character"
        and "This character" or "All characters"))
    row.binding:SetEnabled(MPL.SetAppearanceCharacterBinding~=nil)
    local personal=false
    local selected=MPL.GetAppearanceProfileID()
    for _,entry in ipairs(MPL.GetAppearanceProfiles()) do if entry.id==selected then personal=not entry.builtin; break end end
    row.rename:SetEnabled(personal); row.delete:SetEnabled(personal)
    return place(row,y)
end

local function dungeonList()
    if MPL.GetAppearanceDungeonList then return MPL.GetAppearanceDungeonList() end
    local result={}
    for id,item in pairs(MPL.DungeonCatalog or {}) do
        if type(item)=="table" then result[#result+1]={id=item.id or id,name=item.canonical or item.name or tostring(id)} end
    end
    table.sort(result,function(a,b) return tostring(a.name)<tostring(b.name) end)
    return result
end
local function aliases(f,y)
    for _,dungeon in ipairs(dungeonList()) do
        local id=dungeon.id
        local row=extra(f,"alias_"..tostring(id),56)
        if not row.control then
            row.label=text(row,dungeon.name,0,0,530)
            row.control=edit(row,4,-22,410)
            row.control:SetMaxLetters(80)
            row.commit=function(self)
                if report(MPL.SetDungeonAlias(id,self:GetText())) then self:ClearFocus(); refresh(f,true); return true end
                return false
            end
            row.control:SetScript("OnEnterPressed",row.commit)
            row.reset=button(row,L["Reset"],434,-22,100,function()
                report(MPL.SetDungeonAlias(id,"")); refresh(f,true)
            end)
        end
        row.label:SetText(dungeon.name)
        if not row.control:HasFocus() then row.control:SetText(MPL.GetDungeonAlias and MPL.GetDungeonAlias(id) or "") end
        y=place(row,y)
    end
    return y
end
local function arrowButton(parent,x,y,delta,callback)
    local b=button(parent,"",x,y,28,callback)
    b.strokes={}
    local function stroke(width,height,offsetX,offsetY,angle)
        local texture=b:CreateTexture(nil,"OVERLAY")
        texture:SetColorTexture(1,0.82,0,1)
        texture:SetSize(width,height); texture:SetPoint("CENTER",offsetX,offsetY)
        texture:SetRotation(angle)
        b.strokes[#b.strokes+1]=texture
    end
    local direction=-delta
    stroke(2,11,0,0,0)
    stroke(7,2,-2,direction*3,direction*math.pi/4)
    stroke(7,2,2,direction*3,-direction*math.pi/4)
    b:HookScript("OnEnter",function(self)
        GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
        GameTooltip:SetText(delta<0 and L["Up"] or L["Down"]); GameTooltip:Show()
    end)
    b:HookScript("OnLeave",function() GameTooltip:Hide() end)
    return b
end
local function enableArrow(b,enabled)
    b:SetEnabled(enabled)
    for _,texture in ipairs(b.strokes) do
        texture:SetVertexColor(enabled and 1 or 0.45,enabled and 1 or 0.45,enabled and 1 or 0.45)
    end
end
local function columnOrder(f,y)
    local row=extra(f,"columnOrder",292)
    if not row.label then
        row.label=text(row,L["Column order"],0,0,530); row.entries={}
    end
    local order=value("columnOrder") or {"dungeon","level","time","runs","points","rank","rate","best","median"}
    local labels={dungeon="Dungeon",level="Key level",time="Duration column",runs="Runs column",points="Points",rank="Leaderboard place",
        rate="Best DPS / HPS",best="Best percentile",median="Median percentile"}
    for i,id in ipairs(order) do
        local entry=row.entries[i]
        if not entry then
            entry={label=text(row,"",40,-29-(i-1)*28,400)}
            entry.visible=checkbox(row,0,-22-(i-1)*28)
            entry.visible:SetPoint("TOPLEFT",0,-22-(i-1)*28); entry.visible:SetSize(32,32)
            entry.visible:SetScript("OnClick",function(self)
                setValue("column_"..entry.id.."_visible",self:GetChecked()==true)
                refresh(f,true)
            end)
            local function move(delta)
                local current=value("columnOrder") or order
                local target=i+delta
                if target<1 or target>#current then return end
                local copy={}; for index,col in ipairs(current) do copy[index]=col end
                copy[i],copy[target]=copy[target],copy[i]
                if setValue("columnOrder",copy) then refresh(f,true) end
            end
            entry.up=arrowButton(row,450,-22-(i-1)*28,-1,function() move(-1) end)
            entry.down=arrowButton(row,484,-22-(i-1)*28,1,function() move(1) end)
            row.entries[i]=entry
        end
        entry.id=id
        entry.visible:SetChecked(value("column_"..id.."_visible")==true)
        entry.visible:SetEnabled(id~="dungeon")
        entry.label:SetText(tostring(i)..". "..translated(labels[id] or id))
        enableArrow(entry.up,i>1); enableArrow(entry.down,i<#order)
    end
    return place(row,y)
end

refresh=function(f,preserveScroll)
    if f and f.draggingSlider then return end
    if not f or not f:IsShown() or f.updating then return end
    f.updating=true
    for _,row in pairs(f.rows) do row:Hide() end
    for _,row in pairs(f.extras) do row:Hide() end
    local query=normalize(f.search:GetText())
    local y=0
    for _,section in ipairs(sections) do
        local b=f.sectionButtons[section.id]
        b.editorSelected=section.id==f.section
        b:SetText(translated(section.label))
    end
    if f.resetSection then f.resetSection:SetShown(f.section~="quick" and f.section~="profiles") end
    if query=="" and f.section=="profiles" then y=profileRow(f,y) end
    if query=="" and (f.section=="quick" or f.section=="profiles") then
        y=themeRow(f,y)
        if f.manageStyle then y=templateLibrary(f,y,"style") end
    end
    if (query=="" and (f.section=="colors" or f.section=="profiles")) or (query~="" and paletteMatches(query)) then y=paletteRow(f,y) end
    if query=="" and (f.section=="colors" or f.section=="profiles") and f.managePalette then y=templateLibrary(f,y,"palette") end
    if query=="" and f.section=="profiles" then y=profiles(f,y) end
    if query=="" and f.section=="table" then y=columnOrder(f,y) end
    for _,field in ipairs(MPL.AppearanceFields or {}) do
        local inQuick=quick[field.key] or field.key:match("^column_.*_visible$")
        local sectionLabel=field.section
        for _,section in ipairs(sections) do if section.id==field.section then sectionLabel=section.label; break end end
        local searchable=normalize(translated(field.label).." "..field.key.." "..translated(sectionLabel))
        local matched=query~="" and searchable:find(query,1,true)
        local selected=query=="" and (field.section==f.section or f.section=="quick" and inQuick)
        local combinedVisibility=query=="" and field.key:match("^column_.*_visible$")
        local hiddenSpacing=field.key=="cellPadding" or field.key:match("^column_.*_padding$")
        local hiddenColor=field.kind=="color" and not paletteColors[field.key]
        local hiddenHeading=field.key=="headerHeight" or field.key:match("^column_.*_label$")
        local hiddenAlignment=field.key:match("^column_.*_align$")
        local hiddenDigitGap=field.key=="digitGap" and value("levelDigits")~="aligned"
        if not hiddenDigitGap and not hiddenAlignment and not hiddenHeading and not hiddenColor and not hiddenSpacing and not combinedVisibility and field.key~="rowHeight" and field.kind~="order" and (matched or selected) then
            local row=fieldRow(f,field); updateRow(f,row); layoutFieldRow(row); y=place(row,y)
        end
    end
    if query=="" and f.section=="names" then y=aliases(f,y) end
    f.empty:SetShown(y==0)
    f.content:SetHeight(math.max(1,y)); f.scroll:UpdateScrollChildRect()
    if not preserveScroll then stopScrolling(f.scroll); f.scroll:SetVerticalScroll(0) end
    updateScroll(f)
    f.updating=false
    if MPL.ApplyAppearanceToEditor then MPL.ApplyAppearanceToEditor(f) end
end

function MPL.RefreshAppearanceEditor()
    local f=MPL.appearanceEditor
    if f and f:IsShown() then refresh(f,true) end
end

local function finish(f,save)
    if f.finishing then return end
    f.draggingSlider=nil
    if MPL.EndAppearanceAction then MPL.EndAppearanceAction() end
    if save then
        for _,pool in ipairs({f.rows,f.extras}) do
            for _,row in pairs(pool) do
                local input=row.hex or row.control
                if row.commit and input and input:HasFocus() and not row.commit(input) then return end
            end
        end
    end
    f.finishing=true; f.session=f.session+1
    if ColorPickerFrame and ColorPickerFrame.mplAppearanceOwner==f then
        ColorPickerFrame.mplAppearanceOwner=nil; ColorPickerFrame:Hide()
    end
    f.pendingColor=nil; hideChoices(f)
    if f.transfer then f.transfer:Hide() end
    if save then MPL.SaveAppearanceEdit() else MPL.CancelAppearanceEdit() end
    f:Hide(); f.finishing=false
end

function MPL.RefreshAppearanceFontList()
    MPL.RefreshAppearanceEditor()
end

function MPL.ShowAppearanceTransfer(importing,includeAliases)
    local f=MPL.appearanceEditor
    if not f or not f:IsShown() then return end
    local dialog=f.transfer
    if not dialog then
        dialog=MPL.CreateDialog("MPlusLogsAppearanceTransfer",L["Share appearance"],640,400)
        track("surfaces",dialog)
        track("labels",dialog.title,"title")
        dialog.closeButton:Hide()
        dialog:SetParent(f); dialog:SetFrameLevel(f:GetFrameLevel()+35)
        dialog.description=text(dialog,"",22,-52,590)
        dialog.description:SetWordWrap(true); dialog.description.editorAutoHeight=true
        dialog.scroll=CreateFrame("ScrollFrame",nil,dialog,"UIPanelScrollFrameTemplate")
        dialog.scroll:SetPoint("TOPLEFT",22,-90); dialog.scroll:SetPoint("BOTTOMRIGHT",-42,66)
        dialog.input=CreateFrame("EditBox",nil,dialog.scroll,"BackdropTemplate")
        track("inputs",dialog.input,"secondary")
        dialog.input.editorMultiline=true
        dialog.input:SetMultiLine(true); dialog.input:SetAutoFocus(false); dialog.input:SetFontObject("ChatFontNormal")
        dialog.input:SetWidth(560); dialog.input:SetMaxLetters(60000); dialog.input:SetTextInsets(6,6,6,6)
        dialog.input:SetHeight(220); dialog.scroll:SetScrollChild(dialog.input)
        dialog.input:SetScript("OnTextChanged",function(self)
            local height=self:GetStringHeight()
            self:SetHeight(math.max(220,type(height)=="number" and height+20 or 220))
        end)
        dialog.input:SetScript("OnEscapePressed",function() dialog.input:ClearFocus(); dialog:Hide() end)
        dialog.apply=button(dialog,L["Preview import"],22,-350,200,function()
            local ok,err=MPL.ImportAppearance(dialog.input:GetText())
            if report(ok,err) then dialog.input:ClearFocus(); dialog:Hide(); refresh(f) end
        end)
        dialog.close=button(dialog,L["Close"],434,-350,160,function() dialog.input:ClearFocus(); dialog:Hide() end)
        f.transfer=dialog
    end
    dialog.description:SetText(importing and L["Paste an appearance string. Import is previewed until you save the editor."]
        or L["Copy this appearance string with Ctrl+C."])
    dialog.apply:SetShown(importing)
    dialog.input:SetText(importing and "" or MPL.ExportAppearance(includeAliases))
    dialog:Show(); dialog.input:SetFocus(); dialog.input:HighlightText()
    if MPL.ApplyAppearanceToEditor then MPL.ApplyAppearanceToEditor(f) end
end

local function effectiveScale(frame)
    local scale=frame and frame:GetScale()
    return type(scale)=="number" and scale>0 and scale or 1
end
local function fitEditor(f)
    local width,height=UIParent:GetWidth(),UIParent:GetHeight()
    if type(width)~="number" or width<320 then width=1024 end
    if type(height)~="number" or height<320 then height=768 end
    f:SetScale(math.min(1,(width-24)/f:GetWidth(),(height-24)/f:GetHeight()))
    f:SetClampedToScreen(true)
end

local function themeColor(key,alpha)
    local c=value(key) or MPL.AppearanceDefaults and MPL.AppearanceDefaults[key] or {1,1,1,1}
    return c[1],c[2],c[3],(c[4] or 1)*(alpha or 1)
end
local function border(frame)
    local thickness=1
    if frame.editorBorderThickness~=thickness then
        frame:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Buttons/WHITE8X8",
            edgeSize=math.max(.01,thickness),insets={left=1,right=1,top=1,bottom=1}})
        frame.editorBorderThickness=thickness
    end
    if thickness==0 then frame:SetBackdropBorderColor(0,0,0,0)
    else frame:SetBackdropBorderColor(themeColor("borderColor")) end
end
paintButton=function(b)
    local enabled=b:IsEnabled()~=false
    local key=not enabled and "disabledColor" or (b.editorHovered and "hoverColor" or (b.editorSelected and "selectedColor" or "buttonColor"))
    border(b); b:SetBackdropColor(themeColor(key))
    if b.editorHovered then b:SetBackdropBorderColor(themeColor("accentColor")) end
    if b.caption then
        b.caption:SetTextColor(themeColor(enabled and "buttonTextColor" or "mutedColor"))
    end
    for _,stroke in ipairs(b.strokes or {}) do stroke:SetColorTexture(themeColor(enabled and "buttonTextColor" or "mutedColor")) end
    if b.selectionMark then b.selectionMark:SetColorTexture(themeColor("accentColor")) end
end
function MPL.ApplyAppearanceToEditor(f)
    f=f or MPL.appearanceEditor
    if f and f.draggingSlider then return end
    if not f or not f:IsShown() or f.editorPainting then return end
    f.editorPainting=true
    if f.extras.theme then updateStyleRow(f.extras.theme) end
    if f.extras.profile then updateProfileRow(f.extras.profile) end
    if f.extras.colorPalette then updatePaletteRow(f.extras.colorPalette) end
    fitEditor(f)
    local opacity=value("surfaceOpacity") or 1
    styleEditorFont(f.title,"title")
    local titleBand=math.max(36,(f.title.mplAppliedFontSize or 16)+16)
    border(f); f:SetBackdropColor(0,0,0,0)
    if not f.titleFill then
        f.titleFill=f:CreateTexture(nil,"BACKGROUND")
        f.appearanceBodyFill=f:CreateTexture(nil,"BACKGROUND")
    end
    -- These tiles do not overlap: semitransparent title and body keep the
    -- requested alpha, just like the disjoint profile-window backgrounds.
    f.titleFill:ClearAllPoints(); f.titleFill:SetPoint("TOPLEFT",1,-1)
    f.titleFill:SetSize(f:GetWidth()-2,titleBand-1)
    f.titleFill:SetColorTexture(themeColor("titleBackgroundColor",opacity))
    f.appearanceBodyFill:ClearAllPoints(); f.appearanceBodyFill:SetPoint("TOPLEFT",1,-titleBand)
    f.appearanceBodyFill:SetSize(f:GetWidth()-2,f:GetHeight()-titleBand-1)
    f.appearanceBodyFill:SetColorTexture(themeColor("backgroundColor",opacity))
    for _,label in ipairs(widgets.labels) do
        if not label.editorFontSample then styleEditorFont(label,label.editorFontRole or "secondary") end
        label:SetTextColor(themeColor(label.editorError and "warningTextColor" or "textColor"))
    end
    if f.transfer then
        f.transfer.scroll:SetPoint("TOPLEFT",22,-math.max(90,52+f.transfer.description:GetHeight()+12))
    end
    for _,b in ipairs(widgets.buttons) do
        styleEditorButton(b)
        b:SetHeight(math.max(b.editorBaseHeight or editorControlHeight,(b.caption.mplAppliedFontSize or editorFontSize)+12))
        paintButton(b)
    end
    for _,input in ipairs(widgets.inputs) do
        styleEditorFont(input,input.editorFontRole or "secondary")
        input:SetHeight(input.editorMultiline and math.max(220,(input:GetStringHeight() or 0)+20) or editorControlHeight)
        border(input); input:SetBackdropColor(themeColor("buttonColor"))
        input:SetTextColor(themeColor("textColor"))
    end
    for _,b in ipairs(widgets.checks) do
        border(b); b:SetBackdropColor(themeColor("buttonColor"))
        b.checkMark:SetVertexColor(themeColor(b:IsEnabled()==false and "disabledColor" or "accentColor"))
    end
    for _,slider in ipairs(widgets.sliders) do
        border(slider); slider:SetBackdropColor(themeColor("buttonColor"))
        if not slider.editorThumb then
            slider.editorThumb=slider:CreateTexture(nil,"OVERLAY")
            slider.editorThumb:SetSize(16,26); slider.editorThumb:SetTexture("Interface/Buttons/WHITE8X8")
            slider:SetThumbTexture(slider.editorThumb)
        end
        slider.editorThumb:SetVertexColor(themeColor("accentColor"))
    end
    if f.scrollThumb then
        border(f.scroll.ScrollBar)
        f.scroll.ScrollBar:SetBackdropColor(themeColor("buttonColor"))
        f.scrollThumb:SetVertexColor(themeColor("accentColor"))
    end
    for _,surface in ipairs(widgets.surfaces) do
        border(surface); surface:SetBackdropColor(themeColor("backgroundColor",opacity))
        surface:SetScale(1) -- child dialogs already inherit the editor's scale
    end
    for _,row in pairs(f.extras) do
        if row.editorPanelPadding then
            border(row); row:SetBackdropColor(themeColor("headerColor",opacity))
            row.panelAccent:SetColorTexture(themeColor("accentColor"))
        end
    end
    for _,key in ipairs({"theme","colorPalette"}) do
        local row=f.extras[key]
        if row and row.manage then
            row.manage.editorLayout.x=610-row.manage:GetWidth()
            row.control:SetWidth(row.manage.editorLayout.x-12)
        end
    end
    local spacing=extraSpacing()
    for _,key in ipairs({"profiles","styleLibrary","paletteLibrary"}) do
        local row=f.extras[key]
        if row and row.create then
            local x=0
            for _,b in ipairs({row.create,row.rename,row.delete}) do
                b.editorLayout.x=x; x=x+b:GetWidth()+12
            end
        end
    end
    for _,pool in pairs(widgets) do
        for _,widget in ipairs(pool) do
            local layout=widget.editorLayout
            if layout and layout.parent.editorExtra then
                local padding=layout.parent.editorPanelPadding or 0
                widget:ClearAllPoints(); widget:SetPoint("TOPLEFT",layout.x+padding,layout.y*spacing-padding)
            end
        end
    end
    for _,row in pairs(f.extras) do row:SetHeight(row.editorBaseHeight*spacing+2*(row.editorPanelPadding or 0)) end
    local sectionY=titleBand+12
    for _,section in ipairs(sections) do
        local b=f.sectionButtons[section.id]
        b:ClearAllPoints(); b:SetPoint("TOPLEFT",18,-sectionY)
        sectionY=sectionY+b:GetHeight()+6
    end
    local searchLabelTop=sectionY+12
    local searchTop=searchLabelTop+f.searchLabel:GetHeight()+6
    f.searchLabel:ClearAllPoints(); f.searchLabel:SetPoint("TOPLEFT",22,-searchLabelTop); f.searchLabel:SetWidth(216)
    f.search:ClearAllPoints(); f.search:SetPoint("TOPLEFT",22,-searchTop); f.search:SetWidth(216)
    f.previewInfo:ClearAllPoints(); f.previewInfo:SetPoint("TOPLEFT",22,-searchTop-f.search:GetHeight()-16)
    -- Font styling assigns a single-line height; let this sidebar explanation
    -- use its full wrapped height instead of clipping the remaining lines.
    f.previewInfo:SetWidth(216); f.previewInfo:SetWordWrap(true)
    f.previewInfo:SetNonSpaceWrap(false); f.previewInfo:SetJustifyV("TOP")
    f.previewInfo:SetHeight(0)
    f.scroll:SetPoint("TOPLEFT",260,-titleBand-12)
    local buttonHeight=editorControlHeight
    local statusTop=552+buttonHeight+12
    local saveTop=math.max(612,statusTop+f.status:GetHeight()+4)
    f:SetHeight(saveTop+buttonHeight+14)
    f.appearanceBodyFill:SetHeight(f:GetHeight()-titleBand-1)
    local x=262
    for _,b in ipairs({f.resetSection,f.resetAll,f.undo}) do
        b:ClearAllPoints(); b:SetPoint("TOPLEFT",x,-552)
        x=x+b:GetWidth()+12
    end
    f.status:ClearAllPoints(); f.status:SetPoint("TOPLEFT",262,-statusTop)
    local cancelX=f:GetWidth()-28-f.cancel:GetWidth()
    f.save:ClearAllPoints(); f.save:SetPoint("TOPLEFT",cancelX-12-f.save:GetWidth(),-saveTop)
    f.cancel:ClearAllPoints(); f.cancel:SetPoint("TOPLEFT",cancelX,-saveTop)
    f.scroll:SetPoint("BOTTOMRIGHT",-40,f:GetHeight()-536)
    -- Update displayed values and font samples without hiding/reflowing rows.
    f.updating=true
    for _,row in pairs(f.rows) do if row:IsShown() then updateRow(f,row) end end
    f.updating=false
    fitEditor(f)
    f.editorPainting=false
end
local function promote(frame)
    local callback=frame.GetScript and frame:GetScript("OnMouseDown")
    if callback then callback(frame) else frame:Raise() end
end
local function showPreview(f)
    if not MPL.ShowAppearancePreview then return end
    local preview=MPL.ShowAppearancePreview()
    if not preview then return end
    local screenWidth=UIParent:GetWidth()
    local screenHeight=UIParent:GetHeight()
    local editorWidth=f:GetWidth()*effectiveScale(f)
    local previewWidth=preview:GetWidth()*effectiveScale(preview)
    local sideBySide=type(screenWidth)=="number" and editorWidth+previewWidth+48<=screenWidth
    if sideBySide then
        f:ClearAllPoints(); f:SetPoint("LEFT",UIParent,"LEFT",16/effectiveScale(f),0)
        preview:ClearAllPoints(); preview:SetPoint("RIGHT",UIParent,"RIGHT",-16/effectiveScale(preview),0)
    else
        -- Keep the sample behind the editor on smaller screens.
        preview:ClearAllPoints(); preview:SetPoint("RIGHT",UIParent,"RIGHT",-12/effectiveScale(preview),0)
    end
    promote(f)
    if type(screenHeight)=="number" and screenHeight>320 then preview:SetClampedToScreen(true) end
    return preview
end

function MPL.OpenAppearanceSettings()
    if not MPL.BeginAppearanceEdit then return end
    local f=MPL.appearanceEditor
    if f and f:IsShown() then f:Raise(); return f end
    if InCombatLockdown and InCombatLockdown() and not f then
        status(L["Open appearance settings after combat."],true)
        if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage(L["Open appearance settings after combat."]) end
        return nil
    end
    if not f then
        f=MPL.CreateDialog("MPlusLogsAppearanceEditor",L["MPlusLogs — Appearance"],920,658)
        MPL.appearanceEditor=f; f.rows={}; f.extras={}; f.section="quick"; f.session=0
        track("labels",f.title,"title")
        f.title:ClearAllPoints(); f.title:SetPoint("TOPLEFT",20,-8)
        f.closeButton:Hide()
        f.closeButton=button(f,"",882,-6,28,function() finish(f,false) end)
        f.closeButton.editorBaseHeight=28
        f.closeButton.strokes={}
        for _,angle in ipairs({math.pi/4,-math.pi/4}) do
            local stroke=f.closeButton:CreateTexture(nil,"OVERLAY")
            stroke:SetSize(19,2); stroke:SetPoint("CENTER"); stroke:SetRotation(angle)
            f.closeButton.strokes[#f.closeButton.strokes+1]=stroke
        end
        f.search=edit(f,22,-360,166); f.search:SetMaxLetters(80)
        f.searchLabel=text(f,L["Search settings"],22,-339,166)
        f.search:SetScript("OnTextChanged",function() hideChoices(f); refresh(f) end)
        f.sectionButtons={}
        for i,section in ipairs(sections) do
            local id=section.id
            local b=button(f,translated(section.label),18,-48-(i-1)*46,220,function()
                f.section=id; f.search:SetText(""); hideChoices(f); refresh(f)
            end)
            b.editorBaseHeight=40; b:SetHeight(40); f.sectionButtons[id]=b
        end
        f.previewInfo=text(f,L["Changes appear immediately. No logs are downloaded."],22,-348,160)
        f.previewInfo:SetWordWrap(true)
        f.scroll=CreateFrame("ScrollFrame",nil,f)
        f.scroll:SetPoint("TOPLEFT",260,-48); f.scroll:SetPoint("BOTTOMRIGHT",-40,108)
        f.content=CreateFrame("Frame",nil,f.scroll); f.content:SetSize(618,1); f.scroll:SetScrollChild(f.content)
        setupEditorScroll(f)
        f.scroll:HookScript("OnScrollRangeChanged",function() updateScroll(f) end)
        f.scroll:HookScript("OnSizeChanged",function() updateScroll(f) end)
        f.empty=text(f.content,L["No matching settings."],0,0,530); f.empty:Hide()
        f.resetSection=button(f,L["Reset section"],208,-552,172,function()
            report(MPL.ResetAppearance(f.section=="quick" and nil or f.section)); refresh(f)
        end)
        f.resetAll=button(f,L["Reset theme"],390,-552,150,function() report(MPL.ResetAppearance()); refresh(f) end)
        f.undo=button(f,L["Undo"],550,-552,150,function() report(MPL.UndoAppearanceEdit()); refresh(f,true) end)
        f.status=text(f,"",208,-588,550); f.status:SetWordWrap(true)
        f.status.editorAutoHeight=true
        f.save=button(f,L["Save"],582,-612,100,function() finish(f,true) end)
        f.cancel=button(f,L["Cancel"],692,-612,100,function() finish(f,false) end)
        for _,b in ipairs({f.resetSection,f.resetAll,f.undo,f.save,f.cancel}) do b.editorMinWidth=b:GetWidth() end
        f.closeButton:SetScript("OnClick",function() finish(f,false) end)
        f:SetScript("OnHide",function() if not f.finishing then finish(f,false) end end)
    end
    MPL.BeginAppearanceEdit(); f.session=f.session+1; f.finishing=false
    fitEditor(f); f:Show(); status(""); refresh(f)
    if MPL.panel and type(MPL.panel.profile)=="table" then
        if MPL.appearancePreview then MPL.appearancePreview:Hide() end
        if not MPL.panel:IsShown() then
            MPL.panel:Show()
            if MPL.ApplyAppearanceToViews then MPL.ApplyAppearanceToViews() end
        end
        promote(f)
    else
        showPreview(f)
    end
    return f
end

function MPL.OpenProfileSettingsMenu(anchor)
    if MenuUtil and MenuUtil.CreateContextMenu then
        MenuUtil.CreateContextMenu(anchor,function(_,root)
            root:CreateButton(L["Appearance…"],function() MPL.OpenAppearanceSettings() end)
            root:CreateButton(L["General settings…"],function() MPL.OpenSettings() end)
        end)
        return
    end
    local menu=MPL.appearanceSettingsMenu
    if not menu then
        menu=CreateFrame("Frame",nil,UIParent,"BackdropTemplate")
        menu:SetSize(230,82); menu:SetFrameStrata("DIALOG"); menu:SetFrameLevel(400)
        menu:SetClampedToScreen(true)
        menu:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8",edgeFile="Interface/Tooltips/UI-Tooltip-Border",edgeSize=16})
        menu:SetBackdropColor(0.035,0.035,0.05,1); menu:EnableMouse(true)
        menu.appearance=button(menu,L["Appearance…"],12,-12,206,function() menu:Hide(); MPL.OpenAppearanceSettings() end)
        menu.general=button(menu,L["General settings…"],12,-44,206,function() menu:Hide(); MPL.OpenSettings() end)
        MPL.appearanceSettingsMenu=menu
    end
    if menu:IsShown() then menu:Hide(); return end
    menu:ClearAllPoints(); menu:SetPoint("TOPRIGHT",anchor,"BOTTOMRIGHT",0,-2); menu:Show()
end
