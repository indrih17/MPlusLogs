"""Production download windows collect native paste events without growing text."""
import unittest
import test_batch
import clipboard_protocol
import realm_resolver


class PasteCaptureTests(unittest.TestCase):
    def setUp(self):
        self.case=test_batch.BatchTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.lua,self.mpl=self.case.lua,self.case.mpl
        self.lua.execute('IsControlKeyDown=function() return true end')

    def paste(self,reply):
        f=self.mpl.downloadWindow
        f.edit.scripts.OnKeyDown(f.edit,'V')
        self.assertTrue(f.capturePaste)
        f.edit.SetText(f.edit,reply[:1])
        f.edit.scripts.OnTextChanged(f.edit,True)
        self.lua.eval('function(edit,body) for i=1,#body do edit.scripts.OnChar(edit,body:sub(i,i)) end end')(f.edit,reply)
        self.case.flush();self.case.flush()

    def test_regular_batch_preserves_copy_and_imports_captured_reply(self):
        self.mpl.ShowBatchDownload()
        f=self.mpl.downloadWindow
        request=f.request
        f.edit.scripts.OnKeyDown(f.edit,'C')
        self.assertEqual(f.edit.GetText(f.edit),request)
        reply=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.case.cache,self.case.fetch)
        self.paste(reply)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertEqual(self.mpl.lastBatchResult.count,1)
        self.assertFalse(f.shown)

    def test_regular_single_player_recovers_after_invalid_paste(self):
        self.mpl.ShowDownload('Alice','Гордунни',None)
        f=self.mpl.downloadWindow
        request=f.request
        # A pasted reply must not depend on observing the earlier Ctrl+C key.
        self.paste('unrelated text')
        self.assertIsNotNone(self.mpl.pendingReply)
        self.assertEqual(f.edit.GetText(f.edit),request)
        reply=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.case.cache,self.case.fetch)
        self.paste(reply)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNotNone(self.mpl.GetProfile('Alice','Гордунни'))

    def test_closing_window_cancels_deferred_capture(self):
        self.mpl.ShowDownload('Alice','Гордунни',None)
        f=self.mpl.downloadWindow
        f.edit.scripts.OnKeyDown(f.edit,'V')
        f.edit.scripts.OnChar(f.edit,'M')
        f.Hide(f);f.scripts.OnHide(f)
        self.case.flush();self.case.flush()
        self.assertIsNone(self.mpl.lastBatchResult)
        self.assertFalse(f.charBuffer)


if __name__=='__main__':unittest.main()
