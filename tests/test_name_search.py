"""Real Lua group snapshot -> clipboard -> Companion adapter -> validated Lua storage."""
import copy
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from urllib.parse import quote,unquote
import test_addon
import test_search_specs
sys.path.insert(0,str(test_addon.ROOT/'tools'))
import clipboard_protocol
import name_search
import name_search_browser
import realm_resolver


class Client:
    def __init__(self,realms=('silvermoon',),wrong_class=False,fail=False):
        self.name_search=lambda name,region:[{'realm_slug':s} for s in realms]
        self.wrong_class=wrong_class
        self.fail=fail
        self.calls=[]

    def __call__(self,args):
        self.calls.append(args)
        if self.fail and args.name=='Mirkowrr': raise ValueError('Search/API unavailable')
        raw=test_addon.api_fixture()
        char=raw['data']['characterData']['character']
        char['name']=args.name
        char['damage']=char.pop('performance')
        char['healing']=copy.deepcopy(char['damage'])
        char['server'].update(name=args.server_slug.title(),slug=args.server_slug)
        char['classID']=70 if args.name=='Frákkie' or self.wrong_class else 51
        raw['data']['gameData']={'classes':[{'id':51,'name':'Warrior'},{'id':70,'name':'Monk'}]}
        return raw


class NameSearchTests(unittest.TestCase):
    def setUp(self):
        test_search_specs.SearchSpecTests.setUp(self)
        self.lua.execute('''
            searchMembers[1]={name="Frákkie-Draenor",isLeader=true,classFilename="MONK",assignedRole="DAMAGER"}
            searchMembers[2]={name="Mirkowrr",isLeader=false,classFilename="WARRIOR",assignedRole="DAMAGER"}
        ''')
        self.lua.execute('return assert(loadstring(...))',
            (test_addon.ROOT/'SearchGroup.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.mpl.ShowSearchGroup(10)

    def response(self,client=None):
        self.mpl.BeginSearchGroupRequest()
        request=self.mpl.searchGroupWindow.request
        return clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,client or Client())

    def browser(self,**options):
        temporary_root=patch.object(name_search.tempfile,'tempdir',str(self.cache))
        temporary_root.start(); self.addCleanup(temporary_root.stop)
        search=name_search.BrowserSearch(**options)
        self.addCleanup(search.profile.cleanup)
        return search

    def join_search_group(self,name='Joined-Silvermoon'):
        self.lua.execute('''
            searchMembers[3]={name=...,classFilename="WARRIOR",assignedRole="DAMAGER"}
            C_LFGList.GetSearchResultInfo=function()
                return {leaderName=leaderName,activityIDs={1},numMembers=#searchMembers}
            end
            eventFrames[1].scripts.OnEvent(eventFrames[1],"LFG_LIST_SEARCH_RESULT_UPDATED",10)
        ''',name)

    def test_join_adds_tab_without_changing_selected_profile_or_loading(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.OpenSearchGroupProfile(2)
        self.join_search_group()
        self.assertEqual(len(self.mpl.panel.searchPlayers),3)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertTrue(self.mpl.panel.playerTabs[2].selected)
        self.assertIsNone(self.mpl.downloadWindow)
        tab=self.mpl.panel.playerTabs[3]
        tab.scripts.OnClick(tab)
        self.assertEqual(self.mpl.panel.name,'Joined')
        self.assertFalse(self.mpl.panel.profile)
        self.mpl.panel.loadButton.scripts.OnClick(self.mpl.panel.loadButton)
        _,body=clipboard_protocol.unwrap_request(self.mpl.downloadWindow.request)
        members=name_search.parse(body)
        self.assertEqual([p['name'] for p in members],['Joined'])

    def test_join_during_exchange_preserves_original_reply_and_new_tab(self):
        reply=self.response()
        self.join_search_group()
        self.assertEqual(len(self.mpl.searchGroupWindow.players),3)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        self.assertEqual(len(self.mpl.panel.searchPlayers),3)
        self.assertFalse(self.mpl.searchGroupWindow.players[3].loaded)
        self.assertTrue(self.mpl.searchGroupWindow.players[2].loaded)

    def test_repeated_join_events_do_not_duplicate_tabs_or_reset_the_metric(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.OpenSearchGroupProfile(2)
        self.mpl.panel.viewMetric='hps'
        self.join_search_group()
        self.join_search_group()
        self.assertEqual(len(self.mpl.panel.searchPlayers),3)
        self.assertEqual(self.mpl.panel.viewMetric,'hps')
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')

    def test_cached_new_member_opens_without_a_new_exchange(self):
        self.join_search_group()
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.OpenSearchGroupProfile(2)
        self.lua.execute('searchMembers[3]=nil; eventFrames[1].scripts.OnEvent(eventFrames[1],"LFG_LIST_SEARCH_RESULT_UPDATED",10)')
        self.join_search_group()
        tab=self.mpl.panel.playerTabs[3]
        tab.scripts.OnClick(tab)
        self.assertEqual(self.mpl.panel.name,'Joined')
        self.assertTrue(self.mpl.panel.profile)
        self.assertIsNone(self.mpl.downloadWindow)

    def test_unrelated_or_temporarily_unavailable_listing_does_not_change_tabs(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.OpenSearchGroupProfile(2)
        self.lua.execute('''
            searchMembers[3]={name="Joined",classFilename="WARRIOR",assignedRole="DAMAGER"}
            eventFrames[1].scripts.OnEvent(eventFrames[1],"LFG_LIST_SEARCH_RESULT_UPDATED",99)
        ''')
        self.assertEqual(len(self.mpl.panel.searchPlayers),2)
        self.lua.execute('C_LFGList.GetSearchResultInfo=function() return nil end')
        self.mpl.UpdateSearchGroupRoster(10)
        self.assertEqual(len(self.mpl.panel.searchPlayers),2)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')

    def test_departing_selected_member_remains_readable_and_is_not_requested_again(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.OpenSearchGroupProfile(2)
        self.lua.execute('searchMembers[2]={name="Replacement-Silvermoon",classFilename="WARRIOR",assignedRole="DAMAGER"}')
        self.mpl.UpdateSearchGroupRoster(10)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertTrue(self.mpl.panel.profile)
        self.mpl.BeginSearchGroupRequest()
        _,body=clipboard_protocol.unwrap_request(self.mpl.searchGroupWindow.request)
        self.assertEqual([p['name'] for p in name_search.parse(body)],['Replacement'])

    def test_real_party_join_updates_tabs_without_opening_an_exchange(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.lua.execute('''
            local MPL=...
            partyPlayers={{name="Frákkie",realm="Draenor",role="DAMAGER"},
                {name="Mirkowrr",realm="Silvermoon",role="DAMAGER"}}
            MPL.CollectParty=function() return partyPlayers end
            MPL.ShowGroupProfiles(partyPlayers,partyPlayers[2],true)
            partyPlayers[3]={name="Joined",realm="Silvermoon",role="DAMAGER"}
            eventFrames[1].scripts.OnEvent(eventFrames[1],"GROUP_ROSTER_UPDATE")
        ''',self.mpl)
        self.assertEqual(len(self.mpl.panel.groupPlayers),3)
        self.assertTrue(self.mpl.panel.playerTabs[3].shown)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertIsNone(self.mpl.downloadWindow)

    def test_unknown_realm_survives_request_and_is_resolved_before_storage(self):
        client=Client()
        reply=self.response(client)
        request=self.mpl.searchGroupWindow.request
        _,body=clipboard_protocol.unwrap_request(request)
        members=name_search.parse(body)
        self.assertEqual(members[1]['realm'],'')
        self.assertEqual(members[0]['realm'],'Draenor')
        self.assertIn('namesearch',request)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        player=self.mpl.searchGroupWindow.players[2]
        self.assertEqual(player.realm,'Silvermoon')
        self.assertTrue(player.loaded)
        self.assertEqual(len(self.mpl.GetProfile('Mirkowrr','Silvermoon')[0].dungeons),1)
        self.assertTrue(self.mpl.GetProfile('Mirkowrr','Silvermoon')[0].realmInferred)
        payload=unquote(unquote(reply.split('MPLB1\n',1)[1]).splitlines()[-1].split('\t')[6])
        self.assertEqual(self.mpl.Import(payload),1)
        self.assertTrue(self.mpl.GetProfile('Mirkowrr','Silvermoon')[0].realmInferred)
        self.mpl.ShowProfile('Mirkowrr','Silvermoon',None,True)
        self.assertIn(self.mpl.L['Match based on name and class; realm not confirmed in game.'],self.mpl.panel.footer.text)
        self.assertIsNone(self.mpl.GetProfile('Mirkowrr','Draenor')[0])
        # No network calls for repeated queries within the five-minute cache.
        self.mpl.ReceiveSearchGroupReply(self.response(client))
        self.assertEqual(len(client.calls),2)

    def test_member_tabs_and_profile_button_show_the_selected_player(self):
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response()),2)
        f=self.mpl.searchGroupWindow
        self.mpl.panel.playerTabs[2].scripts.OnClick(self.mpl.panel.playerTabs[2])
        self.assertEqual(f.selected,2)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertEqual(self.mpl.panel.realm,'Silvermoon')
        self.assertEqual(len(self.mpl.panel.groupPlayers),2)

    def test_received_group_opens_logs_immediately_with_all_player_tabs(self):
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response()),2)
        self.assertTrue(self.mpl.panel.shown)
        self.assertFalse(self.mpl.searchGroupWindow.shown)
        self.assertEqual(self.mpl.panel.name,'Frákkie')
        self.assertEqual(len(self.mpl.panel.playerTabs),2)
        tab=self.mpl.panel.playerTabs[2]
        tab.scripts.OnClick(tab)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertEqual(self.mpl.panel.realm,'Silvermoon')

    def test_loaded_tabs_remain_readable_after_listing_data_disappears(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.lua.execute('C_LFGList.GetSearchResultInfo=function() return nil end')
        tab=self.mpl.panel.playerTabs[2]
        tab.scripts.OnClick(tab)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertEqual(self.mpl.panel.realm,'Silvermoon')
        self.assertTrue(self.mpl.panel.playerTabs[2].selected)

    def test_failed_tabs_remain_readable_after_listing_data_disappears(self):
        self.mpl.ReceiveSearchGroupReply(self.response(Client(fail=True)))
        self.lua.execute('C_LFGList.GetSearchResultInfo=function() return nil end')
        tab=self.mpl.panel.playerTabs[2]
        tab.scripts.OnClick(tab)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertIn('Search/API unavailable',self.mpl.panel.emptyMessage.text)

    def test_search_menu_uses_the_standard_logs_exchange_for_group_resolution(self):
        self.mpl.companionInfo=self.lua.table_from(dict(capabilities=self.lua.table_from(dict(namesearch=True))))
        self.lua.execute('buttons={}; Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root)')
        self.assertEqual(len(self.lua.globals().buttons),2)
        self.lua.globals().buttons[1]()
        exchange=self.mpl.downloadWindow
        self.assertTrue(exchange.shown)
        self.assertFalse(self.mpl.searchGroupWindow.shown)
        self.assertIn('MPLQ2\nMPLN1\n',exchange.request)
        reply=clipboard_protocol.reply(exchange.request,realm_resolver.load_mappings(),self.cache,Client())
        exchange.edit.SetText(exchange.edit,reply)
        exchange.edit.scripts.OnTextChanged(exchange.edit)
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
        self.assertFalse(exchange.shown)
        self.assertTrue(self.mpl.panel.shown)
        self.assertEqual(len(self.mpl.panel.playerTabs),2)

    def test_search_menu_keeps_group_request_before_companion_handshake(self):
        # A reload clears session capabilities. Opening a group must still
        # negotiate the group protocol rather than silently opening its leader.
        self.mpl.companionInfo = None
        self.lua.execute('buttons={}; Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root); buttons[1]()')
        exchange = self.mpl.downloadWindow
        self.assertIsNotNone(exchange)
        self.assertTrue(exchange.shown)
        _, body = clipboard_protocol.unwrap_request(exchange.request)
        self.assertEqual([p['name'] for p in name_search.parse(body)], ['Frákkie', 'Mirkowrr'])

    def test_search_menu_keeps_group_request_with_older_companion(self):
        # Protocol negotiation already reports unsupported group requests.
        # Missing capabilities must not silently change the requested roster.
        self.mpl.companionInfo = self.lua.table_from(dict(capabilities=self.lua.table_from({})))
        self.lua.execute('buttons={}; Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root); buttons[1]()')
        self.assertIsNotNone(self.mpl.downloadWindow)
        self.assertIn('MPLQ2\nMPLN1\n', self.mpl.downloadWindow.request)

    def test_context_menu_log_link_is_a_url_with_and_without_saved_profile(self):
        for saved in (False,True):
            if saved:
                self.mpl.ReceiveSearchGroupReply(self.response())
            self.lua.execute('buttons={}; Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root); buttons[2]()')
            profile=self.mpl.GetProfile('Frákkie','Draenor')[0]
            self.assertEqual(self.mpl.copy.edit.text,self.mpl.URL('Frákkie','Draenor',profile))
            self.assertTrue(self.mpl.copy.edit.text.startswith('https://www.warcraftlogs.com/'))
            self.assertEqual(self.mpl.copy.title.text,self.mpl.L['Ссылка Warcraft Logs'])

    def test_reopening_a_fresh_search_group_does_not_start_another_exchange(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.ShowSearchGroupLogs(10)
        self.assertTrue(self.mpl.panel.shown)
        self.assertFalse(self.mpl.searchGroupWindow.shown)
        self.assertIsNone(self.lua.eval('function(f) return rawget(f,"requestID") end')(self.mpl.searchGroupWindow))
        if self.mpl.downloadWindow:
            self.assertFalse(self.mpl.downloadWindow.shown)

    def test_reopening_same_roster_under_new_listing_reuses_resolved_realms(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.ShowSearchGroupLogs(11)
        self.assertIsNone(self.mpl.downloadWindow)
        self.assertEqual(self.mpl.panel.searchPlayers[2].realm, 'Silvermoon')
        self.assertEqual(self.mpl.panel.searchPlayers[2].searchResultID, 11)

    def test_returning_to_previous_group_reuses_its_exact_roster(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.lua.execute('leaderName="Other-Draenor"')
        self.mpl.ShowSearchGroup(11)
        self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)
        self.lua.execute('leaderName="Frákkie-Draenor"')
        self.mpl.ShowSearchGroupLogs(12)
        self.assertIsNone(self.mpl.downloadWindow)
        self.assertEqual(self.mpl.panel.searchPlayers[2].realm, 'Silvermoon')

    def test_reopening_group_requests_only_stale_members(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        profile, _, _ = self.mpl.GetProfile('Mirkowrr', 'Silvermoon')
        profile.updated = '2000-01-01 00:00 UTC'
        self.mpl.ShowSearchGroupLogs(10)
        _, body = clipboard_protocol.unwrap_request(self.mpl.downloadWindow.request)
        self.assertEqual([p['name'] for p in name_search.parse(body)], ['Mirkowrr'])

    def test_fresh_stored_profile_recovers_missing_loaded_marker(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.searchGroupWindow.players[2].loaded = None
        self.mpl.ShowSearchGroupLogs(10)
        self.assertIsNone(self.mpl.downloadWindow)
        self.assertTrue(self.mpl.searchGroupWindow.players[2].loaded)

    def test_restored_roster_still_checks_profile_freshness(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        profile, _, _ = self.mpl.GetProfile('Mirkowrr', 'Silvermoon')
        profile.updated = '2000-01-01 00:00 UTC'
        self.mpl.ShowSearchGroupLogs(11)
        _, body = clipboard_protocol.unwrap_request(self.mpl.downloadWindow.request)
        members = name_search.parse(body)
        self.assertEqual([p['name'] for p in members], ['Mirkowrr'])
        self.assertEqual(members[0]['realm'], 'Silvermoon')

    def test_expired_roster_does_not_restore_unknown_realms(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.lua.execute('leaderName="Other-Draenor"')
        self.mpl.ShowSearchGroup(11)
        self.lua.execute('''
            local now=GetServerTime()
            GetServerTime=function() return now+6*3600 end
            leaderName="Frákkie-Draenor"
        ''')
        self.mpl.ShowSearchGroup(12)
        self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)

    def test_changed_authoritative_realm_is_not_overwritten_by_snapshot(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.lua.execute('searchMembers[2].name="Mirkowrr-Kazzak"')
        self.mpl.ShowSearchGroup(11)
        self.assertEqual(self.mpl.searchGroupWindow.players[2].realm, 'Kazzak')

    def test_roster_without_known_leader_realm_is_not_reused_across_listings(self):
        self.lua.execute('leaderName="Frákkie"')
        self.mpl.ShowSearchGroup(11)
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.assertEqual(self.mpl.searchGroupWindow.players[2].realm, 'Silvermoon')
        self.mpl.ShowSearchGroup(12)
        self.assertIsNone(self.mpl.searchGroupWindow.players[1].realm)
        self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)

    def test_partial_reply_opens_first_loaded_profile_and_keeps_failed_tab(self):
        self.mpl.searchGroupWindow.selected=2
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(Client(fail=True))),1)
        self.assertEqual(self.mpl.panel.name,'Frákkie')
        self.assertFalse(self.mpl.searchGroupWindow.shown)
        failed=self.mpl.panel.playerTabs[2]
        failed.scripts.OnClick(failed)
        self.assertFalse(self.mpl.searchGroupWindow.shown)
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertIn('Search/API unavailable',self.mpl.panel.emptyMessage.text)
        self.assertEqual(self.mpl.searchGroupWindow.selected,2)

    def test_group_import_opens_fresh_summary_instead_of_old_selected_spec(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.lua.execute('''
            local MPL=...
            local key=MPL.Key("Mirkowrr","Silvermoon")
            local old={}
            for k,v in pairs(MPL.GetProfile("Mirkowrr","Silvermoon","All specs")) do old[k]=v end
            old.spec="Arms"; old.updated="2026-10-13 00:00 UTC"
            MPL.StoreProfiles({old=old})
            MPL.SelectSpec("Mirkowrr","Silvermoon","Arms","DAMAGER")
        ''',self.mpl)
        self.mpl.searchGroupWindow.selected=2
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.assertEqual(self.mpl.panel.selectedSpec,'All specs')
        self.assertEqual(self.mpl.panel.profile.spec,'All specs')
        self.assertNotEqual(self.mpl.panel.profile.updated,'2026-10-13 00:00 UTC')

    def test_all_failures_are_shown_in_the_shared_panel_and_retry_uses_group_exchange(self):
        class Unavailable(Client):
            def __call__(self,args):
                raise ValueError('API unavailable')
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(Unavailable())),0)
        panel=self.mpl.panel
        self.assertTrue(panel.shown)
        self.assertFalse(self.mpl.searchGroupWindow.shown)
        self.assertIsNone(self.lua.globals().MPlusLogsSearchGroup)
        self.assertIn('API unavailable',panel.emptyMessage.text)
        self.assertFalse(panel.profile)
        panel.playerTabs[2].scripts.OnClick(panel.playerTabs[2])
        self.assertTrue(panel.playerTabs[2].selected)
        self.assertEqual(panel.name,'Mirkowrr')
        self.assertEqual(panel.lookup.text,'Mirkowrr')
        panel.loadButton.scripts.OnClick(panel.loadButton)
        self.assertTrue(self.mpl.downloadWindow.shown)
        self.assertEqual(self.mpl.downloadWindow.searchResultID,10)
        self.assertIn('MPLN1',self.mpl.downloadWindow.request)

    def test_changed_roster_allows_viewing_then_retry_uses_current_roster(self):
        self.mpl.ReceiveSearchGroupReply(self.response(Client(fail=True)))
        self.lua.execute('''
            searchMembers[3]={name="Joined",classFilename="WARRIOR",assignedRole="DAMAGER"}
            C_LFGList.GetSearchResultInfo=function()
                return {leaderName=leaderName,activityIDs={1},numMembers=#searchMembers}
            end
        ''')
        self.mpl.panel.playerTabs[2].scripts.OnClick(self.mpl.panel.playerTabs[2])
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')
        self.assertIn('Search/API unavailable',self.mpl.panel.emptyMessage.text)
        self.mpl.panel.loadButton.scripts.OnClick(self.mpl.panel.loadButton)
        self.assertTrue(self.mpl.downloadWindow.shown)
        self.assertFalse(self.mpl.searchGroupWindow.shown)
        _,body=clipboard_protocol.unwrap_request(self.mpl.downloadWindow.request)
        self.assertEqual([p['name'] for p in name_search.parse(body)],['Mirkowrr','Joined'])

    def test_authoritative_server_ids_are_independent_of_localized_names(self):
        args=type('Args',(),dict(name='Mirkowrr',server_slug='silvermoon'))()
        raw=Client()(args)
        char=raw['data']['characterData']['character']
        char['server']['id']=123
        raw['data']['worldData']={'server':{'id':123}}
        member=dict(name='Mirkowrr',region='eu',class_name='WARRIOR')
        for alias in ('Localized realm','Français','Español','Русский сервер','한국어','简体中文','繁體中文'):
            with self.subTest(alias=alias):
                self.assertIsNotNone(name_search.verified(raw,member,alias))
        raw['data']['worldData']['server']['id']=456
        self.assertIsNone(name_search.verified(raw,member,'silvermoon'))

    def test_retry_after_member_joins_uses_the_current_roster(self):
        old_reply=self.response()
        self.lua.execute('''
            searchMembers[3]={name="Joined",classFilename="WARRIOR",assignedRole="DAMAGER"}
            C_LFGList.GetSearchResultInfo=function()
                return {leaderName=leaderName,activityIDs={1},numMembers=#searchMembers}
            end
        ''')
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(old_reply),2)
        self.assertEqual(len(self.mpl.panel.searchPlayers),2)
        self.assertEqual(self.mpl.panel.name,'Frákkie')
        self.mpl.BeginSearchGroupRequest()
        _,body=clipboard_protocol.unwrap_request(self.mpl.searchGroupWindow.request)
        self.assertEqual([p['name'] for p in name_search.parse(body)],['Joined'])
        reply=clipboard_protocol.reply(self.mpl.searchGroupWindow.request,realm_resolver.load_mappings(),self.cache,Client())
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),1)
        self.assertTrue(all(p.loaded for p in self.mpl.searchGroupWindow.players.values()))

    def test_inflight_reply_survives_listing_disappearance(self):
        reply=self.response()
        self.lua.execute('C_LFGList.GetSearchResultInfo=function() return nil end')
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        self.assertTrue(self.mpl.panel.shown)
        self.mpl.panel.playerTabs[2].scripts.OnClick(self.mpl.panel.playerTabs[2])
        self.assertEqual(self.mpl.panel.name,'Mirkowrr')

    def test_inflight_reply_survives_member_leaving_or_reordering(self):
        reply=self.response()
        self.lua.execute('searchMembers[1],searchMembers[2]=searchMembers[2],searchMembers[1]')
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        self.assertEqual(self.mpl.panel.searchPlayers[1].name,'Frákkie')
        self.assertEqual(self.mpl.panel.searchPlayers[2].name,'Mirkowrr')

    def test_failed_member_stays_visible_in_profile_tabs(self):
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(Client(fail=True))),1)
        f=self.mpl.searchGroupWindow
        self.mpl.OpenSearchGroupProfile(f.selected)
        self.assertEqual(len(self.mpl.panel.searchPlayers),2)
        tab=self.mpl.panel.playerTabs[2]
        self.assertTrue(tab.shown)
        tab.scripts.OnClick(tab)
        self.assertEqual(f.selected,2)
        self.assertIn('Search/API unavailable',self.mpl.panel.emptyMessage.text)

    def test_ambiguous_match_requires_realm_choice_inside_addon(self):
        from test_name_search_roles import RoleClient
        client=RoleClient(specs=('Arms','Fury'))
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(client)),1)
        player=self.mpl.searchGroupWindow.players[2]
        self.assertIsNone(player.realm)
        self.assertEqual(len(player.candidates),2)
        self.assertFalse(player.loaded)
        f=self.mpl.searchGroupWindow
        self.mpl.OpenSearchGroupProfile(2)
        choices=self.mpl.panel.searchChoices
        self.assertIn('WCL',choices[1].text)
        self.assertIn('Best %',choices[1].text)
        self.assertIn('Arms',choices[1].text)
        self.assertGreaterEqual(choices[1].height,50)
        choices[2].scripts.OnClick(choices[2])
        reply=clipboard_protocol.reply(f.request,realm_resolver.load_mappings(),self.cache,client)
        self.assertEqual(len(f.requestPlayers),1)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),1)
        self.assertEqual(player.realm,'Silvermoon')
        self.assertTrue(player.loaded)
        self.assertFalse(self.mpl.panel.searchChoices[1].shown)
        self.assertTrue(self.mpl.panel.specButton.shown)

    def test_paladins_with_opposite_role_history_resolve_through_clipboard(self):
        from test_name_search_roles import RoleClient
        class Paladins(RoleClient):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.name=='Mirkowrr':
                    raw['data']['characterData']['character']['classID']=71
                    raw['data']['gameData']['classes'].append(dict(id=71,name='Paladin'))
                return raw
        self.lua.execute('searchMembers[2].classFilename="PALADIN"')
        self.mpl.UpdateSearchGroupRoster(10)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(Paladins(specs=('Protection','Retribution')))),2)
        player=self.mpl.searchGroupWindow.players[2]
        self.assertEqual(player.realm,'Silvermoon')
        self.assertTrue(player.loaded)
        self.assertIsNone(player.candidates)

    def test_candidate_metadata_is_validated_before_any_profile_is_stored(self):
        reply=self.response(Client(realms=('silvermoon','draenor')))
        head,body=reply.split('MPLB1\n',1)
        lines=unquote(body).splitlines()
        original=next(i for i,line in enumerate(lines) if line.startswith('C\t'))
        for field,bad in ((6,'-1'),(7,'nan'),(8,'inf'),(9,'101'),(10,'1.5'),(11,'%7CHplayer:test')):
            with self.subTest(field=field,bad=bad):
                edited=list(lines); row=edited[original].split('\t'); row[field]=bad
                edited[original]='\t'.join(row)
                count,error=self.mpl.ReceiveSearchGroupReply(head+'MPLB1\n'+quote('\n'.join(edited)+'\n',safe=''))
                self.assertIsNone(count)
                self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)

    def test_legacy_candidates_show_missing_data_hint(self):
        reply=self.response(Client(realms=('silvermoon','draenor')))
        head,body=reply.split('MPLB1\n',1)
        lines=unquote(body).splitlines()
        lines=['\t'.join(line.split('\t')[:6]) if line.startswith('C\t') else line for line in lines]
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(head+'MPLB1\n'+quote('\n'.join(lines)+'\n',safe='')),1)
        self.mpl.OpenSearchGroupProfile(2)
        self.assertIn(self.mpl.L['Role data unavailable; update Companion'],self.mpl.panel.searchChoices[1].text)

    def test_empty_season_profile_does_not_prove_a_different_identity(self):
        class EmptySeason(Client):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.server_slug=='neptulon':
                    char=raw['data']['characterData']['character']
                    for metric in ('damage','healing'):
                        char[metric]['throughputRankings']=[]
                        char[metric]['allStars']=[]
                        for row in char[metric]['rankings']:
                            row.update(totalKills=0,rankPercent=None,medianPercent=None,bestAmount=0)
                return raw
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(EmptySeason(realms=('neptulon','stormscale')))),1)
        player=self.mpl.searchGroupWindow.players[2]
        self.assertIsNone(player.realm)
        self.assertFalse(player.loaded)
        self.assertEqual(len(player.candidates),2)

    def test_hidden_candidate_is_not_silently_discarded_as_empty(self):
        class HiddenCandidate(Client):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.server_slug=='neptulon': raw['data']['characterData']['character']['hidden']=True
                return raw
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(HiddenCandidate(realms=('neptulon','stormscale')))),1)
        self.assertFalse(bool(self.mpl.searchGroupWindow.players[2].loaded))
        self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)
        self.assertEqual(self.mpl.searchGroupWindow.players[2].error,self.mpl.L['Логи этого персонажа скрыты в Warcraft Logs. Доступ к ним не разрешён для текущего аккаунта.'])

    def test_hidden_logs_preserve_unique_verified_realm_and_show_localized_reason(self):
        class Hidden(Client):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.name=='Mirkowrr': raw['data']['characterData']['character']['hidden']=True
                return raw
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(Hidden())),1)
        player=self.mpl.searchGroupWindow.players[2]
        self.assertEqual(player.realm,'Silvermoon')
        self.mpl.OpenSearchGroupProfile(2)
        self.assertEqual(self.mpl.panel.character.text,'Mirkowrr — Silvermoon')
        self.assertEqual(self.mpl.panel.emptyMessage.text,self.mpl.L['Логи этого персонажа скрыты в Warcraft Logs. Доступ к ним не разрешён для текущего аккаунта.'])
        self.assertNotIn('Rankings hidden',self.mpl.panel.emptyMessage.text)

    def test_failure_identity_is_validated_before_any_profile_is_stored(self):
        class Hidden(Client):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.name=='Mirkowrr': raw['data']['characterData']['character']['hidden']=True
                return raw
        reply=self.response(Hidden())
        head,body=reply.split('MPLB1\n',1)
        lines=unquote(body).splitlines()
        row=lines[-1].split('\t')
        self.assertEqual(len(row),7)
        row[5]='MAGE'
        lines[-1]='\t'.join(row)
        count,error=self.mpl.ReceiveSearchGroupReply(head+'MPLB1\n'+quote('\n'.join(lines)+'\n',safe=''))
        self.assertIsNone(count)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)

    def test_wrong_class_and_failed_search_do_not_block_healthy_member(self):
        for client in (Client(wrong_class=True),Client(fail=True)):
            with self.subTest(client=client):
                self.setUp()
                self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(client)),1)
                self.assertTrue(self.mpl.searchGroupWindow.players[1].loaded)
                self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)
                self.assertIsNotNone(self.mpl.searchGroupWindow.players[2].error)

    def test_long_unicode_member_error_does_not_reject_healthy_profiles(self):
        class LongError(Client):
            def __call__(self,args):
                if args.name=='Mirkowrr': raise ValueError('Ошибка ' * 100)
                return super().__call__(args)
        reply=self.response(LongError())
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),1)
        self.assertTrue(self.mpl.searchGroupWindow.players[1].loaded)
        self.assertIn('Ошибка',self.mpl.searchGroupWindow.players[2].error)

    def test_game_confirmed_realm_is_not_overwritten_by_an_older_unknown_realm_request(self):
        reply=self.response()
        self.lua.execute('searchMembers[2].name="Mirkowrr-Draenor"')
        self.mpl.UpdateSearchGroupRoster(10)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        active=self.mpl.searchGroupWindow.players[2]
        self.assertEqual(active.realm,'Draenor')
        self.assertFalse(active.loaded)
        self.assertIsNotNone(self.mpl.GetProfile('Mirkowrr','Silvermoon')[0])

    def test_roster_disappearing_before_exchange_begins_does_not_crash(self):
        self.lua.execute('''
            local MPL=...
            local original=MPL.CollectSearchGroup
            local calls=0
            MPL.CollectSearchGroup=function(...)
                calls=calls+1
                if calls>2 then return nil end
                return original(...)
            end
        ''',self.mpl)
        self.mpl.ShowSearchGroupLogs(10)
        self.assertTrue(self.mpl.downloadWindow.shown)
        self.assertTrue(self.mpl.downloadWindow.request)

    def test_loading_from_existing_tab_includes_newly_joined_missing_member(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.join_search_group()
        cooling,remaining=self.mpl.UpdateProfileLoadButton()
        self.assertFalse(cooling)
        self.mpl.panel.loadButton.scripts.OnClick(self.mpl.panel.loadButton)
        exchange=self.mpl.downloadWindow
        self.assertEqual(exchange.searchResultID,10)
        _,body=clipboard_protocol.unwrap_request(exchange.request)
        self.assertEqual([p['name'] for p in name_search.parse(body)],['Joined'])

    def test_uncached_search_failure_does_not_block_another_cached_identity(self):
        class CachedSearch:
            results={('eu','mirkowrr'):[dict(realm_slug='silvermoon')]}
            def prepare(self,members): raise ValueError('API unavailable')
            def for_member(self,member): return self.results[(member['region'],member['name'].casefold())]
        self.join_search_group('Uncached')
        client=Client();client.name_search=CachedSearch()
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(client)),2)
        self.assertTrue(self.mpl.searchGroupWindow.players[2].loaded)
        self.assertIn('API unavailable',self.mpl.searchGroupWindow.players[3].error)

    def test_finishing_newcomer_loading_keeps_selected_metric(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.panel.viewMetric='hps'
        self.join_search_group()
        self.mpl.ShowSearchGroupLogs(10)
        exchange=self.mpl.downloadWindow
        reply=clipboard_protocol.reply(exchange.request,realm_resolver.load_mappings(),self.cache,Client())
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),1)
        self.assertEqual(self.mpl.panel.name,'Frákkie')
        self.assertEqual(self.mpl.panel.viewMetric,'hps')

    def test_role_change_during_loading_does_not_duplicate_the_player(self):
        reply=self.response()
        self.lua.execute('searchMembers[1].assignedRole="TANK"')
        self.mpl.UpdateSearchGroupRoster(10)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        self.assertEqual(len(self.mpl.searchGroupWindow.players),2)
        self.assertEqual(self.mpl.searchGroupWindow.players[1].role,'TANK')

    def test_late_specialization_metadata_updates_without_losing_metric(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.panel.viewMetric='hps'
        self.lua.execute('searchMembers[1].specName="Танцующий с ветром"')
        self.mpl.UpdateSearchGroupRoster(10)
        self.assertEqual(self.mpl.searchGroupWindow.players[1].specID,269)
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'Танцующий с ветром')
        self.assertEqual(self.mpl.panel.viewMetric,'hps')

    def test_unrelated_reply_is_rejected_but_leader_change_preserves_requested_logs(self):
        reply=self.response()
        f=self.mpl.searchGroupWindow
        count,error=self.mpl.ReceiveSearchGroupReply(reply.replace(f.requestID,'999-999',1))
        self.assertIsNone(count)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)
        self.lua.execute('leaderName="Replacement-Draenor"')
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        self.assertEqual(self.mpl.panel.name,'Frákkie')

    def test_starting_a_new_request_still_rejects_the_previous_reply(self):
        reply=self.response()
        self.mpl.BeginSearchGroupRequest()
        count,error=self.mpl.ReceiveSearchGroupReply(reply)
        self.assertIsNone(count)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)

    def test_forged_profile_rejected_before_any_member_is_stored(self):
        reply=self.response()
        head,body=reply.split('MPLB1\n',1)
        body=unquote(body)
        lines=body.splitlines()
        row=lines[-1].split('\t')
        row[5]='MAGE'
        lines[-1]='\t'.join(row)
        count,error=self.mpl.ReceiveSearchGroupReply(head+'MPLB1\n'+quote('\n'.join(lines)+'\n',safe=''))
        self.assertIsNone(count)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)

    def test_missing_member_name_does_not_invent_an_identity(self):
        self.lua.execute('searchMembers[2].name=nil')
        self.assertIsNone(self.mpl.CollectSearchGroup(10))

    def test_malformed_request_and_missing_capability_are_rejected(self):
        for body in ('MPLN1\n','MPLN1\nN\t1\teu\t\tName\tFAKE\tDAMAGER\tsearch\n'):
            with self.assertRaises(ValueError): name_search.parse(body)
        response=clipboard_protocol.reply('MPLS1\n123-1\nMPLN1\nN\t1\teu\t\tName\tWARRIOR\tDAMAGER\tsearch\n',
            realm_resolver.load_mappings(),self.cache,Client())
        self.assertTrue(response.startswith('MPLE1\n'))

    def test_older_companion_can_return_upgrade_message_without_api_calls(self):
        self.mpl.BeginSearchGroupRequest()
        request=self.mpl.searchGroupWindow.request
        self.assertIn('\nMPLQ2\nMPLN1\n',request)
        client=Client()
        with patch.object(clipboard_protocol,'CAPABILITIES',clipboard_protocol.CAPABILITIES-{'namesearch'}):
            reply=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,client)
        count,error=self.mpl.ReceiveSearchGroupReply(reply)
        self.assertIsNone(count)
        self.assertIn('Companion',error)
        self.assertEqual(len(client.calls),0)

    def test_incomplete_candidate_verification_does_not_become_a_unique_match(self):
        class Partial(Client):
            def __call__(self,args):
                if args.server_slug=='zzbroken': raise ValueError('WCL unavailable')
                return super().__call__(args)
        client=Partial(realms=('silvermoon','zzbroken'))
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(client)),1)
        self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)
        self.assertIsNotNone(self.mpl.searchGroupWindow.players[2].error)

    def test_healer_metric_survives_the_full_exchange(self):
        self.lua.execute('searchMembers[2].assignedRole="HEALER"')
        self.mpl.ShowSearchGroup(10)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response()),2)
        self.assertEqual(self.mpl.GetProfile('Mirkowrr','Silvermoon')[0].metric,'hps')

    def test_search_link_requires_exact_host_name_and_region(self):
        url='https://www.warcraftlogs.com/character/eu/silvermoon/mirkowrr'
        self.assertIsNotNone(name_search_browser.candidate(url,'Mirkowrr','eu'))
        for wrong in (url.replace('warcraftlogs.com','example.com'),url.replace('/eu/','/us/'),url+'x'):
            self.assertIsNone(name_search_browser.candidate(wrong,'Mirkowrr','eu'))

    def test_invalid_class_metadata_is_not_accepted(self):
        member={'name':'Mirkowrr','region':'eu','class_name':'WARRIOR'}
        for raw in ([],{'data':[]},{'data':{'characterData':{'character':{'name':'Mirkowrr','classID':51}}}}):
            with self.assertRaises(ValueError): name_search.verified(raw,member,'silvermoon')

    def test_browser_waits_for_late_candidates_and_page_completion(self):
        snapshot=name_search_browser.SearchSnapshot()
        first='https://www.warcraftlogs.com/character/eu/gordunni/куратор'
        second='https://www.warcraftlogs.com/character/eu/soulflayer/куратор'
        page=dict(state='ready',complete=False,urls=[first])
        self.assertIsNone(snapshot.update(page,'Куратор','eu',0))
        self.assertIsNone(snapshot.update(page,'Куратор','eu',10))
        page['complete']=True
        self.assertIsNone(snapshot.update(page,'Куратор','eu',11))
        page['urls'].append(second)
        self.assertIsNone(snapshot.update(page,'Куратор','eu',12))
        self.assertIsNone(snapshot.update(page,'Куратор','eu',13))
        result=snapshot.update(page,'Куратор','eu',14)
        self.assertEqual({c['realm_slug'] for c in result},{'gordunni','soulflayer'})

    def test_localized_realm_link_matches_canonical_api_realm(self):
        class RussianRealm(Client):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.server_slug=='ревущии-фьорд':
                    raw['data']['characterData']['character']['server'].update(
                        name='Ревущий фьорд',slug='howling-fjord')
                return raw
        client=RussianRealm(realms=('ревущии-фьорд',))
        self.lua.execute('searchMembers[2].name="Газоваяфура"')
        self.mpl.ShowSearchGroup(10)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(client)),2)
        self.assertEqual(self.mpl.searchGroupWindow.players[2].realm,'Ревущий фьорд')

    def test_unrelated_realm_is_still_rejected(self):
        args=type('Args',(),dict(name='Mirkowrr',server_slug='silvermoon'))()
        raw=Client()(args)
        member=dict(name='Mirkowrr',region='eu',class_name='WARRIOR')
        self.assertIsNone(name_search.verified(raw,member,'draenor'))

    def test_realm_display_name_accepts_localized_search_urls(self):
        args=type('Args',(),dict(name='Куратор',server_slug='gordunni'))()
        raw=Client()(args)
        char=raw['data']['characterData']['character']
        char['server'].update(name='Гордунни',slug='gordunni')
        member=dict(name='Куратор',region='eu',class_name='WARRIOR')
        self.assertIsNotNone(name_search.verified(raw,member,'гордунни'))
        char['server'].update(name='Ревущий фьорд',slug='howling-fjord')
        self.assertIsNotNone(name_search.verified(raw,member,'ревущии-фьорд'))
        self.assertIsNone(name_search.verified(raw,member,'гордунни'))
        self.assertIsNone(name_search.verified(raw,dict(member,region='us'),'ревущии-фьорд'))

    def test_search_diagnostic_reports_class_rejection_without_raw_data(self):
        self.mpl.ReceiveSearchGroupReply(self.response(Client(wrong_class=True)))
        report=json.loads((self.cache/'name-search-diagnostic.json').read_text(encoding='utf-8'))
        last=report['members'][1]
        self.assertEqual(last['name'],'Mirkowrr')
        self.assertEqual(last['candidates'][0]['rejected'],['class'])
        self.assertEqual(last['candidates'][0]['actual_class'],'MONK')
        self.assertNotIn('raw',json.dumps(report))

    def test_restart_reuses_raw_reply_instead_of_hitting_profile_cooldown(self):
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(Client())),2)
        class Cooling(Client):
            def __call__(self,args):
                self.calls.append(args)
                raise ValueError('Profile refresh is cooling down; retry after 3038 seconds')
        restarted=Cooling()
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(restarted)),2)
        self.assertEqual(restarted.calls,[])

    def test_search_reuses_two_hour_old_disk_profile_after_restart(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        for path in self.cache.glob('*.json'):
            record=json.loads(path.read_text(encoding='utf-8'))
            if 'raw' not in record: continue
            record['fetched_at']-=7200
            path.write_text(json.dumps(record),encoding='utf-8')
        restarted=Client()
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(restarted)),2)
        self.assertEqual(restarted.calls,[])

    def test_search_refreshes_profiles_older_than_shared_ttl(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        for path in self.cache.glob('*.json'):
            record=json.loads(path.read_text(encoding='utf-8'))
            if 'raw' not in record: continue
            record['fetched_at']-=25*3600
            path.write_text(json.dumps(record),encoding='utf-8')
        restarted=Client()
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(restarted)),2)
        self.assertEqual(len(restarted.calls),2)

    def test_search_role_switch_reuses_raw_dual_profile(self):
        client=Client()
        self.mpl.ReceiveSearchGroupReply(self.response(client))
        self.lua.execute('searchMembers[2].assignedRole="HEALER"')
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(client)),1)
        self.assertEqual(len(client.calls),2)

    def test_search_prefers_newer_disk_profile_over_its_memory_copy(self):
        import time
        client=Client()
        self.mpl.ReceiveSearchGroupReply(self.response(client))
        now=time.time()
        for path in self.cache.glob('*.json'):
            record=json.loads(path.read_text(encoding='utf-8'))
            if 'raw' not in record: continue
            record['fetched_at']=now+5
            char=record['raw']['data']['characterData']['character']
            char['damage']['throughputRankings']['12825']['best_per_second_amount']=999000
            path.write_text(json.dumps(record),encoding='utf-8')
        with patch.object(name_search.time,'time',return_value=now+10):
            self.assertEqual(self.mpl.ReceiveSearchGroupReply(self.response(client)),2)
        self.assertEqual(len(client.calls),2)
        self.assertEqual(self.mpl.panel.profile.dungeons[1].amount,999000)

    def test_cached_summary_preserves_the_actual_fetch_date(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        expected=None
        for path in self.cache.glob('*.json'):
            record=json.loads(path.read_text(encoding='utf-8'))
            if 'fetched_at' not in record: continue
            record['fetched_at']-=600
            expected=datetime.fromtimestamp(record['fetched_at'],timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            path.write_text(json.dumps(record),encoding='utf-8')
        client=Client()
        self.mpl.ReceiveSearchGroupReply(self.response(client))
        self.assertEqual(client.calls,[])
        self.assertEqual(self.mpl.panel.profile.updated,expected)

    def test_name_search_does_not_reuse_another_cache_scope(self):
        first=Client(); first.cache_scope='account-one'
        self.mpl.ReceiveSearchGroupReply(self.response(first))
        second=Client(); second.cache_scope='account-two'
        self.mpl.ReceiveSearchGroupReply(self.response(second))
        self.assertEqual(len(second.calls),2)

    def test_browser_check_notifies_companion_and_success_is_cached(self):
        notifications=[]
        search=self.browser(status=notifications.append)
        class Process:
            returncode=0
            polls=0
            def poll(self):
                self.polls+=1
                return None if self.polls==1 else 0
        def launch(command,**kwargs):
            target=Path(command[-1])
            target.write_text(json.dumps({'state':'found','candidates':[{'realm_slug':'silvermoon'}]}),encoding='utf-8')
            Path(str(target)+'.verification').write_text('1',encoding='ascii')
            return Process()
        with patch.object(name_search.subprocess,'Popen',side_effect=launch) as spawn,patch.object(name_search.time,'sleep'):
            self.assertEqual(search('Mirkowrr','eu'),[{'realm_slug':'silvermoon'}])
            self.assertEqual(search('Mirkowrr','eu'),[{'realm_slug':'silvermoon'}])
        self.assertEqual(spawn.call_count,1)
        self.assertEqual(len(notifications),1)

    def test_cancellation_terminates_only_the_owned_browser_worker(self):
        from unittest.mock import Mock
        cancel=Mock();cancel.is_set.return_value=True
        process=Mock();process.poll.return_value=None
        search=self.browser(cancel=cancel)
        with patch.object(name_search.subprocess,'Popen',return_value=process):
            with self.assertRaises(ValueError): search('Mirkowrr','eu')
        process.terminate.assert_called_once()
        process.wait.assert_called_once()


if __name__=='__main__': unittest.main()
