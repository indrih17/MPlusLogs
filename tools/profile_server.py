"""Bounded public WCL cache with verified accounts, fair queue and persistent budgets."""
from collections import OrderedDict, deque
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from api_budget import Budget, BudgetError
import build_database as builder
from clipboard_companion import Client as WCLClient
from profile_service import service_url
import realm_resolver
import wcl_sync as wcl

SPECS = set("Affliction Arcane Arms Assassination Augmentation Balance BeastMastery Blood Brewmaster Demonology Destruction Devastation Discipline Elemental Enhancement Feral Fire Frost Fury Guardian Havoc Holy Marksmanship Mistweaver Outlaw Preservation Protection Restoration Retribution Shadow Subtlety Survival Unholy Vengeance Windwalker".split())


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ServiceError(ValueError):
    def __init__(self, status, message, retry_after=0):
        self.status, self.retry_after = status, retry_after
        super().__init__(message)


class Store:
    def __init__(self, path, clock=time.time):
        self.clock, self.lock = clock, threading.RLock()
        self.deliveries = {}  # One-time bearer delivery stays in RAM, never in SQLite pages.
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY,user TEXT,expires REAL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS tickets (state TEXT PRIMARY KEY,poll TEXT UNIQUE,expires REAL,consumed INTEGER,session TEXT)")
            self.db.execute("CREATE TABLE IF NOT EXISTS usage (subject TEXT,at REAL)")
            self.db.execute("CREATE INDEX IF NOT EXISTS usage_subject ON usage(subject,at)")

    def limit(self, subject, count, seconds, charge=True):
        now = self.clock()
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("DELETE FROM usage WHERE at<=?", (now - 86400,))
            self.db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            self.db.execute("DELETE FROM tickets WHERE expires<=?", (now,))
            for state in list(self.deliveries):
                if not self.db.execute("SELECT 1 FROM tickets WHERE state=?", (state,)).fetchone():
                    del self.deliveries[state]
            total, oldest = self.db.execute("SELECT COUNT(*),MIN(at) FROM usage WHERE subject=? AND at>?", (subject, now - seconds)).fetchone()
            if total >= count:
                raise ServiceError(429, "Profile server request limit reached", max(1, int(oldest + seconds - now) + 1))
            if charge:
                self.db.execute("INSERT INTO usage VALUES (?,?)", (subject, now))

    def charge_profile(self, user, hourly, daily):
        with self.lock:
            self.limit("fetch:" + user, hourly, 3600, False)
            self.limit("fetch:" + user, daily, 86400)

    def issue_session(self, user):
        token, expiry = secrets.token_urlsafe(48), self.clock() + 30 * 86400
        with self.lock, self.db:
            # Re-login cannot reset usage. Keep a bounded number of sessions per account.
            rows = self.db.execute("SELECT token FROM sessions WHERE user=? ORDER BY expires DESC", (user,)).fetchall()
            for row in rows[4:]:
                self.db.execute("DELETE FROM sessions WHERE token=?", row)
            self.db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), user, expiry))
        return {"access_token": token, "expires_at": expiry}

    def user(self, token):
        if not isinstance(token, str) or len(token) > 256:
            raise ServiceError(401, "Profile server sign-in required")
        with self.lock:
            row = self.db.execute("SELECT user FROM sessions WHERE token=? AND expires>?", (digest(token), self.clock())).fetchone()
        if not row:
            raise ServiceError(401, "Profile server session expired")
        return row[0]

    def revoke(self, token):
        with self.lock, self.db:
            self.db.execute("DELETE FROM sessions WHERE token=?", (digest(token),))

    def start(self):
        state, poll = secrets.token_hex(32), secrets.token_urlsafe(48)
        with self.lock, self.db:
            if self.db.execute("SELECT COUNT(*) FROM tickets WHERE expires>?", (self.clock(),)).fetchone()[0] >= 2048:
                raise ServiceError(429, "Too many pending sign-ins", 60)
            self.db.execute("INSERT INTO tickets VALUES (?,?,?,0,NULL)", (digest(state), digest(poll), self.clock() + 300))
        return {"state": state, "poll_token": poll}

    def ticket(self, state, consume=False):
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT consumed FROM tickets WHERE state=? AND expires>?", (digest(state), self.clock())).fetchone()
            if not row or row[0]:
                raise ServiceError(400, "Invalid or expired authorization state")
            if consume:
                self.db.execute("UPDATE tickets SET consumed=1 WHERE state=?", (digest(state),))

    def finish(self, state, session):
        with self.lock, self.db:
            if session:
                self.deliveries[digest(state)] = session
            self.db.execute("UPDATE tickets SET session=? WHERE state=?", ("ready" if session else "failed", digest(state)))

    def poll(self, poll):
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT state,session FROM tickets WHERE poll=? AND expires>?", (digest(poll), self.clock())).fetchone()
            if not row:
                raise ServiceError(400, "Invalid or expired authorization ticket")
            if row[1] is None:
                return {"status": "pending"}
            self.db.execute("DELETE FROM tickets WHERE state=?", (row[0],))
            session = self.deliveries.pop(row[0], None)
            return {"status": "ready", "session": session} if session else {"status": "failed"}


