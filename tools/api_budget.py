"""Persistent rolling request budget and upstream cooldown; contains no credentials."""
import math
from pathlib import Path
import sqlite3
import threading
import time

import wcl_sync as wcl


class BudgetError(ValueError):
    def __init__(self, message, retry_after, global_stop=True):
        self.global_stop = global_stop
        self.retry_after = max(1, math.ceil(retry_after))
        super().__init__(message + f"; retry after {self.retry_after} seconds")


class Budget:
    def __init__(self, path=None, hourly=120, clock=time.time):
        if path is not None:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path) if path is not None else ":memory:", timeout=10, check_same_thread=False)
        self.lock = threading.RLock()
        self.hourly, self.clock = hourly, clock
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS attempts (at REAL NOT NULL, key TEXT NOT NULL)")
            self.db.execute("CREATE INDEX IF NOT EXISTS attempts_at ON attempts(at)")
            self.db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value REAL NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")

    def _value(self, key, default=0):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, value))

    def reserve(self, key, pace=False):
        now = self.clock()
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("DELETE FROM attempts WHERE at<=?", (now - 3600,))
            self.db.execute("DELETE FROM state WHERE key LIKE 'profile:%' AND value<=?", (now,))
            until = self._value("blocked_until")
            if until > now:
                raise BudgetError("WCL API budget is low", until - now)
            until = self._value("profile:" + key)
            if until > now:
                raise BudgetError("Profile refresh is cooling down", until - now, False)
            count, first = self.db.execute("SELECT COUNT(*), MIN(at) FROM attempts").fetchone()
            if count >= self.hourly:
                raise BudgetError("Local hourly query limit reached", first + 3600 - now)
            reset = self._value("reset_at")
            cap = self._value("limit")
            if now < reset and cap - self._value("spent") < max(100, cap * .1) + self._value("largest_observed_cost"):
                raise BudgetError("WCL API budget is low", reset - now)
            scheduled = max(now, self._value("next_request_at")) if pace else now
            if scheduled - now > 30:
                raise BudgetError("WCL requests are cooling down", scheduled - now)
            self.db.execute("INSERT INTO attempts VALUES (?,?)", (now, key))
            # Even unsuccessful attempts cannot be spammed for one identity.
            self._set("profile:" + key, now + 300)
            self._increment("upstream_attempts")
            if pace:
                self._set("next_request_at", scheduled + 1)
            return scheduled - now

    def _increment(self, name):
        self.db.execute("INSERT INTO counters VALUES (?,1) ON CONFLICT(key) DO UPDATE SET value=value+1", (name,))

    def count(self, name):
        with self.lock, self.db:
            self._increment(name)

    def observe(self, limit):
        if not isinstance(limit, dict):
            return
        try:
            cap, spent, reset = (float(limit[key]) for key in ("limitPerHour", "pointsSpentThisHour", "pointsResetIn"))
            if not all(math.isfinite(x) for x in (cap, spent, reset)) or cap <= 0 or spent < 0 or not 0 <= reset <= 86400:
                return
        except (KeyError, ValueError, TypeError):
            return
        now = self.clock()
        with self.lock, self.db:
            prior = self._value("spent")
            if now < self._value("reset_at") and spent >= prior:
                # This may include other traffic sharing the quota; treat it conservatively.
                self._set("largest_observed_cost", max(self._value("largest_observed_cost"), spent - prior))
                self._set("observed_points_delta", self._value("observed_points_delta") + spent - prior)
            else:
                self._set("largest_observed_cost", 0)
            self._set("limit", cap)
            self._set("spent", spent)
            self._set("reset_at", now + reset)
            # Absolute reserve helps small quotas; proportional reserve scales up.
            if cap - spent < max(100, cap * .1):
                self._set("blocked_until", max(self._value("blocked_until"), now + reset))

    def success(self, key):
        with self.lock, self.db:
            self._set("profile:" + key, self.clock() + 3600)

    def failure(self, error):
        self.observe(getattr(error, "rate_limit", None))
        status = getattr(error, "status", None)
        if status is None and "HTTP 429" in str(error):
            status = 429
        if status == 429 or status == 401 or status is not None and status >= 500 or isinstance(error, wcl.APIError):
            now = self.clock()
            with self.lock, self.db:
                self._increment("upstream_errors")
                pause = max(60, getattr(error, "retry_after", 0))
                if status == 429:
                    pause = max(pause, self._value("reset_at") - now)
                self._set("blocked_until", max(self._value("blocked_until"), now + pause))
            return True
        return False

    def snapshot(self):
        with self.lock:
            return {"counters": dict(self.db.execute("SELECT key,value FROM counters")),
                    "limitPerHour": self._value("limit"), "pointsSpentThisHour": self._value("spent"),
                    "resetAt": self._value("reset_at"), "blockedUntil": self._value("blocked_until"),
                    "largestObservedCost": self._value("largest_observed_cost"),
                    "observedPointsDelta": self._value("observed_points_delta")}

    def close(self):
        self.db.close()
