"""Party/applicant tabs and one shared Companion exchange."""
import unittest
import copy
from unittest.mock import patch

import test_batch
import test_addon
import clipboard_protocol
import realm_resolver


class GroupProfileTests(unittest.TestCase):
    setUp = test_batch.BatchTests.setUp
    players = test_batch.BatchTests.players
    fetch = test_batch.BatchTests.fetch
    flush = test_batch.BatchTests.flush

    def party(self):
        self.lua.execute('''
            UnitExists=function(unit) return unit=="player" or unit:match("^party[1-4]$")~=nil end
            UnitFullName=function(unit)
                return unit=="player" and "Alice" or "Member"..unit:sub(-1),"Гордунни"
            end
            UnitGroupRolesAssigned=function(unit) return unit=="player" and "HEALER" or "DAMAGER" end
            IsInRaid=function() return false end
        ''')

    def test_slash_opens_five_tabs_including_self_and_one_batch(self):
        self.party()
        self.lua.globals().SlashCmdList.MPLUSLOGS("")
        f = self.mpl.panel
        self.assertEqual(len(f.groupPlayers), 5)
        self.assertEqual(len(f.playerTabs), 5)
        self.assertEqual(f.name, "Alice")
        self.assertEqual(len(self.mpl.pendingReply.players), 5)
        self.assertIn("MPLQ2\n", self.mpl.downloadWindow.request)
        f.playerTabs[4].scripts.OnClick()
        self.assertEqual(f.name, "Member3")
        self.assertEqual(len(f.groupPlayers), 5)
        self.assertFalse(f.inviteButton.shown)

    def open_unit_menu(self, name):
        self.lua.execute('''
            eventFrames={}
            local original=CreateFrame
            CreateFrame=function(...) local f=original(...); eventFrames[#eventFrames+1]=f; return f end
        ''')
        self.lua.execute("return assert(loadstring(...))", (test_addon.ROOT / "Integration.lua").read_text(encoding="utf-8"))("MPlusLogs", self.mpl)
        self.lua.execute('''
            eventFrames[1].scripts.OnEvent(eventFrames[1],"PLAYER_LOGIN")
            menuRoot={}
            function menuRoot:CreateDivider() end
            function menuRoot:CreateButton(_,callback) if not self.callback then self.callback=callback end end
        ''')
        self.lua.globals().Menu.callbacks.MENU_UNIT_PARTY(None, self.lua.globals().menuRoot,
            self.lua.table_from({'name':name,'realm':'Гордунни'}))
        self.lua.globals().menuRoot.callback()

    def test_party_menu_opens_whole_party_with_clicked_member_selected(self):
        self.party()
        self.open_unit_menu('Member3')
        f=self.mpl.panel
        self.assertEqual(f.name,'Member3')
        self.assertEqual(len(f.groupPlayers),5)
        self.assertEqual(len(self.mpl.pendingReply.players),5)
        f.playerTabs[2].scripts.OnClick()
        self.assertEqual(f.name,'Member1')
        self.assertEqual(len(f.groupPlayers),5)

    def test_party_menu_does_not_replace_unrelated_character_with_party(self):
        self.party()
        self.open_unit_menu('Other')
        self.assertEqual(self.mpl.panel.name,'Other')
        self.assertNotEqual(self.lua.eval('type')(self.mpl.panel.groupPlayers),'table')

    def test_applicant_group_keeps_clicked_member_and_only_its_application(self):
        self.mpl.ShowProfile("Bob", "Гордунни", self.players()[2])
        f = self.mpl.panel
        self.assertEqual(f.name, "Bob")
        self.assertEqual(len(f.groupPlayers), 2)
        self.assertEqual(f.groupPlayers[1].memberIndex, 1)
        f.playerTabs[1].scripts.OnClick()
        self.assertEqual(f.name, "Alice")
        self.assertEqual(f.applicant.memberIndex, 1)
        self.assertEqual(f.applicant.applicantID, 10)

    def test_load_button_in_party_tab_keeps_whole_party_request(self):
        self.party()
        self.mpl.ShowGroupProfiles(self.mpl.CollectParty())
        f = self.mpl.panel
        f.playerTabs[3].scripts.OnClick()
        f.loadButton.scripts.OnClick()
        self.assertTrue(self.mpl.pendingReply.batch)
        self.assertEqual(len(self.mpl.pendingReply.players), 5)
        request = self.mpl.downloadWindow.request
        response = clipboard_protocol.reply(request, realm_resolver.load_mappings(), self.cache, self.fetch)
        self.assertEqual(self.mpl.ReceiveReply(response, True), 5)
        self.assertEqual(f.name, "Member2")
        f.playerTabs[2].scripts.OnClick()
        self.assertTrue(f.profile)
        self.assertTrue(f.scroll.shown)

    def test_party_refresh_uses_current_selected_spec_instead_of_opening_snapshot(self):
        self.party()
        self.mpl.ShowGroupProfiles(self.mpl.CollectParty())
        # The window initially captured All specs. The user then opens an older
        # Arms profile and asks to refresh it without closing the party window.
        self.lua.execute('''
            local p={name="Member2",realm="Гордунни",region="eu",spec="Arms",role="DAMAGER",
                metric="dps",dual=true,season="test",updated="2026-10-10 04:00 UTC",source="WCL API",dungeons={}}
            MPlusLogs.StoreProfiles({p})
            MPlusLogs.SelectSpec("Member2","Гордунни","Arms","DAMAGER")
        ''')
        f = self.mpl.panel
        f.playerTabs[3].scripts.OnClick()
        self.assertTrue(f.stale)
        f.loadButton.scripts.OnClick()
        self.assertIn('Arms', self.mpl.downloadWindow.request)
        response = clipboard_protocol.reply(self.mpl.downloadWindow.request, realm_resolver.load_mappings(), self.cache, self.fetch)
        self.mpl.ReceiveReply(response, True)
        self.assertEqual(f.profile.spec, 'Arms')
        self.assertFalse(f.stale)

    def test_fresh_aggregate_does_not_skip_stale_selected_spec(self):
        self.party()
        self.mpl.ShowGroupProfiles(self.mpl.CollectParty())
        self.lua.execute('''
            local function stored(spec,updated)
                return {name="Member2",realm="Гордунни",region="eu",spec=spec,role="DAMAGER",
                    metric="dps",dual=true,season="test",updated=updated,source="WCL API",dungeons={}}
            end
            MPlusLogs.StoreProfiles({stored("Arms","2026-10-10 04:00 UTC")})
            MPlusLogs.StoreProfiles({stored("All specs","2026-10-12 04:00 UTC")})
            MPlusLogs.SelectSpec("Member2","Гордунни","Arms","DAMAGER")
        ''')
        old_pending = self.mpl.pendingReply.players[3]
        pending = self.mpl.FilterFreshProfiles(self.mpl.panel.groupPlayers)[0]
        selected = next(player for player in pending.values() if player.name == 'Member2')
        self.assertEqual(selected.spec, 'Arms')
        self.assertEqual(old_pending.spec, '')
        self.assertEqual(self.mpl.panel.groupPlayers[3].spec, 'All specs')

    def test_load_button_in_applicant_tab_keeps_application_group(self):
        self.mpl.ShowProfile("Bob", "Гордунни", self.players()[2])
        self.mpl.panel.loadButton.scripts.OnClick()
        self.assertTrue(self.mpl.pendingReply.batch)
        self.assertEqual(len(self.mpl.pendingReply.players), 2)

    def test_batch_reply_refreshes_selected_tab_and_keeps_hidden_member(self):
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        f = self.mpl.panel
        f.playerTabs[2].scripts.OnClick()
        request = self.mpl.downloadWindow.request
        response = clipboard_protocol.reply(request, realm_resolver.load_mappings(), self.cache, self.fetch)
        self.assertEqual(self.mpl.ReceiveReply(response, True), 1)
        self.assertEqual(f.name, "Bob")
        self.assertEqual(len(f.groupPlayers), 2)
        self.assertIn("скрыты", f.footer.text)
        f.playerTabs[1].scripts.OnClick()
        self.assertEqual(f.name, "Alice")
        self.assertTrue(f.scroll.shown)
        self.assertEqual(f.profile.metric, "hps")

    def test_fresh_profiles_skip_download_and_unrelated_lookup_clears_tabs(self):
        self.lua.execute('''
            MPlusLogs.FilterFreshProfiles=function() return {},2 end
        ''')
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.downloadWindow)
        f = self.mpl.panel
        self.mpl.ShowProfile("Other", "Гордунни")
        self.assertFalse(f.playerTabs[1].shown)
        self.assertFalse(f.playerTabs[2].shown)

    def test_refresh_of_fresh_party_does_not_open_empty_exchange_or_clear_pending(self):
        self.lua.execute('MPlusLogs.FilterFreshProfiles=function() return {},2 end')
        self.mpl.ShowProfile('Alice', 'Гордунни', self.players()[1])
        self.lua.execute('MPlusLogs.pendingReply={id="other-request"}')
        self.mpl.panel.loadButton.scripts.OnClick()
        self.assertIsNone(self.mpl.downloadWindow)
        self.assertEqual(self.mpl.pendingReply.id, 'other-request')

    def test_old_batch_reply_does_not_reopen_group_after_manual_lookup(self):
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        request = self.mpl.downloadWindow.request
        self.mpl.ShowProfile("Other", "Гордунни")
        response = clipboard_protocol.reply(request, realm_resolver.load_mappings(), self.cache, self.fetch)
        self.mpl.ReceiveReply(response, True)
        self.assertEqual(self.mpl.panel.name, "Other")
        self.assertFalse(self.mpl.panel.playerTabs[1].shown)

    def test_request_filters_fresh_member_but_keeps_both_tabs(self):
        self.lua.execute('''
            MPlusLogsDB.profiles[MPlusLogs.Key("Alice","Гордунни")]={
                updated="2026-10-12 04:00 UTC",metric="hps",dual=true,spec="All specs"}
        ''')
        self.mpl.ShowProfile("Bob", "Гордунни", self.players()[2])
        self.assertEqual(len(self.mpl.panel.groupPlayers), 2)
        self.assertEqual(len(self.mpl.pendingReply.players), 1)
        self.assertEqual(self.mpl.pendingReply.players[1].name, "Bob")

    def test_spec_refresh_preserves_group_tabs_without_new_request(self):
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        request_id = self.mpl.pendingReply.id
        self.mpl.ShowProfile("Alice", "Гордунни", self.mpl.panel.applicant, True)
        self.assertEqual(len(self.mpl.panel.groupPlayers), 2)
        self.assertEqual(self.mpl.pendingReply.id, request_id)
        self.assertTrue(self.mpl.panel.playerTabs[2].shown)

    def test_party_skips_unavailable_and_duplicate_identity(self):
        self.party()
        self.lua.execute('''
            UnitFullName=function(unit)
                if unit=="party4" then return nil end
                if unit=="party3" then return "Alice","Гордунни" end
                return unit=="player" and "Alice" or unit,"Гордунни"
            end
        ''')
        self.assertEqual(len(self.mpl.CollectParty()), 3)

    def test_single_saved_spec_can_load_other_specs_without_reloading_party(self):
        self.party()
        self.mpl.SelectSpec('Member2', 'Гордунни', 'Subtlety', 'DAMAGER')
        calls = []
        def fetch(args):
            calls.append(args.name)
            raw = self.fetch(args)
            char = raw['data']['characterData']['character']
            char['damage']['allStars'] = [{'spec':'Subtlety','points':3000}, {'spec':'Assassination','points':2000}]
            char['damage']['rankings'][0]['spec'] = 'Subtlety'
            char['healing'] = copy.deepcopy(char['damage'])
            return raw
        self.mpl.ShowGroupProfiles(self.mpl.CollectParty())
        response = clipboard_protocol.reply(self.mpl.downloadWindow.request, realm_resolver.load_mappings(), self.cache, fetch)
        self.assertEqual(self.mpl.ReceiveReply(response, True), 5)
        f = self.mpl.panel
        f.playerTabs[3].scripts.OnClick()
        self.assertEqual(set(self.mpl.ProfileSpecs('Member2', 'Гордунни').values()), {'Subtlety'})
        self.assertTrue(f.specButton.canSelectSpecs)
        self.assertTrue(f.specButton.arrow.shown)
        self.lua.execute('''
            MenuUtil={CreateContextMenu=function(_,build)
                specActions={}
                build(nil,{CreateTitle=function() end,CreateRadio=function() end,CreateDivider=function() end,
                    CreateButton=function(_,text,callback) specActions[text]=callback end})
            end}
        ''')
        f.specButton.scripts.OnClick()
        self.lua.globals().specActions['Загрузить другие специализации']()
        self.assertFalse(self.mpl.pendingReply.batch)
        self.assertTrue(self.mpl.pendingReply.includeSpecs)
        calls.clear()
        response = clipboard_protocol.reply(self.mpl.downloadWindow.request, realm_resolver.load_mappings(), self.cache, fetch)
        count, error = self.mpl.ReceiveReply(response, True)
        self.assertEqual(count, 2)
        self.assertIsNone(error)
        self.assertEqual(set(calls), {'Member2'})
        self.assertEqual(set(self.mpl.ProfileSpecs('Member2', 'Гордунни').values()), {'Subtlety', 'Assassination'})
        self.assertEqual(len(f.groupPlayers), 5)
        self.assertEqual(f.name, 'Member2')

    def test_manual_party_update_bypasses_companion_cache_and_imports_new_level(self):
        self.party()
        for name in ('Alice', 'Member1', 'Member2', 'Member3', 'Member4'):
            self.mpl.SelectSpec(name, 'Гордунни', 'All specs', 'HEALER' if name=='Alice' else 'DAMAGER')
        calls=[]
        level=[19]
        def fetch(args):
            calls.append(args.name)
            raw=self.fetch(args)
            char=raw['data']['characterData']['character']
            for metric in ('damage','healing'):
                char[metric]['throughputRankings']['12825']['best_level']=level[0]
            return raw
        self.mpl.ShowGroupProfiles(self.mpl.CollectParty())
        with patch('build_database.time.time',return_value=100000):
            response=clipboard_protocol.reply(self.mpl.downloadWindow.request,realm_resolver.load_mappings(),self.cache,fetch)
        self.assertEqual(self.mpl.ReceiveReply(response,True),5)
        self.assertEqual(self.mpl.panel.profile.dungeons[1].level,19)
        self.assertEqual(len(calls),5)
        level[0]=20
        for stamp in (143200,143201,143500):
            self.mpl.panel.loadButton.scripts.OnClick()
            self.assertTrue(self.mpl.pendingReply.refresh)
            self.assertIn('MPLC1 refresh\n',self.mpl.downloadWindow.request)
            with patch('build_database.time.time',return_value=stamp):
                response=clipboard_protocol.reply(self.mpl.downloadWindow.request,realm_resolver.load_mappings(),self.cache,fetch)
            self.assertEqual(self.mpl.ReceiveReply(response,True),5)
            self.assertEqual(self.mpl.panel.profile.dungeons[1].level,20)
        self.assertEqual(len(calls),15)


if __name__ == "__main__":
    unittest.main()