class Service:
    def __init__(self, directory, public_url, client_id="", secret="", hourly=60, daily=300,
                 global_hourly=500, fetcher=None, clock=time.time, start_worker=True):
        self.directory, self.clock = Path(directory), clock
        self.directory.mkdir(parents=True, exist_ok=True)
        self.public_url = service_url(public_url)
        self.client_id, self.secret = client_id, secret
        self.store = Store(self.directory / "service.sqlite3", clock)
        self.client = WCLClient(global_hourly, client_id, secret, state_path=self.directory / "api-state.sqlite3")
        self.client.budget.clock = clock
        self.fetcher = fetcher or self.client
        self.hourly, self.daily = hourly, daily
        self.mapping = realm_resolver.load_mappings()
        self.cache = self.directory / "cache"
        self.cv = threading.Condition(threading.RLock())
        self.queues, self.jobs, self.inflight = OrderedDict(), {}, {}
        self.stopped = False
        self.last_prune = clock()
        self.worker = threading.Thread(target=self.run, daemon=True)
        if start_worker:
            self.worker.start()

    def entry(self, body):
        if not isinstance(body, dict) or set(body) - {"name", "realm", "region", "spec"}:
            raise ServiceError(400, "Only character profile requests are supported")
        name, realm, region = (body.get(key) for key in ("name", "realm", "region"))
        if (not isinstance(name, str) or not 1 <= len(name) <= 24 or not name.isalpha()
                or not isinstance(realm, str) or not 1 <= len(realm) <= 100
                or region not in {"eu", "us", "kr", "tw", "cn"}):
            raise ServiceError(400, "Invalid character identity")
        spec = body.get("spec")
        if spec is not None and spec not in SPECS:
            raise ServiceError(400, "Unsupported specialization")
        try:
            slug = realm_resolver.resolve(self.mapping, region, realm)
        except ValueError:
            raise ServiceError(400, "Unknown or ambiguous realm") from None
        return {"name": name, "realm": realm, "region": region, "spec": spec, "server_slug": slug}

    def cached(self, entry, allow_stale=False):
        record = builder.read_cache(builder.cache_path(self.cache, entry))
        if not record:
            return None
        age = self.clock() - record["fetched_at"]
        if age < 0:
            return None
        if record.get("negative") and age < 6 * 3600:
            return {"status": "ready", "negative": True, "fetched_at": record["fetched_at"], "error": record["error"]}
        if "raw" in record and (age < 24 * 3600 or allow_stale and age < 7 * 86400):
            raw = json.loads(json.dumps(record["raw"]))
            raw.get("data", {}).pop("rateLimitData", None)
            result = {"status": "ready", "raw": raw, "fetched_at": record["fetched_at"]}
            if age >= 24 * 3600 or record.get("refresh_error"):
                result["error"] = "WCL API: cached; refresh unavailable"
            return result
        return None

    def submit(self, user, body):
        entry = self.entry(body)
        key = builder.cache_path(self.cache, entry).stem
        with self.cv:
            self.cleanup()
            cached = self.cached(entry)
            if cached:
                self.client.budget.count("negative_cache_hits" if cached.get("negative") else "cache_hits")
                return cached
            paused = self.client.budget.snapshot()["blockedUntil"] - self.clock()
            if paused > 0:
                return self.cached(entry, allow_stale=True) or {"status": "failed", "retry_after": max(1, int(paused))}
            # A single job is shared across all accounts that request the same public key.
            existing = self.inflight.get(key)
            if existing:
                existing["users"].add(user)
                self.client.budget.count("coalesced_requests")
                return {"status": "queued", "job": existing["id"]}
            self.store.limit("fetch:" + user, self.hourly, 3600, False)
            self.store.limit("fetch:" + user, self.daily, 86400, False)
            active = sum(1 for job in self.inflight.values() if job["owner"] == user)
            if len(self.inflight) >= 128 or active >= 8 or len(self.jobs) >= 2048:
                raise ServiceError(429, "Profile queue is full; retry later", 60)
            job_id = secrets.token_hex(32)
            job = {"id": job_id, "key": key, "entry": entry, "owner": user, "users": {user},
                   "created": self.clock(), "result": None, "done": None}
            self.jobs[job_id] = self.inflight[key] = job
            self.queues.setdefault(user, deque()).append(job)
            self.cv.notify()
            return {"status": "queued", "job": job_id}

    def cleanup(self):
        for key, job in list(self.jobs.items()):
            if job["done"] is not None and self.clock() - job["done"] >= 300:
                del self.jobs[key]

    def result(self, user, job_id):
        with self.cv:
            self.cleanup()
            job = self.jobs.get(job_id)
            if not job or user not in job["users"]:
                raise ServiceError(404, "Profile job not found")
            return job["result"] or {"status": "queued", "job": job_id}

    def run_once(self):
        with self.cv:
            if not self.queues:
                return False
            user, queue = self.queues.popitem(last=False)
            job = queue.popleft()
            if queue:
                self.queues[user] = queue  # Round robin between accounts, including large batches.
        try:
            if self.clock() - job["created"] > 180:
                raise ServiceError(429, "Profile queue wait expired", 60)
            def charged_fetch(args):
                if self.fetcher is self.client:
                    self.client.before_fetch = lambda: self.store.charge_profile(user, self.hourly, self.daily)
                else:
                    self.store.charge_profile(user, self.hourly, self.daily)
                return self.fetcher(args)
            builder.build([job["entry"]], self.cache, fetcher=charged_fetch, now=self.clock())
            result = self.cached(job["entry"], allow_stale=True)
            if result is None:
                result = {"status": "failed", "retry_after": 60}
        except (ServiceError, ValueError, OSError, TypeError, KeyError):
            result = self.cached(job["entry"], allow_stale=True) or {"status": "failed", "retry_after": 60}
        with self.cv:
            job["result"], job["done"] = result, self.clock()
            self.inflight.pop(job["key"], None)
        return True

    def run(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.queues or self.stopped, timeout=60)
                if self.stopped:
                    return
            self.run_once()
            if self.clock() - self.last_prune >= 3600:
                self.last_prune = self.clock()
                for path in self.cache.glob("*.json"):
                    record = builder.read_cache(path)
                    retention = 6 * 3600 if record and record.get("negative") else 7 * 86400
                    if not record or self.clock() - record["fetched_at"] >= retention:
                        try:
                            path.unlink()
                        except OSError:
                            pass

    def authorize(self, state):
        self.store.ticket(state)
        return wcl.ROOT + "/oauth/authorize?" + urlencode({"client_id": self.client_id,
            "redirect_uri": self.public_url + "/auth/callback", "response_type": "code",
            "scope": "view-user-profile", "state": state})

    def callback(self, state, code):
        self.store.ticket(state, consume=True)
        try:
            delay = self.client.budget.reserve("login:" + digest(state), pace=True)
            if delay:
                time.sleep(delay)
            basic = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
            token = wcl.request_json(wcl.ROOT + "/oauth/token", urlencode({"grant_type": "authorization_code",
                "code": code, "redirect_uri": self.public_url + "/auth/callback"}).encode(),
                {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
            raw = wcl.request_json(wcl.ROOT + "/api/v2/user", json.dumps({"query":
                "{ rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn } userData { currentUser { id } } }"}).encode(),
                {"Authorization": "Bearer " + token["access_token"], "Content-Type": "application/json"})
            self.client.budget.observe(raw.get("data", {}).get("rateLimitData"))
            user_id = raw.get("data", {}).get("userData", {}).get("currentUser", {}).get("id")
            if raw.get("errors") or not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
                raise ValueError("Warcraft Logs account identity unavailable")
            session = self.store.issue_session(str(user_id))
            self.store.finish(state, session)
            return True
        except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            self.client.budget.failure(exc)
            self.store.finish(state, None)
            return False

    def close(self):
        with self.cv:
            self.stopped = True
            self.cv.notify_all()
        if self.worker.is_alive():
            self.worker.join(timeout=50)
        self.store.db.close()
        self.client.budget.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # OAuth codes, bearer tokens, request paths and bodies must never be logged.

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def send(self, status, payload, retry=0):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        if retry:
            self.send_header("Retry-After", str(max(1, int(retry))))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ServiceError(400, "Invalid request size") from None
        if not 1 <= size <= 8192 or self.headers.get("Transfer-Encoding"):
            raise ServiceError(413, "Request body too large or missing")
        try:
            result = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            raise ServiceError(400, "Invalid JSON request") from None
        if not isinstance(result, dict):
            raise ServiceError(400, "Expected a JSON object")
        return result

    def token(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 300:
            raise ServiceError(401, "Profile server sign-in required")
        return auth[7:]

    def dispatch(self):
        service = self.server.service
        # Ignore user-supplied forwarding headers. Production proxy overwrites X-Real-IP.
        peer = self.client_address[0]
        if self.server.trust_proxy:
            peer = self.headers.get("X-Real-IP", peer)
            if len(peer) > 64:
                raise ServiceError(400, "Invalid proxy address")
        service.store.limit("ip:" + digest(peer), 600, 60)
        path = urlsplit(self.path).path
        if self.command == "GET":
            if path == "/healthz":
                return self.send(200, {"ok": True})
            if path == "/metrics":
                if not self.server.admin_token or not secrets.compare_digest(self.token(), self.server.admin_token):
                    raise ServiceError(403, "Admin authentication required")
                return self.send(200, service.client.budget.snapshot())
            query = parse_qs(urlsplit(self.path).query)
            state = query.get("state", [""])[0]
            if len(state) != 64 or any(c not in "0123456789abcdef" for c in state):
                raise ServiceError(400, "Invalid authorization state")
            if path == "/auth/authorize":
                self.send_response(302)
                self.send_header("Location", service.authorize(state))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/auth/callback":
                code = query.get("code", [""])[0]
                if not code or len(code) > 4096:
                    service.store.ticket(state, consume=True)
                    service.store.finish(state, None)
                    return self.send(400, {"message": "Warcraft Logs sign-in cancelled. Return to Companion."})
                success = service.callback(state, code)
                return self.send(200 if success else 400, {"message": "Return to MPlusLogs Companion. You may close this tab."})
            raise ServiceError(404, "Endpoint not found")
        if self.command != "POST":
            raise ServiceError(405, "Method not supported")
        body = self.body()
        if path == "/v1/auth/start":
            service.store.limit("auth:" + digest(peer), 10, 3600)
            service.store.limit("auth:global", 240, 3600)
            return self.send(200, service.store.start())
        if path == "/v1/auth/poll":
            poll = body.get("poll_token")
            if not isinstance(poll, str) or len(poll) > 100:
                raise ServiceError(400, "Invalid authorization ticket")
            return self.send(200, service.store.poll(poll))
        token = self.token()
        user = service.store.user(token)
        service.store.limit("read:" + user, 300, 60)
        if path == "/v1/profile":
            result = service.submit(user, body)
            return self.send(202 if result["status"] == "queued" else 200, result)
        if path == "/v1/job":
            job = body.get("job")
            if not isinstance(job, str) or len(job) != 64:
                raise ServiceError(400, "Invalid profile job")
            result = service.result(user, job)
            return self.send(202 if result["status"] == "queued" else 200, result)
        if path == "/v1/auth/logout":
            service.store.revoke(token)
            return self.send(200, {"ok": True})
        raise ServiceError(404, "Endpoint not found")

    def handle_request(self):
        try:
            self.dispatch()
        except (ServiceError, BudgetError) as exc:
            self.send(getattr(exc, "status", 429), {"error": str(exc)}, getattr(exc, "retry_after", 0))
        except (ValueError, OSError, TypeError, KeyError, AttributeError):
            self.send(400, {"error": "Invalid request or temporarily unavailable service"})

    do_GET = do_POST = handle_request


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address, service, admin_token="", trust_proxy=False):
        self.service, self.admin_token, self.trust_proxy = service, admin_token, trust_proxy
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def main():
    # One worker/process owns the fair queue. Refuse a second service on the same volume.
    import fcntl
    directory = Path(os.environ.get("MPLUSLOGS_DATA", "/data"))
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "service.lock").open("w") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        client_id, secret = os.environ.get("WCL_CLIENT_ID"), os.environ.get("WCL_CLIENT_SECRET")
        if not client_id or not secret:
            raise SystemExit("Configure WCL_CLIENT_ID and WCL_CLIENT_SECRET on the server")
        service = Service(directory, os.environ["MPLUSLOGS_PUBLIC_URL"], client_id, secret,
            hourly=int(os.environ.get("MPLUSLOGS_USER_HOURLY", "60")), daily=int(os.environ.get("MPLUSLOGS_USER_DAILY", "300")),
            global_hourly=int(os.environ.get("MPLUSLOGS_GLOBAL_HOURLY", "500")))
        try:
            with Server(("0.0.0.0", 8080), service, os.environ.get("MPLUSLOGS_ADMIN_TOKEN", ""),
                        os.environ.get("MPLUSLOGS_TRUST_PROXY") == "1") as server:
                server.serve_forever()
        finally:
            service.close()


if __name__ == "__main__":
    main()
