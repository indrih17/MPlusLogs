"""Shared cache, fair admission, OAuth state and Companion/server HTTP integration."""
import copy
import gc
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests"), str(ROOT / ".test-deps")]
from test_api_efficiency import dual
import build_database as builder
import profile_service as client
import profile_server as server
import wcl_sync as wcl
import export_release_source


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-work-")
        self.addCleanup(self.temp.cleanup)
        self.clock = [100000]
        self.calls = []
        def fetch(args):
            self.calls.append(args.name)
            return dual(args.name)
        self.service = server.Service(Path(self.temp.name), "http://localhost:8080", fetcher=fetch,
                                      clock=lambda: self.clock[0], start_worker=False)
        self.addCleanup(self.service.close)
        self.entry = {"name": "Киндрих", "realm": "Гордунни", "region": "eu", "spec": None}

    def test_ten_accounts_share_one_inflight_fetch_then_cache(self):
        jobs = [self.service.submit(str(i), self.entry) for i in range(10)]
        self.assertEqual(len({item["job"] for item in jobs}), 1)
        self.service.run_once()
        for i in range(10):
            self.assertEqual(self.service.result(str(i), jobs[i]["job"])["status"], "ready")
        self.assertEqual(self.calls, ["Киндрих"])
        self.assertEqual(self.service.submit("new-account", self.entry)["status"], "ready")
        self.assertEqual(self.service.store.db.execute("SELECT COUNT(*) FROM usage WHERE subject LIKE 'fetch:%'").fetchone()[0], 1)

    def test_round_robin_prevents_one_account_batch_from_monopolizing_worker(self):
        for name in ("Alice", "Bobby", "Carol"):
            self.service.submit("bulk", dict(self.entry, name=name))
        self.service.submit("other", dict(self.entry, name="David"))
        for _ in range(4): self.service.run_once()
        self.assertEqual(self.calls, ["Alice", "David", "Bobby", "Carol"])

    def test_account_quota_survives_new_session_and_service_restart(self):
        self.service.hourly = 1
        job = self.service.submit("42", self.entry)
        self.service.run_once()
        token = self.service.store.issue_session("42")["access_token"]
        self.assertEqual(self.service.store.user(token), "42")
        with self.assertRaises(server.ServiceError):
            self.service.submit("42", dict(self.entry, name="Another"))
        restarted = server.Store(Path(self.temp.name) / "service.sqlite3", clock=lambda: self.clock[0])
        try:
            self.assertEqual(restarted.user(token), "42")
            with self.assertRaises(server.ServiceError): restarted.charge_profile("42", 1, 300)
            restarted.revoke(token)
            with self.assertRaises(server.ServiceError): restarted.user(token)
        finally:
            restarted.db.close()
        # Cached reads remain available after exhausting new-profile quota.
        self.assertEqual(self.service.submit("42", self.entry)["status"], "ready")

    def test_negative_cache_shared_but_temporary_error_is_not_missing_logs(self):
        def empty(_):
            return {"data": {"characterData": {"character": None}}}
        self.service.fetcher = empty
        job = self.service.submit("one", self.entry)
        self.service.run_once()
        self.assertTrue(self.service.result("one", job["job"])["negative"])
        self.assertTrue(self.service.submit("two", self.entry)["negative"])
        self.service.fetcher = lambda _: (_ for _ in ()).throw(wcl.APIError("WCL HTTP 500; retry", 500))
        other = self.service.submit("two", dict(self.entry, name="Another"))
        self.service.run_once()
        self.assertEqual(self.service.result("two", other["job"])["status"], "failed")
        record = builder.read_cache(builder.cache_path(self.service.cache, self.service.entry(dict(self.entry, name="Another"))))
        self.assertFalse(record.get("negative"))

    def test_queue_is_bounded_job_not_readable_by_unrelated_account_and_expires(self):
        job = self.service.submit("one", self.entry)
        with self.assertRaises(server.ServiceError): self.service.result("two", job["job"])
        for name in ("Alice", "Bobby", "Carol", "David", "Emily", "Frank", "Grace"):
            self.service.submit("one", dict(self.entry, name=name))
        with self.assertRaises(server.ServiceError): self.service.submit("one", dict(self.entry, name="Henry"))
        self.clock[0] += 181
        self.service.run_once()
        self.assertFalse(self.calls)
        self.assertEqual(self.service.result("one", job["job"])["status"], "failed")

    def test_raw_query_private_filter_and_unbounded_spec_are_rejected(self):
        for body in (dict(self.entry, query="{reportData{}}"), dict(self.entry, includePrivate=True),
                     dict(self.entry, spec="invented"), dict(self.entry, region="invalid")):
            with self.assertRaises(server.ServiceError): self.service.submit("one", body)
        self.assertFalse(self.calls)

    def test_oauth_state_is_single_use_and_identity_is_from_wcl_not_client(self):
        ticket = self.service.store.start()
        self.assertIn("view-user-profile", self.service.authorize(ticket["state"]))
        raw = {"data": {"userData": {"currentUser": {"id": 42}}}}
        with patch.object(wcl, "request_json", side_effect=[{"access_token": "private-wcl-token"}, raw]) as fetch:
            self.assertTrue(self.service.callback(ticket["state"], "one-use-code"))
        session = self.service.store.poll(ticket["poll_token"])["session"]
        self.assertEqual(self.service.store.user(session["access_token"]), "42")
        self.assertNotIn("private-wcl-token", json.dumps(session))
        self.assertIn("currentUser", fetch.call_args_list[1].args[1].decode())
        with self.assertRaises(server.ServiceError): self.service.callback(ticket["state"], "replay")
        with self.assertRaises(server.ServiceError): self.service.store.poll(ticket["poll_token"])
        self.assertNotIn("private-wcl-token", (Path(self.temp.name) / "service.sqlite3").read_bytes().decode("latin1"))
        self.assertNotIn(session["access_token"], (Path(self.temp.name) / "service.sqlite3").read_bytes().decode("latin1"))

    def test_unknown_identity_does_not_create_a_session(self):
        ticket = self.service.store.start()
        with patch.object(wcl, "request_json", side_effect=[{"access_token": "private"}, {"data": {"userData": {"currentUser": None}}}]):
            self.assertFalse(self.service.callback(ticket["state"], "code"))
        self.assertEqual(self.service.store.poll(ticket["poll_token"])["status"], "failed")

    def test_public_reply_strips_global_rate_data_and_preserves_fetched_time(self):
        raw = dual()
        raw["data"]["rateLimitData"] = {"limitPerHour": 720, "pointsSpentThisHour": 9, "pointsResetIn": 100}
        self.service.fetcher = lambda _: copy.deepcopy(raw)
        job = self.service.submit("one", self.entry)
        self.service.run_once()
        result = self.service.result("one", job["job"])
        self.assertEqual(result["fetched_at"], 100000)
        self.assertNotIn("rateLimitData", result["raw"]["data"])

    def test_source_export_includes_docker_only_allowlisted_files(self):
        names = {entry["path"] for entry in export_release_source.entries()}
        self.assertIn("server/compose.yaml", names)
        self.assertIn("server/README.md", names)
        self.assertNotIn("server/.env", names)
        self.assertFalse(any(name.endswith(".sqlite3") for name in names))


