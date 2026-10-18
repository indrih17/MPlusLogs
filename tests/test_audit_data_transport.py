"""Offline regressions for failed transport and regional batch correlation."""
import io
import json
from http.client import HTTPConnection, IncompleteRead
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import unquote
from test_api_efficiency import dual

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import clipboard_companion as companion
import build_database as builder
import wcl_sync as wcl


class DataTransportAuditTests(unittest.TestCase):
    def test_truncated_http_response_finishes_admission_and_stops_batch(self):
        client = companion.Client(token_provider=lambda: "test-token")
        self.addCleanup(client.budget.close)
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = IncompleteRead(b'{"data":', 100)
        with patch.object(wcl, "urlopen", return_value=response):
            with self.assertRaises(wcl.APIError) as failure:
                client.query_metadata("{characterData{character{name}}}")
        self.assertEqual(failure.exception.code, "network")
        self.assertEqual(client.request_metrics[-1]["outcome"], "error")
        self.assertGreater(client.budget.snapshot()["blockedUntil"], 0)
        statuses = client.budget.db.execute("SELECT status FROM point_reservations").fetchall()
        self.assertEqual(statuses, [("uncertain",)])

    def test_invalid_json_is_a_safe_upstream_error(self):
        response = io.BytesIO(b"<html>temporary upstream failure</html>")
        with patch.object(wcl, "urlopen", return_value=response):
            with self.assertRaises(wcl.APIError) as failure:
                wcl.request_json(wcl.ROOT, b"{}", {})
        self.assertEqual(failure.exception.code, "schema")
        self.assertNotIn("<html>", str(failure.exception))

    def test_malformed_authorization_never_appears_in_transport_error(self):
        def validate_headers(request, **kwargs):
            # Exercise http.client's real header validation without connecting.
            connection = HTTPConnection("localhost")
            connection.putrequest("POST", "/")
            connection.putheader("Authorization", request.get_header("Authorization"))
            self.fail("Malformed Authorization header was accepted")
        for token in ("sensitive-token\r\nInjected: yes", "sensitive-token\x00", "sensitive-token\u00e9"):
            with self.subTest(token=repr(token)), patch.object(wcl, "urlopen", side_effect=validate_headers):
                with self.assertRaises(wcl.APIError) as failure:
                    wcl.request_json(wcl.ROOT, b"{}", {"Authorization": "Bearer " + token})
                self.assertEqual(failure.exception.code, "auth")
                self.assertNotIn("sensitive-token", str(failure.exception))

    def test_oauth_rejects_non_object_or_non_string_token(self):
        for response in ([], None, "token", {"access_token": ["token"]}, {"access_token": 123}):
            with self.subTest(response=response), patch.object(wcl, "request_json", return_value=response):
                with self.assertRaises(wcl.APIError):
                    wcl.access_token("test-client", "test-secret")

    def test_batch_error_is_correlated_by_region(self):
        mapping = {region: {"TestRealm": "testrealm"} for region in ("eu", "us")}
        request = "MPLQ2\nQ\teu\tTestRealm\tAlice\nQ\tus\tTestRealm\tAlice\n"
        def fetch(args):
            raise wcl.NoProfile("hidden in " + args.region, "hidden")
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-data-") as directory:
            result, report = companion.process_request(request, mapping, Path(directory), fetcher=fetch)
        failures = [list(map(unquote, line.split("\t"))) for line in result.splitlines()[1:]]
        self.assertEqual([row[4] for row in failures], ["hidden in eu", "hidden in us"])
        self.assertEqual([row["region"] for row in report["errors"]], ["eu", "us"])

    def test_corrupt_retry_metadata_does_not_block_cache_recovery(self):
        entry = dict(name="Alice", realm="TestRealm", server_slug="testrealm", region="eu")
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-data-") as directory:
            cache = Path(directory)
            path = builder.cache_path(cache, entry)
            path.write_text(json.dumps(dict(fetched_at=1000, retry_until=5000, refresh_error=123)), encoding="utf-8")
            calls = []
            def fetch(args):
                calls.append(args.name)
                raise wcl.NoProfile("Character not found", "missing")
            profiles, report = builder.build([entry], cache, fetcher=fetch, now=2000)
        self.assertEqual(calls, ["Alice"])
        self.assertEqual(profiles, [])
        self.assertEqual(report["errors"][0]["error_code"], "missing")

    def test_roster_members_are_validated_before_queue_merge(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-data-") as directory:
            manifest = Path(directory) / "roster.json"
            queue = Path(directory) / "queue.txt"
            manifest.write_text("[null]", encoding="utf-8")
            queue.write_text("MPLQ1\nQ\teu\tGordunni\tAlice", encoding="utf-8")
            with self.assertRaises(ValueError):
                builder.load_entries(manifest=manifest, requests=queue)

    def test_redirected_character_never_replaces_valid_cached_profile(self):
        entry = dict(name="Alice", realm="Гордунни", server_slug="gordunni", region="eu")
        for field, value in (("name", "Renamed"), ("slug", "new-realm"), ("region", "us")):
            with self.subTest(field=field), tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-data-") as directory:
                cache = Path(directory)
                builder.build([entry], cache, fetcher=lambda _: dual("Alice"), now=1000)
                redirected = dual("Alice")
                char = redirected["data"]["characterData"]["character"]
                if field == "name": char["name"] = value
                elif field == "region": char["server"]["region"]["slug"] = value
                else:
                    char["server"]["slug"] = value
                    char["server"]["name"] = "New Realm"
                profiles, report = builder.build([entry], cache, fetcher=lambda _: redirected, now=2000, refresh=True)
                self.assertEqual(report["errors"][0]["error_code"], "missing")
                self.assertEqual(profiles[0]["name"], "Alice")
                record = builder.read_cache(builder.cache_path(cache, entry))
                self.assertEqual(record["raw"]["data"]["characterData"]["character"]["name"], "Alice")
                self.assertEqual(record["fetched_at"], 1000)

    def test_requested_identity_accepts_unicode_case_and_server_alias_ids(self):
        entry = dict(name="FRA\u0301KKIE", realm="Alias Realm", server_slug="old-alias", region="eu")
        raw = dual("Frákkie")
        raw["data"]["worldData"] = {"server": {"id": 123}}
        raw["data"]["characterData"]["character"]["server"]["id"] = 123
        builder.validate_raw(raw, builder.arguments(entry))

    def test_legacy_redirected_cache_is_refetched_before_export(self):
        entry = dict(name="Alice", realm="Гордунни", server_slug="gordunni", region="eu")
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-data-") as directory:
            cache = Path(directory)
            builder.cache_path(cache, entry).write_text(json.dumps(dict(fetched_at=1000, raw=dual("Renamed"))), encoding="utf-8")
            calls = []
            def fetch(args):
                calls.append(args.name)
                return dual(args.name)
            profiles, report = builder.build([entry], cache, fetcher=fetch, now=1001)
        self.assertEqual(calls, ["Alice"])
        self.assertEqual(profiles[0]["name"], "Alice")
        self.assertEqual(report["errors"], [])


if __name__ == "__main__":
    unittest.main()
