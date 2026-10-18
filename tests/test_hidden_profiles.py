"""Hidden WCL profiles survive party imports and suppress repeat requests."""
import unittest
from urllib.parse import quote

import test_group_profiles as group_tests
import clipboard_protocol
import realm_resolver


class HiddenProfileTests(unittest.TestCase):
    setUp = group_tests.GroupProfileTests.setUp
    players = group_tests.GroupProfileTests.players
    fetch = group_tests.GroupProfileTests.fetch

    def known_hidden(self,name,realm='Гордунни'):
        self.lua.execute('''
            local name,realm=...
            MPlusLogsDB.profileStates=MPlusLogsDB.profileStates or {}
            MPlusLogsDB.profileStates[MPlusLogs.Key(name,realm)]={reason="hidden",expires=GetServerTime()+21600,spec="Arms"}
        ''',name,realm)
    def hidden_single(self):
        self.mpl.ShowDownload('Other', 'Thrall', None)
        response = 'MPLE1\n' + self.mpl.pendingReply.id + '\n' + quote('Rankings hidden: access denied', safe='')
        f=self.mpl.downloadWindow
        f.edit.SetText(f.edit,response)
        f.edit.scripts.OnTextChanged()
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
        self.assertIsNone(self.mpl.pendingReply)

    def test_hidden_single_blocks_repeat_after_reload_and_spec_switch(self):
        self.hidden_single()
        self.mpl.profileStates = None
        self.mpl.SelectSpec('Other', 'Thrall', 'Arms')
        self.mpl.ShowProfile('Other', 'Thrall')
        f = self.mpl.panel
        self.assertIn('скрыты', f.emptyMessage.text)
        self.assertNotIn('ещё не загружены', f.emptyMessage.text)
        self.assertFalse(f.loadButton.shown)
        self.assertEqual(f.specButton.detail.text, 'Логи скрыты')
        self.mpl.ShowDownload('Other', 'Thrall', None, None, None, True)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertFalse(self.mpl.downloadWindow.shown)
        self.mpl.ShowProfile('Available', 'Thrall')
        self.assertTrue(f.loadButton.shown)

    def test_batch_hidden_state_survives_closing_party_and_reload(self):
        self.mpl.ShowProfile('Bob', 'Гордунни', self.players()[2])
        response = clipboard_protocol.reply(self.mpl.downloadWindow.request, realm_resolver.load_mappings(), self.cache, self.fetch)
        self.assertEqual(self.mpl.ReceiveReply(response, True), 1)
        self.assertIn('скрыты', self.mpl.panel.emptyMessage.text)
        self.assertFalse(self.mpl.panel.loadButton.shown)
        self.mpl.profileStates = None
        self.mpl.ShowProfile('Bob', 'Гордунни')
        self.assertIn('скрыты', self.mpl.panel.emptyMessage.text)
        self.assertFalse(self.mpl.panel.loadButton.shown)
        for refresh in (False, True):
            pending, fresh = self.mpl.FilterFreshProfiles(self.players(), refresh)
            self.assertNotIn('Bob', [p.name for p in pending.values()])
            self.assertEqual(fresh, 1)  # Hidden is not a loaded profile.

    def test_hidden_candidates_disable_batch_without_claiming_fresh_data(self):
        self.lua.execute('''
            MPlusLogsDB.profileStates={}
            for _,name in ipairs({"Alice","Bob"}) do
                MPlusLogsDB.profileStates[MPlusLogs.Key(name,"Гордунни")]=
                    {reason="hidden",expires=GetServerTime()+21600,spec="Arms"}
            end
        ''')
        self.mpl.InstallBatchButton()
        self.assertFalse(self.mpl.batchButton.enabled)
        self.assertEqual(self.mpl.batchButton.text, 'Загрузить логи всех (0/2)')
        self.mpl.batchButton.scripts.OnEnter()
        lines = [line[1] for line in self.lua.globals().GameTooltip.lines.values()]
        self.assertIn('Скрытые логи: 2', lines)
        self.assertIn('Нет актуальных данных: 0', lines)
        self.mpl.ShowBatchDownload()
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.downloadWindow)

    def test_hidden_expiry_allows_recheck_and_success_clears_saved_state(self):
        self.hidden_single()
        self.lua.execute('GetServerTime=function() return 1791777600+21600 end')
        self.mpl.ShowProfile('Other', 'Thrall')
        self.assertTrue(self.mpl.panel.loadButton.shown)
        self.mpl.ShowDownload('Other', 'Thrall', None)
        self.assertIsNotNone(self.mpl.pendingReply)
        # A successful import must also clear saved access failures.
        self.lua.execute('''
            MPlusLogsDB.profileStates[MPlusLogs.Key("Other","Thrall")]=
                {reason="hidden",expires=GetServerTime()+21600}
            MPlusLogs.StoreProfiles({{name="Other",realm="Thrall",region="eu",spec="All specs",
                metric="dps",dual=true,season="test",source="WCL API",updated="2026-10-12 04:00 UTC",dungeons={}}})
        ''')
        self.mpl.ShowProfile('Other', 'Thrall')
        self.assertTrue(self.mpl.panel.profile)
        self.assertTrue(self.mpl.panel.loadButton.shown)

    def test_party_opens_on_hidden_member_but_still_loads_available_members(self):
        self.known_hidden('Bob')
        self.mpl.ShowGroupProfiles(self.players(),self.players()[2])
        self.assertEqual(self.mpl.panel.name,'Bob')
        self.assertIn('скрыты',self.mpl.panel.emptyMessage.text)
        self.assertFalse(self.mpl.panel.loadButton.shown)
        self.assertEqual(len(self.mpl.pendingReply.players),1)
        self.assertEqual(self.mpl.pendingReply.players[1].name,'Alice')
        self.assertNotIn('Bob',self.mpl.downloadWindow.request)

    def test_transport_filters_hidden_without_losing_existing_pending_request(self):
        self.known_hidden('Bob')
        self.mpl.SendBatchRequest(self.players(),True)
        self.assertEqual(len(self.mpl.pendingReply.players),1)
        self.assertEqual(self.mpl.pendingReply.players[1].name,'Alice')
        request_id=self.mpl.pendingReply.id
        blocked,error=self.mpl.SendRequest('Bob','Гордунни','dps','Fury',None,True,True)
        self.assertIsNone(blocked)
        self.assertIn('скрыты',error)
        self.assertEqual(self.mpl.pendingReply.id,request_id)

    def test_hidden_member_does_not_reduce_group_refresh_cooldown_to_zero(self):
        self.lua.execute('''
            MPlusLogs.StoreProfiles({{name="Alice",realm="Гордунни",region="eu",spec="All specs",
                role="HEALER",metric="hps",dual=true,season="test",source="WCL API",updated="2026-10-12 04:00 UTC",dungeons={}}})
        ''')
        self.known_hidden('Bob')
        self.mpl.ShowGroupProfiles(self.players())
        self.assertIsNone(self.mpl.pendingReply)
        cooling,remaining=self.mpl.UpdateProfileLoadButton()
        self.assertTrue(cooling)
        self.assertEqual(remaining,300)
        self.mpl.panel.loadButton.scripts.OnClick()
        self.assertIn('5 мин. 0 сек.',self.mpl.panel.footer.text)
