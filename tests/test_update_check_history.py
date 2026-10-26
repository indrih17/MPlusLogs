"""Persistent update diagnostics must remain bounded, private and optional."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import companion_update as updates


class UpdateCheckHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(directory.cleanup)
        self.settings = Path(directory.name) / "user data" / "settings.json"
        self.path = self.settings.with_name("update-check.json")
        settings_patch = patch.object(updates.local_settings, "PATH", self.settings)
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

    def record(self, status, timestamp, **kwargs):
        clock = Mock()
        clock.now.return_value.isoformat.return_value = timestamp
        with patch.object(updates, "datetime", clock):
            updates.record_check(status, **kwargs)
        clock.now.assert_called_once_with(updates.timezone.utc)

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_check_start_and_success_are_separate_and_settings_remain_untouched(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"secret_dpapi":"unchanged"}', encoding="utf-8")
        self.record("checking", "2026-10-26T10:00:00+00:00")
        self.assertEqual(self.read(), {"status": "checking", "last_attempt": "2026-10-26T10:00:00+00:00"})
        self.record("current", "2026-10-26T10:00:05+00:00")
        self.assertEqual(self.read(), {"status": "current", "last_attempt": "2026-10-26T10:00:00+00:00",
                                     "last_success": "2026-10-26T10:00:05+00:00"})
        self.assertEqual(self.settings.read_text(encoding="utf-8"), '{"secret_dpapi":"unchanged"}')
        self.assertFalse(self.path.with_suffix(".tmp").exists())

    def test_available_and_ready_preserve_attempt_and_track_verified_version(self):
        self.record("checking", "attempt")
        self.record("available", "manifest", version="1.2.3")
        self.assertEqual(self.read()["available_version"], "1.2.3")
        self.assertEqual(self.read()["last_success"], "manifest")
        self.record("ready", "download", version="1.2.3")
        self.assertEqual(self.read(), {"status": "ready", "last_attempt": "attempt",
                                     "last_success": "download", "available_version": "1.2.3"})

    def test_failures_preserve_successful_check_and_never_store_exception_text(self):
        self.record("checking", "attempt")
        self.record("available", "success", version="1.2.3")
        for status in ("check_error", "download_error"):
            with self.subTest(status=status):
                self.record(status, "failure", error=OSError("https://user:password@example.com/?token=secret"))
                self.assertEqual(self.read(), {"status": status, "last_attempt": "attempt",
                                             "last_success": "success", "available_version": "1.2.3",
                                             "error_type": "OSError"})
                self.assertNotIn("password", self.path.read_text(encoding="utf-8"))
                self.assertNotIn("token", self.path.read_text(encoding="utf-8"))

    def test_retry_records_new_attempt_without_erasing_previous_success(self):
        self.record("checking", "first")
        self.record("current", "success")
        self.record("check_error", "failure", error=TimeoutError("secret"))
        self.record("checking", "retry")
        self.assertEqual(self.read(), {"status": "checking", "last_attempt": "retry", "last_success": "success"})

    def test_current_clears_obsolete_available_version(self):
        self.record("available", "before", version="1.2.3")
        self.record("current", "after")
        self.assertEqual(self.read(), {"status": "current", "last_success": "after"})

    def test_bad_history_is_replaced_without_reusing_untrusted_fields(self):
        self.path.parent.mkdir(parents=True)
        for content in (b"broken", b"[]", b"null", b"\xff", b"x" * (updates.CHECK_HISTORY_LIMIT + 1),
                        b'{"secret":"discard","error":"token=secret","available_version":"bad"}'):
            with self.subTest(content_length=len(content)):
                self.path.write_bytes(content)
                self.record("checking", "attempt")
                self.assertEqual(self.read(), {"status": "checking", "last_attempt": "attempt"})

    def test_history_read_has_an_explicit_byte_limit(self):
        source = Mock()
        source.__enter__ = Mock(return_value=source)
        source.__exit__ = Mock(return_value=False)
        source.read.return_value = b"{}"
        with patch.object(Path, "open", return_value=source), patch.object(Path, "write_text"), patch.object(Path, "replace"):
            updates.record_check("checking")
        source.read.assert_called_once_with(updates.CHECK_HISTORY_LIMIT + 1)

    def test_write_and_replace_failures_never_escape_or_destroy_last_record(self):
        self.record("current", "success")
        original = self.path.read_bytes()
        for method in ("mkdir", "write_text", "replace"):
            with self.subTest(method=method), patch.object(Path, method, side_effect=PermissionError("denied")):
                updates.record_check("checking")
                self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
