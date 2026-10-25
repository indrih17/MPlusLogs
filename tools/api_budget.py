"""Persistent rolling request budget and upstream cooldown; contains no credentials."""
import math
from pathlib import Path
import sqlite3
import threading
import time
import uuid

import wcl_sync as wcl


def failure_code(error):
    code = getattr(error, 'code', None)
    if code in wcl.ERROR_CODES: return code
    if getattr(error, 'status', None) == 429 or 'HTTP 429' in str(error): return 'budget'
    if getattr(error, 'status', None) == 401: return 'auth'
    return 'network' if isinstance(error, OSError) else 'unknown'


def failure_deadline(error, count, now):
    """Retry hints are lower bounds; only actual failures advance the backoff."""
    code = failure_code(error)
    details = wcl.error_info(error, now)
    hint = details['retry_at'] if getattr(error,'retry_at',0)>now else now + max(0,getattr(error,'retry_after',0))
    limit=getattr(error,'rate_limit',None)
    if code=='budget' and isinstance(limit,dict):
        reset=limit.get('pointsResetIn')
        if type(reset) in (int,float) and math.isfinite(reset) and 0<reset<=86400:
            hint=max(hint,now+reset)
    if code == 'budget': delay = 0 if hint > now else 60
    elif code in {'schema', 'auth'}: delay = 60
    else: delay = min(120, 15 * 2 ** min(3, max(0, count - 1)))
    return math.ceil(max(now + delay, hint))


class BudgetError(ValueError):
    def __init__(self, message, retry_after, global_stop=True, code=None, retry_at=0):
        self.global_stop = global_stop
        self.code = code or ("budget" if global_stop else "retry")
        self.retry_after = max(1, math.ceil(retry_after))
        self.attempted = False
        self.retry_at = retry_at
        super().__init__(message + f"; retry after {self.retry_after} seconds")


class Admission(float):
    """Preserve the delay API while identifying one point reservation."""
    def __new__(cls, delay, identity):
        result=super().__new__(cls,delay)
        result.identity=identity
        return result


