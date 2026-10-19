"""Completion notifications follow the current reply and independent preferences."""
import importlib.machinery
import importlib.util
import queue
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

from test_addon import ROOT
sys.path.insert(0,str(ROOT/'tools'))
import companion_i18n as i18n
import windows_integration as windows


loader=importlib.machinery.SourceFileLoader('ready_notifications_gui',str(ROOT/'tools/companion_gui.pyw'))
spec=importlib.util.spec_from_loader(loader.name,loader)
gui=importlib.util.module_from_spec(spec)
loader.exec_module(gui)


class ReadyNotificationTests(unittest.TestCase):
    def setUp(self):
        self.app=app=gui.App.__new__(gui.App)
        app.exiting=app.installing_update=False
        app.stop=threading.Event()
        app.instance=None
        app.last_theme_check=time.monotonic()
        app.last_heartbeat=time.time()
        app.messages=queue.Queue()
        app.root=Mock()
        app.root.winfo_height.return_value=330
        app.body=Mock()
        app.body.winfo_reqheight.return_value=330
        app.clear_progress=Mock()
        app.show_progress=Mock()
        app.start=Mock()
        app.tray=Mock()
        app.popup=Mock()
        app.popup.status=None
        app.sound=Mock()
        app.sound.get.return_value=False
        app.notifications=Mock()
        app.notifications.get.return_value=True
        app.status=Mock()
        app.status.get.side_effect=lambda: i18n.tr(app.status.set.call_args.args[0])
        app.update_status=Mock()
        app.update_button=Mock()
        app.notification_test_status=Mock()
        self.play_sound=self.enterContext(patch.object(gui.companion_audio,'play_ready',return_value=True))

    def event(self,kind,value,stop=None):
        self.app.messages.put(('worker',(stop or self.app.stop,kind,value)))

    def test_one_localized_notification_after_whole_group_is_ready(self):
        for completed in range(6):
            self.event('progress',dict(stage='profiles',completed=completed,total=5))
        text='Ответ в буфере. Вернитесь в WoW и нажмите Ctrl+V.'
        self.event('ready',text)
        with patch.object(i18n,'_language','enUS'):
            self.app.poll()
        self.app.popup.show.assert_called_once_with(
            'MPlusLogs Companion','The reply is on the clipboard. Return to WoW and press Ctrl+V.')
        self.app.root.bell.assert_not_called()
        self.play_sound.assert_not_called()

    def test_changed_clipboard_notification_explains_copy_step(self):
        text='Ответ готов. Буфер изменился — нажмите «Скопировать последний ответ».'
        self.event('ready',text)
        self.app.poll()
        self.assertEqual(self.app.popup.show.call_args.args,('MPlusLogs Companion',i18n.tr(text)))

    def test_notifications_can_be_disabled_without_disabling_sound(self):
        self.app.notifications.get.return_value=False
        self.app.sound.get.return_value=True
        self.event('ready','Reply ready')
        self.app.poll()
        self.app.popup.show.assert_not_called()
        self.play_sound.assert_called_once()
        self.app.root.bell.assert_not_called()

    def test_stale_stopped_and_error_events_do_not_notify(self):
        stale=threading.Event()
        self.event('ready','Old reply',stale)
        self.event('status','HTTP 429')
        self.app.poll()
        self.app.stop.set()
        self.event('ready','Stopped reply')
        self.app.poll()
        self.app.popup.show.assert_not_called()
        self.app.root.bell.assert_not_called()
        self.play_sound.assert_not_called()

    def test_missing_tray_does_not_prevent_ready_status_or_sound(self):
        self.app.tray=None
        self.app.sound.get.return_value=True
        self.event('ready','Reply ready')
        self.app.poll()
        self.app.status.set.assert_called_with('Reply ready')
        self.app.popup.show.assert_called_once_with('MPlusLogs Companion','Reply ready')
        self.play_sound.assert_called_once()
        self.app.root.bell.assert_not_called()

    def test_update_uses_own_popup_regardless_of_notification_preference(self):
        for enabled in (False,True):
            with self.subTest(notifications=enabled):
                self.app.notifications.get.return_value=enabled
                self.app.popup.show.reset_mock()
                self.app.update_button.pack.reset_mock()
                self.app.messages.put(('update_ready',({'version':'1.2.3'},'installer.exe')))
                self.app.poll()
                self.app.popup.show.assert_called_once_with(
                    'MPlusLogs Companion 1.2.3',
                    i18n.tr('Companion update is ready. Click to install and restart.'),
                    on_click=self.app.install_update)
                self.app.update_button.pack.assert_called_once()
                self.app.tray.notify.assert_not_called()
                self.play_sound.assert_not_called()

    def test_update_popup_click_installs_the_already_downloaded_update(self):
        self.app.notifications.get.return_value=False
        self.app.install_update=Mock()
        self.app.messages.put(('update_ready',({'version':'1.2.3'},'installer.exe')))
        self.app.poll()
        self.app.install_update.assert_not_called()
        self.app.popup.show.call_args.kwargs['on_click']()
        self.app.install_update.assert_called_once()
        self.assertEqual(self.app.update_installer,'installer.exe')

    def test_required_update_popup_failure_does_not_break_update_action(self):
        self.app.notifications.get.return_value=False
        self.app.popup.show.side_effect=gui.tk.TclError('display unavailable')
        self.app.messages.put(('update_ready',({'version':'1.2.3'},'installer.exe')))
        self.app.poll()
        self.assertEqual(self.app.available_update,{'version':'1.2.3'})
        self.assertEqual(self.app.update_installer,'installer.exe')
        self.app.update_button.pack.assert_called_once()
        self.app.start.assert_called_once()

    def test_ready_notification_does_not_open_or_focus_companion(self):
        self.app.show=Mock()
        self.event('ready','Reply ready')
        self.app.poll()
        self.app.show.assert_not_called()
        self.app.root.deiconify.assert_not_called()
        self.app.root.focus_force.assert_not_called()

    def test_test_button_sends_a_distinct_localized_notification(self):
        self.app.test_notification()
        self.app.popup.show.assert_called_once_with('MPlusLogs Companion',
            i18n.tr('Это тестовое уведомление MPlusLogs Companion.'))
        self.app.root.bell.assert_not_called()

    def test_test_button_honors_disabled_notifications(self):
        self.app.notifications.get.return_value=False
        self.app.test_notification()
        self.app.popup.show.assert_not_called()
        self.app.notification_test_status.set.assert_called_once_with('Сначала включите всплывающие уведомления.')


