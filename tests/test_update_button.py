"""One settings button checks for updates, reports the result and installs them."""
import gc
import unittest
from unittest.mock import Mock, patch

import test_ready_notifications as ready

gui=ready.gui


class UpdateButtonTests(unittest.TestCase):
    def setUp(self):
        ready.ReadyNotificationTests.setUp(self)
        self.enterContext(patch.object(gui.updates,'record_check'))

    def prepare_button(self):
        app=self.app
        app.settings_update_text=Mock()
        app.settings_update_button=Mock()
        app.update_check_state='idle'
        app.settings_window=Mock()
        app.available_update=app.update_installer=app.update_worker=None
        app.failed_update_version=None
        return app

    def check(self,data=None,error=None):
        # Collect Tk objects from earlier UI tests on the main thread.
        gc.collect()
        with patch.object(gui.updates,'check',return_value=data,side_effect=error), \
             patch.object(gui.updates,'download',return_value='installer.exe'):
            self.app.settings_update_action()
            self.app.update_worker.join(timeout=5)
            self.assertFalse(self.app.update_worker.is_alive())
        self.app.poll()

    def test_no_update_result_is_in_button_and_resets_on_close(self):
        app=self.prepare_button()
        self.check()
        self.assertEqual(app.update_check_state,'current')
        app.settings_update_text.set.assert_called_with('No updates found')
        app.settings_update_button.configure.assert_called_with(state='normal')
        window=app.settings_window
        app.close_settings()
        window.destroy.assert_called_once()
        self.assertIsNone(app.settings_window)
        self.assertIsNone(app.settings_update_button)
        app.settings_update_text.set.assert_called_with('Check Companion updates')

    def test_local_preview_allows_manual_check_without_automatic_check(self):
        app=self.prepare_button()
        app.preview=True
        with patch.object(gui.updates,'portable_build',return_value=False), \
             patch.object(gui.updates,'check') as check:
            app.check_updates()
            check.assert_not_called()
            self.assertIsNone(app.update_worker)
        with patch.object(gui.updates,'portable_build',return_value=False):
            self.check()
        app.settings_update_text.set.assert_called_with('No updates found')

    def test_found_update_changes_same_button_action_to_install(self):
        app=self.prepare_button()
        button=app.settings_update_button
        self.check({'version':'1.2.3'})
        self.assertIs(app.settings_update_button,button)
        self.assertEqual(app.update_check_state,'ready')
        app.settings_update_text.set.assert_called_with('Update available — install and restart')
        with patch.object(app,'install_update') as install,patch.object(app,'check_updates') as check:
            app.settings_update_action()
        install.assert_called_once()
        check.assert_not_called()
        app.close_settings()
        self.assertEqual(app.update_check_state,'ready')
        self.assertEqual(app.update_installer,'installer.exe')

    def test_error_leaves_button_available_for_retry(self):
        app=self.prepare_button()
        self.check(error=OSError('offline'))
        self.assertEqual(app.update_check_state,'error')
        app.settings_update_text.set.assert_called_with('Update check failed — retry')
        app.settings_update_button.configure.assert_called_with(state='normal')
        self.check()
        self.assertEqual(app.update_check_state,'current')

    def test_in_progress_states_disable_the_settings_button(self):
        app=self.prepare_button()
        for state in ('checking','downloading','installing'):
            with self.subTest(state=state):
                app.set_update_check_state(state)
                app.settings_update_button.configure.assert_called_with(state='disabled')

    def test_closing_during_check_does_not_touch_destroyed_button(self):
        app=self.prepare_button()
        app.set_update_check_state('checking')
        app.close_settings()
        app.messages.put(('update_current',None))
        app.poll()
        self.assertEqual(app.update_check_state,'current')
        self.assertIsNone(app.settings_update_button)

    def test_install_launch_failure_restores_install_action(self):
        app=self.prepare_button()
        app.available_update={'version':'1.2.3'}
        app.update_installer='installer.exe'
        app.worker=app.auth_worker=None
        app.session=None
        app.mode_diagnostic=False
        app.show=Mock()
        with patch.object(gui.updates,'launch_installer',side_effect=OSError('busy')):
            app.settings_update_action()
        self.assertFalse(app.installing_update)
        self.assertEqual(app.update_check_state,'ready')
        app.settings_update_button.configure.assert_called_with(state='normal')
        app.show.assert_called_once()

    def test_authentication_in_progress_opens_app_without_launching_installer(self):
        app=self.prepare_button()
        app.available_update={'version':'1.2.3'}
        app.update_installer='installer.exe'
        app.auth_worker=Mock()
        app.auth_worker.is_alive.return_value=True
        app.show=Mock()
        with patch.object(gui.updates,'launch_installer') as launch:
            app.install_update()
        launch.assert_not_called()
        app.show.assert_called_once()
        self.assertFalse(app.installing_update)
        app.update_status.set.assert_called_with('Finish Warcraft Logs sign-in before updating.')

    def test_missing_update_opens_app_and_checks_again(self):
        app=self.prepare_button()
        app.show=Mock()
        app.check_updates=Mock()
        with patch.object(gui.updates,'launch_installer') as launch:
            app.install_update()
        launch.assert_not_called()
        app.show.assert_called_once()
        app.check_updates.assert_called_once_with(manual=True)


if __name__=='__main__': unittest.main()
