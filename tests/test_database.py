"""Batch database, cache, queue and generated Lua checks without network."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / ".test-deps"))
import build_database as builder
import inspect_archon
from test_addon import api_fixture, MOCK, load_locales
from lupa.lua51 import LuaRuntime


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".test-work-",dir=ROOT)
        self.directory = Path(self.temp.name)
        # Verify that recursive TemporaryDirectory cleanup stays in this workspace.
        self.assertTrue(self.directory.resolve().is_relative_to(ROOT.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.entry = {"character_id": 81818678, "realm": "Гордунни", "spec": "Guardian"}
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.mpl = self.lua.table()
        load_locales(self.lua,self.mpl)
        self.lua.execute("return assert(loadstring(...))", (ROOT / "Data.lua").read_text(encoding="utf-8"))("MPlusLogs",self.mpl)
        self.lua.execute("MPlusLogsDB = {profiles={}}")

    def build(self, entries=None, **kwargs):
        return builder.build(entries or [self.entry], self.directory, **kwargs)

    def test_fresh_cache_avoids_network_and_preserves_date(self):
        profiles, report = self.build(fetcher=lambda _: api_fixture(), now=100000)
        self.assertEqual(report["fetched"], 1)
        def forbidden(_):
            raise AssertionError("Fresh cache must not use network")
        cached, report = self.build(fetcher=forbidden, now=100001)
        self.assertEqual(report["fetched"], 0)
        self.assertEqual(cached[0]["updated"], profiles[0]["updated"])

    def test_expired_cache_survives_api_failure(self):
        self.build(fetcher=lambda _: api_fixture(), now=100000)
        def fail(_):
            raise ValueError("HTTP 429")
        profiles, report = self.build(fetcher=fail, now=200000)
        self.assertEqual(len(profiles), 1)
        self.assertIn("cached", profiles[0]["source"])
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(report["fetched"], 1)

    def test_failed_queries_count_towards_limit(self):
        def fail(_):
            raise ValueError("API unavailable")
        entries = [dict(self.entry,character_id=i) for i in range(10)]
        profiles, report = self.build(entries, fetcher=fail, now=100000, max_fetch=2)
        self.assertFalse(profiles)
        self.assertEqual(report["fetched"], 2)

    def test_bundle_loads_other_player_and_safe_quoting(self):
        raw = api_fixture()
        raw["data"]["characterData"]["character"]["name"] = "Друг"
        profiles, _ = self.build(fetcher=lambda _: raw, now=2000000000)
        profiles[0]["source"] = 'Literal "quotes" \\ and ]] text'
        code = builder.bundle(profiles)
        self.lua.execute("return assert(loadstring(...))",code)("MPlusLogs",self.mpl)
        self.mpl.LoadBundle()
        p, _, _ = self.mpl.GetProfile("Друг-Гордунни")
        self.assertEqual(p.name, "Друг")
        self.assertEqual(p.source, profiles[0]["source"])
        self.assertEqual(p.best, 62)

    def test_newer_bundle_wins_over_old_manual_import(self):
        profiles, _ = self.build(fetcher=lambda _: api_fixture(), now=2000000000)
        older = dict(profiles[0], updated="2020-01-01 00:00 UTC", best=1)
        import wcl_sync
        self.mpl.Import(wcl_sync.export(older))
        self.lua.execute("return assert(loadstring(...))",builder.bundle(profiles))("MPlusLogs",self.mpl)
        self.mpl.LoadBundle()
        self.assertEqual(self.mpl.GetProfile("Киндрих-Гордунни")[0].best,62)

    def test_queue_cyrillic_and_realm_resolution(self):
        self.mpl.Remember("Друг","Гордунни")
        self.mpl.Remember("Друг","Гордунни")
        text, count = self.mpl.ExportRequests()
        self.assertEqual(count,1)
        queue = self.directory / "requests.mplq"
        queue.write_text(text,encoding="utf-8")
        entries = builder.load_entries(requests=queue,realms=ROOT / "realm-slugs.json")
        self.assertEqual(entries[0]["name"], "Друг")
        self.assertEqual(entries[0]["server_slug"],"gordunni")
        queue.write_text(text.replace("%D0%93%D0%BE%D1%80%D0%B4%D1%83%D0%BD%D0%BD%D0%B8","UnknownRealm"),encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.load_entries(requests=queue)

    def test_multiple_specs_allowed_but_exact_duplicate_rejected(self):
        import json
        path = self.directory / "roster.json"
        path.write_text(json.dumps([self.entry,dict(self.entry,spec="Feral")]),encoding="utf-8")
        self.assertEqual(len(builder.load_entries(manifest=path)),2)
        path.write_text(json.dumps([self.entry,self.entry]),encoding="utf-8")
        with self.assertRaises(ValueError):
            builder.load_entries(manifest=path)

    def test_archon_decoder_matches_installed_record(self):
        import json
        report_path = ROOT / "archon-inspection.json"
        if not report_path.exists():
            self.skipTest("Optional integration check requires a local Archon inspection report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        import re
        path = Path(report["source"]) / report["character"][0]["file"]
        if not path.exists():
            self.skipTest("Optional integration check requires the installed Archon database")
        text = path.read_text(encoding="utf-8-sig")
        encoded = re.search(r"Киндрих:([A-Za-z0-9+/]+={0,2})[.]",text).group(1)
        lookup = re.findall(r"'([^']*)'",re.search(r"local lookup = \{([^\n]+)\}",text).group(1))
        self.assertEqual(inspect_archon.decode(encoded,lookup),report["character"][0]["decoded"])
        self.assertEqual(report["zonesByProviderMetadata"],{"53":534})


if __name__ == "__main__":
    unittest.main()
