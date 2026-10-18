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
from types import SimpleNamespace
from urllib.parse import unquote

import wcl_sync as wcl
import realm_resolver
from api_budget import BudgetError
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
                           spec=entry.get("spec"), metric=entry.get("metric", "dps"),role=entry.get("role"))


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
        return record
    except (ValueError, OSError, AttributeError):
        return None


def validate_raw(raw, args):
    # Presentation choice must never determine whether a raw reply is cacheable.
    character = wcl.character_data(raw)
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


def build(entries, cache_dir, ttl_hours=24, max_fetch=20, offline=False, fetcher=None, now=None, refresh=False, progress=None):
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
        cached = read_cache(path)
        ttl = 6 * 3600 if cached and cached.get("negative") else max(3600, ttl_hours * 3600)
        if refresh:
            ttl = min(ttl, 300)
        fresh = cached and ("raw" in cached or cached.get("negative")) and 0 <= now - cached["fetched_at"] < ttl
        record = cached
        failure = None
        details = {}
        if fresh:
            if cached.get("negative"):
                negative_hits += 1
                errors.append(dict(character=entry.get("name") or entry.get("character_id"), realm=entry["realm"], error=cached["error"],
                                   error_code=cached.get("error_code",wcl.legacy_error_code(cached["error"])), retry_at=cached["fetched_at"]+6*3600))
                continue
            hits += 1
        if not fresh and not offline:
            if auth_failure:
                failure = auth_failure
                details = auth_details
            elif cached and now < cached.get("retry_until", 0):
                failure = cached.get("refresh_error", "Profile refresh is cooling down")
                details = dict(error_code=cached.get("error_code",wcl.legacy_error_code(failure)), retry_at=cached["retry_until"])
            elif fetched >= max_fetch:
                failure = "Per-run request limit reached"
                details = dict(error_code="budget",retry_at=0)
            elif remaining is not None and remaining < 100:
                failure = "WCL hourly budget is low; retry after reset"
                details = dict(error_code="budget",retry_at=0)
            else:
                try:
                    args = arguments(entry)
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
                    details=wcl.error_info(exc,now)
                    status = getattr(exc, "status", None)
                    if status == 429 or "HTTP 429" in failure or isinstance(exc, wcl.APIError) or isinstance(exc, BudgetError) and exc.global_stop:
                        auth_failure = failure  # Stop this whole batch, rather than hammer upstream.
                        auth_details = details
                    # Back off for this key without discarding a previous good result.
                    pause = max(300, getattr(exc, "retry_after", 0))
                    record = dict(cached or {"fetched_at": 0}, retry_until=now + pause, refresh_error=failure, **details)
                    atomic_write(path, json.dumps(record, ensure_ascii=False))
                    if not token and not fetcher:
                        auth_failure = failure
        elif not fresh and offline:
            failure = "Offline: using cache without refresh"
        if failure:
            errors.append(dict(character=entry.get("name") or entry.get("character_id"), realm=entry["realm"], error=failure, **details))
        if not record or record.get("negative") or "raw" not in record:
            continue
        try:
            profile = wcl.normalize(record["raw"], arguments(entry))
            profile["updated"] = datetime.fromtimestamp(record["fetched_at"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if failure:
                profile["source"] = "WCL API: cached; refresh unavailable"
            profiles.append(profile)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(dict(character=entry.get("name") or entry.get("character_id"), realm=entry["realm"], error=str(exc), **wcl.error_info(exc,now)))
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