class NativeNotificationTests(unittest.TestCase):
    def test_ready_can_suppress_windows_sound_without_changing_update_default(self):
        tray=windows.Tray.__new__(windows.Tray)
        tray.hwnd=123
        tray.notification_queue=queue.Queue()
        with patch.object(windows.ctypes,'WinDLL',create=True) as library:
            tray.notify('MPlusLogs Companion','Reply ready',silent=True)
            library.return_value.PostMessageW.assert_called_with(123,0x8003,0,0)
            tray.notify('MPlusLogs Companion','Update ready')
            self.assertEqual(tray.notification_queue.get_nowait(),('MPlusLogs Companion','Reply ready',0x11))
            self.assertEqual(tray.notification_queue.get_nowait(),('MPlusLogs Companion','Update ready',1))
            self.assertTrue(tray.notification_queue.empty())


class InstallerNotificationCommandTests(unittest.TestCase):
    def test_installer_command_saves_choice_without_opening_app_or_taking_instance(self):
        for value in ('on','off'):
            with self.subTest(value=value),patch.object(sys,'argv',['companion','--set-notifications',value]), \
                 patch.object(gui.local_settings,'set_notifications') as save, \
                 patch.object(gui.tk,'Tk') as root,patch.object(gui.windows,'SingleInstance') as instance:
                gui.main()
                save.assert_called_once_with(value=='on')
                root.assert_not_called()
                instance.assert_not_called()

    def test_invalid_or_failed_installer_choice_returns_failure(self):
        for args in ([],['invalid']):
            with patch.object(sys,'argv',['companion','--set-notifications',*args]), \
                 patch.object(gui.local_settings,'set_notifications') as save:
                with self.assertRaises(SystemExit) as failure:
                    gui.main()
                self.assertEqual(failure.exception.code,2)
                save.assert_not_called()
        with patch.object(sys,'argv',['companion','--set-notifications','on']), \
             patch.object(gui.local_settings,'set_notifications',side_effect=OSError('read-only')):
            with self.assertRaises(SystemExit) as failure:
                gui.main()
            self.assertEqual(failure.exception.code,1)


if __name__=='__main__': unittest.main()
