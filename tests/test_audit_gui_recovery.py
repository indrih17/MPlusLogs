"""Recoverable local failures must not strand sign-in or completed replies."""
import importlib.machinery
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import queue
import sys
import threading
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
loader = importlib.machinery.SourceFileLoader("audit_gui_recovery", str(ROOT / "tools/companion_gui.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
gui = importlib.util.module_from_spec(spec)
loader.exec_module(gui)


class RecoveryTests(unittest.TestCase):
    def test_failed_startup_change_does_not_restore_stale_oauth_tokens(self):
        app = gui.App.__new__(gui.App)
        app.config_lock = threading.RLock()
        app.config = {"oauth": {"access_token": "old-token"}, "theme": "light"}
        app.root = Mock()
        app.startup_mode = Mock()
        app.startup_mode.get.return_value = "retail"
        app.sound, app.theme, app.language = Mock(), Mock(), Mock()
        app.sound.get.return_value = True
        app.theme.get.return_value = "dark"
        app.language.get.return_value = "enUS"

        def refresh_then_fail():
            # Token refresh can finish while the main thread starts the watcher.
            with app.config_lock:
                refreshed = dict(app.config, oauth={"access_token": "refreshed-token"})
                gui.local_settings.save_config(refreshed)
                app.config = refreshed
            raise OSError("watcher could not start")

        with patch.object(gui.windows, "autostart_enabled", return_value=False), \
                patch.object(gui.windows, "retail_autostart_enabled", return_value=False), \
                patch.object(gui.windows, "set_autostart"), \
                patch.object(gui.windows, "set_retail_autostart"), \
                patch.object(gui.windows, "ensure_retail_watcher", side_effect=refresh_then_fail), \
                patch.object(gui.local_settings, "save_config") as save, \
                patch.object(gui.messagebox, "showerror"):
            app.save_preferences()
        self.assertEqual(app.config["oauth"]["access_token"], "refreshed-token")
        self.assertEqual(save.call_args.args[0]["oauth"]["access_token"], "refreshed-token")

    def test_invalid_compressed_payload_reports_a_recoverable_update_error(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("MPlusLogs-Companion/MPlusLogs-Companion.exe", b"fixture" * 20)
            archive.writestr("MPlusLogs-Companion/_internal/companion-build.json",
                             json.dumps({"version": "1.2.3", "portable": True}))
        value = bytearray(content.getvalue())
        with zipfile.ZipFile(io.BytesIO(value)) as archive:
            entry = archive.infolist()[0]
        offset = entry.header_offset + 30 + len(entry.filename.encode())
        value[offset:offset + entry.compress_size] = b"\xff" * entry.compress_size
        data = {"version": "1.2.3", "size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-work-") as directory:
            archive = Path(directory) / "invalid.zip"
            archive.write_bytes(value)
            stage = Path(directory) / "stage"
            stage.mkdir()
            with patch.object(gui.updates.portable_update.tempfile, "mkdtemp", return_value=str(stage)):
                with self.assertRaises(ValueError):
                    gui.updates.portable_update.prepare(archive, data)
            self.assertFalse(stage.exists())

    def test_failed_sign_out_does_not_cancel_an_active_sign_in(self):
        app = gui.App.__new__(gui.App)
        app.auth_cancel = threading.Event()
        app.config_lock = threading.RLock()
        app.config = {"oauth": {"access_token": "fixture"}, "theme": "dark"}
        app.session = object()
        previous_session = app.session
        app.root = Mock()
        app.login_button = Mock()
        app.want_running = False  # Paused while browser sign-in is in progress.
        with patch.object(gui.local_settings, "save_config", side_effect=OSError("locked settings")), \
                patch.object(gui.messagebox, "showerror") as show_error:
            app.sign_out()
        show_error.assert_called_once()
        self.assertFalse(app.auth_cancel.is_set(), "Failed sign-out must leave the pending login usable")
        self.assertIs(app.session, previous_session)
        self.assertIn("oauth", app.config)

    def test_completed_reply_survives_locked_last_result_file(self):
        app = gui.App.__new__(gui.App)
        app.messages = queue.Queue()
        app.clipboard_events = []
        app.installing_update = False
        stop = Mock()
        stop.wait.side_effect = [False, True]
        stop.is_set.return_value = False
        clipboard = Mock()
        clipboard.sequence.return_value = 7
        clipboard.read.return_value = "MPLS1\n12345-1\nMPLQ1\nQ\teu\tGordunni\tFixture\tdps\tGuardian\n"
        clipboard.reply_if_unchanged.return_value = True
        response = "MPLE1\n12345-1\nfixture"
        with patch.object(gui.bridge, "WindowsClipboard", return_value=clipboard), \
                patch.object(gui.realm_resolver, "load_mappings", return_value={}), \
                patch.object(gui.cache_maintenance, "maintain"), \
                patch.object(gui.clipboard_protocol, "reply", return_value=response), \
                patch.object(gui.build_database, "atomic_write", side_effect=PermissionError("locked result")):
            app.watch(stop, None, True, 0)
        clipboard.reply_if_unchanged.assert_called_once_with(clipboard.read.return_value, response)
        messages = list(app.messages.queue)
        self.assertTrue(any(value[1:] == ("result", response) for kind, value in messages if kind == "worker"))
        self.assertTrue(any(value[1] == "ready" for kind, value in messages if kind == "worker"))


if __name__ == "__main__":
    unittest.main()
