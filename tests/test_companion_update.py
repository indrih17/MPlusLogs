"""Update trust boundaries, damaged downloads and independent versioning."""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import companion_update as updates
import companion_version as versions


def manifest(content=b"installer", version="1.2.3"):
    return {"schema": 1, "version": version, "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "url": f"https://github.com/indrih17/MPlusLogs/releases/download/companion-v{version}/MPlusLogs-Companion-{version}-Setup.exe"}


class UpdateTests(unittest.TestCase):
    def test_check_only_offers_newer_versions(self):
        for current, offered in (("1.2.2", True), ("1.2.3", False), ("1.2.10", False)):
            with patch.object(updates, "urlopen", return_value=io.BytesIO(json.dumps(manifest()).encode())), \
                 patch.object(updates, "current_version", return_value=current):
                self.assertEqual(updates.check() is not None, offered)

    def test_manifest_rejects_foreign_urls_unbounded_files_and_invalid_versions(self):
        for changes in ({"url": "https://example.com/Setup.exe"}, {"url": manifest()["url"] + "?redirect=x"},
                        {"size": updates.MAX_INSTALLER + 1}, {"size": True}, {"sha256": "bad"},
                        {"version": "1.2.3-beta"}, {"schema": 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                updates.validate_manifest(dict(manifest(), **changes))

    def test_download_verifies_bytes_and_cleans_failed_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            for index, (content, success) in enumerate(((b"installer", True), (b"damaged!!", False), (b"too much content", False), (b"short", False))):
                destination = Path(folder) / str(index)
                destination.mkdir()
                with patch.object(updates.tempfile, "mkdtemp", return_value=str(destination)), \
                     patch.object(updates, "urlopen", return_value=io.BytesIO(content)):
                    if success:
                        self.assertEqual(updates.download(manifest()).read_bytes(), content)
                    else:
                        with self.assertRaises(ValueError):
                            updates.download(manifest())
                        self.assertFalse(destination.exists())

    def test_installer_tampering_never_launches(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            target = Path(folder) / "Setup.exe"
            target.write_bytes(b"tampered!")
            with patch.object(sys, "frozen", True, create=True), patch.object(updates.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError):
                    updates.launch_installer(target, manifest(), result_root=Path(folder) / "results")
                launch.assert_not_called()

    def test_helper_waits_for_process_and_preserves_install_directory(self):
        import base64
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            target = Path(folder) / "Setup.exe"
            target.write_bytes(b"installer")
            with patch.object(sys, "frozen", True, create=True), patch.object(updates, 'portable_build', return_value=False), patch.object(updates.subprocess, "Popen") as launch:
                updates.launch_installer(target, manifest(), result_root=Path(folder) / "results")
                args = launch.call_args.args[0]
                script = base64.b64decode(args[-1]).decode("utf-16-le")
                self.assertIn("Wait-Process -Id", script)
                self.assertIn("/UPDATECOMPANION=1", script)
                self.assertIn("/DIR=", script)
                self.assertIn("finally", script)
                self.assertIn("$installer.ExitCode", script)
                self.assertIn("$code -eq 0 -and $installed", script)
                self.assertIn("update-result.json", script)
                self.assertIn("/LOG=", script)
                self.assertIn("/FORCECLOSEAPPLICATIONS", script)
                self.assertIn("Test-Path -LiteralPath", script)
                self.assertEqual(args[args.index("-WindowStyle") + 1], "Hidden")
                self.assertEqual(launch.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_companion_version_changes_once_for_changed_inputs(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            (root / "packaging").mkdir()
            (root / "tools").mkdir()
            (root / "tools/app.py").write_text("old")
            (root / "realm-slugs.json").write_text("{}")
            data = root / "packaging/companion-version.json"
            for name in ("companion.iss", "COMPANION-README.txt"):
                (root / "packaging" / name).write_text("1.0.0")
            with patch.object(versions, "ROOT", root), patch.object(versions, "METADATA", data), patch.object(versions, "RUNTIME", ["app.py"]):
                data.write_text(json.dumps({"version": "1.0.0", "source_hash": versions.source_hash()}))
                self.assertFalse(versions.prepare())
                # An addon version change is absent from the Companion fingerprint.
                (root / "MPlusLogs.toc").write_text("## Version: 99.0.0")
                self.assertFalse(versions.prepare())
                (root / "tools/app.py").write_text("new")
                self.assertTrue(versions.prepare())
                self.assertEqual(versions.version(), "1.0.1")
                self.assertFalse(versions.prepare())

    @unittest.skipUnless(sys.platform == "win32", "Windows updater helper")
    def test_failed_installer_exit_is_persisted_for_the_next_launch(self):
        import base64
        import subprocess
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            result_root = root / "results"
            result_root.mkdir()
            target = root / "Reject.cmd"
            target.write_text("@exit /b 7\n")
            departed = subprocess.Popen([sys.executable, "-c", "pass"])
            departed.wait(timeout=10)
            script = updates.installer_script(target, manifest(), root / "Absent.exe", departed.pid, result_root)
            encoded = base64.b64encode(script.encode("utf-16-le")).decode()
            subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                           capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            result = json.loads((result_root / "update-result.json").read_text(encoding="utf-8-sig"))
            self.assertFalse(result["success"])
            self.assertEqual(result["exit_code"], 7)
            with patch.object(updates.local_settings, "PATH", result_root / "settings.json"):
                self.assertEqual(updates.last_result()["expected_version"], "1.2.3")

    def test_ui_waits_for_request_worker_before_launching_installer(self):
        loader = importlib.machinery.SourceFileLoader("update_gui_test", str(ROOT / "tools/companion_gui.pyw"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        gui = importlib.util.module_from_spec(spec)
        loader.exec_module(gui)
        app = gui.App.__new__(gui.App)
        app.root = Mock()
        app.worker = Mock()
        app.worker.is_alive.return_value = True
        app.update_installer, app.available_update = "setup", manifest()
        app.exit = Mock()
        with patch.object(updates, "launch_installer") as launch:
            app.finish_update()
            launch.assert_not_called()
            app.root.after.assert_called_once()
            app.worker.is_alive.return_value = False
            app.finish_update()
            launch.assert_called_once_with("setup", app.available_update)
            app.exit.assert_called_once()

    def test_failed_version_is_not_downloaded_automatically_but_can_be_retried(self):
        import gc
        import queue
        # Dispose earlier Tk test objects on the main thread before starting a worker.
        gc.collect()
        loader = importlib.machinery.SourceFileLoader("retry_update_gui_test", str(ROOT / "tools/companion_gui.pyw"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        gui = importlib.util.module_from_spec(spec)
        loader.exec_module(gui)
        app = gui.App.__new__(gui.App)
        app.installing_update = False
        app.update_worker = None
        app.available_update = app.update_installer = None
        app.failed_update_version = "1.2.3"
        app.messages = queue.Queue()
        app.update_status = Mock()
        with patch.object(updates, "check", return_value=manifest()), patch.object(updates, "download", return_value="test-installer") as download:
            app.check_updates()
            app.update_worker.join(timeout=5)
            self.assertFalse(app.update_worker.is_alive())
            download.assert_not_called()
            app.check_updates(manual=True)
            app.update_worker.join(timeout=5)
            download.assert_called_once()


if __name__ == "__main__":
    unittest.main()
