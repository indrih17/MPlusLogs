"""Retail path discrimination and launch lifecycle, without starting the game."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "tools"))
import retail_launcher as launcher
import windows_integration as windows


class RetailLauncherTests(unittest.TestCase):
    def test_retail_only_executable_path(self):
        for path in (r"E:\World of Warcraft\_retail_\Wow.exe",r"C:\Games\_RETAIL_\WOW.EXE"):
            self.assertTrue(launcher.is_retail_path(path))
        for path in (r"E:\World of Warcraft\_classic_\WowClassic.exe",
                     r"E:\World of Warcraft\_classic_\Wow.exe",
                     r"E:\World of Warcraft\_ptr_\Wow.exe",
                     r"E:\World of Warcraft\_retail_\WowT.exe",
                     r"E:\World of Warcraft\_retail_\subfolder\Wow.exe"):
            self.assertFalse(launcher.is_retail_path(path))

    def test_exit_stays_closed_until_next_game_launch(self):
        state = launcher.LaunchState()
        self.assertTrue(state.update({10},False))
        self.assertFalse(state.update({10},False))  # Manual exit during the same game.
        self.assertFalse(state.update(set(),False))
        self.assertTrue(state.update({11},False))

    def test_existing_companion_does_not_get_relaunched(self):
        state = launcher.LaunchState()
        self.assertFalse(state.update({10},True))
        self.assertFalse(state.update({10},False))
        self.assertTrue(state.update({11},False))

    def test_watcher_launches_on_transitions_and_stops_when_disabled(self):
        instance = Mock(primary=True)
        with patch.object(windows,"SingleInstance",return_value=instance), \
             patch.object(windows,"retail_autostart_enabled",side_effect=[True,True,True,False]), \
             patch.object(windows,"instance_running",return_value=False), \
             patch.object(launcher,"retail_processes",side_effect=[{10},{10},{11}]), \
             patch.object(launcher.time,"sleep"), patch.object(launcher.subprocess,"Popen") as spawn:
            launcher.watch()
        self.assertEqual(spawn.call_count,2)
        self.assertIn("--background",spawn.call_args.args[0])
        instance.close.assert_called_once()

    def test_duplicate_watcher_never_launches_or_enumerates(self):
        instance = Mock(primary=False)
        with patch.object(windows,"SingleInstance",return_value=instance), \
             patch.object(launcher,"retail_processes") as scan, patch.object(launcher.subprocess,"Popen") as spawn:
            launcher.watch()
        scan.assert_not_called()
        spawn.assert_not_called()
        instance.close.assert_called_once()

    @unittest.skipUnless(sys.platform=="win32","Windows registry")
    def test_independent_windows_and_retail_registration(self):
        import uuid,winreg
        temporary_key = r"Software\MPlusLogsTest-" + uuid.uuid4().hex
        with patch.object(windows,"RUN_KEY",temporary_key):
            try:
                windows.set_retail_autostart(True)
                self.assertTrue(windows.retail_autostart_enabled())
                self.assertFalse(windows.autostart_enabled())
                windows.set_autostart(True)
                self.assertTrue(windows.autostart_enabled())
                windows.set_retail_autostart(False)
                self.assertTrue(windows.autostart_enabled())
                self.assertFalse(windows.retail_autostart_enabled())
            finally:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER,temporary_key)


if __name__=="__main__":
    unittest.main()
