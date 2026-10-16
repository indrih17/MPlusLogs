"""Clipboard privacy transactions and exact history cleanup; no live clipboard writes."""
import base64
import ctypes
import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import clipboard_companion as bridge
import clipboard_history as history

REQUEST='MPLS1\n12345-1\nMPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\tGuardian\n'


class ClipboardPrivacyTests(unittest.TestCase):
    def clipboard(self,current=REQUEST,fail_format=None):
        buffers={};freed=[];published={};events=[]
        def allocate(flags,size):
            handle=len(buffers)+1;buffers[handle]=ctypes.create_string_buffer(size);return handle
        def put(format_id,handle):
            if format_id==fail_format:return 0
            if format_id==13:self.assertEqual(set(published),{101,102,103})
            published[format_id]=buffers[handle].raw;events.append(format_id);return handle
        clipboard=object.__new__(bridge.WindowsClipboard)
        clipboard.owner=99;clipboard.private_formats=[101,102,103]
        clipboard.kernel=SimpleNamespace(GlobalAlloc=allocate,GlobalLock=lambda h:ctypes.addressof(buffers[h]),
            GlobalUnlock=lambda h:None,GlobalFree=freed.append)
        clipboard.user=SimpleNamespace(OpenClipboard=lambda owner:True,CloseClipboard=lambda:events.append('closed'),
            EmptyClipboard=lambda:events.append('empty') or True,SetClipboardData=put)
        clipboard._read_open=lambda:current
        return clipboard,freed,published,events

    def test_reply_has_privacy_flags_before_text_and_remains_pastable(self):
        clipboard,freed,published,events=self.clipboard()
        with patch.object(history,'forget_request') as forget:
            self.assertTrue(clipboard.reply_if_unchanged(REQUEST,'MPLS1\nreply'))
            forget.assert_called_once_with(REQUEST)
        self.assertEqual(published[13],('MPLS1\nreply\0').encode('utf-16-le'))
        self.assertTrue(all(published[f]==b'\0'*4 for f in (101,102,103)))
        self.assertFalse(freed)
        self.assertEqual(events,['empty',101,102,103,13,'closed'])

    def test_unrelated_current_clipboard_is_not_replaced(self):
        clipboard,freed,published,events=self.clipboard('user text')
        with patch.object(history,'forget_request'):
            self.assertFalse(clipboard.reply_if_unchanged(REQUEST,'reply'))
        self.assertFalse(published)
        self.assertNotIn('empty',events)
        self.assertEqual(len(freed),4)

    def test_failed_private_flag_does_not_publish_unprotected_text(self):
        clipboard,freed,published,events=self.clipboard(fail_format=102)
        with self.assertRaises(OSError):clipboard.write_private('reply')
        self.assertEqual(set(published),{101})
        self.assertEqual(len(freed),3)
        self.assertNotIn(13,events)
        self.assertEqual(events[-1],'closed')

    def test_explicit_copy_last_reply_is_also_private(self):
        clipboard,freed,published,_=self.clipboard('unrelated current clipboard')
        self.assertTrue(clipboard.write_private('last reply'))
        self.assertIn(13,published)
        self.assertFalse(freed)

    def test_copy_last_reply_button_uses_private_writer(self):
        path=Path(__file__).resolve().parents[1]/'tools/companion_gui.pyw'
        loader=importlib.machinery.SourceFileLoader('private_copy_gui_test',str(path))
        spec=importlib.util.spec_from_loader(loader.name,loader)
        gui=importlib.util.module_from_spec(spec);loader.exec_module(gui)
        app=SimpleNamespace(result='MPLS1\nreply',root=SimpleNamespace(winfo_id=lambda:42),
                            status=SimpleNamespace(set=lambda text:None))
        with patch.object(gui.bridge,'WindowsClipboard') as clipboard:
            gui.App.copy(app)
        clipboard.assert_called_once_with(owner=42)
        clipboard.return_value.write_private.assert_called_once_with(app.result)

    def test_history_only_accepts_explicit_requests(self):
        self.assertTrue(history.valid_request(REQUEST))
        for text in ('hello','MPLS1\nwrong\nhello','MPLE1\n12345-1\nerror','MPLS1\n12345-1\nMPL1\n'):
            self.assertFalse(history.valid_request(text))

    @unittest.skipUnless(sys.platform=='win32','Windows subprocess flags')
    def test_history_input_is_stdin_not_executable_code(self):
        with patch.object(history.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='1')) as run:
            self.assertEqual(history.remove_request(REQUEST),1)
        args,kwargs=run.call_args
        self.assertNotIn(REQUEST,' '.join(args[0]))
        self.assertEqual(base64.b64decode(kwargs['input']).decode('utf-8'),REQUEST)
        self.assertEqual(kwargs['creationflags'],subprocess.CREATE_NO_WINDOW)
        self.assertEqual(kwargs['timeout'],8)

    @unittest.skipUnless(sys.platform=='win32','Windows history API')
    def test_unavailable_history_is_nonfatal(self):
        for result in (SimpleNamespace(returncode=2,stdout=''),SimpleNamespace(returncode=1,stdout='')):
            with patch.object(history.subprocess,'run',return_value=result):
                self.assertIsNone(history.remove_request(REQUEST))
        with patch.object(history.subprocess,'run',side_effect=subprocess.TimeoutExpired('powershell',8)):
            self.assertIsNone(history.remove_request(REQUEST))

    @unittest.skipUnless(sys.platform=='win32','Windows PowerShell')
    def test_real_powershell_matcher_deletes_only_exact_text_and_skips_images(self):
        matcher=history.SCRIPT.split('function Remove-ExactRequest',1)[1].split('# Request text',1)[0]
        code='function Remove-ExactRequest'+matcher+r'''
class TestContent {
    [bool] $IsText
    TestContent([bool]$isText) { $this.IsText=$isText }
    [bool] Contains([string]$format) { return $this.IsText }
}
$expected="MPLS1`n12345-1`nMPLQ1`nQ"
$items=@(
    [pscustomobject]@{Id='request';Content=[TestContent]::new($true);Text=$expected},
    [pscustomobject]@{Id='unrelated';Content=[TestContent]::new($true);Text='user text'},
    [pscustomobject]@{Id='near';Content=[TestContent]::new($true);Text=($expected+'other')},
    [pscustomobject]@{Id='image';Content=[TestContent]::new($false);Text=$expected}
)
$deleted=New-Object 'System.Collections.Generic.List[string]'
$count=Remove-ExactRequest $items $expected {param($item) $item.Text} {param($item) $deleted.Add($item.Id); $true}
if ($count -ne 1 -or $deleted.Count -ne 1 -or $deleted[0] -ne 'request') { throw 'Wrong history item removed' }
'OK'
'''
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
            base64.b64encode(code.encode('utf-16-le')).decode('ascii')],capture_output=True,text=True,
            timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'OK')


if __name__=='__main__':unittest.main()
