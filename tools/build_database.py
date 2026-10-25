"""Build a shareable M+ addon database from a roster/seen-player queue and WCL API."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace
from urllib.parse import unquote

import wcl_sync as wcl
import realm_resolver
from api_budget import BudgetError, failure_code, failure_deadline
import cache_maintenance

ROOT = Path(__file__).resolve().parents[1]


def identity(region, realm, name):
    def normalized(text):
        return re.sub(r"[\s\-']", "", text.casefold())
    return region.lower(), normalized(realm), normalized(name)


def profile_identity(entry):
    return (*identity(entry.get("region", "eu"), entry["realm"],
                      entry.get("name") or str(entry.get("character_id"))),
            entry.get("spec") or "All specs", entry.get("role") or "")


def load_entries(manifest=None, requests=None, realms=None):
    entries = []
    if manifest:
        entries = json.loads(manifest.read_text(encoding="utf-8-sig"))
        if not isinstance(entries, list):
            raise ValueError("Roster must be a JSON array")
        if any(not isinstance(entry, dict) for entry in entries):
            raise ValueError("Every roster entry must be a JSON object")
    if requests:
        text = requests.read_text(encoding="utf-8-sig")
        mapping = realm_resolver.load_mappings(realms)
        seen = {profile_identity(e) for e in entries if e.get("name")}
        for request in realm_resolver.parse_queue(text,mapping):
            key = profile_identity(request)
            if key in seen:
                continue
            entries.append(request)
            seen.add(key)
    if not entries or len(entries) > 1000:
        raise ValueError("Roster must contain 1..1000 characters")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("realm"):
            raise ValueError("Every roster entry needs a localized realm name")
        if not entry.get("character_id") and not (entry.get("name") and entry.get("server_slug")):
            raise ValueError("Each entry needs character_id or name + server_slug")
        if entry.get("region", "eu") not in {"eu", "us", "kr", "tw", "cn"}:
            raise ValueError("Unsupported region")
        if entry.get("metric", "dps") not in {"dps", "hps"}:
            raise ValueError("Unsupported metric")
        if entry.get("role") not in {None,"HEALER","TANK","DAMAGER"}:
            raise ValueError("Unsupported role")
        key = profile_identity(entry)
        if key in seen:
            raise ValueError("Duplicate character specialization/role; remove duplicate roster entries")
        seen.add(key)
    return entries


def arguments(entry):
    return SimpleNamespace(character_id=entry.get("character_id"), name=entry.get("name"),
                           realm=entry["realm"], server_slug=entry.get("server_slug"),
                           region=entry.get("region", "eu"), zone=55, season="Midnight M+ Season 2",
                           spec=entry.get("spec"), metric=entry.get("metric", "dps"),role=entry.get("role"),
                           class_name=entry.get("class_name"), class_id=entry.get("class_id"),
                           include_secondary=bool(entry.get("include_secondary", False)))


def cache_path(directory, entry):
    # Raw dual replies depend on WCL filters, not display role, metric or localized realm.
    args = arguments(entry)
    key = {"id": args.character_id, "name": (args.name or "").casefold(),
           "slug": (args.server_slug or "").casefold(), "region": args.region.lower(),
           "zone": args.zone, "season": args.season, "spec": args.spec,
           "scope": entry.get("_cache_scope", "public"), "query_version": "mplus-dual-v3"}
    encoded = json.dumps(key, sort_keys=True, ensure_ascii=True).encode()
    return directory / (hashlib.sha256(encoded).hexdigest() + ".json")


def read_cache(path):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        stamp = record.get("fetched_at")
        if (not isinstance(stamp, (float, int)) or isinstance(stamp, bool)
                or not 0 <= stamp <= 253402300799 or not math.isfinite(stamp)):
            return None
        retry = record.get("retry_until", 0)
        if (not isinstance(retry, (float, int)) or isinstance(retry, bool)
                or not 0 <= retry <= 253402300799 or not math.isfinite(retry)):
            return None
        if record.get("negative") and (not isinstance(record.get("error"), str) or not record["error"]):
            return None
        if "refresh_error" in record and not isinstance(record["refresh_error"], str):
            return None
        return record
    except (ValueError, OSError, AttributeError):
        return None


def validate_raw(raw, args):
    # Presentation choice must never determine whether a raw reply is cacheable.
    character = wcl.character_data(raw)
    wcl.validate_identity(raw, args)
    if wcl.primary_only_raw(raw):
        if not wcl.cache_satisfies(raw,args):
            raise wcl.ProfileError("Incomplete requested metrics; refresh with both WCL metrics", "retry")
        try:
            wcl.normalize(raw, args)
        except wcl.NoSeasonLogs:
            raise wcl.ProfileError("No primary measurements; refresh with both WCL metrics", "retry") from None
        return
    # Hidden characters return zoneRankings error objects rather than ranking
    # arrays. Classify access/absence before validating the metric schema.
    if character and "damage" in character and "healing" in character:
        damage, healing = wcl.rankings(character["damage"]), wcl.rankings(character["healing"])
        if not damage["rankings"] and not healing["rankings"]:
            wcl.normalize(raw, args)  # Produces the typed absence response.
        for role, metric in (("DAMAGER", damage), ("HEALER", healing)):
            # A DPS-only character may legitimately have no healing rankings.
            if metric["rankings"]:
                wcl.normalize(raw, SimpleNamespace(**dict(vars(args), role=role)))
    else:
        wcl.normalize(raw, args)  # Legacy fixtures / offline conversion.


def lua_string(text):
    # Lua 5.1 has no JSON-style Unicode escapes. Quote UTF-8 byte by byte,
    # including quotes, backslashes and controls; imported data cannot inject Lua.
    return '"' + "".join(chr(b) if 32 <= b < 127 and b not in (34, 92) else f"\\{b:03d}"
                         for b in text.encode("utf-8")) + '"'


def bundle(profiles):
    keys = [profile_identity(p) for p in profiles]
    if len(set(keys)) != len(keys):
        raise ValueError("Different roster entries resolved to the same character specialization/role; database not replaced")
    text = "MPL1\n" + "".join(wcl.export(p).removeprefix("MPL1\n") for p in profiles)
    if len(text.encode()) > 500000:
        raise ValueError("Database exceeds current 500 KB limit; split datasets or extend addon storage")
    return "local _, MPL = ...\n-- Generated public WCL data. Contains no credentials.\nMPL.bundledText = " + lua_string(text) + "\n"


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _profile_resources():
    """Cheap Windows memory/CPU counters; unavailable telemetry stays conservative."""
    if sys.platform != 'win32':
        return None, None
    import ctypes
    from ctypes import wintypes
    class Memory(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
            (name, ctypes.c_ulonglong) for name in (
                'total', 'available', 'page_total', 'page_available',
                'virtual_total', 'virtual_available', 'extended')]
    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        available = memory.available if kernel.GlobalMemoryStatusEx(ctypes.byref(memory)) else None
        idle, system, user = (wintypes.FILETIME() for _ in range(3))
        ticks = None
        if kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(system), ctypes.byref(user)):
            values = [value.dwLowDateTime + (value.dwHighDateTime << 32) for value in (idle, system, user)]
            ticks = (values[0], values[1] + values[2])
        return available, ticks
    except (OSError, AttributeError):
        return None, None


class _ProfileWaves:
    """Bound I/O by memory and measured pressure, never by a CPU core count."""
    def __init__(self, maximum):
        self.maximum = min(50, max(1, maximum))
        self.ceiling = self.maximum
        self.previous = None
        self.ticks = None
        self.healthy = 0

    def desired(self, remaining):
        memory, ticks = _profile_resources()
        # Leave headroom for WoW and the GUI. Unknown telemetry is not evidence
        # that a machine can comfortably absorb fifty replies at once.
        gib = 1024 ** 3
        resource_cap = 16
        if memory is not None:
            resource_cap = next((cap for threshold, cap in (
                (gib/2, 4), (gib, 8), (2*gib, 16), (4*gib, 32))
                if memory < threshold), 50)
        if ticks and self.ticks:
            idle, total = ticks[0]-self.ticks[0], ticks[1]-self.ticks[1]
            if total > 0 and 1-idle/total >= .9:
                resource_cap = min(resource_cap, 8)
        self.ticks = ticks
        # Balance remaining real requests over the fewest waves permitted by
        # the current resource ceiling, avoiding a large wave and a tiny tail.
        limit = min(self.maximum, self.ceiling, resource_cap)
        waves = math.ceil(remaining/limit)
        return math.ceil(remaining/waves)

    def observe(self, width, elapsed, cpu, durations):
        if not durations:
            return
        latency = statistics.median(durations)
        throughput = len(durations)/max(elapsed, .000001)
        # CPU covers normalization, JSON/cache writes and scheduler work too.
        # Ignore sub-50ms waves, whose ratios are dominated by timer noise.
        cpu_pressure = elapsed >= .05 and cpu/elapsed >= .65
        congestion = (len(durations) >= 4 and self.previous is not None
                      and latency > self.previous[0]*1.75
                      and throughput < self.previous[1]*1.1)
        if cpu_pressure or congestion:
            self.ceiling = max(1, min(self.ceiling, width//2))
            self.healthy = 0
        else:
            self.healthy += 1
            if self.healthy >= 2:
                self.ceiling = min(self.maximum, max(self.ceiling+1, math.ceil(self.ceiling*1.25)))
                self.healthy = 0
        if len(durations) >= 4:
            self.previous = (latency, throughput)


def _parallel_build(entries, cache_dir, ttl_hours, max_fetch, offline, fetcher, now, refresh, progress, max_workers):
    entries=list(entries)
    now=time.time() if now is None else now
    guard=threading.Lock()
    cache_locks={cache_path(cache_dir,entry):threading.Lock() for entry in entries}
    fetched=0
    stopped=None
    remaining=None
    token=None
    token_lock=threading.Lock()
    durations=[]

    def shared_fetch(args):
        nonlocal fetched,stopped,remaining,token
        with guard:
            if stopped:
                error=wcl.ProfileError(stopped['message'],stopped['error_code'],stopped['retry_at'])
                error.attempted=False
                raise error
            if fetched>=max_fetch:
                raise wcl.ProfileError('Per-run request limit reached','budget')
            if remaining is not None and remaining<100:
                raise wcl.ProfileError('WCL hourly budget is low; retry after reset','budget')
            if getattr(fetcher,'cancel',None) is not None and fetcher.cancel.is_set():
                raise wcl.ProfileError('Profile loading stopped','retry')
            fetched+=1
        started=time.monotonic()
        try:
            if fetcher:
                raw=fetcher(args)
            else:
                with token_lock:
                    token=token or wcl.access_token()
                raw=wcl.fetch(args,token)
            limit=wcl.rate_limit_data(raw)
            if limit:
                points=limit['limitPerHour']-limit['pointsSpentThisHour']
                with guard:remaining=points if remaining is None else min(remaining,points)
            return raw
        except (ValueError,OSError,KeyError,TypeError) as exc:
            if wcl.stops_batch(exc):
                with guard:
                    if stopped is None:
                        details,_=_failure_details(exc,None,now)
                        stopped=dict(message=str(exc),**details)
            raise
        finally:
            with guard:durations.append(time.monotonic()-started)

    shared_fetch.budget=getattr(fetcher,'budget',None)
    shared_fetch.auth_generation=getattr(fetcher,'auth_generation','')
    if hasattr(fetcher,'reconcile_failure'):shared_fetch.reconcile_failure=fetcher.reconcile_failure
    def run(entry):
        # Role/realm aliases can share one raw cache key. Serialize that key,
        # so the second view reads the completed cache instead of racing .tmp.
        with cache_locks[cache_path(cache_dir,entry)]:
            return build([entry],cache_dir,ttl_hours,max_fetch,offline,shared_fetch,now,refresh)

    results={}
    completed=0
    if progress:progress(0,len(entries),entries[0] if entries else None)
    if max_workers>3:
        policy=_ProfileWaves(max_workers)
        # Establish a system CPU interval including the quota probe.
        policy.desired(max(1,len(entries)))
        def finish(index, result):
            nonlocal completed
            results[index]=result;completed+=1
            if progress:progress(completed,len(entries),entries[index] if completed<len(entries) else None)

        # Cached, offline and cooling-down views need no network slots. Group
        # role/realm aliases by raw key, so they do not inflate the wave size.
        groups={}
        for index,entry in enumerate(entries):
            path=cache_path(cache_dir,entry)
            cached=_prepare_retry_cache(path,read_cache(path),entry,now,fetcher)
            if offline or (_fresh_cache(cached,now,ttl_hours,refresh) and _complete_cache(cached,entry)) or _retry_cache_active(cached,now,fetcher):
                finish(index,run(entries[index]))
            else:
                groups.setdefault(path,[]).append(index)
        pending=list(groups.values())
        if pending and max_fetch>0:
            probe=pending.pop(0)
            started=time.monotonic();cpu=time.process_time()
            for index in probe:finish(index,run(entries[index]))
            policy.observe(1,time.monotonic()-started,time.process_time()-cpu,durations)
        durations.clear()
        capacity=getattr(fetcher,'parallel_capacity',None)
        with ThreadPoolExecutor(max_workers=min(50,max_workers)) as pool:
            while pending:
                if stopped or fetched>=max_fetch:
                    # Visit remaining entries to retain stale-cache fallback
                    # and error details, without asking the network again.
                    for group in pending:
                        for index in group:finish(index,run(entries[index]))
                    break
                desired=policy.desired(min(len(pending),max_fetch-fetched))
                allowed=min(desired,capacity(desired)) if capacity else min(3,desired)
                if allowed<=0:
                    with guard:
                        if stopped is None:
                            budget=getattr(fetcher,'budget',None)
                            reset=budget.snapshot()['resetAt'] if budget else 0
                            stopped=dict(message='Local API safety reserve reached',error_code='budget',
                                         retry_at=math.ceil(max(now+60,reset)))
                            if budget:
                                try:budget.check_upstream()
                                except BudgetError as exc:
                                    details,_=_failure_details(exc,None,now)
                                    stopped=dict(message=str(exc),**details)
                    # Still visit cached entries and preserve old usable profiles.
                    allowed=desired
                wave,pending=pending[:allowed],pending[allowed:]
                started=time.monotonic();cpu=time.process_time()
                jobs={pool.submit(run,entries[group[0]]):group for group in wave}
                for job in as_completed(jobs):
                    group=jobs[job];finish(group[0],job.result())
                    for index in group[1:]:finish(index,run(entries[index]))
                policy.observe(len(wave),time.monotonic()-started,time.process_time()-cpu,durations)
                durations.clear()
    else:
        with ThreadPoolExecutor(max_workers=max(1,max_workers)) as pool:
            jobs={pool.submit(run,entry):index for index,entry in enumerate(entries)}
            for job in as_completed(jobs):
                index=jobs[job];results[index]=job.result();completed+=1
                if progress:progress(completed,len(entries),entries[index] if completed<len(entries) else None)
    profiles,errors=[],[]
    hits=negative_hits=0
    for index in range(len(entries)):
        loaded,report=results[index]
        profiles.extend(loaded);errors.extend(report['errors'])
        hits+=report['cacheHits'];negative_hits+=report['negativeCacheHits']
    return profiles,dict(profiles=len(profiles),fetched=fetched,cacheHits=hits,negativeCacheHits=negative_hits,
                         remainingApiPoints=remaining,errors=errors)


def _fresh_cache(cached,now,ttl_hours,refresh):
    ttl=6*3600 if cached and cached.get('negative') else max(3600,ttl_hours*3600)
    if refresh:ttl=min(ttl,300)
    return cached and ('raw' in cached or cached.get('negative')) and 0<=now-cached['fetched_at']<ttl


def _complete_cache(cached, entry):
    if not cached or "raw" not in cached:
        return True
    try:
        args = arguments(entry)
        wcl.validate_identity(cached["raw"], args)
        args.class_id = wcl.character_data(cached["raw"]).get("classID", args.class_id)
        args.class_name = wcl.character_class_name(cached["raw"])
        return wcl.cache_satisfies(cached["raw"], args)
    except (ValueError, KeyError, TypeError):
        return False


def _retry_cache_active(cached,now,fetcher):
    if not cached or now>=cached.get('retry_until',0):return False
    if cached.get('retry_policy_version')==1:return True
    budget=getattr(fetcher,'budget',None)
    message=cached.get('refresh_error','').lower()
    if budget and (cached.get('error_code')=='budget' or cached.get('retry_policy_version')!=1 and 'api budget is low' in message):
        try:
            budget.check_upstream()
            return False
        except BudgetError:
            pass
    return True


def _prepare_retry_cache(path, cached, entry, now, fetcher):
    """One-time migration with a fixed deadline; cache reads never slide it."""
    if not cached or not cached.get('refresh_error'):return cached
    code=cached.get('error_code',wcl.legacy_error_code(cached['refresh_error']))
    generation=getattr(fetcher,'auth_generation','')
    relogged=code=='auth' and bool(generation) and cached.get('auth_generation')!=generation
    budget=getattr(fetcher,'budget',None)
    budget_error=None
    if code=='budget' and budget:
        if cached.get('retry_policy_version')==1:return cached
        try:budget.check_upstream()
        except BudgetError as exc:budget_error=exc
        if budget_error and budget_error.code=='budget':
            until=failure_deadline(budget_error,1,now)
            if cached.get('retry_until')==until and cached.get('retry_policy_version')==1:return cached
            record=dict(cached,retry_policy_version=1,retry_until=until,retry_at=until)
            reconcile=getattr(fetcher,'reconcile_failure',None)
            if reconcile:reconcile(entry,until,now)
            atomic_write(path,json.dumps(record,ensure_ascii=False))
            return record
        code=budget_error.code if budget_error else 'retry'
    elif not relogged and (cached.get('retry_policy_version')==1 or code not in {'schema','network','retry','unknown','auth'}):return cached
    record=dict(cached)
    stamp=record.get('error_at',record.get('error_saved_at'))
    if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=stamp<=now:stamp=now
    error=budget_error or wcl.ProfileError(record['refresh_error'],code)
    until=0 if relogged else min(record.get('retry_until',0),failure_deadline(error,1,stamp))
    record.update(retry_policy_version=1,error_at=stamp,retry_until=until,retry_at=until,failure_count=0,error_code=code)
    if budget_error:record['refresh_error']=str(budget_error)
    elif cached.get('error_code')=='budget':record['refresh_error']='WCL requests are cooling down after an upstream error'
    if code=='auth':record['auth_generation']=generation
    reconcile=getattr(fetcher,'reconcile_failure',None)
    if reconcile:reconcile(entry,until,stamp)
    atomic_write(path,json.dumps(record,ensure_ascii=False))
    return record


def _failure_details(error, cached, now):
    details=wcl.error_info(error,now)
    details['error_code']=failure_code(error)
    previous=(cached or {}).get('failure_count',0)
    if type(previous) is not int or not 0<=previous<=8:previous=0
    count=getattr(error,'failure_count',previous+(getattr(error,'attempted',True) is not False))
    if type(count) is not int or not 0<=count<=8:count=min(8,previous+1)
    details['retry_at']=failure_deadline(error,count,now)
    return details,count


def build(entries, cache_dir, ttl_hours=wcl.PROFILE_CACHE_TTL_HOURS, max_fetch=20, offline=False, fetcher=None, now=None, refresh=False, progress=None, max_workers=1):
    if max_workers>1:
        entries=list(entries)
        if len(entries)>1:
            return _parallel_build(entries,cache_dir,ttl_hours,max_fetch,offline,fetcher,now,refresh,progress,max_workers)
    if progress:
        entries = list(entries)
    now = time.time() if now is None else now
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_maintenance.maintain(cache_dir)
    profiles, errors, fetched = [], [], 0
    hits = negative_hits = 0
    token = None
    auth_failure = None
    auth_details = {}
    remaining = None
    for index, entry in enumerate(entries):
        if progress:
            progress(index, len(entries), entry)
        path = cache_path(cache_dir, entry)
        cached = _prepare_retry_cache(path,read_cache(path),entry,now,fetcher)
        fresh = _fresh_cache(cached,now,ttl_hours,refresh) and _complete_cache(cached,entry)
        record = cached
        failure = None
        details = {}
        if fresh:
            if cached.get("negative"):
                negative_hits += 1
                errors.append(dict(character=entry.get("name") or entry.get("character_id"), region=entry.get("region", "eu"), realm=entry["realm"], error=cached["error"],
                                   error_code=cached.get("error_code",wcl.legacy_error_code(cached["error"])), retry_at=cached["fetched_at"]+6*3600))
                continue
            hits += 1
        if not fresh and not offline:
            if auth_failure:
                failure = auth_failure
                details = auth_details
            elif _retry_cache_active(cached,now,fetcher):
                failure = cached.get("refresh_error", "Profile refresh is cooling down")
                details = dict(error_code=cached.get("error_code",wcl.legacy_error_code(failure)), retry_at=cached["retry_until"])
                # Older releases labelled every upstream pause as exhausted
                # quota. Keep the gate, but report the current reason accurately.
                budget=getattr(fetcher, 'budget', None)
                if budget and details['error_code']=='budget':
                    try:budget.check_upstream()
                    except BudgetError as exc:
                        if exc.code!='budget':
                            failure=str(exc)
                            details['error_code']=exc.code
            elif fetched >= max_fetch:
                failure = "Per-run request limit reached"
                details = dict(error_code="budget",retry_at=0)
            elif remaining is not None and remaining < 100:
                failure = "WCL hourly budget is low; retry after reset"
                details = dict(error_code="budget",retry_at=0)
            else:
                try:
                    args = arguments(entry)
                    if cached and "refresh with both WCL metrics" in cached.get("refresh_error", ""):
                        args.include_secondary = True
                    if cached and "raw" in cached:
                        try:
                            args.class_id = wcl.character_data(cached["raw"]).get("classID", args.class_id)
                            args.class_name = wcl.character_class_name(cached["raw"])
                        except (ValueError, KeyError, TypeError):
                            pass
                    fetched += 1
                    if fetcher:
                        raw = fetcher(args)
                    else:
                        token = token or wcl.access_token()
                        raw = wcl.fetch(args, token)
                    # Read budget before normalization, including valid empty replies.
                    limit = wcl.rate_limit_data(raw)
                    if limit:
                        remaining = limit["limitPerHour"] - limit["pointsSpentThisHour"]
                    validate_raw(raw, args)  # Never replace good cache with malformed JSON.
                    record = {"fetched_at": now, "raw": raw}
                    atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2))
                except wcl.NoProfile as exc:
                    failure = str(exc)
                    details=wcl.error_info(exc,now)
                    record = dict(fetched_at=now, negative=True, error=failure, **details)
                    atomic_write(path, json.dumps(record, ensure_ascii=False))
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    failure = str(exc)
                    details,count=_failure_details(exc,cached,now)
                    # Back off for this key without discarding a previous good result.
                    if wcl.stops_batch(exc):
                        auth_failure = failure  # Stop this whole batch, rather than hammer upstream.
                        auth_details = details
                    record = dict(cached or {"fetched_at": 0}, retry_until=details['retry_at'], refresh_error=failure,
                                  retry_policy_version=1,error_at=now,failure_count=count, **details)
                    if details['error_code']=='auth':record['auth_generation']=getattr(fetcher,'auth_generation','')
                    atomic_write(path, json.dumps(record, ensure_ascii=False))
                    if not token and not fetcher:
                        auth_failure = failure
        elif not fresh and offline:
            failure = "Offline: using cache without refresh"
        if failure:
            errors.append(dict(character=entry.get("name") or entry.get("character_id"), region=entry.get("region", "eu"), realm=entry["realm"], error=failure, **details))
        if not record or record.get("negative") or "raw" not in record:
            continue
        try:
            if not _complete_cache(record, entry):
                raise wcl.ProfileError("Secondary metric requires a full WCL profile", "retry")
            profile = wcl.normalize(record["raw"], arguments(entry))
            profile["updated"] = datetime.fromtimestamp(record["fetched_at"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if failure:
                profile["source"] = "WCL API: cached; refresh unavailable"
            profiles.append(profile)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(dict(character=entry.get("name") or entry.get("character_id"), region=entry.get("region", "eu"), realm=entry["realm"], error=str(exc), **wcl.error_info(exc,now)))
    if progress:
        progress(len(entries), len(entries), None)
    budget = getattr(fetcher, "budget", None)
    if budget:
        for _ in range(hits): budget.count("cache_hits")
        for _ in range(negative_hits): budget.count("negative_cache_hits")
    return profiles, {"profiles": len(profiles), "fetched": fetched, "cacheHits": hits,
                      "negativeCacheHits": negative_hits, "remainingApiPoints": remaining, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="JSON list of friends/characters")
    parser.add_argument("--requests", type=Path, help="MPLQ1 list exported by /mpl requests")
    parser.add_argument("--realm-slugs", type=Path, default=ROOT / "realm-slugs.json")
    parser.add_argument("--cache", type=Path, default=ROOT / ".wcl-cache")
    parser.add_argument("--output", type=Path, default=ROOT / "Database.lua")
    parser.add_argument("--report", type=Path, default=ROOT / "database-build-report.json")
    parser.add_argument("--ttl-hours", type=float, default=24)
    parser.add_argument("--max-fetch", type=int, default=20)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not args.manifest and not args.requests:
        parser.error("Specify --manifest or --requests")
    if args.ttl_hours < 0 or not 0 <= args.max_fetch <= 1000:
        parser.error("Invalid TTL or request limit")
    try:
        entries = load_entries(args.manifest, args.requests, args.realm_slugs)
        profiles, report = build(entries, args.cache, args.ttl_hours, args.max_fetch, args.offline)
        atomic_write(args.report, json.dumps(report, ensure_ascii=False, indent=2))
        if not profiles:
            raise ValueError("No usable WCL profiles. Existing Database.lua preserved. See build report")
        content = bundle(profiles)
        atomic_write(args.output, content)
        print(f"Database: {len(profiles)} profiles, {report['fetched']} API queries -> {args.output}")
        print("In WoW use /reload. Share Database.lua with friends who have MPlusLogs installed.")
        if report["errors"]:
            print(f"Some profiles could not refresh ({len(report['errors'])}); see {args.report}")
            return 2
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
