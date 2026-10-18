"""Applicant snapshot -> one clipboard exchange -> atomic multi-player import."""
import copy
import tempfile
import unittest
import sys
from pathlib import Path
from urllib.parse import quote

from test_addon import ROOT,MOCK,LuaRuntime,api_fixture,load_locales
sys.path.insert(0,str(ROOT/'tools'))
import clipboard_protocol
import realm_resolver


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix=".test-work-",dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.cache=Path(self.temp.name)
        self.lua=LuaRuntime(unpack_returned_tuples=True); self.lua.execute(MOCK)
        self.lua.execute('''
            MPlusLogsDB={profiles={},companionIntroDismissed=true}
            timers={}; C_Timer={After=function(_,fn) timers[#timers+1]=fn end}
            LFGListFrame={ApplicationViewer=CreateFrame("Frame")}
            LFGListPVEStub=CreateFrame("Frame"); LFGListPVEStub:SetWidth(338)
            LFGListFrame.GetParent=function() return LFGListPVEStub end
            PVEFrame=CreateFrame("Frame"); PVEFrame:SetWidth(563); PVEFrame:Show()
            local viewer=LFGListFrame.ApplicationViewer
            viewer:Show()
            LFGListFrame.activePanel=viewer
            viewer.InfoBackground=CreateFrame("Frame"); viewer.InfoBackground:SetWidth(338)
            viewer.DescriptionFrame=CreateFrame("Frame"); viewer.DescriptionFrame:SetWidth(310)
            for _,key in ipairs({"NameColumnHeader","RoleColumnHeader","ItemLevelColumnHeader","RatingColumnHeader"}) do
                viewer[key]=CreateFrame("Button"); viewer[key].Label=CreateFrame("Frame")
                viewer[key].Label:SetText(key); viewer[key]:Show()
            end
            viewer.ScrollBox=CreateFrame("Frame")
            local row=CreateFrame("Frame"); row.applicantID=10; row.Members={}
            for i=1,2 do
                local member=CreateFrame("Button",nil,row); member.memberIdx=i
                for _,key in ipairs({"Name","RoleIcon1","ItemLevel","Rating"}) do member[key]=CreateFrame("Frame",nil,member) end
                member:Show(); row.Members[i]=member
            end
            testRows={row}
            viewer.ScrollBox.ForEachFrame=function(_,fn) for _,frame in ipairs(testRows) do fn(frame) end end
            C_LFGList.GetApplicants=function() return {10,20,30} end
            C_LFGList.GetApplicantInfo=function(id)
                return {numMembers=id==10 and 2 or 1,applicationStatus=id==30 and "invited" or "applied"}
            end
            C_LFGList.GetApplicantMemberInfo=function(id,member)
                local name=id==10 and (member==1 and "Alice" or "Bob") or "Alice"
                return name.."-Гордунни",nil,nil,nil,nil,nil,false,true,false,name=="Alice" and "HEALER" or "DAMAGER"
            end
        ''')
        self.mpl=self.lua.table()
        load_locales(self.lua,self.mpl)
        for file in ("Data.lua","Snapshot.lua","Transport.lua","UI.lua","Integration.lua"):
            self.lua.execute("return assert(loadstring(...))",(ROOT/file).read_text(encoding='utf-8'))("MPlusLogs",self.mpl)

    def players(self):
        players=self.mpl.CollectApplicants()
        return players[0] if isinstance(players,tuple) else players

    def fetch(self,args):
        if args.name=="Bob": raise ValueError("Rankings hidden")
        raw=api_fixture(); char=raw['data']['characterData']['character']
        char['name']=args.name
        char['damage']=char.pop('performance')
        char['healing']=copy.deepcopy(char['damage'])
        return raw

    def flush(self):
        self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")

    def test_all_group_members_deduplicated_and_invited_excluded(self):
        players=self.players()
        self.assertEqual(len(players),2)
        self.assertEqual(players[1].name,"Alice")
        self.assertEqual(players[1].role,"HEALER")
        self.assertEqual(players[2].name,"Bob")

    def test_applicant_without_available_realm_is_skipped_and_recovers(self):
        self.lua.execute('''
            GetNormalizedRealmName=function() return nil end
            C_LFGList.GetApplicantMemberInfo=function(id,member)
                if id==10 and member==1 then return "Alice" end
                return "Bob-Гордунни"
            end
        ''')
        self.mpl.InstallBatchButton()
        self.assertEqual(len(self.players()),1)
        self.assertEqual(self.mpl.batchButton.text,"Загрузить логи всех (0/1)")
        self.lua.execute('GetNormalizedRealmName=function() return "Гордунни" end')
        self.mpl.UpdateBatchButton()
        self.assertEqual(len(self.players()),2)
        self.assertEqual(self.mpl.batchButton.text,"Загрузить логи всех (0/2)")

    def test_unavailable_applicant_name_does_not_create_identity(self):
        self.lua.execute('C_LFGList.GetApplicantMemberInfo=function() return nil end')
        self.mpl.InstallBatchButton()
        self.assertEqual(len(self.players()),0)
        self.assertIsNone(self.mpl.roles)
        self.assertIsNone(self.mpl.specs)

    def test_button_is_in_group_application_viewer(self):
        self.mpl.InstallBatchButton()
        self.assertEqual(self.mpl.batchButton.text,"Загрузить логи всех (0/2)")
        self.assertTrue(self.lua.eval("function(a,b) return a==b end")(self.mpl.batchButton.parent,self.lua.globals().LFGListFrame.ApplicationViewer))

    def test_batch_button_tracks_raid_and_dungeon_listing_switches(self):
        self.lua.execute('''
            listingCategory=2
            C_LFGList.GetActiveEntryInfo=function() return {activityIDs={123}} end
            C_LFGList.GetActivityInfoTable=function() return {categoryID=listingCategory,isMythicPlusActivity=listingCategory==2} end
            IsInRaid=function() return false end
        ''')
        self.mpl.InstallBatchButton()
        button=self.mpl.batchButton
        self.assertTrue(button.enabled)
        self.lua.globals().listingCategory=3
        self.mpl.UpdateBatchButton()
        self.assertFalse(button.enabled)
        self.assertEqual(button.text,"Загрузить логи всех (0/2)")
        self.lua.execute('listingCategory=2; IsInRaid=function() return true end')
        button.Show(button)
        button.scripts.OnUpdate(button,30)
        self.assertTrue(button.enabled)

    def test_batch_button_rechecks_listing_before_starting_a_request(self):
        self.lua.execute('''
            listingCategory=2
            C_LFGList.GetActiveEntryInfo=function() return {activityIDs={123}} end
            C_LFGList.GetActivityInfoTable=function() return {categoryID=listingCategory,isMythicPlusActivity=listingCategory==2} end
        ''')
        self.mpl.InstallBatchButton()
        button=self.mpl.batchButton
        self.lua.globals().listingCategory=3
        # The listing changed before the button received its next update.
        button.scripts.OnClick()
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.downloadWindow)
        self.lua.globals().listingCategory=2
        button.scripts.OnClick()
        self.assertIsNotNone(self.mpl.pendingReply)
        self.assertTrue(self.mpl.pendingReply.batch)

    def test_one_exchange_imports_success_and_reports_hidden_character(self):
        self.mpl.ShowBatchDownload()
        f=self.mpl.downloadWindow
        request=f.edit.GetText(f.edit)
        self.assertIn("MPLQ2\n",request)
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,self.fetch)
        f.edit.SetText(f.edit,response); f.edit.scripts.OnTextChanged(f.edit,True); self.flush()
        self.assertIsNone(self.mpl.pendingReply)
        self.assertFalse(f.shown)
        self.assertIsNone(self.mpl.batchResultsWindow)
        self.assertEqual(self.mpl.lastBatchResult.count,1)
        self.mpl.OpenBatchResults()
        result=self.mpl.batchResultsWindow
        self.assertTrue(result.shown)
        self.assertIn("1 из 2",result.summary.text)
        self.assertIn("скрыты",result.rows[2].status.text)
        profile,_,_=self.mpl.GetProfile("Alice-Гордунни")
        self.assertEqual(profile.metric,"hps")
        self.assertTrue(profile.dual)
        self.assertEqual(self.lua.eval("function(t) local n=0; for _ in pairs(t) do n=n+1 end; return n end")(self.lua.globals().MPlusLogsDB.profiles),1)

    def test_failure_only_batch_finishes_with_report(self):
        _,request=self.mpl.SendBatchRequest(self.players())
        def fail(_): raise ValueError("WCL unavailable")
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,fail)
        self.assertTrue(response.startswith("MPLS1\n"))
        self.assertEqual(self.mpl.ReceiveReply(response,True),0)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.batchResultsWindow)
        self.mpl.OpenBatchResults()
        self.assertIn("0 из 2",self.mpl.batchResultsWindow.summary.text)

    def test_download_shortcuts_select_request_and_require_ctrl_for_copy(self):
        self.lua.execute('IsControlKeyDown=function() return controlDown or false end')
        self.mpl.ShowBatchDownload()
        f=self.mpl.downloadWindow
        self.flush()
        self.assertEqual(f.phase,'copy')
        self.assertTrue(f.edit.focused)
        self.assertTrue(f.edit.highlighted)
        f.edit.scripts.OnKeyDown(f.edit,'C')
        self.assertEqual(f.phase,'copy')
        self.lua.globals().controlDown=True
        f.edit.highlighted=False
        f.edit.scripts.OnKeyDown(f.edit,'C')
        self.assertEqual(f.phase,'waiting')
        self.assertTrue(f.edit.highlighted)
        f.edit.highlighted=False
        f.edit.scripts.OnKeyDown(f.edit,'V')
        self.assertTrue(f.edit.highlighted)
        response=clipboard_protocol.reply(f.request,realm_resolver.load_mappings(),self.cache,self.fetch)
        f.edit.SetText(f.edit,response[:1])
        f.edit.scripts.OnTextChanged(f.edit,True)
        self.lua.eval('function(edit,body) for i=1,#body do edit.scripts.OnChar(edit,body:sub(i,i)) end end')(f.edit,response)
        self.flush()
        self.flush()
        self.assertFalse(f.shown)
        self.assertEqual(self.mpl.lastBatchResult.count,1)

    def test_download_click_restores_selection_and_invalid_paste_can_be_retried(self):
        self.mpl.ShowBatchDownload()
        f=self.mpl.downloadWindow
        self.flush()
        f.edit.highlighted=False
        f.edit.scripts.OnMouseUp(f.edit)
        self.flush()
        self.assertTrue(f.edit.highlighted)
        request=f.request
        f.edit.SetText(f.edit,'unrelated clipboard contents')
        f.edit.scripts.OnTextChanged(f.edit,True)
        self.flush()
        self.assertTrue(f.shown)
        self.assertEqual(f.edit.text,request)
        self.assertTrue(f.edit.highlighted)
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,self.fetch)
        f.edit.SetText(f.edit,response)
        f.edit.scripts.OnTextChanged(f.edit,True)
        self.flush()
        self.assertFalse(f.shown)
        self.assertEqual(self.mpl.lastBatchResult.count,1)

    def test_unrequested_player_and_incomplete_receipt_cannot_import(self):
        request_id,_=self.mpl.SendBatchRequest(self.players())
        for body in ("MPL2\nF\teu\tГордунни\tMallory\terror\n", "MPL2\nF\teu\tГордунни\tAlice\terror\n"):
            response="MPLS1\n"+request_id+"\nMPLB1\n"+quote(body,safe='')
            count,err=self.mpl.ReceiveReply(response,True)
            self.assertIsNone(count)
            self.assertIsNone(self.lua.eval("next")(self.lua.globals().MPlusLogsDB.profiles))
            self.assertIsNotNone(self.mpl.pendingReply)

    def test_new_applicants_after_copy_do_not_change_expected_snapshot(self):
        _,request=self.mpl.SendBatchRequest(self.players())
        self.lua.execute('C_LFGList.GetApplicants=function() return {} end')
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,self.fetch)
        self.assertEqual(self.mpl.ReceiveReply(response,True),1)

    def test_no_mplus_runs_are_reported_as_missing_data(self):
        _,request=self.mpl.SendBatchRequest(self.players())
        def empty(args):
            raw=self.fetch(type('Args',(),{'name':'Alice'})())
            char=raw['data']['characterData']['character']; char['name']=args.name
            char['damage']['rankings']=[];char['healing']['rankings']=[]
            return raw
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,empty)
        self.assertEqual(self.mpl.ReceiveReply(response,True),0)
        self.mpl.OpenBatchResults()
        self.assertIn("не найдены открытые логи M+",self.mpl.batchResultsWindow.rows[1].status.text)

    def test_counter_tracks_current_candidates_and_expired_profiles(self):
        self.mpl.InstallBatchButton()
        _,request=self.mpl.SendBatchRequest(self.players())
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,self.fetch)
        self.assertEqual(self.mpl.ReceiveReply(response,True),1)
        self.assertEqual(self.mpl.batchButton.text,"Загрузить логи всех (1/2)")
        # The downloaded Alice leaves; a new uncached Carol replaces her.
        self.lua.execute('''
            C_LFGList.GetApplicantMemberInfo=function(id,member)
                local name=id==10 and (member==1 and "Carol" or "Bob") or "Carol"
                return name.."-Гордунни"
            end
        ''')
        self.mpl.UpdateBatchButton()
        self.assertEqual(self.mpl.batchButton.text,"Загрузить логи всех (0/2)")
        # Alice returns; stale data should not count as up to date.
        self.lua.execute('C_LFGList.GetApplicantMemberInfo=function() return "Alice-Гордунни" end')
        profile,_,_=self.mpl.GetProfile("Alice-Гордунни")
        profile.updated="2026-10-01 00:00 UTC"
        self.mpl.UpdateBatchButton()
        self.assertEqual(self.mpl.batchButton.text,"Загрузить логи всех (0/1)")
        self.lua.execute('C_LFGList.GetApplicants=function() return {} end')
        self.mpl.UpdateBatchButton()
        self.assertEqual(self.mpl.batchButton.text,"Загрузить логи всех (0/0)")

    def test_30_fresh_plus_5_new_only_fetches_5_and_preserves_previous_profiles(self):
        self.lua.execute('''
            C_LFGList.GetApplicants=function() local ids={}; for i=1,35 do ids[i]=i end; return ids end
            C_LFGList.GetApplicantInfo=function() return {numMembers=1,applicationStatus="applied"} end
            C_LFGList.GetApplicantMemberInfo=function(id)
                return "Player"..id.."-Гордунни",nil,nil,nil,nil,nil,false,false,true,"DAMAGER"
            end
            for i=1,30 do
                local key=MPlusLogs.Key("Player"..i,"Гордунни")
                MPlusLogsDB.profiles[key]={updated="2026-10-12 04:00 UTC",metric="dps",dual=true,spec="All specs"}
            end
            originalProfile=MPlusLogsDB.profiles[MPlusLogs.Key("Player1","Гордунни")]
        ''')
        self.mpl.ShowBatchDownload()
        request=self.mpl.downloadWindow.request
        parsed=realm_resolver.parse_queue(clipboard_protocol.unwrap_request(request)[1],realm_resolver.load_mappings())
        self.assertEqual(len(parsed),5)
        self.assertEqual({entry['name'] for entry in parsed},{'Player'+str(i) for i in range(31,36)})
        self.assertEqual(len(self.mpl.pendingReply.players),5)
        self.assertIn('5 / 35',self.mpl.downloadWindow.character.text)
        calls=[]
        def fetch_new(args):
            calls.append(args.name)
            raw=self.fetch(type('Args',(),{'name':'Alice'})())
            raw['data']['characterData']['character']['name']=args.name
            return raw
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,fetch_new)
        self.assertEqual(self.mpl.ReceiveReply(response,True),5)
        self.assertEqual(len(calls),5)
        self.assertTrue(self.lua.eval('originalProfile==MPlusLogsDB.profiles[MPlusLogs.Key("Player1","Гордунни")]'))
        # Opening again makes no request when every candidate is fresh.
        self.mpl.ShowBatchDownload()
        self.assertIsNone(self.mpl.pendingReply)
        self.assertEqual(self.mpl.downloadWindow.request,'')
        self.assertIn('актуальные логи',self.mpl.downloadWindow.status.text)

    def test_expired_unknown_date_and_missing_role_metric_are_requested(self):
        self.lua.execute('''
            MPlusLogsDB.profiles[MPlusLogs.Key("Alice","Гордунни")]=
                {updated="2026-10-12 04:00 UTC",metric="hps",dual=false,spec="All specs"}
            MPlusLogsDB.profiles[MPlusLogs.Key("Bob","Гордунни")]=
                {updated="2026-10-12 04:00 UTC",metric="dps",dual=true,spec="All specs"}
        ''')
        pending,skipped=self.mpl.FilterFreshProfiles(self.players())
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[1].name,'Alice')
        self.assertEqual(skipped,1)
        bob,_,_=self.mpl.GetProfile('Bob','Гордунни')
        for date in ['2026-10-01 04:00 UTC','date unknown']:
            bob.updated=date
            pending,skipped=self.mpl.FilterFreshProfiles(self.players())
            self.assertEqual(len(pending),2)
            self.assertEqual(skipped,0)

    def test_all_fresh_disables_batch_button_but_explicit_refresh_still_works(self):
        self.mpl.InstallBatchButton()
        self.lua.execute('''
            for _,name in ipairs({"Alice","Bob"}) do
                MPlusLogsDB.profiles[MPlusLogs.Key(name,"Гордунни")]=
                    {updated="2026-10-12 04:00 UTC",metric="dps",dual=true,spec="All specs"}
            end
        ''')
        self.mpl.UpdateBatchButton()
        self.assertEqual(self.mpl.batchButton.text,'Загрузить логи всех (2/2)')
        self.assertFalse(self.mpl.batchButton.enabled)
        self.mpl.ShowDownload('Alice','Гордунни',None)
        self.assertIsNotNone(self.mpl.pendingReply)
        self.assertFalse(self.mpl.pendingReply.batch)


if __name__=='__main__':unittest.main()
