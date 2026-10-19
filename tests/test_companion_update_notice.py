"""Validated clipboard replies recommend the published Companion without blocking imports."""
import unittest
from unittest.mock import patch

import test_batch as batch
from test_addon import ROOT
import clipboard_protocol
import realm_resolver


class CompanionUpdateNoticeTests(unittest.TestCase):
    players=batch.BatchTests.players
    fetch=batch.BatchTests.fetch
    flush=batch.BatchTests.flush

    def setUp(self):
        batch.BatchTests.setUp(self)
        self.lua.execute('return assert(loadstring(...))',
                         (ROOT/'CompanionUpdate.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        # Keep comparison fixtures stable when the production recommendation advances.
        self.mpl.recommendedCompanionVersion='1.0.24'

    def test_versions_compare_numerically_and_current_or_newer_do_not_notify(self):
        for version in ('1.0.9','1.0.23','0.99.99'):
            with self.subTest(version=version):
                notice=self.mpl.GetCompanionUpdateNotice(version)
                self.assertEqual(notice.installed,version)
                self.assertEqual(notice.recommended,'1.0.24')
        for version in ('1.0.24','1.0.25','1.1.0','2.0.0'):
            with self.subTest(version=version):
                self.assertIsNone(self.mpl.GetCompanionUpdateNotice(version))

    def test_preview_command_opens_same_dialog_without_consuming_real_notice(self):
        self.lua.globals().SlashCmdList.MPLUSLOGS('testupdate')
        self.assertTrue(self.mpl.companionUpdateWindow.shown)
        self.assertIn('1.0.23',self.mpl.companionUpdateWindow.message.text)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionUpdateNoticeVersion)

    def test_open_button_selects_command_without_installer_link(self):
        self.lua.globals().SlashCmdList.MPLUSLOGS('testupdate')
        f=self.mpl.companionUpdateWindow
        f.openCompanion.scripts.OnClick()
        self.assertEqual(f.edit.text,'MPLUI1 OPEN_UPDATES')
        self.assertTrue(f.edit.focused)
        self.assertTrue(f.edit.highlighted)
        self.assertIn('Ctrl+C',f.instructions.text)
        self.assertIsNone(self.lua.eval('rawget')(f,'copyLink'))
        self.assertNotIn('https://',f.edit.text)
        self.assertIn('\n',f.instructions.text)

    def test_no_version_is_unknown_not_claimed_outdated(self):
        self.mpl.QueueCompanionUpdateNotice(None)
        self.flush()
        f=self.mpl.companionUpdateWindow
        self.assertTrue(f.shown)
        self.assertIn('не сообщил свою версию',f.message.text)
        self.assertIsNone(self.lua.eval('rawget')(f.edit,'focused'))
        self.assertEqual(f.edit.text,'MPLUI1 OPEN_UPDATES')
        f.openCompanion.scripts.OnClick()
        self.assertTrue(f.edit.focused)
        self.assertTrue(f.edit.highlighted)

    def test_notice_shown_once_per_recommended_version_without_expiry(self):
        self.mpl.QueueCompanionUpdateNotice('1.0.23')
        self.flush()
        f=self.mpl.companionUpdateWindow
        self.assertTrue(f.shown)
        self.assertEqual(len(self.lua.globals().timers),0)
        f.Hide(f)
        self.mpl.QueueCompanionUpdateNotice('1.0.23')
        self.flush()
        self.assertFalse(f.shown)
        self.mpl.recommendedCompanionVersion='1.0.25'
        self.mpl.QueueCompanionUpdateNotice('1.0.23')
        self.flush()
        self.assertTrue(f.shown)
        self.assertIn('1.0.25',f.message.text)

    def test_combat_defers_and_updated_reply_cancels_queued_notice(self):
        self.lua.globals().combat=True
        self.mpl.QueueCompanionUpdateNotice('1.0.23')
        self.flush()
        self.assertIsNone(self.mpl.companionUpdateWindow)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionUpdateNoticeVersion)
        self.mpl.QueueCompanionUpdateNotice('1.0.24')
        self.lua.globals().combat=False
        self.mpl.TryCompanionUpdateNotice()
        self.assertIsNone(self.mpl.companionUpdateWindow)
        self.mpl.QueueCompanionUpdateNotice('1.0.23')
        self.flush()
        self.assertTrue(self.mpl.companionUpdateWindow.shown)

    def reply(self,version):
        self.mpl.ShowBatchDownload()
        f=self.mpl.downloadWindow
        with patch.object(clipboard_protocol.companion_update,'current_version',return_value=version):
            response=clipboard_protocol.reply(f.edit.GetText(f.edit),realm_resolver.load_mappings(),self.cache,self.fetch)
        return f,response

    def test_old_reply_imports_logs_then_shows_notice_after_exchange_closes(self):
        f,response=self.reply('1.0.23')
        f.edit.SetText(f.edit,response)
        f.edit.scripts.OnTextChanged(f.edit,True)
        self.flush()
        self.assertFalse(f.shown)
        self.assertEqual(self.mpl.lastBatchResult.count,1)
        self.assertIsNone(self.mpl.companionUpdateWindow)
        self.flush()
        self.assertTrue(self.mpl.companionUpdateWindow.shown)
        self.assertIn('1.0.23',self.mpl.companionUpdateWindow.message.text)

    def test_wrong_request_and_malformed_payload_do_not_show_notice(self):
        f,response=self.reply('1.0.23')
        wrong=response.replace(self.mpl.pendingReply.id,'999-999',1)
        result=self.mpl.ReceiveReply(wrong,True)
        self.assertIsNone(result[0])
        self.mpl.ReceiveReply(response.split('MPLB1\n')[0]+'MPLB1\ninvalid',True)
        self.flush()
        self.assertIsNone(self.mpl.companionUpdateWindow)
        self.assertIsNone(self.mpl.pendingCompanionUpdateNotice)

    def test_missing_metadata_after_success_is_not_replaced_with_stale_session_version(self):
        f,response=self.reply('1.0.24')
        self.mpl.companionInfo=self.lua.table_from({'version':'1.0.24'})
        lines=response.split('\n')
        response='\n'.join(line for line in lines if not line.startswith('MPLV1 '))
        result=self.mpl.ReceiveReply(response,True)
        self.assertEqual(result,1)
        self.flush()
        self.assertIn('не сообщил свою версию',self.mpl.companionUpdateWindow.message.text)


if __name__=='__main__': unittest.main()