class Budget:
    def __init__(self, path=None, hourly=120, clock=time.time):
        if path is not None:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path) if path is not None else ":memory:", timeout=10, check_same_thread=False)
        self.lock = threading.RLock()
        self.hourly, self.clock = hourly, clock
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute("CREATE TABLE IF NOT EXISTS attempts (at REAL NOT NULL, key TEXT NOT NULL)")
            self.db.execute("CREATE INDEX IF NOT EXISTS attempts_at ON attempts(at)")
            self.db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value REAL NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS point_reservations (id TEXT PRIMARY KEY, at REAL NOT NULL, key TEXT NOT NULL, cost REAL NOT NULL, status TEXT NOT NULL, finished REAL NOT NULL)")
            if self._value('point_ledger_version')<2:
                # Legacy attempts are history, not unresolved monetary holds.
                # Old maxima could be a batch-wide delta, not a request price.
                now=self.clock()
                self._set('largest_observed_cost',0)
                self._set('point_window_start',now)
                self._set('point_window_base',self._value('spent') if now<self._value('reset_at') else 0)
                self._set('point_ledger_version',2)

    def _value(self, key, default=0):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, value))

    def _point_projection(self, now):
        # Pending holds and completed costs have separate lifecycles. The local
        # completed floor covers replies whose WCL snapshot precedes charging;
        # max() reconciles it with WCL instead of adding completed work twice.
        start=self._value('point_window_start')
        charged=self.db.execute("SELECT COALESCE(SUM(cost),0) FROM point_reservations WHERE status='settled' AND finished>=? AND at>?",(start,now-3600)).fetchone()[0]
        reserved=self.db.execute("SELECT COALESCE(SUM(cost),0) FROM point_reservations WHERE status IN ('pending','uncertain') AND at>?",(now-3600,)).fetchone()[0]
        cost = max(1, self._value("largest_observed_cost"))
        floor=self._value('point_window_base')+charged if now<self._value('reset_at') else 0
        return max(self._value('spent') if now<self._value('reset_at') else 0,floor)+reserved, reserved, cost

    def _check_upstream(self,now, reserve_next=False):
        until=self._value('blocked_until')
        if until>now:
            self._raise_blocked(now, until)
        reset=self._value('reset_at')
        cap=self._value('limit')
        if now < reset:
            projected, _, cost = self._point_projection(now)
            needed=max(100, cap * .1) + (cost if reserve_next else 0)
            if cap - projected < needed:
                message='WCL API budget is low' if cap-self._value('spent')<needed else 'Local API safety reserve reached'
                raise BudgetError(message,reset-now,retry_at=math.ceil(reset))

    def _raise_blocked(self, now, until):
        # Legacy records do not say what caused the pause. Keep the admission
        # gate, but only call it exhausted quota when we have quota evidence.
        low = (now < self._value('budget_blocked_until') or
               now < self._value('reset_at') and
               self._value('limit') - self._value('spent') < max(100, self._value('limit') * .1))
        if low: raise BudgetError('WCL API budget is low', until-now,retry_at=math.ceil(until))
        raise BudgetError('WCL requests are cooling down after an upstream error', until-now, code='retry',retry_at=math.ceil(until))

    def check_upstream(self, admission=None):
        with self.lock:
            if getattr(admission,'identity',None):
                # The admission already owns its slot. Only a genuine upstream
                # stop can revoke it; other local holds cannot reject it again.
                now=self.clock()
                until=self._value('blocked_until')
                if until>now:self._raise_blocked(now, until)
                cap=self._value('limit');reset=self._value('reset_at')
                if now<reset and cap-self._value('spent')<max(100,cap*.1):
                    raise BudgetError('WCL API budget is low',reset-now,retry_at=math.ceil(reset))
            else:self._check_upstream(self.clock())

    def reserve(self, key, pace=False, profile=True):
        now = self.clock()
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("DELETE FROM attempts WHERE at<=?", (now - 3600,))
            self.db.execute("DELETE FROM point_reservations WHERE at<=?",(now-3600,))
            self.db.execute("DELETE FROM state WHERE key LIKE 'profile:%' AND value<=?", (now,))
            self._check_upstream(now, reserve_next=True)
            until = self._value("profile:" + key)
            if profile and until > now:
                raise BudgetError("Profile refresh is cooling down", until - now, False,retry_at=math.ceil(until))
            count, first = self.db.execute("SELECT COUNT(*), MIN(at) FROM attempts").fetchone()
            if count >= self.hourly:
                raise BudgetError("Local hourly query limit reached", first + 3600 - now,retry_at=math.ceil(first+3600))
            scheduled = max(now, self._value("next_request_at")) if pace else now
            if scheduled - now > 30:
                raise BudgetError("WCL requests are cooling down", scheduled - now,retry_at=math.ceil(scheduled))
            self.db.execute("INSERT INTO attempts VALUES (?,?)", (now, key))
            identity=uuid.uuid4().hex
            self.db.execute("INSERT INTO point_reservations VALUES (?,?,?,?,?,?)",(identity,now,key,max(1,self._value('largest_observed_cost')),'pending',0))
            # Even unsuccessful attempts cannot be spammed for one identity.
            if profile: self._set("profile:" + key, now + 300)
            self._increment("upstream_attempts")
            if pace:
                self._set("next_request_at", scheduled + 1)
            return Admission(scheduled-now,identity)

    @staticmethod
    def _request_cost(limit):
        measured=limit.get('currentRequest') if isinstance(limit,dict) else None
        measured=measured.get('total') if isinstance(measured,dict) else None
        return measured if type(measured) in (int,float) and math.isfinite(measured) and measured>0 else None

    def complete(self, admission, limit=None, sent=True, uncertain=False):
        identity=getattr(admission,'identity',None)
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self._observe(limit,self._request_cost(limit) or 0)
            if identity:
                status='cancelled' if not sent else 'uncertain' if uncertain else 'settled'
                cost=self._request_cost(limit)
                self.db.execute("UPDATE point_reservations SET status=?,cost=COALESCE(?,cost),finished=? WHERE id=? AND status='pending'",(status,cost,self.clock(),identity))

    def _increment(self, name):
        self.db.execute("INSERT INTO counters VALUES (?,1) ON CONFLICT(key) DO UPDATE SET value=value+1", (name,))

    def count(self, name):
        with self.lock, self.db:
            self._increment(name)

    def observe(self, limit):
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self._observe(limit)

    def _observe(self, limit, current_cost=0):
        if not isinstance(limit, dict):
            return
        try:
            cap, spent, reset = (float(limit[key]) for key in ("limitPerHour", "pointsSpentThisHour", "pointsResetIn"))
            if not all(math.isfinite(x) for x in (cap, spent, reset)) or cap <= 0 or spent < 0 or not 0 <= reset <= 86400:
                return
        except (KeyError, ValueError, TypeError):
            return
        now = self.clock()
        prior = self._value("spent")
        measured=self._request_cost(limit)
        old_reset=self._value('reset_at')
        # Concurrent replies may arrive out of order within the same
        # quota window. Never restore points from an older observation.
        if now<old_reset and now+reset<=old_reset+60:
            spent=max(prior,spent)
            reset=max(reset,old_reset-now)
        if now>=old_reset:
            self._set('point_window_start',now)
            self._set('point_window_base',max(0,spent-current_cost))
            self._set('largest_observed_cost',measured or 0)
        elif measured is not None:
            self._set('largest_observed_cost',max(self._value('largest_observed_cost'),measured))
        if measured is not None:
            # Only active holds may learn a higher price. Completed work keeps
            # its actual cost, and a quota-only snapshot is never a unit price.
            self.db.execute("UPDATE point_reservations SET cost=MAX(cost,?) WHERE status='pending'",(measured,))
        self._set('observed_points_delta',self._value('observed_points_delta')+max(0,spent-prior))
        self._set("limit", cap)
        self._set("spent", spent)
        self._set("reset_at", now + reset)
        # Absolute reserve helps small quotas; proportional reserve scales up.
        if cap - spent < max(100, cap * .1):
            self._set("blocked_until", max(self._value("blocked_until"), now + reset))
            self._set("budget_blocked_until", max(self._value("budget_blocked_until"), now + reset))

    def _owns_profile(self, key, admission):
        identity=getattr(admission, 'identity', None)
        if not identity:return False
        row=self.db.execute('SELECT id FROM point_reservations WHERE key=? ORDER BY rowid DESC LIMIT 1',(key,)).fetchone()
        return bool(row and row[0]==identity)

    def authenticated(self, generation):
        """A validated login clears authentication failures, never quota holds."""
        if not isinstance(generation, str) or not generation:return
        with self.lock,self.db:
            previous=self._value('auth_generation', '')
            if previous==generation:return
            keys=[row[0][len('failure_code:'):] for row in self.db.execute(
                "SELECT key FROM state WHERE key LIKE 'failure_code:%' AND value='auth'")]
            for key in keys:
                for prefix in ('profile:', 'failure_count:', 'failure_code:'):
                    self.db.execute('DELETE FROM state WHERE key=?',(prefix+key,))
            self._set('auth_generation', generation)

    def reconcile_failure(self, key, until, error_at):
        """Migrate an old failed-cache gate without changing a newer admission."""
        with self.lock,self.db:
            latest=self.db.execute('SELECT at FROM point_reservations WHERE key=? ORDER BY rowid DESC LIMIT 1',(key,)).fetchone()
            if latest and latest[0]>error_at:return
            gate=self._value('profile:'+key)
            if gate and gate<=error_at+301:self._set('profile:'+key,min(gate,until))

    def success(self, key, admission=None, profile=True):
        with self.lock, self.db:
            # Normal reads use the cache TTL; explicit refresh is allowed after
            # five minutes, matching the addon and builder refresh controls.
            if admission is not None and not self._owns_profile(key,admission):return
            if profile:self._set("profile:" + key, self.clock() + 300)
            for prefix in ('failure_count:', 'failure_code:'):
                self.db.execute('DELETE FROM state WHERE key=?',(prefix+key,))

    def failure(self, error, key=None, admission=None, profile=True, sent=True, auth_generation=None):
        self.observe(getattr(error, "rate_limit", None))
        now=self.clock()
        code=failure_code(error)
        with self.lock,self.db:
            owned=key is not None and self._owns_profile(key,admission)
            if (owned and code=='auth' and auth_generation is not None
                    and self._value('auth_generation','')!=auth_generation):
                # A worker from the previous validated login must not recreate
                # an authentication gate after the new login has cleared it.
                if profile:self._set('profile:'+key,min(self._value('profile:'+key),now))
                owned=False
            count=int(self._value('failure_count:'+key)) + int(sent) if owned else 1
            until=failure_deadline(error,count,now)
            if owned:
                self._set('failure_count:'+key,min(count,8))
                self._set('failure_code:'+key,code)
                if profile:self._set('profile:'+key,until)
                error.failure_count=min(count,8)
                error.retry_at=until
                error.attempted=sent
        status = getattr(error, "status", None)
        if status is None and "HTTP 429" in str(error):
            status = 429
        if code!='auth' and wcl.stops_batch(error):
            with self.lock, self.db:
                self.db.execute('BEGIN IMMEDIATE')
                self._increment("upstream_errors")
                pause = until-now
                if status == 429:
                    pause = max(pause, self._value("reset_at") - now)
                    self._set("budget_blocked_until", max(self._value("budget_blocked_until"), now + pause))
                self._set("blocked_until", max(self._value("blocked_until"), now + pause))
                error.retry_at=math.ceil(max(getattr(error,'retry_at',0),self._value('blocked_until')))
            return True
        return False

    def snapshot(self):
        with self.lock:
            projected, reserved, cost = self._point_projection(self.clock())
            return {"counters": dict(self.db.execute("SELECT key,value FROM counters")),
                    "limitPerHour": self._value("limit"), "pointsSpentThisHour": self._value("spent"),
                    "resetAt": self._value("reset_at"), "blockedUntil": self._value("blocked_until"),
                    "largestObservedCost": self._value("largest_observed_cost"),
                    "projectedSpentThisHour": projected,
                    "localReservedPoints": reserved, "requestCostEstimate": cost,
                    "observedPointsDelta": self._value("observed_points_delta")}

    def close(self):
        self.db.close()
