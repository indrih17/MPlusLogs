local _, MPL = ...

MPL.TUTORIAL_VERSION = 2

local WIDTH, CONTENT_X, CONTENT_WIDTH = 880, 222, 608
local pending, pendingResume, pendingStep, pendingSource = false, false, nil, nil
local render

local function saved()
    MPlusLogsDB = MPlusLogsDB or {}
    return MPlusLogsDB
end

local function copy() return MPL.GetTutorialCopy(MPL.locale) end

local function remember(f)
    local db = saved()
    db.tutorialProgressVersion = MPL.TUTORIAL_VERSION
    db.tutorialStepId = copy().steps[f.step].id
end

local function startingStep()
    local db = saved()
    if tonumber(db.tutorialProgressVersion) == MPL.TUTORIAL_VERSION then
        for i, step in ipairs(copy().steps) do
            if step.id == db.tutorialStepId then return i end
        end
    end
    return 1
end

local function text(parent, width, template, size)
    local field = parent:CreateFontString(nil, "OVERLAY", template or "GameFontHighlightLarge")
    field:SetWidth(width)
    field:SetJustifyH("LEFT")
    field:SetWordWrap(true)
    field:SetSpacing(3)
    local font, _, flags = field:GetFont()
    if font then field:SetFont(font, size or 16, flags) end
    return field
end

