"""Explicit clipboard command opens update settings without importing or copying data."""
import queue
import unittest
from unittest.mock import Mock,patch

import test_ready_notifications as ready
import clipboard_protocol as protocol

gui=ready.gui


class OpenCompanionTests(unittest.TestCase):
    setUp=ready.ReadyNotificationTests.setUp

    def test_only_exact_open_command_is_recognized(self):
        for text in ('MPLUI1 OPEN_UPDATES','MPLUI1 OPEN_UPDATES\n','MPLUI1 OPEN_UPDATES\r\n'):
            self.assertTrue(protocol.is_open_updates_command(text))
            self.assertEqual(protocol.describe_clipboard(text)['kind'],'open_updates')
        for text in ('MPLUI1 OPEN_UPDATES extra','private MPLUI1 OPEN_UPDATES','MPLUI1 INSTALL',' MPLUI1 OPEN_UPDATES'):
            self.assertFalse(protocol.is_open_updates_command(text))
        self.assertIsNone(protocol.unwrap_request('MPLUI1 OPEN_UPDATES'))

    def test_worker_works_signed_out_without_wcl_or_clipboard_write(self):
        app=self.app
        app.clipboard_events=[]
        stop=Mock()
        stop.wait.side_effect=[False,True]
        clipboard=Mock()
        clipboard.sequence.return_value=42
        clipboard.read.return_value='MPLUI1 OPEN_UPDATES'
        with patch.object(gui.bridge,'WindowsClipboard',return_value=clipboard), \
             patch.object(gui.realm_resolver,'load_mappings',return_value={}), \
             patch.object(gui.cache_maintenance,'maintain'), \
             patch.object(protocol,'reply') as reply,patch.object(gui.build_database,'atomic_write') as write:
            app.watch(stop,None,False,0)
        reply.assert_not_called()
        write.assert_not_called()
        clipboard.reply_if_unchanged.assert_not_called()
        self.assertTrue(any(value[1]=='open_updates' for kind,value in list(app.messages.queue) if kind=='worker'))

    def test_command_opens_settings_and_checks_updates_without_installing(self):
        app=self.app
        app.show=Mock();app.settings=Mock();app.settings_window=Mock()
        app.check_updates=Mock();app.install_update=Mock()
        app.messages.put(('worker',(app.stop,'open_updates',None)))
        app.poll()
        app.show.assert_called_once()
        app.settings.assert_called_once()
        app.settings_window.focus_force.assert_called_once()
        app.check_updates.assert_called_once_with(manual=True)
        app.install_update.assert_not_called()


if __name__=='__main__': unittest.main()
