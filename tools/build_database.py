"""Build a shareable M+ addon database from a roster/seen-player queue and WCL API."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
from urllib.parse import unquote

import wcl_sync as wcl
import realm_resolver

ROOT = Path(__file__).resolve().parents[1]


def identity(region, realm, name):
    def normalized(text):
        return re.sub(r"[\s\-']", "", text.casefold())
    return region.lower(), normalized(realm), normalized(name)


def load_entries(manifest=None, requests=None, realms=None):
    entries = []
    if manifest:
        entries = json.loads(manifest.read_text(encoding="utf-8-sig"))
        if not isinstance(entries, list):
            raise ValueError("Roster must be a JSON array")
    if requests:
        text = requests.read_text(encoding="utf-8-sig")
        mapping = realm_resolver.load_mappings(realms)
        seen = {identity(e.get("region", "eu"), e.get("realm", ""), e["name"]) for e in entries if e.get("name")}
        for request in realm_resolver.parse_queue(text,mapping):
            key = identity(request["region"], request["realm"], request["name"])
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
        key = identity(entry.get("region", "eu"), entry["realm"], entry.get("name") or str(entry["character_id"]))
        if key in seen:
            raise ValueError("One spec/metric per character is currently supported; remove duplicate roster entries")
        seen.add(key)
    return entries


def arguments(entry):
    return SimpleNamespace(character_id=entry.get("character_id"), name=entry.get("name"),
                           realm=entry["realm"], server_slug=entry.get("server_slug"),
                           region=entry.get("region", "eu"), zone=55, season="Midnight M+ Season 2",
                           spec=entry.get("spec"), metric=entry.get("metric", "dps"),role=entry.get("role"))


def cache_path(directory, entry):
    # Query filters belong to the cache key. A Guardian cache cannot satisfy a healer request.
    encoded = json.dumps({**vars(arguments(entry)),"query_version":"mplus-dual-v2"}, sort_keys=True, ensure_ascii=True).encode()
    return directory / (hashlib.sha256(encoded).hexdigest() + ".json")


def lua_string(text):
    # Lua 5.1 has no JSON-style Unicode escapes. Quote UTF-8 byte by byte,
    # including quotes, backslashes and controls; imported data cannot inject Lua.
    return '"' + "".join(chr(b) if 32 <= b < 127 and b not in (34, 92) else f"\\{b:03d}"
                         for b in text.encode("utf-8")) + '"'


def bundle(profiles):
    keys = [identity(p["region"], p["realm"], p["name"]) for p in profiles]
    if len(set(keys)) != len(keys):
        raise ValueError("Different roster entries resolved to the same character; database not replaced")
    text = "MPL1\n" + "".join(wcl.export(p).removeprefix("MPL1\n") for p in profiles)
    if len(text.encode()) > 500000:
        raise ValueError("Database exceeds current 500 KB limit; split datasets or extend addon storage")
    return "local _, MPL = ...\n-- Generated public WCL data. Contains no credentials.\nMPL.bundledText = " + lua_string(text) + "\n"


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def build(entries, cache_dir, ttl_hours=24, max_fetch=20, offline=False, fetcher=None, now=None):
    now = time.time() if now is None else now
    cache_dir.mkdir(parents=True, exist_ok=True)
    profiles, errors, fetched = [], [], 0
    token = None
    auth_failure = None
    remaining = None
    for entry in entries:
        path = cache_path(cache_dir, entry)
        cached = None
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(cached.get("fetched_at"), (float, int)):
                    cached = None
            except (ValueError, OSError, AttributeError):
                cached = None
        fresh = cached and 0 <= now - cached["fetched_at"] < ttl_hours * 3600
        record = cached
        failure = None
        if not fresh and not offline:
            if auth_failure:
                failure = auth_failure
            elif fetched >= max_fetch:
                failure = "Per-run request limit reached"
            elif remaining is not None and remaining < 100:
                failure = "WCL hourly budget is low; retry after reset"
            else:
                try:
                    args = arguments(entry)
                    fetched += 1
                    if fetcher:
                        raw = fetcher(args)
                    else:
                        token = token or wcl.access_token()
                        raw = wcl.fetch(args, token)
                    wcl.normalize(raw, args)  # Validate before replacing a good cache.
                    record = {"fetched_at": now, "raw": raw}
                    atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2))
                    limit = raw.get("data", {}).get("rateLimitData")
                    if limit:
                        remaining = limit["limitPerHour"] - limit["pointsSpentThisHour"]
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    failure = str(exc)
                    if not token and not fetcher:
                        auth_failure = failure
        elif not fresh and offline:
            failure = "Offline: using cache without refresh"
        if failure:
            errors.append({"character": entry.get("name") or entry.get("character_id"), "realm": entry["realm"], "error": failure})
        if not record:
            continue
        try:
            profile = wcl.normalize(record["raw"], arguments(entry))
            profile["updated"] = datetime.fromtimestamp(record["fetched_at"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if failure:
                profile["source"] = "WCL API: cached; refresh unavailable"
            profiles.append(profile)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"character": entry.get("name") or entry.get("character_id"), "realm": entry["realm"], "error": str(exc)})
    return profiles, {"profiles": len(profiles), "fetched": fetched, "remainingApiPoints": remaining, "errors": errors}


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
