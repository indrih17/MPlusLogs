"""First-load guidance and evidence of a Companion response; no OS probing."""
import unittest
from urllib.parse import quote
import test_screenshot_transport as transport_tests


class CompanionIntroTests(unittest.TestCase):
    setUp = transport_tests.ReplyTests.setUp

    def first_use(self):
        self.lua.execute('MPlusLogsDB.companionIntroDismissed=nil; MPlusLogsDB.companionReplySeen=nil')

    def test_first_request_waits_for_user_and_download_only_copies_link(self):
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        intro=self.mpl.companionIntroWindow
        self.assertTrue(intro.shown)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.downloadWindow)
        intro.download.scripts.OnClick()
        self.assertEqual(self.mpl.copy.edit.text,'https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Setup.exe')
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.assertEqual(self.mpl.copy.title.text,'Скачать MPlusLogs Companion')
        self.assertIn('браузере',self.mpl.copy.copyHint.text)
        intro['continue'].scripts.OnClick()
        self.assertEqual(self.mpl.pendingReply.name,'Alice')
        self.assertTrue(self.mpl.downloadWindow.companionHint.shown)
        self.assertFalse(self.mpl.CompanionHasReplied())

    def test_closing_intro_does_not_send_or_mark_it_as_dismissed(self):
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        intro=self.mpl.companionIntroWindow
        intro.close.scripts.OnClick()
        intro.scripts.OnHide()
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.lua.eval("rawget")(intro,"continueLoading"))
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.mpl.ShowDownload('Bob','Area 52',None)
        intro['continue'].scripts.OnClick()
        self.assertEqual(self.mpl.pendingReply.name,'Bob')

    def test_group_context_survives_intro(self):
        self.first_use()
        players=self.lua.table_from([self.lua.table_from({'name':n,'realm':'Area 52'}) for n in ('Alice','Bob')])
        self.mpl.ShowDownload('Alice','Area 52',None,None,players,True)
        self.mpl.companionIntroWindow['continue'].scripts.OnClick()
        self.assertTrue(self.mpl.pendingReply.batch)
        self.assertEqual(len(self.mpl.pendingReply.players),2)
        self.assertEqual(len(self.mpl.pendingReply.groupPlayers),2)
        self.assertTrue(self.mpl.pendingReply.refresh)

    def test_error_response_proves_companion_replied_but_wrong_request_does_not(self):
        self.first_use()
        self.mpl.SendRequest('Alice','Area 52','dps','')
        self.mpl.ReceiveReply('MPLE1\nwrong-id\nHTTP%20401',True)
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.mpl.ReceiveReply('MPLE1\n12345-1\n',True)
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.mpl.ReceiveReply('MPLE1\n12345-1\nHTTP%20401',True)
        self.assertTrue(self.mpl.CompanionHasReplied())
        self.mpl.ShowDownload('Alice','Area 52',None)
        self.assertIsNone(self.mpl.companionIntroWindow)
        self.assertFalse(self.mpl.downloadWindow.companionHint.shown)
        self.assertTrue(self.lua.globals().MPlusLogsDB.companionReplySeen)

    def test_success_remembers_reply_but_manual_import_does_not(self):
        self.first_use()
        self.mpl.Import(self.body)
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.mpl.SendRequest('Киндрих','Гордунни','dps','')
        count,error=self.mpl.ReceiveReply('MPLS1\n12345-1\n'+self.metadata+self.body,True)
        self.assertTrue(count,error)
        self.assertIsNone(error)
        self.assertTrue(self.mpl.CompanionHasReplied())
        self.mpl.ShowDownload('Киндрих','Гордунни',None)
        self.assertIsNone(self.mpl.companionIntroWindow)
        self.assertFalse(self.mpl.downloadWindow.companionHint.shown)

    def test_pasting_request_before_first_reply_explains_installation(self):
        self.mpl.ShowDownload('Alice','Area 52',None)
        window=self.mpl.downloadWindow
        self.lua.execute('IsControlKeyDown=function() return true end')
        window.edit.scripts.OnKeyDown(window.edit,'C')
        window.edit.scripts.OnKeyDown(window.edit,'V')
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
        self.assertIn('MPlusLogs Companion пока не ответил',window.status.text)
        self.assertNotIn('Companion не установлен',window.status.text)
        self.assertTrue(window.companionHint.shown)
        self.assertFalse(self.mpl.CompanionHasReplied())

    def test_valid_batch_response_remembers_companion(self):
        self.first_use()
        players=self.lua.table_from([self.lua.table_from({'name':'Киндрих','realm':'Гордунни','spec':''})])
        request_id,_=self.mpl.SendBatchRequest(players)
        body=self.body.replace('MPL1\n','MPL2\n',1)
        count=self.mpl.ReceiveReply('MPLS1\n'+request_id+'\n'+self.metadata+body,True)
        self.assertTrue(count)
        self.assertTrue(self.mpl.CompanionHasReplied())

    def test_existing_wcl_logs_do_not_trigger_installation_popup_after_reload(self):
        self.first_use()
        self.mpl.Import(self.body)
        self.mpl.ShowDownload('Киндрих','Гордунни',None)
        self.assertIsNone(self.mpl.companionIntroWindow)
        self.assertIsNotNone(self.mpl.pendingReply)
        # Previous logs hide installation help without claiming a live connection.
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.assertTrue(self.mpl.CompanionHasHistory())
        self.assertFalse(self.mpl.downloadWindow.companionHint.shown)
        self.assertEqual(self.mpl.downloadWindow.height,382)

    def test_bundled_screenshot_does_not_count_as_previous_connection(self):
        self.first_use()
        self.mpl.Import(self.body)
        self.lua.execute('''
            for _,profile in pairs(MPlusLogsDB.profiles) do
                profile.source="Снимок со скриншота пользователя"
            end
        ''')
        self.mpl.ShowDownload('Киндрих','Гордунни',None)
        self.assertTrue(self.mpl.companionIntroWindow.shown)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertFalse(self.mpl.CompanionHasReplied())

    def test_cached_refresh_warning_describes_previous_attempt_not_live_connection(self):
        self.first_use()
        self.mpl.Import(self.body)
        self.lua.execute('''
            for _,profile in pairs(MPlusLogsDB.profiles) do
                profile.source="WCL API: cached; refresh unavailable"
            end
        ''')
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.assertNotIn('refresh unavailable',self.mpl.panel.source.text)
        self.assertIn('последней попытке',self.mpl.panel.source.text)

    def test_opening_saved_profile_never_shows_intro(self):
        self.first_use()
        self.mpl.Import(self.body)
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.assertTrue(self.mpl.panel.shown)
        self.assertIsNone(self.mpl.companionIntroWindow)
        self.assertIsNone(self.mpl.pendingReply)


if __name__=='__main__': unittest.main()
