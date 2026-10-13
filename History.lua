local _, MPL = ...
local L = MPL.L

local function value(text)
    return text:gsub("%%(%x%x)",function(hex) return string.char(tonumber(hex,16)) end):gsub("[%z\1-\31\127|]","")
end
local function fields(line)
    local result={}
    for part in (line.."\t"):gmatch("(.-)\t") do result[#result+1]=value(part) end
    return result
end
local function number(text,max)
    local n=tonumber(text)
    if not n or n~=n or n<0 or n>max or n%1~=0 then error("Invalid history number") end
    return n
end
local function text(s)
    if not s or #s>250 then error("Invalid history text") end
    return s
end

function MPL.ParseHistory(body)
    if type(body)~="string" or #body>500000 then return nil,L["Invalid local history"] end
    local ok,result=pcall(function()
        local header,summary,current=false,nil,nil
        local runs,seen={},{}
        for line in (body.."\n"):gmatch("([^\n]*)\n") do
            line=line:gsub("\r$","")
            if line~="" then
                if not header then
                    if line~="MPLH1" then error("Invalid history header") end
                    header=true
                else
                    local f=fields(line)
                    if f[1]=="S" then
                        if summary or current or #f~=7 then error("Invalid history summary") end
                        if not ({eu=true,us=true,kr=true,tw=true,cn=true})[f[3]] then error("Invalid history region") end
                        summary={updated=text(f[2]),region=f[3],realm=text(f[4]),name=text(f[5]),total=number(f[6],2000),count=number(f[7],100)}
                        if summary.name=="" or summary.realm=="" or summary.count>summary.total then error("Invalid history identity") end
                    elseif f[1]=="R" then
                        if not summary or current or #f~=14 or #runs>=100 then error("Invalid history run") end
                        if #f[2]~=64 or f[2]:find("[^0-9a-f]") or seen[f[2]] then error("Invalid history run ID") end
                        if not ({completed=true,in_progress=true,incomplete=true,abandoned=true})[f[9]]
                            or not ({complete=true,partial=true})[f[10]] then error("Invalid history coverage") end
                        local duration=f[8]~="" and tonumber(f[8]) or nil
                        if f[8]~="" and (not duration or duration~=duration or duration<=0 or duration>86400) then error("Invalid history duration") end
                        current={id=f[2],dungeon=text(f[3]),mapID=number(f[4],10000),level=number(f[5],100),
                            started=text(f[6]),ended=text(f[7]),duration=duration,status=f[9],coverage=f[10],
                            source=text(f[11]),firstLine=number(f[12],1000000000),lastLine=number(f[13],1000000000),
                            yearInferred=number(f[14],1)==1,region=summary.region,players={}}
                        if current.lastLine<current.firstLine or current.level<1 then error("Invalid history source span") end
                        if not current.started:match("^%d%d%d%d%-%d%d%-%d%dT%d%d:%d%d:%d%d%.%d+$")
                            or (current.ended~="" and not current.ended:match("^%d%d%d%d%-%d%d%-%d%dT%d%d:%d%d:%d%d%.%d+$"))
                            or (current.coverage=="complete" and (current.ended=="" or not duration)) then error("Invalid history timestamp") end
                        seen[current.id]=true
                    elseif f[1]=="A" then
                        if not current or #f~=9 or #current.players>=5 then error("Invalid history actor") end
                        if not f[2]:match("^Player%-%d+%-%x+$") then error("Invalid history GUID") end
                        if f[6]~="" and not ({TANK=true,HEALER=true,DAMAGER=true})[f[6]] then error("Invalid history role") end
                        for _,p in ipairs(current.players) do if p.guid==f[2] then error("Duplicate history actor") end end
                        current.players[#current.players+1]={guid=f[2],name=text(f[3]),realm=text(f[4]),specID=number(f[5],10000),
                            role=f[6],interrupts=number(f[7],1000000),deaths=number(f[8],1000000),dispels=number(f[9],1000000)}
                    elseif f[1]=="E" then
                        if not current or #f~=1 then error("Invalid history terminator") end
                        local found=false
                        for _,p in ipairs(current.players) do
                            if MPL.Normalize(p.name)==MPL.Normalize(summary.name) and MPL.Normalize(p.realm)==MPL.Normalize(summary.realm) then found=true end
                            if current.coverage=="complete" and (p.name=="" or p.realm=="") then error("Incomplete history roster") end
                        end
                        if not found or (current.coverage=="complete" and (#current.players~=5 or current.status~="completed")) then error("History identity or coverage mismatch") end
                        runs[#runs+1]=current; current=nil
                    else error("Unknown history record") end
                end
            end
        end
        if not summary or current or #runs~=summary.count then error("Incomplete history reply") end
        summary.runs=runs
        return summary
    end)
    if not ok then return nil,L["Invalid local history"] end
    return result
end

function MPL.StoreHistory(result)
    MPlusLogsDB=MPlusLogsDB or {}; MPlusLogsDB.localHistory=MPlusLogsDB.localHistory or {}
    local history=MPlusLogsDB.localHistory
    history.runs=history.runs or {}; history.requests=history.requests or {}
    for _,run in ipairs(result.runs) do
        local old=history.runs[run.id]
        if not old or old.coverage~="complete" or run.coverage=="complete" then history.runs[run.id]=run end
    end
    history.requests[MPL.Key(result.name,result.realm,result.region)]={updated=result.updated,total=result.total}
    local ordered={}
    for _,run in pairs(history.runs) do ordered[#ordered+1]=run end
    table.sort(ordered,function(a,b) return a.started>b.started end)
    for i=501,#ordered do history.runs[ordered[i].id]=nil end
    return #result.runs
end

function MPL.HistoryRuns(name,realm)
    local runs,observations={},0
    local totals={interrupts=0,deaths=0,dispels=0}
    local history=MPlusLogsDB and MPlusLogsDB.localHistory
    for _,run in pairs(history and history.runs or {}) do
        if run.region==MPL.Region() then
            for _,p in ipairs(run.players) do
                if MPL.Normalize(p.name)==MPL.Normalize(name) and MPL.Normalize(p.realm)==MPL.Normalize(realm) then
                    runs[#runs+1]=run
                    if run.coverage=="complete" then
                        observations=observations+1
                        for key in pairs(totals) do totals[key]=totals[key]+p[key] end
                    end
                    break
                end
            end
        end
    end
    table.sort(runs,function(a,b) return a.started>b.started end)
    return runs,observations,totals
end