local function place(field, parent, x, y, value)
    field:ClearAllPoints()
    field:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y)
    field:SetHeight(0)
    field:SetText(value)
    local height = field:GetStringHeight()
    if type(height) ~= "number" or height <= 0 then
        local lines = 0
        for line in (value.."\n"):gmatch("(.-)\n") do
            lines = lines + math.max(1, math.ceil(#line / 66))
        end
        height = lines * 20
    end
    field:SetHeight(height + 2)
    return y + height + 2
end

local function button(parent, width, label, callback)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetSize(width, 28)
    b:SetText(label)
    b:SetNormalFontObject("GameFontNormalLarge")
    b:SetHighlightFontObject("GameFontHighlightLarge")
    b:SetScript("OnClick", callback)
    return b
end

function MPL.RefreshTutorialDisplays()
    local hidden = MPL.GetOption("hideTutorial")
    for _, frame in pairs({MPL.panel, MPL.downloadWindow}) do
        if frame.tutorialButton then frame.tutorialButton:SetShown(not hidden) end
    end
    local download = MPL.downloadWindow
    if download then download.setStatus(download.status:GetText(), download.statusIsError) end
    local guide = MPL.tutorialWindow
    if guide and guide.hidePreference ~= hidden then
        guide.hidePreference = hidden
        guide.hideOnFinish:SetChecked(hidden)
    end
end

function MPL.CreateTutorialHelpButton(parent, stepId, style)
    local b
    if style == "header" then
        b = CreateFrame("Button", nil, parent, "BackdropTemplate")
        b:SetSize(160, 22)
        b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8", edgeFile="Interface/Buttons/WHITE8X8", edgeSize=1})
        b:SetBackdropColor(0.16, 0.10, 0.21, 1)
        b:SetBackdropBorderColor(0.40, 0.29, 0.51, 1)
        b.caption = b:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        b.caption:SetPoint("CENTER")
        b.caption:SetWidth(160)
        b.caption:SetJustifyH("CENTER")
        b:SetFontString(b.caption)
        b.caption:SetText(copy().openGuide)
        b.caption:SetTextColor(1, 1, 1)
        b:SetText(copy().openGuide)
    elseif style == "icon" then
        b = button(parent, 24, "?", nil)
    else
        b = button(parent, 160, copy().openGuide, nil)
    end
    b:SetScript("OnClick", function()
        GameTooltip:Hide()
        local step = type(stepId) == "function" and stepId() or stepId
        MPL.ShowTutorial(step, parent)
    end)
    b:SetHeight(style == "icon" and 24 or 22)
    b:SetNormalFontObject(style == "icon" and "GameFontNormalLarge" or (style == "header" and "GameFontHighlight" or "GameFontNormal"))
    b:SetHighlightFontObject(style == "icon" and "GameFontHighlightLarge" or "GameFontHighlight")
    b:SetScript("OnEnter", function()
        if style == "header" then
            b:SetBackdropBorderColor(0.75, 0.55, 0.96, 1)
            b.caption:SetTextColor(1, 0.82, 0)
        end
        GameTooltip:SetOwner(b, "ANCHOR_BOTTOM")
        GameTooltip:ClearLines()
        GameTooltip:AddLine(copy().openGuide, 1, 0.82, 0)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", function()
        if style == "header" then
            b:SetBackdropBorderColor(0.40, 0.29, 0.51, 1)
            b.caption:SetTextColor(1, 1, 1)
        end
        GameTooltip:Hide()
    end)
    b:SetShown(not MPL.GetOption("hideTutorial"))
    return b
end

function MPL.TutorialCoversWindow(source)
    local f = MPL.tutorialWindow
    return f ~= nil and f.sourceWindow == source and (f:IsShown() or f.suspendedFor ~= nil)
end

local function restoreSourceFocus(f)
    local source, revision = f.sourceWindow, f.sourceRevision
    f.sourceWindow, f.sourceRevision = nil, nil
    if source and revision and source:IsShown() and source.revision == revision
        and (source.phase == "copy" or source.phase == "waiting")
        and type(source.focusInput) == "function" then source.focusInput() end
end

local function scrollArea(parent, x, right, width)
    local scroll = CreateFrame("ScrollFrame", nil, parent, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -88)
    scroll:SetPoint("BOTTOMRIGHT", parent, "BOTTOMRIGHT", -right, 88)
    local content = CreateFrame("Frame", nil, scroll)
    content:SetSize(width, 1)
    scroll:SetScrollChild(content)
    scroll:EnableMouseWheel(true)
    scroll:SetScript("OnMouseWheel", function(self, delta)
        local maximum = math.max(0, content:GetHeight() - self:GetHeight())
        self:SetVerticalScroll(math.max(0, math.min(maximum, self:GetVerticalScroll() - delta*48)))
    end)
    return scroll, content
end

local function setScrollRange(scroll, content, height, reset)
    scroll:SetHeight(height)
    local maximum = math.max(0, content:GetHeight() - height)
    local position = reset and 0 or scroll:GetVerticalScroll()
    scroll:SetVerticalScroll(math.max(0, math.min(maximum, position)))
    if scroll.ScrollBar then scroll.ScrollBar:SetShown(maximum > 0) end
end

local function updateScrollHint(f)
    local height = f.scroll:GetHeight()
    local overflow = f.content:GetHeight() > height+1
    f.scrollHint:SetShown(overflow and f.scroll:GetVerticalScroll() <= 0.5)
    if f.scrollThumb then
        f.scrollThumb:SetHeight(math.max(32, math.min(120,
            math.max(1, height-32)*height/math.max(1, height, f.content:GetHeight()))))
    end
end

local function addScrollIndicators(f)
    local bar = f.scroll.ScrollBar
    if bar then
        bar:SetWidth(20)
        local border = bar:CreateTexture(nil, "BACKGROUND")
        border:SetAllPoints()
        border:SetColorTexture(0.38, 0.30, 0.12, 1)
        local track = bar:CreateTexture(nil, "BORDER")
        track:SetPoint("TOPLEFT", 2, -2)
        track:SetPoint("BOTTOMRIGHT", -2, 2)
        track:SetColorTexture(0.10, 0.09, 0.06, 1)
        local thumb = bar:CreateTexture(nil, "ARTWORK")
        thumb:SetTexture("Interface/Buttons/WHITE8X8")
        thumb:SetVertexColor(0.95, 0.73, 0.24, 1)
        thumb:SetSize(16, 52)
        bar:SetThumbTexture(thumb)
        f.scrollThumb = thumb
    end
    -- Draw the chevrons with textures: their appearance does not depend on
    -- whether the client font contains a particular arrow character.
    f.scrollHint = CreateFrame("Frame", nil, f)
    f.scrollHint:SetSize(CONTENT_WIDTH, 28)
    f.scrollHint:SetPoint("TOPLEFT", f.scroll, "BOTTOMLEFT", 0, -4)
    for row = 0, 1 do
        for side = -1, 1, 2 do
            local stroke = f.scrollHint:CreateTexture(nil, "OVERLAY")
            stroke:SetTexture("Interface/Buttons/WHITE8X8")
            stroke:SetVertexColor(1, 0.82, 0.22, 1)
            stroke:SetSize(16, 3)
            stroke:SetPoint("CENTER", f.scrollHint, "CENTER", side*5, 5-row*8)
            stroke:SetRotation(side*math.pi/4)
        end
    end
    f.scroll:HookScript("OnVerticalScroll", function() updateScrollHint(f) end)
    f.scroll:HookScript("OnScrollRangeChanged", function() updateScrollHint(f) end)
    f.scroll:HookScript("OnSizeChanged", function() updateScrollHint(f) end)
end

local function goTo(f, step)
    f.step = math.max(1, math.min(#copy().steps, step))
    remember(f)
    render(f)
end

function MPL.TutorialCompleted()
    local f = MPL.tutorialWindow
    if f then MPL.SetOption("hideTutorial", f.hideOnFinish:GetChecked() == true) end
    local db = saved()
    db.tutorialCompletedVersion = MPL.TUTORIAL_VERSION
    db.tutorialStepId, db.tutorialProgressVersion = nil, nil
    pending, pendingResume, pendingStep, pendingSource = false, false, nil, nil
    if f then
        f.finishing = true
        f.suspendedFor = nil
        f:Hide()
        f.finishing = false
        restoreSourceFocus(f)
    end
end

local function suspendFor(f, other)
    if not other or not other:IsShown() then return end
    if not f.resumeHooks[other] then
        other:HookScript("OnHide", function()
            if f.suspendedFor ~= other then return end
            if InCombatLockdown() then pendingResume = true; return end
            f.suspendedFor = nil
            render(f)
            f:Show()
        end)
        f.resumeHooks[other] = true
    end
    f.suspendedFor = other
    f:Hide()
end

local function createWindow()
    local c = copy()
    local f = MPL.CreateDialog("MPlusLogsTutorialWindow", c.title, WIDTH, 720)
    f.step, f.finishing, f.resumeHooks = 1, false, {}
    f.contents = text(f, 174, "GameFontNormalLarge")
    place(f.contents, f, 24, 52, c.contents)
    f.progress = text(f, CONTENT_WIDTH, "GameFontNormalLarge")
    f.sidebar, f.sidebarContent = scrollArea(f, 24, WIDTH-198, 174)
    f.scroll, f.content = scrollArea(f, CONTENT_X, 50, CONTENT_WIDTH)
    addScrollIndicators(f)
    f.stepButtons = {}
    for i, step in ipairs(c.steps) do
        local index = i
        local b = CreateFrame("Button", nil, f.sidebarContent, "BackdropTemplate")
        b:SetSize(174, 44)
        b:SetPoint("TOPLEFT", f.sidebarContent, "TOPLEFT", 0, -(i-1)*50)
        b:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8"})
        b.caption = text(b, 158, "GameFontHighlight", 14)
        b.caption:SetPoint("LEFT", b, "LEFT", 8, 0)
        b.caption:SetText(i..". "..step.shortTitle)
        b:SetScript("OnClick", function() goTo(f, index) end)
        f.stepButtons[i] = b
    end
    f.sidebarContent:SetHeight(#c.steps*50-6)
    f.heading = text(f.content, CONTENT_WIDTH, "GameFontNormalLarge", 20)
    f.body = text(f.content, CONTENT_WIDTH)
    f.locationCard = CreateFrame("Frame", nil, f.content, "BackdropTemplate")
    f.locationCard:SetWidth(CONTENT_WIDTH)
    f.locationCard:SetBackdrop({bgFile="Interface/Buttons/WHITE8X8", edgeFile="Interface/Buttons/WHITE8X8", edgeSize=1})
    f.locationCard:SetBackdropColor(0.055, 0.075, 0.10, 1)
    f.locationCard:SetBackdropBorderColor(0.20, 0.27, 0.34, 1)
    local accent = f.locationCard:CreateTexture(nil, "ARTWORK")
    accent:SetPoint("TOPLEFT", 0, 0)
    accent:SetPoint("BOTTOMLEFT", 0, 0)
    accent:SetWidth(3)
    accent:SetColorTexture(0.80, 0.62, 0.22, 1)
    f.locationLabel = text(f.locationCard, CONTENT_WIDTH-32, "GameFontNormalLarge")
    f.location = text(f.locationCard, CONTENT_WIDTH-32)
    f.instructionLabel = text(f.content, CONTENT_WIDTH, "GameFontNormalLarge")
    f.instructions = {}
    f.resultLabel = text(f.content, CONTENT_WIDTH, "GameFontNormalLarge")
    f.result = text(f.content, CONTENT_WIDTH)
    f.pitfallLabel = text(f.content, CONTENT_WIDTH, "GameFontNormalLarge")
    f.pitfall = text(f.content, CONTENT_WIDTH)
    f.title:SetWidth(360)
    f.reopen = text(f, 420, "GameFontHighlight", 14)
    f.reopen:SetJustifyH("RIGHT")
    f.reopen:SetPoint("TOPRIGHT", f, "TOPRIGHT", -44, -16)
    f.reopen:SetText(c.reopen)
    f.back = button(f, 110, c.back, function() goTo(f, f.step-1) end)
    f.back:SetPoint("BOTTOMLEFT", CONTENT_X, 20)
    f.later = button(f, 174, c.later, function() f:Hide() end)
    f.later:SetPoint("BOTTOMLEFT", 24, 20)
    f.next = button(f, 130, c.next, function()
        if f.step == #copy().steps then MPL.TutorialCompleted()
        else goTo(f, f.step+1) end
    end)
    f.next:SetPoint("BOTTOMRIGHT", -28, 20)
    f.action = button(f, 300, "", function()
        if InCombatLockdown() then return end
        local action = copy().steps[f.step].action
        if action == "download" and MPL.ShowCompanionDownload then
            MPL.ShowCompanionDownload()
            suspendFor(f, MPL.copy)
        elseif action == "settings" and MPL.OpenSettings then
            MPL.OpenSettings()
            suspendFor(f, SettingsPanel)
        end
    end)
    f.action:SetPoint("BOTTOMLEFT", CONTENT_X+122, 20)
    f.hideOnFinish = CreateFrame("CheckButton", nil, f, "UICheckButtonTemplate")
    f.hideOnFinish:SetSize(26, 26)
    f.hideOnFinish:SetPoint("BOTTOMLEFT", CONTENT_X, 62)
    f.hideOnFinish.caption = text(f.hideOnFinish, CONTENT_WIDTH-34, "GameFontHighlight", 14)
    f.hideOnFinish.caption:SetText(c.hideAfterFinish)
    f.hideOnFinish.caption:SetPoint("LEFT", f.hideOnFinish, "RIGHT", 4, 0)
    f.hideOnFinish.caption:SetHeight(40)
    f.hideOnFinish:SetHitRectInsets(0, -CONTENT_WIDTH+26, -7, -7)
    f:SetScript("OnHide", function()
        if f.suspendedFor then return end
        restoreSourceFocus(f)
        if f.finishing then return end
        remember(f)
        pending, pendingResume, pendingStep, pendingSource = false, false, nil, nil
        saved().tutorialDismissedVersion = MPL.TUTORIAL_VERSION
    end)
    MPL.tutorialWindow = f
    return f
end

local function renderLocationCard(f, step, c)
    local y = place(f.locationLabel, f.locationCard, 16, 14, c.locationLabel) + 8
    y = place(f.location, f.locationCard, 16, y, step.location) + 14
    f.locationCard:SetHeight(y)
    return y
end

render = function(f)
    local c = copy()
    local step = c.steps[f.step]
    local changed = f.renderedStep ~= f.step
    place(f.progress, f, CONTENT_X, 52, string.format(c.progress, f.step, #c.steps))
    for i, b in ipairs(f.stepButtons) do
        local selected = i == f.step
        b:SetBackdropColor(selected and 0.22 or 0.075, selected and 0.15 or 0.075, selected and 0.30 or 0.095, 1)
        b.caption:SetTextColor(selected and 1 or 0.85, selected and 0.82 or 0.85, selected and 0.30 or 0.85)
    end
    local y = place(f.heading, f.content, 0, 0, step.title) + 16
    y = place(f.body, f.content, 0, y, step.intro) + 18
    f.locationCard:ClearAllPoints()
    f.locationCard:SetPoint("TOPLEFT", f.content, "TOPLEFT", 0, -y)
    y = y + renderLocationCard(f, step, c) + 22
    y = place(f.instructionLabel, f.content, 0, y, c.actionLabel) + 10
    for i, instruction in ipairs(step.instructions) do
        if not f.instructions[i] then f.instructions[i] = text(f.content, CONTENT_WIDTH) end
        f.instructions[i]:Show()
        y = place(f.instructions[i], f.content, 0, y, i..". "..instruction) + 10
    end
    for i = #step.instructions+1, #f.instructions do f.instructions[i]:Hide() end
    y = place(f.resultLabel, f.content, 0, y+4, c.resultLabel) + 8
    y = place(f.result, f.content, 0, y, step.result) + 18
    y = place(f.pitfallLabel, f.content, 0, y, c.pitfallLabel) + 8
    y = place(f.pitfall, f.content, 0, y, step.pitfall) + 18
    f.action:SetShown(step.action ~= nil)
    if step.action then
        f.action:SetText(step.action == "download" and c.download or c.settings)
    end
    f.content:SetHeight(y)
    f.back:SetEnabled(f.step > 1)
    f.next:SetText(f.step == #c.steps and c.finish or c.next)
    local finalStep = f.step == #c.steps
    f.hideOnFinish:SetShown(finalStep)
    local footerSpace = finalStep and 48 or 0
    f.scroll:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -50, 88+footerSpace)
    local screenWidth, screenHeight = UIParent:GetWidth(), UIParent:GetHeight()
    local scale = math.max(0.1, math.min(1, (screenWidth-32)/WIDTH))
    f:SetScale(scale)
    f:SetHeight(math.min(720, math.max(260, (screenHeight-48)/scale)))
    local viewport = math.max(1, f:GetHeight()-176)
    setScrollRange(f.scroll, f.content, math.max(1, viewport-footerSpace), changed)
    updateScrollHint(f)
    setScrollRange(f.sidebar, f.sidebarContent, viewport, false)
    local top, bottom = (f.step-1)*50, (f.step-1)*50+44
    local position = f.sidebar:GetVerticalScroll()
    if top < position then f.sidebar:SetVerticalScroll(top)
    elseif bottom > position+viewport then f.sidebar:SetVerticalScroll(bottom-viewport) end
    f.renderedStep = f.step
end

function MPL.ShowTutorial(stepId, source)
    if InCombatLockdown() then
        -- A newer click supersedes a suspended chapter awaiting combat end.
        pendingResume = false
        local f = MPL.tutorialWindow
        if f then f.suspendedFor = nil end
        pending, pendingStep, pendingSource = true, stepId, source
        return false
    end
    local f = MPL.tutorialWindow or createWindow()
    f.hidePreference = MPL.GetOption("hideTutorial")
    f.hideOnFinish:SetChecked(f.hidePreference)
    f.step, f.renderedStep, f.finishing, f.suspendedFor = startingStep(), nil, false, nil
    for i, step in ipairs(copy().steps) do
        if step.id == stepId then f.step = i; break end
    end
    f.sourceWindow = source
    f.sourceRevision = source and type(source.revision) == "number" and source.revision or nil
    if f.sourceRevision and source.edit then source.edit:ClearFocus() end
    pendingResume = false
    remember(f)
    render(f)
    pending, pendingStep, pendingSource = false, nil, nil
    f:Show()
    return true
end

function MPL.ShowTutorialFromSettings()
    -- Cancel a suspended guide before closing Settings, so its OnHide hook
    -- cannot reopen it ahead of the explicit manual request (also in combat).
    local f = MPL.tutorialWindow
    local source = f and f.sourceWindow
    if source and not source:IsShown() then source = nil end
    if f then f.suspendedFor = nil end
    pendingResume = false
    if SettingsPanel and SettingsPanel:IsShown() then SettingsPanel:Hide() end
    return MPL.ShowTutorial(nil, source)
end

function MPL.TryPendingTutorial()
    if pendingResume then
        if InCombatLockdown() then return false end
        pendingResume = false
        local f = MPL.tutorialWindow
        if f and f.suspendedFor then f.suspendedFor = nil; render(f); f:Show(); return true end
    end
    if not pending then return false end
    if InCombatLockdown() then return false end
    local step, source = pendingStep, pendingSource
    pending, pendingStep, pendingSource = false, nil, nil
    if source and not source:IsShown() then return false end
    return MPL.ShowTutorial(step, source)
end
