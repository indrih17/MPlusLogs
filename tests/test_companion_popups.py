"""Popup lifetime, hover, queued replies and deliberate activation."""
from pathlib import Path
import gc
import sys
import tkinter as tk
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import companion_notifications as notifications


class PopupTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.activate=Mock()
        self.popup=notifications.PopupNotifications(self.root,self.activate,duration=20)
        self.native=patch.object(notifications,'show_without_activation')
        self.presenter=self.native.start()

    def tearDown(self):
        self.popup.close()
        self.root.update_idletasks()
        self.root.destroy()
        self.native.stop()
        # Mock call arguments also retain the presented Tk window/root.
        self.popup = self.root = self.presenter = self.native = self.activate = None
        gc.collect()

    def test_card_shows_brand_text_and_expires_without_activating_owner(self):
        self.popup.show('MPlusLogs Companion','Reply ready: Ctrl+V')
        self.assertEqual(self.popup.status['state'],'shown')
        self.assertEqual(self.popup.current,('MPlusLogs Companion','Reply ready: Ctrl+V'))
        self.presenter.assert_called_once()
        self.activate.assert_not_called()
        self.root.after(40,self.root.quit);self.root.mainloop()
        self.assertIsNone(self.popup.window)
        self.assertEqual(self.popup.status['state'],'closed')
        self.activate.assert_not_called()

    def test_next_notice_waits_until_current_one_is_dismissed(self):
        self.popup.show('MPlusLogs','Reply ready')
        self.popup.show('MPlusLogs','Update ready')
        self.assertEqual(self.popup.current,('MPlusLogs','Reply ready'))
        self.assertEqual(len(self.popup.pending),1)
        self.popup._dismiss()
        self.assertEqual(self.popup.current,('MPlusLogs','Update ready'))

    def test_repeated_notice_does_not_create_duplicate_cards(self):
        self.popup.show('MPlusLogs','Reply ready')
        first=self.popup.window
        self.popup.show('MPlusLogs','Reply ready')
        self.assertIs(self.popup.window,first)
        self.assertFalse(self.popup.pending)

    def test_hover_pauses_expiry_and_leaving_resumes_it(self):
        self.popup.show('MPlusLogs','Reply ready')
        self.popup._cancel_timer()
        self.root.after(40,self.root.quit);self.root.mainloop()
        self.assertIsNotNone(self.popup.window)
        self.popup._schedule()
        self.root.after(40,self.root.quit);self.root.mainloop()
        self.assertIsNone(self.popup.window)

    def test_disabling_or_exiting_closes_card_cancels_timer_and_clears_queue(self):
        self.popup.show('MPlusLogs','Reply ready')
        self.popup.show('MPlusLogs','Update ready')
        self.popup.close()
        self.assertIsNone(self.popup.window)
        self.assertIsNone(self.popup.timer)
        self.assertFalse(self.popup.pending)
        self.activate.assert_not_called()

    def test_only_clicking_card_activates_companion(self):
        self.popup.show('MPlusLogs','Reply ready')
        self.popup._activate()
        self.activate.assert_called_once()
        self.assertIsNone(self.popup.window)

    def test_icon_failure_cleans_up_and_next_notification_can_show(self):
        with patch.object(notifications.tk,'PhotoImage',side_effect=tk.TclError('bad icon')):
            with self.assertRaises(tk.TclError):self.popup.show('MPlusLogs','First')
        self.assertIsNone(self.popup.window)
        self.popup.show('MPlusLogs','Second')
        self.assertEqual(self.popup.current,('MPlusLogs','Second'))

    def test_queued_update_keeps_its_install_action_and_clears_cards_before_install(self):
        def install():
            self.assertIsNone(self.popup.window)
            self.assertFalse(self.popup.pending)
            self.assertIsNone(self.popup.current_action)
        action=Mock(side_effect=install)
        self.popup.show('MPlusLogs','Reply ready')
        self.popup.show('MPlusLogs','Update ready',on_click=action)
        self.popup.show('MPlusLogs','Update ready',on_click=action)
        self.assertEqual(len(self.popup.pending),1)
        self.popup._dismiss()
        self.popup.show('MPlusLogs','Another reply')
        self.popup._activate()
        action.assert_called_once()
        self.activate.assert_not_called()

    def test_dismissing_update_never_installs_and_next_reply_uses_default_action(self):
        install=Mock()
        self.popup.show('MPlusLogs','Update ready',on_click=install)
        self.popup.show('MPlusLogs','Reply ready')
        self.popup._dismiss()
        install.assert_not_called()
        self.popup._activate()
        self.activate.assert_called_once()
        install.assert_not_called()

    def test_repeated_update_does_not_install_or_duplicate(self):
        install=Mock()
        self.popup.show('MPlusLogs','Update ready',on_click=install)
        window=self.popup.window
        self.popup.show('MPlusLogs','Update ready',on_click=install)
        self.assertIs(self.popup.window,window)
        self.assertFalse(self.popup.pending)
        self.popup.close()
        install.assert_not_called()

    def test_repeated_notice_keeps_hovered_card_visible(self):
        self.popup.show('MPlusLogs','Reply ready')
        self.popup._enter()
        self.popup.show('MPlusLogs','Reply ready')
        self.assertIsNone(self.popup.timer)
        self.root.after(40,self.root.quit);self.root.mainloop()
        self.assertIsNotNone(self.popup.window)


if __name__=='__main__':unittest.main()