class HTTPTests(unittest.TestCase):
    def test_companion_roundtrip_never_contacts_direct_wcl_and_keeps_provenance(self):
        gc.collect()  # Dispose prior Tk test windows on the main thread before HTTP workers.
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-work-") as temp:
            service = server.Service(Path(temp), "http://localhost:8080", fetcher=lambda args: dual(args.name))
            http = server.Server(("127.0.0.1", 0), service)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                base = "http://127.0.0.1:" + str(http.server_address[1])
                tokens = service.store.issue_session("42")
                tokens["_service_url"] = base
                remote = client.Client(client.Session(tokens))
                args = SimpleNamespace(name="Киндрих", realm="Гордунни", region="eu", spec=None)
                with patch.object(wcl, "fetch", side_effect=AssertionError("Must not fall back to direct WCL")):
                    raw = remote(args)
                self.assertIn("_mplus_cache", raw)
                entry = {"name": "Киндрих", "realm": "Гордунни", "region": "eu", "server_slug": "gordunni", "_cache_scope": remote.cache_scope}
                profiles, _ = builder.build([entry], Path(temp) / "client-cache", fetcher=remote)
                self.assertEqual(profiles[0]["name"], "Киндрих")
                self.assertEqual(service.client.budget.snapshot()["counters"]["cache_hits"], 1)
                with self.assertRaises(wcl.APIError) as denied:
                    client.request(base, "/v1/profile", {"name": "Киндрих", "realm": "Гордунни", "region": "eu"}, "forged-token")
                self.assertEqual(denied.exception.status, 401)
                client.request(base, "/v1/auth/logout", {}, tokens["access_token"])
                with self.assertRaises(wcl.APIError): client.request(base, "/v1/job", {"job": "0" * 64}, tokens["access_token"])
            finally:
                http.shutdown()
                http.server_close()
                worker.join(timeout=5)
                service.close()

    def test_client_disallows_non_https_and_credentials_in_service_urls(self):
        for url in ("http://example.com", "https://user:secret@example.com", "https://example.com/path", "https://example.com?token=x"):
            with self.assertRaises(ValueError): client.service_url(url)
        self.assertEqual(client.service_url("https://example.com/"), "https://example.com")


if __name__ == "__main__":
    unittest.main()
