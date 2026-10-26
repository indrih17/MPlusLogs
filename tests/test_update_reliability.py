"""Automatic update checks, retries and notices without network or a Tk window."""
import gc
from http.client import IncompleteRead
import unittest
from unittest.mock import patch

import test_update_button as buttons

gui=buttons.gui


class UpdateReliabilityTests(unittest.TestCase):
    def setUp(self):
        buttons.UpdateButtonTests.setUp(self)
        buttons.UpdateButtonTests.prepare_button(self)
        self.app.automatic_updates=True
        self.record=self.enterContext(patch.object(gui.updates,'record_check'))
        self.installer_exists=self.enterContext(patch.object(gui.Path,'is_file',return_value=True))

    def request(self, data=None, error=None, download_error=None):
        gc.collect()
        with patch.object(gui.updates,'check',return_value=data,side_effect=error), \
             patch.object(gui.updates,'download',return_value='installer.exe',side_effect=download_error) as download:
            self.app.check_updates()
            self.app.update_worker.join(timeout=5)
            self.assertFalse(self.app.update_worker.is_alive())
        self.app.poll()
        return download

    def test_regular_check_runs_hourly_and_replaces_existing_timer(self):
        self.app.schedule_update_check()
        timer=self.app.update_check_after
        self.app.root.after.assert_called_with(3600000,self.app.scheduled_update_check)
        self.app.schedule_update_check(300000)
        self.app.root.after_cancel.assert_called_once_with(timer)
        self.app.root.after.assert_called_with(300000,self.app.scheduled_update_check)

    def test_background_check_failure_is_visible_and_retries_after_five_minutes(self):
        self.request(error=OSError('offline'))
        self.assertEqual(self.app.update_check_state,'error')
        self.app.root.after.assert_any_call(300000,self.app.scheduled_update_check)
        self.record.assert_any_call('check_error',error=unittest.mock.ANY)
        self.request()
        self.app.root.after.assert_any_call(3600000,self.app.scheduled_update_check)

    def test_download_failure_still_announces_available_version_with_notifications_disabled(self):
        self.app.notifications.get.return_value=False
        self.request({'version':'1.2.3'},download_error=OSError('offline'))
        self.assertEqual(self.app.available_update['version'],'1.2.3')
        self.assertIsNone(self.app.update_installer)
        self.app.popup.show.assert_called_once()
        self.assertIn('1.2.3',self.app.popup.show.call_args.args[0])
        self.assertEqual(self.app.popup.show.call_args.kwargs['on_click'],self.app.show)
        self.app.root.after.assert_any_call(300000,self.app.scheduled_update_check)
        self.record.assert_any_call('download_error',version='1.2.3',error=unittest.mock.ANY)

    def test_repeated_download_failures_do_not_repeat_popup(self):
        for _ in range(2):
            self.request({'version':'1.2.3'},download_error=OSError('offline'))
        self.app.popup.show.assert_called_once()

    def test_truncated_http_responses_retry_instead_of_stalling_worker_state(self):
        self.request(error=IncompleteRead(b'',10))
        self.assertEqual(self.app.update_check_state,'error')
        self.app.root.after.assert_any_call(300000,self.app.scheduled_update_check)
        self.request({'version':'1.2.3'},download_error=IncompleteRead(b'',10))
        self.assertEqual(self.app.update_check_state,'error')
        self.app.root.after.assert_any_call(300000,self.app.scheduled_update_check)
        self.assertIsNone(self.app.update_installer)

    def test_ready_installer_is_reused_and_reminder_is_throttled(self):
        self.request({'version':'1.2.3'})
        self.app.popup.show.reset_mock()
        download=self.request({'version':'1.2.3'})
        download.assert_not_called()
        self.assertEqual(self.app.update_installer,'installer.exe')
        self.app.popup.show.assert_not_called()
        with patch.object(gui.time,'monotonic',return_value=self.app.last_update_notice[1]+21601):
            self.app.notify_update(self.app.available_update,ready=True)
        self.app.popup.show.assert_called_once()

    def test_new_release_is_discovered_even_when_older_installer_is_ready(self):
        self.request({'version':'1.2.3'})
        download=self.request({'version':'1.2.4'})
        download.assert_called_once()
        self.assertEqual(self.app.available_update['version'],'1.2.4')

    def test_deleted_staged_installer_is_downloaded_again(self):
        self.request({'version':'1.2.3'})
        self.installer_exists.return_value=False
        download=self.request({'version':'1.2.3'})
        download.assert_called_once()
        self.assertEqual(self.app.update_check_state,'ready')

    def test_failed_install_is_announced_without_automatic_reinstallation(self):
        self.app.failed_update_version='1.2.3'
        download=self.request({'version':'1.2.3'})
        download.assert_not_called()
        self.app.popup.show.assert_called_once()

    def test_exit_prevents_scheduling_more_checks(self):
        self.app.exiting=True
        self.app.schedule_update_check()
        self.app.root.after.assert_not_called()


if __name__=='__main__':
    unittest.main()
