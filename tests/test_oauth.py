"""Security and lifecycle checks for OAuth; never contact WCL or use real credentials."""
import importlib.util
import importlib.machinery
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import wcl_oauth as oauth
import wcl_sync
import clipboard_companion
import local_settings
import windows_integration


class OAuthTests(unittest.TestCase):
    def test_s256_rfc7636_vector(self):
        self.assertEqual(oauth.challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
                         "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_callback_rejects_forgery_and_duplicates(self):
        for path in ("/callback?code=x&state=wrong", "/other?code=x&state=expected",
                     "/callback?code=x&state=expected&state=expected", "/callback?state=expected"):
            with self.assertRaises(ValueError):
                oauth.callback_code(path, "expected")
        self.assertEqual(oauth.callback_code("/callback?code=one-use&state=expected", "expected"), "one-use")
        with self.assertRaises(PermissionError):
            oauth.callback_code("/callback?error=access_denied&state=expected", "expected")

    def test_browser_loopback_exchange_has_no_secret(self):
        callbacks = []
        threads = []
        def opener(url):
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["code_challenge_method"], ["S256"])
            self.assertNotIn("client_secret", query)
            def callback():
                with urlopen(oauth.REDIRECT_URI + "?" + urlencode({"state": query["state"][0], "code": "test-code"}), timeout=5) as response:
                    callbacks.append(response.status)
            thread = threading.Thread(target=callback)
            threads.append(thread)
            thread.start()
            return True
        response = {"access_token": "fake-access", "refresh_token": "fake-refresh", "expires_in": 3600}
        with patch.object(oauth, "exchange", return_value=response) as exchange:
            tokens = oauth.login("public-id", opener=opener, timeout=5)
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(callbacks, [200])
        self.assertEqual(tokens["access_token"], "fake-access")
        fields = exchange.call_args.args[0]
        self.assertNotIn("client_secret", fields)
        self.assertEqual(fields["grant_type"], "authorization_code")
        self.assertEqual(fields["redirect_uri"], oauth.REDIRECT_URI)
        self.assertGreaterEqual(len(fields["code_verifier"]), 43)

    def test_cancel_does_not_exchange(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(oauth, "exchange") as exchange:
            with self.assertRaises(ValueError):
                oauth.login("public-id", cancel=cancel, opener=lambda url: True)
            exchange.assert_not_called()

    def test_refresh_preserves_refresh_token_and_persists(self):
        saved = []
        session = oauth.Session("public-id", {"access_token": "expired", "refresh_token": "refresh", "expires_at": 0}, saved.append)
        with patch.object(oauth, "exchange", return_value={"access_token": "renewed", "expires_in": 3600}) as exchange:
            self.assertEqual(session.access_token(), "renewed")
            self.assertEqual(session.access_token(), "renewed")
            self.assertEqual(exchange.call_count, 1)
            self.assertNotIn("client_secret", exchange.call_args.args[0])
        self.assertEqual(saved[0]["refresh_token"], "refresh")

    def test_expired_session_without_refresh_requires_login(self):
        session = oauth.Session("public-id", {"access_token": "old", "expires_at": 0}, lambda value: None)
        with patch.object(oauth, "exchange") as exchange:
            with self.assertRaises(ValueError):
                session.access_token()
            exchange.assert_not_called()

    def test_account_scope_survives_rotating_tokens_restart_and_login(self):
        tokens = {"access_token": "old", "refresh_token": "old-refresh", "expires_at": 0,
                  "_account_id": 17, "_api_budget": {"limit": 720}}
        saved = []
        session = oauth.Session("public-id", tokens, saved.append)
        with patch.object(oauth, "exchange", return_value={"access_token": "new", "refresh_token": "new-refresh", "expires_in": 3600}), \
             patch.object(wcl_sync, "request_json") as request:
            scope = session.cache_scope()
            session.access_token()
            self.assertEqual(session.cache_scope(), scope)
            restarted = oauth.Session("public-id", saved[-1], saved.append)
            self.assertEqual(restarted.cache_scope(), scope)
            login = oauth.Session("public-id", dict(saved[-1], access_token="another-login", refresh_token="another-refresh"), saved.append)
            self.assertEqual(login.cache_scope(), scope)
            request.assert_not_called()
        self.assertEqual(saved[-1]["_account_id"], 17)
        self.assertEqual(saved[-1]["_api_budget"], {"limit": 720})
        for account, client in ((18, "public-id"), (17, "other-client")):
            other = oauth.Session(client, dict(saved[-1], _account_id=account), saved.append)
            self.assertNotEqual(other.cache_scope(), scope)

    def test_legacy_session_resolves_account_once_and_persists_it(self):
        tokens = {"access_token": "test", "expires_at": time.time() + 3600}
        saved = []
        response = {"data": {"characterData": {"__typename": "CharacterData"},
                             "userData": {"currentUser": {"id": 17}}, "rateLimitData": {"limitPerHour": 720}}}
        session = oauth.Session("public-id", tokens, saved.append)
        with patch.object(wcl_sync, "request_json", return_value=response) as request:
            scope = session.cache_scope()
            self.assertEqual(session.cache_scope(), scope)
            self.assertEqual(oauth.Session("public-id", saved[-1], saved.append).cache_scope(), scope)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(saved[-1]["_account_id"], 17)
        self.assertIn("currentUser { id }", json.loads(request.call_args.args[1])["query"])

    def test_login_probe_records_identity_and_returns_quota(self):
        tokens = {"access_token": "test"}
        quota = {"limitPerHour": 720, "pointsSpentThisHour": 10, "pointsResetIn": 300}
        response = {"data": {"characterData": {"__typename": "CharacterData"},
                             "userData": {"currentUser": {"id": 17}}, "rateLimitData": quota}}
        with patch.object(wcl_sync, "request_json", return_value=response):
            self.assertEqual(oauth.validate_access(tokens), quota)
        self.assertEqual(tokens["_account_id"], 17)

    def test_unverified_identity_never_persists_or_shares_cache(self):
        for value in (None, True, "17", 0, -1, 1.5, 2147483648):
            with self.subTest(value=value):
                saved = []
                session = oauth.Session("public-id", {"access_token": "test", "expires_at": time.time()+3600}, saved.append)
                response = {"data": {"characterData": {"__typename": "CharacterData"},
                                     "userData": {"currentUser": {"id": value}}}}
                with patch.object(wcl_sync, "request_json", return_value=response):
                    with self.assertRaises(ValueError):
                        session.cache_scope()
                self.assertFalse(saved)


    def test_oauth_requests_use_user_endpoint_and_invalidate_401(self):
        invalidate = unittest.mock.Mock()
        client = clipboard_companion.Client(token_provider=lambda: "fake-token", invalidate_token=invalidate)
        with patch.object(wcl_sync, "fetch", return_value={"data": {}}) as fetch:
            client(SimpleNamespace())
            self.assertEqual(fetch.call_args.kwargs, {"endpoint": "user"})
        with patch.object(wcl_sync, "fetch", side_effect=ValueError("WCL HTTP 401")):
            with self.assertRaises(ValueError):
                client(SimpleNamespace(name="Other"))
        invalidate.assert_called_once()

    def test_user_endpoint_preserves_rankings_query(self):
        args = SimpleNamespace(character_id=None, name="Example", server_slug="example", region="eu", zone=55, spec=None)
        with patch.object(wcl_sync, "request_json", return_value={"data": {}}) as request:
            wcl_sync.fetch(args, "fake-token", endpoint="user")
        self.assertTrue(request.call_args.args[0].endswith("/api/v2/user"))
        body = json.loads(request.call_args.args[1])
        self.assertIn("points_and_healing", body["query"])
        self.assertIn("points_and_damage", body["query"])

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI")
    def test_dpapi_roundtrip_and_no_plaintext_or_legacy_secret(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-work-") as directory:
            target = Path(directory) / "settings.json"
            tokens = {"access_token": "fake-private-access", "refresh_token": "fake-private-refresh", "expires_at": time.time() + 3600}
            with patch.object(local_settings, "PATH", target):
                local_settings.save_config({"oauth_client_id": "public", "oauth": tokens, "theme": "dark", "secret": "legacy-secret", "secret_dpapi": "legacy"})
                text = target.read_text()
                self.assertNotIn("fake-private", text)
                self.assertNotIn("legacy", text)
                self.assertEqual(local_settings.load()["oauth"], tokens)
                self.assertEqual(local_settings.load()["theme"], "dark")
                local_settings.save_config({"oauth_client_id": "public"})
                self.assertNotIn("oauth", local_settings.load())


@unittest.skipUnless(sys.platform == "win32", "Windows shell")
class WindowsLifecycleTests(unittest.TestCase):
    def test_second_instance_signals_primary(self):
        # Test uses a unique namespace so an already-running app is unaffected.
        real_library = windows_integration.ctypes.WinDLL
        class KernelProxy:
            def __init__(self):
                self.real = real_library("kernel32", use_last_error=True)
            def __getattr__(self, name):
                return getattr(self.real, name)
            def CreateMutexW(self, security, owner, name):
                self.real.CreateMutexW.argtypes = [windows_integration.ctypes.c_void_p, windows_integration.wt.BOOL, windows_integration.wt.LPCWSTR]
                self.real.CreateMutexW.restype = windows_integration.wt.HANDLE
                return self.real.CreateMutexW(security, owner, name + ".test." + str(__import__("os").getpid()))
            def CreateEventW(self, security, manual, initial, name):
                self.real.CreateEventW.argtypes = [windows_integration.ctypes.c_void_p, windows_integration.wt.BOOL, windows_integration.wt.BOOL, windows_integration.wt.LPCWSTR]
                self.real.CreateEventW.restype = windows_integration.wt.HANDLE
                return self.real.CreateEventW(security, manual, initial, name + ".test." + str(__import__("os").getpid()))
        # Function proxies need writable argtypes/restype attributes.
        class Function:
            def __init__(self, callback):
                self.callback = callback
            def __call__(self, *args):
                return self.callback(*args)
        proxy = KernelProxy()
        mutex, event = proxy.CreateMutexW, proxy.CreateEventW
        proxy.CreateMutexW, proxy.CreateEventW = Function(mutex), Function(event)
        with patch.object(windows_integration.ctypes, "WinDLL", return_value=proxy):
            first = windows_integration.SingleInstance()
            second = windows_integration.SingleInstance()
            try:
                self.assertTrue(first.primary)
                self.assertFalse(second.primary)
                self.assertTrue(first.show_requested())
                self.assertFalse(first.show_requested())
            finally:
                second.close()
                first.close()

    def test_native_tray_lifecycle(self):
        import queue
        try:
            tray = windows_integration.Tray(queue.Queue())
        except OSError as exc:
            if "PermissionError" in str(exc) or "startup timed out" in str(exc):
                self.skipTest("This Windows session denies or delays native tray creation")
            raise
        self.assertTrue(tray.hwnd)
        self.assertIsNone(tray.error)
        tray.close()
        self.assertFalse(tray.thread.is_alive())
        self.assertIsNone(tray.hwnd)

    def test_gui_start_hide_show_sign_out_exit(self):
        import tkinter as tk
        loader = importlib.machinery.SourceFileLoader("companion_gui_test", str(ROOT / "tools/companion_gui.pyw"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        gui = importlib.util.module_from_spec(spec)
        loader.exec_module(gui)
        with patch.object(local_settings, "load", return_value={}), patch.object(sys, "argv", ["test"]):
            root = tk.Tk()
            root.withdraw()
            app = gui.App(root)
            try:
                app.last_heartbeat = time.time()
                root.update()
                self.assertIsNotNone(app.tray)
                self.assertEqual(root.resizable(), (0,0))
                with patch.object(gui.appearance, "system_theme", return_value="dark"):
                    app.theme.set("system")
                    app.refresh_theme()
                    self.assertEqual(root.cget("background"), gui.appearance.PALETTES["dark"]["background"])
                    app.settings()
                    self.assertEqual(app.settings_window.cget("background"), root.cget("background"))
                with patch.object(gui.appearance, "system_theme", return_value="light"):
                    app.refresh_theme()
                    self.assertEqual(root.cget("background"), gui.appearance.PALETTES["light"]["background"])
                    app.theme.set("dark")
                    app.refresh_theme()
                    self.assertEqual(root.cget("background"), gui.appearance.PALETTES["dark"]["background"])
                app.settings_window.destroy()
                app.show()
                root.update()
                self.assertEqual(root.state(), "normal")
                app.hide()
                root.update()
                self.assertEqual(root.state(), "withdrawn")
                app.mode_diagnostic, app.want_running = True, True
                app.start()
                self.assertTrue(app.worker.is_alive())
                with patch.object(local_settings, "save_config"):
                    app.messages.put(("auth", ({"access_token": "fake", "expires_at": time.time() + 3600}, app.auth_cancel)))
                    app.poll()
                    self.assertEqual(app.login_button.winfo_manager(), "")
                    self.assertTrue(app.want_running)
                    app.sign_out()
                    app.worker.join(timeout=3)
                    self.assertEqual(app.login_button.winfo_manager(), "pack")
                    self.assertIsNone(app.session)
            finally:
                app.exit()

    def test_optional_autostart_registration_in_isolated_key(self):
        import winreg
        import uuid
        key_path = r"Software\MPlusLogsTest-" + uuid.uuid4().hex
        with patch.object(windows_integration, "RUN_KEY", key_path):
            try:
                self.assertFalse(windows_integration.autostart_enabled())
                windows_integration.set_autostart(True)
                self.assertTrue(windows_integration.autostart_enabled())
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    command, _ = winreg.QueryValueEx(key, windows_integration.APP_NAME)
                self.assertIn("--background", command)
                self.assertIn("pythonw.exe", command)
                self.assertIn("companion_gui.pyw", command)
                windows_integration.set_autostart(False)
                self.assertFalse(windows_integration.autostart_enabled())
            finally:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)


if __name__ == "__main__":
    unittest.main()
