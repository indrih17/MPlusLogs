"""Cross-component regressions found by the October 2026 source audit."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_batch
from test_api_efficiency import dual
import build_database as builder
import clipboard_companion as companion
import wcl_sync as wcl
import wcl_oauth as oauth
import local_settings


ROOT = Path(__file__).resolve().parents[1]


class CompanionAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-work-")
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.entry = dict(name="Киндрих", realm="Гордунни", server_slug="gordunni", region="eu")

    def test_manual_refresh_uses_real_client_after_five_minutes(self):
        stamp = [100000]
        client = companion.Client(token_provider=lambda: "test-token")
        self.addCleanup(client.budget.close)
        client.budget.clock = lambda: stamp[0]
        calls = []

        def fetch(*args, **kwargs):
            calls.append(stamp[0])
            raw = dual()
            raw["data"]["characterData"]["character"]["damage"]["rankings"][0]["totalKills"] = len(calls)
            return raw

        with patch.object(wcl, "fetch", side_effect=fetch):
            first, _ = builder.build([self.entry], self.cache, fetcher=client, now=stamp[0])
            stamp[0] += 299
            builder.build([self.entry], self.cache, fetcher=client, now=stamp[0], refresh=True)
            self.assertEqual(calls, [100000])
            stamp[0] += 1
            refreshed, report = builder.build([self.entry], self.cache, fetcher=client, now=stamp[0], refresh=True)
            self.assertEqual(calls, [100000, 100300])
            self.assertEqual(report["errors"], [])
            self.assertGreater(refreshed[0]["runs"], first[0]["runs"])
            stamp[0] += 300
            builder.build([self.entry], self.cache, fetcher=client, now=stamp[0])
            self.assertEqual(len(calls), 2, "ordinary reads must still use the normal cache TTL")

    def test_batch_unicode_error_is_bounded_for_lua_import(self):
        def fail(_):
            raise ValueError("Ошибка загрузки " * 60)

        response, _ = companion.process_request(
            "MPLQ2\nQ\teu\tГордунни\tКиндрих\n", {"eu": {"Гордунни": "gordunni"}},
            self.cache, fetcher=fail, batch=True)
        from urllib.parse import unquote
        message = unquote(response.splitlines()[1].split("\t")[4])
        self.assertLessEqual(len(message.encode("utf-8")), 500)
        from test_addon import LuaRuntime, MOCK, load_locales
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(MOCK)
        mpl = lua.table()
        load_locales(lua, mpl)
        lua.execute("return assert(loadstring(...))", (ROOT / "Data.lua").read_text(encoding="utf-8"))("MPlusLogs", mpl)
        parsed = mpl.Parse(response, True)
        self.assertFalse(isinstance(parsed, tuple), parsed)
        self.assertEqual(len(list(parsed.failures.values())), 1)

    def test_invalid_cache_metadata_is_ignored_and_refetched(self):
        path = builder.cache_path(self.cache, self.entry)
        for change in ({"retry_until": "later"}, {"negative": True}, {"fetched_at": 1e100},
                       {"fetched_at": 10**400}, {"retry_until": 10**400}):
            with self.subTest(change=change):
                record = dict(fetched_at=100000, raw=dual())
                record.update(change)
                path.write_text(json.dumps(record), encoding="utf-8")
                profiles, report = builder.build([self.entry], self.cache, fetcher=lambda _: dual(), now=200000)
                self.assertEqual(len(profiles), 1)
                self.assertEqual(report["fetched"], 1)

    def test_malformed_upstream_structure_preserves_good_cache(self):
        for raw in ({"data": []}, {"data": {"characterData": []}},
                    {"data": {"characterData": {"character": [1]}}}):
            with self.subTest(raw=raw):
                builder.atomic_write(builder.cache_path(self.cache, self.entry),
                                     json.dumps(dict(fetched_at=100000, raw=dual())))
                profiles, report = builder.build([self.entry], self.cache, fetcher=lambda _: raw, now=200000)
                self.assertEqual(len(profiles), 1)
                self.assertIn("cached", profiles[0]["source"])
                self.assertTrue(report["errors"])
                self.assertNotIn("negative", builder.read_cache(builder.cache_path(self.cache, self.entry)))

    def test_malformed_ranking_rows_raise_a_handled_error(self):
        for value in (None, "bad-row", []):
            with self.subTest(value=value):
                raw = copy.deepcopy(dual())
                raw["data"]["characterData"]["character"]["damage"]["rankings"] = [value]
                with self.assertRaises(ValueError):
                    wcl.normalize(raw, builder.arguments(self.entry))

    def test_invalid_settings_container_fails_as_a_recoverable_error(self):
        target = self.cache / "settings.json"
        for data in ([], None, "broken"):
            with self.subTest(data=data), patch.object(local_settings, "PATH", target):
                target.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    local_settings.load()
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), data)

    def test_malformed_oauth_token_response_is_recoverable(self):
        for data in ([], None, dict(access_token="test", expires_in=3600, token_type=True)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                oauth.token_record(data)

    def test_malformed_oauth_access_probe_never_accepts_an_account(self):
        for data in ([], {"data": []}, {"data": {"characterData": {"__typename": "CharacterData"}, "userData": []}}):
            tokens = {"access_token": "test"}
            with self.subTest(data=data), patch.object(wcl, "request_json", return_value=data):
                with self.assertRaises(ValueError):
                    oauth.validate_access(tokens)
                self.assertNotIn("_account_id", tokens)


class AddonAuditTests(unittest.TestCase):
    setUp = test_batch.BatchTests.setUp

    def test_missing_local_realm_does_not_break_profile_or_tooltip(self):
        self.lua.execute("GetNormalizedRealmName=function() return nil end")
        self.assertIsNone(self.mpl.GetProfile("Alice"))
        self.mpl.ShowProfile("Alice")
        self.mpl.AddTooltip(self.lua.globals().GameTooltip, "Alice")
        self.mpl.ShowDownload("Alice")
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.panel)

    def test_missing_local_realm_still_allows_explicit_cross_realm_profiles(self):
        self.lua.execute('''
            GetNormalizedRealmName=function() return nil end
            UnitFullName=function() return "Alice",nil end
        ''')
        self.mpl.ShowProfile("Alice-Гордунни")
        self.assertEqual(self.mpl.panel.realm, "Гордунни")

    def test_unsafe_unit_realm_never_becomes_a_local_character(self):
        self.lua.execute('''
            UnitFullName=function() return "Alice",{secret=true} end
            UnitClass=function() return "Warrior","WARRIOR" end
            GetInspectSpecialization=function() return 73 end
        ''')
        self.assertIsNone(self.mpl.RefreshCharacterSpec("Alice", "Гордунни"))
        self.assertIsNone(self.mpl.classes)


if __name__ == "__main__":
    unittest.main()
