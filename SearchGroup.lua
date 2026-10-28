local _,MPL=...
local L=MPL.L
local sequence=0
-- Realm resolutions belong to an exact roster, not Blizzard's temporary
-- listing ID. Keep a small session cache without guessing from names alone.
local rosterRealms,rosterOrder={},{}
local function rosterKey(signature)
    return MPL.Region()..":"..signature
end
local function rememberRoster(f)
    if not f.signature or not f.players then return end
    local anchored=false
    for _,p in ipairs(f.players) do
        if p.leader and type(p.rosterRealm)=="string" then anchored=true; break end
    end
    if not anchored then return end
    local key=rosterKey(f.signature)
    if not rosterRealms[key] then
        rosterOrder[#rosterOrder+1]=key
        if #rosterOrder>20 then rosterRealms[table.remove(rosterOrder,1)]=nil end
    end
    local entry={at=GetServerTime(),realms={}}
    for i,p in ipairs(f.players) do
        if p.loaded and not p.departed then entry.realms[i]=p.realm end
    end
    rosterRealms[key]=entry
end
local function restoreRoster(players,signature)
    local entry=rosterRealms[rosterKey(signature)]
    if not entry or GetServerTime()-entry.at>=6*3600 then return end
    for i,p in ipairs(players) do
        if not p.realm then p.realm=entry.realms[i] end
    end
end
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

local function listingKeys(info)
    if not MPL.SafeString(info.name) or not safe(info.activityIDs)
        or not C_LFGList.GetActivityInfoTable then return end
    local activities=info.activityIDs
    if activities==nil and safe(info.activityID) and type(info.activityID)=="number" then activities={info.activityID} end
    if type(activities)~="table" then return end
    local mythic=false
    for _,id in ipairs(activities) do
        if not safe(id) then return end
        local activity=C_LFGList.GetActivityInfoTable(id)
        if type(activity)~="table" or not safe(activity) then return end
        local keystone=safe(activity.isMythicPlusActivity) and activity.isMythicPlusActivity==true
            or safe(activity.difficultyID) and activity.difficultyID==8
        if not keystone then return end
        mythic=true
    end
    if not mythic then return end
    local title=info.name:gsub("|c%x%x%x%x%x%x%x%x",""):gsub("|r","")
    -- Timed-run annotations such as +18+++ still describe a level-18 key.
    title=title:gsub("(%d)%++(%s*)$","%1%2")
    local minimum,maximum
    local position=1
    while position<=#title do
        local first,last,digits=title:find("(%d+)",position)
        if not first then break end
        local start=first
        if title:sub(first-1,first-1)=="+" then start=first-1 end
        local before=title:sub(start-1,start-1)
        local low,high=tonumber(digits),tonumber(digits)
        local rest=title:sub(last+1)
        local range,upper=rest:match("^(%s*%-%s*%+?(%d+))")
        if range then high=tonumber(upper); last=last+#range end
        local after=title:sub(last+1,last+1)
        local prefix=title:sub(1,start-1):lower()
        local incidental=prefix:match("ilvl%s*$") or prefix:match("itemlevel%s*$")
            or prefix:match("rio%s*$") or prefix:match("rating%s*$")
        if not before:match("[%w%.:/%+%-]") and not after:match("[%w%.:/%+%-]")
            and not incidental and low>=2 and high<=40 and low<=high then
            if minimum and (minimum~=low or maximum~=high) then return end
            minimum,maximum=low,high
        end
        position=last+1
    end
    return minimum,maximum
end

function MPL.CollectSearchGroup(resultID)
    if InCombatLockdown() or not C_LFGList.GetSearchResultPlayerInfo then return end
    local info=C_LFGList.GetSearchResultInfo(resultID)
    if type(info)~="table" or not safe(info) or not safe(info.numMembers)
        or type(info.numMembers)~="number" or info.numMembers<1 or info.numMembers>5 then return end
    local players,signature={},{}
    local keyMin,keyMax=listingKeys(info)
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
            rosterRealm=realm or false,leader=member.isLeader==true,
            specID=specID,region=MPL.Region(),origin=realm and "known" or "search",
            minLevel=GetMaxLevelForPlayerExpansion and GetMaxLevelForPlayerExpansion() or nil,
            keyMin=keyMin,keyMax=keyMax}
        signature[#signature+1]=enc(name)..":"..enc(realm)..":"..member.classFilename..":"..member.assignedRole
    end
    return players,table.concat(signature,";").."|keys:"..tostring(keyMin or "")..":"..tostring(keyMax or "")
end

local function current(f)
    local _,signature=MPL.CollectSearchGroup(f.resultID)
    return signature and signature==f.signature
end

local function usable(player,displayRefresh)
    if not player.realm then return false end
    local profile=MPL.GetProfile(player.name,player.realm,"All specs",player.role)
    local state=MPL.GetProfileState(player.name,player.realm,"All specs")
    local metric=MPL.PrimaryMetric(profile,player.name,player.realm,player.role)
    return profile and (profile.dual or profile.metric==metric) and not state and not MPL.IsProfileStale(profile)
        and not (displayRefresh and MPL.ProfileNeedsDisplayRefresh(profile))
end

local function cachedProfile(player)
    -- A known identity may have useful old data even when it still needs a
    -- refresh. Never infer an identity from the panel's fallback realm.
    if not player.realm or player.candidates then return end
    local profile=MPL.GetProfile(player.name,player.realm,nil,player.role)
    local state=MPL.GetProfileState(player.name,player.realm,profile and profile.spec)
    if state and (state.reason=="hidden" or state.reason=="empty" or state.reason=="missing") then return end
    return profile
end

local function mergeRoster(f,players,signature)
    local selected=f.players and f.players[f.selected]
    local reused={}
    for i,new in ipairs(players) do
        for _,old in ipairs(f.players or {}) do
            if not reused[old] and MPL.Normalize(old.name)==MPL.Normalize(new.name) and old.class==new.class
                and old.region==new.region
                and (new.rosterRealm or (old.keyMin==new.keyMin and old.keyMax==new.keyMax))
                and not (f.requestID and new.rosterRealm and not old.rosterRealm)
                and (not new.rosterRealm or not old.realm or MPL.Normalize(old.realm)==MPL.Normalize(new.rosterRealm))
                and (not old.rosterRealm or not new.rosterRealm or MPL.Normalize(old.rosterRealm)==MPL.Normalize(new.rosterRealm)) then
                if old.role~=new.role then old.loaded=nil; old.error=nil; old.specID=new.specID
                else old.specID=new.specID or old.specID end
                old.role=new.role
                old.keyMin=new.keyMin; old.keyMax=new.keyMax
                old.leader=new.leader
                old.departed=nil
                if new.rosterRealm then old.realm=new.realm; old.rosterRealm=new.rosterRealm; old.origin="known" end
                players[i]=old; reused[old]=true; break
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
    local cached=not p.loaded and cachedProfile(p)
    MPL.ShowProfile(p.name,p.realm or GetNormalizedRealmName(),nil,true,nil,not p.loaded)
    local panel=MPL.panel
    panel.partyTracked=false
    panel.searchMember=p
    if not p.loaded and not cached then
        -- The fallback realm is only used to initialize the shared panel.
        -- Never display cached logs or submit an ordinary request for it.
        panel.profile=false; panel.class=p.class
        panel.character:SetText(p.name.." — "..(p.realm or L["Realm unknown"]))
        panel.lookup:SetText(p.realm and p.name.."-"..p.realm:gsub(" ","") or p.name)
        panel.scroll:Hide(); panel.emptyMessage:Show()
        panel.emptyMessage:ClearAllPoints(); panel.emptyMessage:SetPoint("TOPLEFT",20,-200)
        panel.emptyMessage:SetWidth(panel:GetWidth()-60)
        panel.emptyMessage:SetText(p.error or (p.candidates and L["Choose the character's realm"] or L["Load logs to identify this character"]))
        panel.emptyMessage:SetHeight(100)
        panel.source:SetText(""); panel.note:SetText(""); panel.footer:SetText("")
        panel.specButton:Hide(); panel.currentSpec:Hide()
        panel.centerLoadButton=false
        panel.loadButton:ClearAllPoints(); panel.loadButton:SetPoint("BOTTOMRIGHT",-40,20)
        panel.loadButton:SetSize(170,24); panel.loadButton:SetText(L["Load group logs"])
    end
    if cached and p.error then MPL.SetProfileFooter(panel,p.error) end
    panel.searchChoices=type(panel.searchChoices)=="table" and panel.searchChoices or {}
    for _,b in ipairs(panel.searchChoices) do b:Hide() end
    for i,c in ipairs(p.candidates or {}) do
        local b=panel.searchChoices[i]
        if not b then
            b=MPL.CreateProfileChoiceButton(panel,panel:GetWidth()-60)
            panel.searchChoices[i]=b
        end
        -- Rebind the member when reusing a choice button for another tab.
        b:SetScript("OnClick",function()
            p.realm=c.realm; p.candidates=nil; p.error=nil
            MPL.ShowSearchGroupLogs(f.resultID)
        end)
        b:ClearAllPoints(); b:SetPoint("TOPLEFT",20,-255-(i-1)*56); b:SetSize(panel:GetWidth()-60,52)
        local label=c.name.." — "..c.realm
        if c.scores then
            local function value(v) return v and string.format("%.0f",v) or "—" end
            local roles={}
            for index,role in ipairs({"Tank","Healer","Damage"}) do
                local score=c.scores[index]
                if score and score>0 then roles[#roles+1]=L[role].." "..value(score) end
            end
            label=label.."\nWCL: "..(#roles>0 and table.concat(roles," / ") or "—")
                .."  /  "..L["Best %"].." "..value(c.best).."  /  "..L["Прохождения"].." "..value(c.runs)
            label=label.."\n"..L["Специализация"]..": "..(c.specs~="" and c.specs or "—")
        else
            label=label.."\n"..L["Role data unavailable; update Companion"]
        end
        b:SetText(label); b:Show()
    end
    if not p.loaded and not cached then MPL.RenderProfileStats(panel) end
    MPL.panel.groupPlayers=resolved; MPL.panel.searchPlayers=members
    MPL.RenderPlayerTabs(MPL.panel)
    if metric then
        panel.viewMetric=metric; MPL.RenderProfileStats(panel)
        if type(scroll)=="number" then panel.scroll:SetVerticalScroll(scroll) end
    end
end

function MPL.BeginSearchGroupRequest(forceSearch)
    local f=MPL.searchGroupWindow
    if not f then return end
    if not current(f) then
        local players,signature=MPL.CollectSearchGroup(f.resultID)
        if players then mergeRoster(f,players,signature); f.onlyMissing=true end
    end
    sequence=sequence+1
    local id=tostring(GetServerTime()).."-"..sequence
    local rows={"MPLN1"}
    local levelSearch,leaderFirst,keyContext=false,false,false
    f.requestPlayers={}; f.requestTargets={}
    for _,p in ipairs(f.players) do
        if not p.departed and (forceSearch or not f.onlyMissing or not usable(p,f.displayRefresh)) then
            local copy={}; for key,value in pairs(p) do copy[key]=value end
            if forceSearch and copy.origin=="search" then copy.realm=nil end
            f.requestPlayers[#f.requestPlayers+1]=copy
            f.requestTargets[#f.requestTargets+1]=p
        end
    end
    for i,p in ipairs(f.requestPlayers) do
        local origin=p.origin
        if p.leader and p.realm and MPL.CompanionSupports("leaderfirst") then
            origin="leader"; leaderFirst=true
        end
        local row={"N",i,enc(p.region),enc(p.realm),enc(p.name),enc(p.class),enc(p.role),origin}
        if type(p.minLevel)=="number" and p.minLevel>0 then row[#row+1]=p.minLevel; levelSearch=true end
        if p.keyMin and p.keyMax then
            row[9]=p.minLevel or ""; row[10]=p.keyMin; row[11]=p.keyMax; keyContext=true
        end
        rows[#rows+1]=table.concat(row,"\t")
    end
    f.requestID=id
    -- Legacy Companions recognize MPLQ2 and can return an explicit capability
    -- upgrade error instead of silently ignoring an unfamiliar request header.
    f.request="MPLS2\n"..id.."\nMPLC1 namesearch,nameerrors,candidateinfo"..(levelSearch and ",levelsearch" or "")
        ..(leaderFirst and ",leaderfirst" or "")
        ..(keyContext and ",keycontext" or "")
        ..(forceSearch and ",rescan" or "")
        ..(MPL.CompanionSupports("errorcodes") and ",errorcodes" or "")
        ..(MPL.CompanionSupports("lazyspecs") and ",lazyspecs" or "")
        ..(MPL.RequestRankColors() and ",rankcolors" or "")
        ..(MPL.CompanionSupports("primarymetric") and ",primarymetric" or "").."\nMPLQ2\n"..table.concat(rows,"\n").."\n"
    f.rankColors=MPL.RequestRankColors()
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
        if message=="" then return nil,L["Invalid group search reply"] end
        MPlusLogsDB=MPlusLogsDB or {}
        MPlusLogsDB.companionReplySeen=true
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
        elseif ((row[1]=="P" or row[1]=="F") and #row==7) or (row[1]=="C" and (#row==6 or #row==12)) then
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
                local candidate={realm=row[4],name=row[5],class=row[6]}
                if #row==12 then
                    local values={}
                    for field=7,11 do
                        local value=tonumber(row[field])
                        local limit=field==10 and 100 or field==11 and 10000000 or 100000000
                        if row[field]~="" and (not value or value~=value or value<0 or value>limit
                            or (field==11 and value%1~=0)) then return nil,L["Invalid group search reply"] end
                        values[field]=value
                    end
                    if #row[12]>400 or row[12]:find("[|%c]") then return nil,L["Invalid group search reply"] end
                    candidate.scores={values[7],values[8],values[9]}
                    candidate.best=values[10]; candidate.runs=values[11]; candidate.specs=row[12]
                end
                list[#list+1]=candidate
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
    local displaySupported=false
    for capability in (capabilities or ""):gmatch("[a-z]+") do
        if capability=="rankcolors" then displaySupported=true end
    end
    MPL.SetProfileDisplayMetadata(profiles,f.rankColors,displaySupported)
    local count=MPL.StoreProfiles(profiles)
    MPlusLogsDB.companionReplySeen=true
    if MPL.QueueCompanionUpdateNotice then MPL.QueueCompanionUpdateNotice(version) end
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
        rememberRoster(f)
        restoreRoster(players,signature)
        f.players=nil; f.selected=1; f.requestID=nil; f.onlyMissing=false
        f.resultID=resultID; mergeRoster(f,players,signature)
    elseif f.signature~=signature then mergeRoster(f,players,signature); f.onlyMissing=true end
end

function MPL.ShowSearchGroupLogs(resultID,forceSearch,displayRefresh)
    if forceSearch and not MPL.CompanionSupports("rescan") then
        if MPL.panel then MPL.SetProfileFooter(MPL.panel,L["Update Companion to search realms again."]) end
        return
    end
    local players=MPL.CollectSearchGroup(resultID)
    if not players then print(L["Group member data is unavailable; try again shortly"]); return end
    MPL.ShowSearchGroup(resultID)
    local f=MPL.searchGroupWindow
    f.displayRefresh=displayRefresh==true
    local fresh=true
    for _,player in ipairs(f.players) do
        if not player.departed then
            if usable(player,displayRefresh) then player.loaded=true else fresh=false end
        end
    end
    if fresh and not forceSearch then
        if MPL.downloadWindow then MPL.downloadWindow:Hide() end
        MPL.OpenSearchGroupProfile(f.selected)
        return
    end
    local first=players[1]
    local selected=f.players[f.selected]
    if selected and (selected.loaded or cachedProfile(selected)) then
        -- Keep the dated profile readable while the normal clipboard exchange
        -- refreshes it. It remains pending until an actual reply is imported.
        MPL.OpenSearchGroupProfile(f.selected,true)
    end
    -- The fallback realm only labels the exchange window. Requests are built
    -- from the roster and retain empty realms until Companion resolves them.
    f.onlyMissing=true
    MPL.ShowDownload(first.name,first.realm or GetNormalizedRealmName(),nil,nil,nil,nil,resultID,nil,nil,forceSearch)
end
