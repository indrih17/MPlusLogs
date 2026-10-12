"""Actual upstream-call counts, cache provenance and persistent abuse protection."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from email.message import Message

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests"), str(ROOT / ".test-deps")]
from test_addon import api_fixture
import build_database as builder
import clipboard_companion as companion
import wcl_sync as wcl
from api_budget import Budget, BudgetError


def dual(name="Киндрих"):
    raw = copy.deepcopy(api_fixture())
    char = raw["data"]["characterData"]["character"]
    char["name"] = name
    char["damage"] = char.pop("performance")
    char["healing"] = copy.deepcopy(char["damage"])
    char["healing"]["bestPerformanceAverage"] = 91
    return raw


class EfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-work-")
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.entry = {"name": "Киндрих", "realm": "Гордунни", "server_slug": "gordunni", "region": "eu"}

    def test_role_and_metric_switch_reuses_both_metrics_with_original_date(self):
        calls = []
        def fetch(args):
            calls.append(args)
            return dual()
        damage, _ = builder.build([dict(self.entry, role="DAMAGER")], self.cache, fetcher=fetch, now=100000)
        healing, report = builder.build([dict(self.entry, role="HEALER", metric="hps")], self.cache, fetcher=fetch, now=100001)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["cacheHits"], 1)
        self.assertEqual(healing[0]["best"], 91)
        self.assertEqual(healing[0]["metric"], "hps")
        self.assertEqual(damage[0]["updated"], healing[0]["updated"])

    def test_dps_only_character_does_not_need_healing_rankings_to_be_cached(self):
        raw = dual()
        raw["data"]["characterData"]["character"]["healing"] = {"rankings": []}
        profiles, _ = builder.build([dict(self.entry, role="DAMAGER")], self.cache, fetcher=lambda _: raw, now=100000)
        self.assertEqual(len(profiles), 1)
        cached, report = builder.build([self.entry], self.cache, fetcher=lambda _: self.fail("must use cache"), now=100001)
        self.assertEqual(len(cached), 1)
        self.assertEqual(report["fetched"], 0)

    def test_spec_season_query_scope_and_realm_slug_are_not_shared(self):
        default = builder.cache_path(self.cache, self.entry)
        for change in ({"spec": "Guardian"}, {"_cache_scope": "user:one"}, {"server_slug": "silvermoon"}, {"region": "us"}):
            self.assertNotEqual(default, builder.cache_path(self.cache, dict(self.entry, **change)))
        self.assertEqual(default, builder.cache_path(self.cache, dict(self.entry, realm="Other localized spelling", name="КИНДРИХ")))

    def test_empty_logs_cached_for_six_hours_then_fetched_once(self):
        calls = []
        def fetch(_):
            calls.append(1)
            raw = dual()
            for metric in ("damage", "healing"):
                raw["data"]["characterData"]["character"][metric]["rankings"] = []
            return raw
        for stamp in (100000, 100001, 121599):
            profiles, report = builder.build([self.entry], self.cache, fetcher=fetch, now=stamp)
            self.assertFalse(profiles)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["negativeCacheHits"], 1)
        builder.build([self.entry], self.cache, fetcher=fetch, now=121600)
        self.assertEqual(len(calls), 2)

    def test_corrupt_response_and_network_failure_are_not_negative_cache(self):
        def malformed(_):
            return {"data": {}}
        builder.build([self.entry], self.cache, fetcher=malformed, now=100000)
        record = builder.read_cache(builder.cache_path(self.cache, self.entry))
        self.assertNotIn("negative", record)
        _, report = builder.build([self.entry], self.cache, fetcher=lambda _: dual(), now=100301)
        self.assertEqual(report["fetched"], 1)

    def test_429_stops_batch_after_one_attempt_and_keeps_good_stale_profile(self):
        builder.build([self.entry], self.cache, fetcher=lambda _: dual(), now=100000)
        calls = []
        def fail(_):
            calls.append(1)
            raise wcl.APIError("WCL HTTP 429; rate limit", 429, 900)
        entries = [self.entry] + [dict(self.entry, name="Other" + str(i)) for i in range(9)]
        profiles, report = builder.build(entries, self.cache, fetcher=fail, now=200000)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["fetched"], 1)
        self.assertEqual(len(profiles), 1)
        self.assertIn("cached", profiles[0]["source"])
        self.assertEqual(profiles[0]["updated"], "1970-01-02 03:46 UTC")

    def test_budget_survives_restart_counts_failures_and_uses_rolling_hour(self):
        stamp = [100000]
        path = self.cache / "api-state.sqlite3"
        budget = Budget(path, hourly=2, clock=lambda: stamp[0])
        budget.reserve("first")
        stamp[0] += 10
        budget.reserve("second")
        budget.close()
        budget = Budget(path, hourly=2, clock=lambda: stamp[0])
        try:
            with self.assertRaises(BudgetError): budget.reserve("third")
            stamp[0] = 103600
            budget.reserve("third")
            with self.assertRaises(BudgetError): budget.reserve("fourth")
        finally:
            budget.close()

    def test_retry_after_and_empty_response_budget_persist_across_clients(self):
        stamp = [100000]
        path = self.cache / "api-state.sqlite3"
        budget = Budget(path, clock=lambda: stamp[0])
        budget.observe({"limitPerHour": 720, "pointsSpentThisHour": 680, "pointsResetIn": 500})
        budget.close()
        budget = Budget(path, clock=lambda: stamp[0])
        try:
            with self.assertRaises(BudgetError): budget.reserve("new")
            stamp[0] += 501
            budget.reserve("new")
            budget.failure(wcl.APIError("WCL HTTP 429; rate limit", 429, 900))
            stamp[0] += 899
            with self.assertRaises(BudgetError): budget.reserve("other")
            stamp[0] += 1
            budget.reserve("other")
        finally:
            budget.close()

    def test_hour_minimum_applies_even_when_ttl_zero(self):
        calls = []
        def fetch(_):
            calls.append(1)
            return dual()
        for stamp in (100000, 100001, 103599, 103600):
            builder.build([self.entry], self.cache, ttl_hours=0, fetcher=fetch, now=stamp)
        self.assertEqual(len(calls), 2)

    def test_http_429_preserves_retry_header_without_leaking_body(self):
        headers = Message()
        headers["Retry-After"] = "120"
        error = HTTPError("https://www.warcraftlogs.com/api/v2/client", 429, "private body", headers, None)
        with patch.object(wcl, "urlopen", side_effect=error):
            with self.assertRaises(wcl.APIError) as raised:
                wcl.request_json("https://example.com", b"{}", {})
        self.assertEqual(raised.exception.retry_after, 120)
        self.assertNotIn("private body", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
