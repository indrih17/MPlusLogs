local _,MPL=...
local L=MPL.L
local sequence=0
local function safe(value) return not (issecretvalue and issecretvalue(value)) end
local function enc(s) return tostring(s or ""):gsub("([^A-Za-z0-9%-%._~])",function(c) return string.format("%%%02X",c:byte()) end) end
local function dec(s) return s:gsub("%%(%x%x)",function(h) return string.char(tonumber(h,16)) end) end
local function fields(line)
    local result={}; for value in (line.."\t"):gmatch("(.-)\t") do result[#result+1]=dec(value) end
    return result
end
local function fullIdentity(full)
    if not MPL.SafeString(full) then return end
    local name,realm=full:match("^([^%-]+)%-(.+)$")
    return name or full,realm
end

function MPL.CollectSearchGroup(resultID)
    if InCombatLockdown() or not C_LFGList.GetSearchResultPlayerInfo then return end
    local info=C_LFGList.GetSearchResultInfo(resultID)
    if type(info)~="table" or not safe(info) or not safe(info.numMembers)
        or type(info.numMembers)~="number" or info.numMembers<1 or info.numMembers>5 then return end
    local players,signature={},{}
    local leaderName,leaderRealm=fullIdentity(info.leaderName)
    for i=1,info.numMembers do
        local member=C_LFGList.GetSearchResultPlayerInfo(resultID,i)
        if type(member)~="table" or not safe(member) or not safe(member.isLeader)
            or not MPL.SafeString(member.classFilename) or not MPL.SafeString(member.assignedRole)
            or not ({TANK=true,HEALER=true,DAMAGER=true})[member.assignedRole] then return end
        local name,realm=fullIdentity(member.name)
        if member.isLeader and leaderName then name,realm=leaderName,leaderRealm end
        if not name then return end
        local specID
        if MPL.SafeString(member.specName) then
            for id,spec in pairs(MPL.specInfo) do
                if spec[3]==member.classFilename and MPL.SpecLabel(spec[1],spec[3])==member.specName then specID=id; break end
            end
        end
        players[#players+1]={name=name,realm=realm,class=member.classFilename,role=member.assignedRole,
            rosterRealm=realm or false,
            specID=specID,region=MPL.Region(),origin=realm and "known" or "search",
            minLevel=GetMaxLevelForPlayerExpansion and GetMaxLevelForPlayerExpansion() or nil}
        signature[#signature+1]=enc(name)..":"..enc(realm)..":"..member.classFilename..":"..member.assignedRole
    end
    return players,table.concat(signature,";")
end

local function button(parent,x,y,width,text,fn)
    local b=CreateFrame("Button",nil,parent,"UIPanelButtonTemplate")
    b:SetSize(width,24); b:SetPoint("TOPLEFT",x,y); b:SetText(text); b:SetScript("OnClick",fn)
    return b
end
local function current(f)
    local _,signature=MPL.CollectSearchGroup(f.resultID)
    return signature and signature==f.signature
end

local function usable(player)
    if not player.realm then return false end
    local profile=MPL.GetProfile(player.name,player.realm,"All specs",player.role)
    local state=MPL.GetProfileState(player.name,player.realm,"All specs")
    return profile and not state and not MPL.IsProfileStale(profile)
end

local function mergeRoster(f,players,signature)
    local selected=f.players and f.players[f.selected]
    for i,new in ipairs(players) do
        for _,old in ipairs(f.players or {}) do
            if MPL.Normalize(old.name)==MPL.Normalize(new.name) and old.class==new.class
                and old.region==new.region
                and not (f.requestID and new.rosterRealm and not old.rosterRealm)
                and (not new.rosterRealm or not old.realm or MPL.Normalize(old.realm)==MPL.Normalize(new.rosterRealm))
                and (not old.rosterRealm or not new.rosterRealm or MPL.Normalize(old.rosterRealm)==MPL.Normalize(new.rosterRealm)) then
                if old.role~=new.role then old.loaded=nil; old.error=nil; old.specID=new.specID
                else old.specID=new.specID or old.specID end
                old.role=new.role
                old.departed=nil
                if new.rosterRealm then old.realm=new.realm; old.rosterRealm=new.rosterRealm; old.origin="known" end
                players[i]=old; break
            end
        end
        local p=players[i]
        p.searchResultID=f.resultID
        if p.realm then MPL.RecordApplicant(p.name.."-"..p.realm,p.role,p.specID,p.class) end
        if not p.loaded and usable(p) then p.loaded=true end
    end
    f.players=players; f.signature=signature; f.selected=1
    for i,p in ipairs(players) do if p==selected then f.selected=i; return end end
    -- Keep viewing a departing member's logs until the user chooses another tab.
    if selected then players[#players+1]=selected; selected.departed=true; f.selected=#players end
end

function MPL.UpdateSearchGroupRoster(resultID)
    local f=MPL.searchGroupWindow
    if not f or f.resultID~=resultID or InCombatLockdown() then return false end
    local players,signature=MPL.CollectSearchGroup(resultID)
    if not players then return true end
    local changed=signature~=f.signature
    local selected=f.players[f.selected]
    local specID,role=selected and selected.specID,selected and selected.role
    mergeRoster(f,players,signature)
    if changed then f.onlyMissing=true end
    local panel=MPL.panel
    if panel and panel:IsShown() and type(panel.searchMember)=="table"
        and panel.searchMember.searchResultID==resultID then
        panel.searchPlayers=f.players
        if selected==f.players[f.selected] and (specID~=selected.specID or role~=selected.role) then
            MPL.OpenSearchGroupProfile(f.selected,true)
        else MPL.RenderPlayerTabs(panel) end
    end
    return true
end

function MPL.SearchGroupHasPendingProfiles(resultID)
    local f=MPL.searchGroupWindow
    if not f or f.resultID~=resultID then return false end
    for _,p in ipairs(f.players) do
        if not p.departed and not usable(p) then return true end
    end
    return false
end

function MPL.OpenSearchGroupProfile(index,preserveView)
    local f=MPL.searchGroupWindow
    local p=f and f.players[index or f.selected]
    if not p then return end
    local previous=MPL.panel
    local metric=preserveView and previous and previous.searchMember==p and previous.viewMetric
    local scroll=metric and previous.scroll:GetVerticalScroll()
    -- Viewing a completed snapshot must not depend on a live LFG listing.
    -- New requests can refresh the roster; replies belong to their snapshot.
    f.selected=index or f.selected
    local members,resolved={},{}
    for _,member in ipairs(f.players) do
        member.searchResultID=f.resultID
        members[#members+1]=member
        if member.loaded then resolved[#resolved+1]=member end
    end
    MPL.ShowProfile(p.name,p.realm or GetNormalizedRealmName(),nil,true,nil,not p.loaded)
    local panel=MPL.panel
    panel.partyTracked=false
    panel.searchMember=p
    if not p.loaded then
        -- The fallback realm is only used to initialize the shared panel.
        -- Never display cached logs or submit an ordinary request for it.
        panel.profile=false; panel.class=p.class
        panel.character:SetText(p.name.." — "..(p.realm or L["Realm unknown"]))
        panel.lookup:SetText(p.realm and p.name.."-"..p.realm:gsub(" ","") or p.name)
        panel.scroll:Hide(); panel.emptyMessage:Show()
        panel.emptyMessage:ClearAllPoints(); panel.emptyMessage:SetPoint("TOPLEFT",80,-200)
        panel.emptyMessage:SetText(p.error or (p.candidates and L["Choose the character's realm"] or L["Load logs to identify this character"]))
        panel.emptyMessage:SetHeight(100)
        panel.source:SetText(""); panel.note:SetText(""); panel.footer:SetText("")
        panel.specButton:Hide(); panel.currentSpec:Hide()
        panel.loadButton:ClearAllPoints(); panel.loadButton:SetPoint("BOTTOMLEFT",730,53)
        panel.loadButton:SetSize(170,24); panel.loadButton:SetText(L["Load group logs"])
        MPL.RenderProfileStats(panel)
    end
    panel.searchChoices=type(panel.searchChoices)=="table" and panel.searchChoices or {}
    for _,b in ipairs(panel.searchChoices) do b:Hide() end
    for i,c in ipairs(p.candidates or {}) do
        local b=panel.searchChoices[i]
        if not b then
            b=button(panel,100,-330-(i-1)*28,720,"")
            panel.searchChoices[i]=b
        end
        -- Rebind the member when reusing a choice button for another tab.
        b:SetScript("OnClick",function()
            p.realm=c.realm; p.candidates=nil; p.error=nil
            MPL.ShowSearchGroupLogs(f.resultID)
        end)
        b:SetText(c.name.." — "..c.realm); b:Show()
    end
    MPL.panel.groupPlayers=resolved; MPL.panel.searchPlayers=members
    MPL.RenderPlayerTabs(MPL.panel)
    if metric then
        panel.viewMetric=metric; MPL.RenderProfileStats(panel)
        if type(scroll)=="number" then panel.scroll:SetVerticalScroll(scroll) end
    end
end

function MPL.BeginSearchGroupRequest()
    local f=MPL.searchGroupWindow
    if not f then return end
    if not current(f) then
        local players,signature=MPL.CollectSearchGroup(f.resultID)
        if players then mergeRoster(f,players,signature); f.onlyMissing=true end
    end
    sequence=sequence+1
    local id=tostring(GetServerTime()).."-"..sequence
    local rows={"MPLN1"}
    local levelSearch=false
    f.requestPlayers={}; f.requestTargets={}
    for _,p in ipairs(f.players) do
        if not p.departed and (not f.onlyMissing or not usable(p)) then
            local copy={}; for key,value in pairs(p) do copy[key]=value end
            f.requestPlayers[#f.requestPlayers+1]=copy
            f.requestTargets[#f.requestTargets+1]=p
        end
    end
    for i,p in ipairs(f.requestPlayers) do
        local row={"N",i,enc(p.region),enc(p.realm),enc(p.name),enc(p.class),enc(p.role),p.origin}
        if type(p.minLevel)=="number" and p.minLevel>0 then row[#row+1]=p.minLevel; levelSearch=true end
        rows[#rows+1]=table.concat(row,"\t")
    end
    f.requestID=id
    -- Legacy Companions recognize MPLQ2 and can return an explicit capability
    -- upgrade error instead of silently ignoring an unfamiliar request header.
    f.request="MPLS2\n"..id.."\nMPLC1 namesearch,nameerrors"..(levelSearch and ",levelsearch" or "")
        ..(MPL.CompanionSupports("errorcodes") and ",errorcodes" or "").."\nMPLQ2\n"..table.concat(rows,"\n").."\n"
    return id,f.request
end

function MPL.ReceiveSearchGroupReply(text)
    local f=MPL.searchGroupWindow
    if not f or not f.requestID then return nil,L["Это ответ на другой запрос"] end
    -- Validate the response against the requested players and request ID below.
    -- LFG changes during network work do not invalidate those characters' logs.
    if #text>1600000 then return nil,L["Invalid group search reply"] end
    text=text:gsub("\r\n","\n")
    local kind,id,body=text:match("^(%w+)\n([^\n]+)\n(.*)")
    if id~=f.requestID then return nil,L["Это ответ на другой запрос"] end
    if kind=="MPLE1" then
        local message=dec(body)
        return nil,message:match("^MPLERR1 ") and message or MPL.T(message)
    end
    if kind~="MPLS1" then return nil,L["Invalid group search reply"] end
    local version,capabilities,payload=body:match("^MPLV1 (%d+%.%d+%.%d+) ([a-z,]+)\n(.*)")
    if version then
        local available={}
        for capability in capabilities:gmatch("[a-z]+") do available[capability]=true end
        MPL.companionInfo={version=version,capabilities=available}
        body=payload
    end
    if not body:match("^MPLB1\n") then return nil,L["Invalid group search reply"] end
    body=dec(body:sub(7))
    if #body>500000 or not body:match("^MPLN2\n") or body:sub(-1)~="\n" then return nil,L["Invalid group search reply"] end
    local staged,profiles={},{}
    for line in body:sub(7):gmatch("([^\n]+)\n") do
        local row=fields(line)
        local index=tonumber(row[2]); local p=index and f.requestPlayers[index]
        if not p or index%1~=0 then return nil,L["Invalid group search reply"] end
        if row[1]=="F" and #row==3 and #row[3]<=400 and not staged[index] then
            local message,code,retry=MPL.DecodeCompanionError(row[3])
            staged[index]={error=MPL.CompanionError((message:gsub("[|%z]","")),code,retry)}
        elseif ((row[1]=="P" or row[1]=="F") and #row==7) or (row[1]=="C" and #row==6) then
            if row[3]~=p.region or MPL.Normalize(row[5])~=MPL.Normalize(p.name) or row[6]~=p.class or not MPL.SafeString(row[4])
                or #row[4]>200 or row[4]:find("[|%c]")
                or (p.realm and MPL.Normalize(p.realm)~=MPL.Normalize(row[4])) then return nil,L["Invalid group search reply"] end
            if row[1]=="F" then
                if staged[index] or #row[7]>400 then return nil,L["Invalid group search reply"] end
                local message,code,retry=MPL.DecodeCompanionError(row[7])
                staged[index]={realm=row[4],error=MPL.CompanionError((message:gsub("[|%z]","")),code,retry)}
            elseif row[1]=="C" then
                if staged[index] and not staged[index].candidates then return nil,L["Invalid group search reply"] end
                staged[index]=staged[index] or {candidates={}}
                local list=staged[index].candidates
                if #list>=6 then return nil,L["Invalid group search reply"] end
                list[#list+1]={realm=row[4],name=row[5],class=row[6]}
            else
                if staged[index] then return nil,L["Invalid group search reply"] end
                local parsed=MPL.Parse(row[7]); local count,profile=0
                if not parsed then return nil,L["Invalid group search reply"] end
                for _,value in pairs(parsed) do count=count+1; profile=value end
                if count~=1 or profile.name~=row[5] or profile.region~=p.region or profile.realm~=row[4]
                    or profile.role~=p.role or profile.spec~="All specs" then return nil,L["Invalid group search reply"] end
                staged[index]={realm=row[4],loaded=true}
                profile.realmInferred=p.origin=="search"
                profiles[MPL.Key(profile.name,profile.realm,profile.region)]=profile
            end
        else return nil,L["Invalid group search reply"] end
    end
    for i in ipairs(f.requestPlayers) do if not staged[i] then return nil,L["Invalid group search reply"] end end
    local count=MPL.StoreProfiles(profiles)
    MPlusLogsDB.companionReplySeen=true
    for i,result in ipairs(staged) do
        local p=f.requestTargets[i]
        p.error=result.error; p.candidates=result.candidates
        p.loaded=result.loaded and p.role==f.requestPlayers[i].role
        if result.realm then
            p.realm=result.realm
            MPL.RecordApplicant(p.name.."-"..p.realm,p.role,p.specID,p.class)
            -- This request imports the aggregate profile only. Open that new
            -- data rather than a manually selected, older specialization.
            MPL.SelectSpec(p.name,p.realm,"All specs",p.role)
        end
    end
    f.requestID=nil; f.requestPlayers=nil; f.requestTargets=nil
    -- Receiving logs completes the exchange: show the actual profile table,
    -- retaining failed/ambiguous members as tabs instead of a second success screen.
    local selected=f.selected
    local panel=MPL.panel
    local keepSelection=panel and type(panel.searchMember)=="table" and panel.searchMember==f.players[selected]
    if not keepSelection and not f.players[selected].loaded then
        selected=nil
        for i,player in ipairs(f.players) do if player.loaded then selected=i; break end end
    end
    MPL.OpenSearchGroupProfile(selected or f.selected,keepSelection)
    return count
end

function MPL.ShowSearchGroup(resultID)
    local players,signature=MPL.CollectSearchGroup(resultID)
    if not players then print(L["Group member data is unavailable; try again shortly"]); return end
    local f=MPL.searchGroupWindow
    if not f then
        -- Roster/request state only; all visible UI belongs to the shared panel
        -- and the standard clipboard exchange dialog.
        f={}
        MPL.searchGroupWindow=f
    end
    if f.resultID~=resultID then
        f.players=nil; f.selected=1; f.requestID=nil; f.onlyMissing=false
        f.resultID=resultID; mergeRoster(f,players,signature)
    elseif f.signature~=signature then mergeRoster(f,players,signature); f.onlyMissing=true end
end

function MPL.ShowSearchGroupLogs(resultID)
    local players=MPL.CollectSearchGroup(resultID)
    if not players then print(L["Group member data is unavailable; try again shortly"]); return end
    MPL.ShowSearchGroup(resultID)
    local f=MPL.searchGroupWindow
    local fresh=true
    for _,player in ipairs(f.players) do
        if not player.departed and (not player.loaded or not usable(player)) then fresh=false; break end
    end
    if fresh then
        if MPL.downloadWindow then MPL.downloadWindow:Hide() end
        MPL.OpenSearchGroupProfile(f.selected)
        return
    end
    local first=players[1]
    -- The fallback realm only labels the exchange window. Requests are built
    -- from the roster and retain empty realms until Companion resolves them.
    MPL.ShowDownload(first.name,first.realm or GetNormalizedRealmName(),nil,nil,nil,nil,resultID)
end
