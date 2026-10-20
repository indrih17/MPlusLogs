"""First-load guidance and evidence of a Companion response; no OS probing."""
import unittest
import test_screenshot_transport as transport_tests


class CompanionIntroTests(unittest.TestCase):
    setUp = transport_tests.ReplyTests.setUp

    def first_use(self):
        self.lua.execute('MPlusLogsDB.companionIntroDismissed=nil; MPlusLogsDB.companionReplySeen=nil')

    def test_preview_opens_real_inline_hint_without_resetting_saved_setup(self):
        self.lua.globals().MPlusLogsDB.companionReplySeen = True
        self.mpl.ShowCompanionIntroPreview()
        window = self.mpl.downloadWindow
        self.assertTrue(window.shown)
        self.assertTrue(window.companionHint.shown)
        self.assertEqual(window.phase, 'copy')
        self.assertEqual(self.mpl.pendingReply.name, 'Киндрих')
        self.assertTrue(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertTrue(self.mpl.CompanionHasReplied())
        window.companionHint['continue'].scripts.OnClick()
        self.assertFalse(window.companionHint.shown)
        self.assertTrue(self.mpl.CompanionHasReplied())

    def test_preview_preserves_waiting_exchange_until_user_acknowledges_setup(self):
        self.first_use()
        self.lua.globals().MPlusLogsDB.companionReplySeen = True
        self.mpl.ShowDownload('Alice', 'Area 52', None)
        window = self.mpl.downloadWindow
        self.lua.execute('IsControlKeyDown=function() return true end')
        window.edit.scripts.OnKeyDown(window.edit, 'C')
        window.setStatus('Connection guidance', True)
        before = (self.mpl.pendingReply.id, window.request, window.phase,
                  window.revision, window.edit.text)
        self.mpl.ShowCompanionIntroPreview()
        self.assertTrue(window.companionHint.shown)
        self.assertEqual((self.mpl.pendingReply.id, window.request, window.phase,
                          window.revision, window.edit.text), before)
        self.assertEqual(window.status.text, 'Connection guidance')
        self.assertTrue(window.errorIcon.shown)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        window.companionHint['continue'].scripts.OnClick()
        self.assertFalse(window.companionHint.shown)
        self.assertTrue(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.mpl.ShowCompanionIntroPreview()
        window.Hide(window)
        window.scripts.OnHide()
        self.assertFalse(window.previewCompanionIntro)
        self.mpl.ShowDownload('Bob', 'Area 52', None)
        self.assertFalse(window.companionHint.shown)

    def test_preview_does_not_prepare_a_request_in_combat(self):
        self.lua.globals().combat = True
        self.mpl.ShowCompanionIntroPreview()
        self.assertIsNone(self.mpl.downloadWindow)
        self.assertIsNone(self.mpl.pendingReply)

    def test_first_request_opens_inline_help_and_download_only_copies_link(self):
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        window=self.mpl.downloadWindow
        self.assertIsNone(self.mpl.companionIntroWindow)
        self.assertTrue(window.shown)
        self.assertTrue(window.companionHint.shown)
        self.assertEqual(window.phase,'copy')
        self.assertEqual(self.mpl.pendingReply.name,'Alice')
        request_id=self.mpl.pendingReply.id
        window.companionHint.download.scripts.OnClick()
        self.assertEqual(self.mpl.copy.edit.text,'https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Setup.exe')
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.assertEqual(self.mpl.copy.title.text,'Скачать MPlusLogs Companion')
        self.assertIn('браузере',self.mpl.copy.copyHint.text)
        self.assertEqual(self.mpl.pendingReply.id,request_id)
        self.assertTrue(window.companionHint.shown)

    def test_closing_download_keeps_help_for_next_request(self):
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        window=self.mpl.downloadWindow
        window.Hide(window)
        window.scripts.OnHide()
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.mpl.ShowDownload('Bob','Area 52',None)
        self.assertEqual(self.mpl.pendingReply.name,'Bob')
        self.assertTrue(window.companionHint.shown)

    def test_already_installed_hides_help_without_restarting_waiting_request(self):
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        window=self.mpl.downloadWindow
        self.lua.execute('IsControlKeyDown=function() return true end')
        window.edit.scripts.OnKeyDown(window.edit,'C')
        window.setStatus('Connection guidance',True)
        request_id=self.mpl.pendingReply.id
        request=window.request
        window.companionHint['continue'].scripts.OnClick()
        self.assertFalse(window.companionHint.shown)
        self.assertEqual(window.height,382)
        self.assertEqual(window.status.text,'Connection guidance')
        self.assertTrue(window.errorIcon.shown)
        self.assertEqual(window.phase,'waiting')
        self.assertEqual(window.request,request)
        self.assertEqual(self.mpl.pendingReply.id,request_id)
        self.assertTrue(window.edit.focused)
        self.assertTrue(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.mpl.ShowDownload('Bob','Area 52',None)
        self.assertFalse(window.companionHint.shown)
        # Reusing saved acknowledgement in a fresh UI session also skips help.
        self.mpl.downloadWindow=None
        self.mpl.ShowDownload('Alice','Area 52',None)
        self.assertFalse(self.mpl.downloadWindow.companionHint.shown)
        self.assertFalse(self.mpl.CompanionHasReplied())

    def test_group_context_survives_inline_help_dismissal(self):
        self.first_use()
        players=self.lua.table_from([self.lua.table_from({'name':n,'realm':'Area 52'}) for n in ('Alice','Bob')])
        self.mpl.ShowDownload('Alice','Area 52',None,None,players,True)
        request_id=self.mpl.pendingReply.id
        self.mpl.downloadWindow.companionHint['continue'].scripts.OnClick()
        self.assertTrue(self.mpl.pendingReply.batch)
        self.assertEqual(len(self.mpl.pendingReply.players),2)
        self.assertEqual(len(self.mpl.pendingReply.groupPlayers),2)
        self.assertTrue(self.mpl.pendingReply.refresh)
        self.assertEqual(self.mpl.pendingReply.id,request_id)

    def test_legacy_acknowledgement_skips_help_without_confirming_exchange(self):
        self.mpl.ShowDownload('Alice','Area 52',None)
        self.assertFalse(self.mpl.downloadWindow.companionHint.shown)
        self.assertFalse(self.mpl.CompanionHasHistory())
        self.assertFalse(self.mpl.CompanionHasReplied())

    def test_long_inline_help_reserves_space_for_buttons(self):
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        window=self.mpl.downloadWindow
        self.lua.execute('local MPL=...; function MPL.downloadWindow.companionHint.text:GetStringHeight() return 120 end',self.mpl)
        window.setStatus('Copy request')
        self.assertEqual(window.companionHint.text.height,120)
        self.assertEqual(window.companionHint.height,168)
        self.assertEqual(window.height,550)

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
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        window=self.mpl.downloadWindow
        self.lua.execute('IsControlKeyDown=function() return true end')
        window.edit.scripts.OnKeyDown(window.edit,'C')
        window.edit.scripts.OnKeyDown(window.edit,'V')
        self.lua.eval('function(edit,body) for i=1,#body do edit.scripts.OnChar(edit,body:sub(i,i)) end end')(window.edit,window.request)
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
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

    def test_search_error_confirms_exchange_only_for_matching_nonempty_reply(self):
        self.first_use()
        from test_addon import ROOT
        self.lua.execute('return assert(loadstring(...))',(ROOT/'SearchGroup.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.lua.execute('local MPL=...; MPL.searchGroupWindow={requestID="search-1"}',self.mpl)
        for reply in ('MPLE1\nwrong-id\nHTTP%20401','MPLE1\nsearch-1\n'):
            self.mpl.ReceiveSearchGroupReply(reply)
            self.assertFalse(self.mpl.CompanionHasReplied())
        _,error=self.mpl.ReceiveSearchGroupReply('MPLE1\nsearch-1\nHTTP%20401')
        self.assertEqual(error,'HTTP 401')
        self.assertTrue(self.mpl.CompanionHasReplied())

    def test_error_paste_hides_help_in_current_window_without_dismissing_it(self):
        self.first_use()
        self.mpl.ShowDownload('Alice','Area 52',None)
        window=self.mpl.downloadWindow
        reply='MPLE1\n'+self.mpl.pendingReply.id+'\nHTTP%20401'
        window.edit.SetText(window.edit,reply)
        window.edit.scripts.OnTextChanged(window.edit,True)
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
        self.assertTrue(self.mpl.CompanionHasReplied())
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertFalse(window.companionHint.shown)
        self.assertTrue(window.errorIcon.shown)
        self.assertEqual(window.height,382)

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
        self.assertIsNone(self.mpl.companionIntroWindow)
        self.assertTrue(self.mpl.downloadWindow.companionHint.shown)
        self.assertIsNotNone(self.mpl.pendingReply)
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
