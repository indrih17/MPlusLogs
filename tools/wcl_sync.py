"""Fetch public WCL profiles and export data-only MPL1 files. Python 3.10+, stdlib only."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import sys
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = "https://www.warcraftlogs.com"
PROFILE_CACHE_TTL_HOURS = 24


class APIError(ValueError):
    """Safe upstream error with machine-readable status and retry timing."""
    def __init__(self, message, status=None, retry_after=0, rate_limit=None, code=None):
        super().__init__(message)
        self.status, self.retry_after, self.rate_limit = status, retry_after, rate_limit
        self.code = code or ("budget" if status == 429 else "auth" if status == 401 else "network" if status is None or status >= 500 else "unknown")


class NoProfile(ValueError):
    """A valid response explicitly says there is no usable public profile."""
    def __init__(self, message, code="unknown"):
        super().__init__(message)
        self.code=code


class NoSeasonLogs(NoProfile):
    """A readable profile has no public M+ measurements for this season."""
    def __init__(self, message):
        super().__init__(message, "empty")


ERROR_CODES={"hidden","missing","empty","retry","budget","auth","schema","network","unknown"}


def legacy_error_code(message):
    """Migration only: caches written before error codes contain text alone."""
    text=message.lower()
    for phrase,code in (("rankings hidden","hidden"),("character not found","missing"),
                        ("публичные логи m+ не найдены","empty"),("no public logs","empty"),
                        ("profile refresh is cooling down","retry"),("http 429","budget")):
        if phrase in text: return code
    return "unknown"


class ProfileError(ValueError):
    def __init__(self, message, code="unknown", retry_at=0):
        super().__init__(message)
        self.code=code if isinstance(code,str) and code in ERROR_CODES else "unknown"
        self.retry_at=retry_at


def error_info(error, now=None):
    code=getattr(error,"code","unknown")
    if not isinstance(code,str) or code not in ERROR_CODES: code="unknown"
    retry=getattr(error,"retry_at",0)
    if not retry and getattr(error,"retry_after",0):
        retry=(time.time() if now is None else now)+error.retry_after
    if type(retry) not in (int,float) or not 0<=retry<=253402300799: retry=0
    return {"error_code":code,"retry_at":int(retry)}


def wire_error(message, details=None, limit=500):
    details=details or {}
    code=details.get("error_code","unknown")
    if not isinstance(code,str) or code not in ERROR_CODES: code="unknown"
    retry=details.get("retry_at",0)
    if type(retry) not in (int,float) or not 0<=retry<=253402300799: retry=0
    text=f"MPLERR1 {code} {int(retry)}:"+message
    return text.encode("utf-8")[:limit].decode("utf-8",errors="ignore")


def retry_seconds(value):
    try:
        return max(0, min(86400, float(value)))
    except (ValueError, TypeError):
        try:
            return max(0, min(86400, parsedate_to_datetime(value).timestamp() - time.time()))
        except (ValueError, TypeError, OverflowError):
            return 0
PRIMARY_ONLY_MARKER = "_mpl_primary_only"
PURE_DPS_NAMES = {"hunter", "rogue", "mage", "warlock"}
PURE_DPS_SPECS = {"BeastMastery", "Beast Mastery", "Marksmanship", "Survival", "Assassination", "Outlaw", "Subtlety", "Arcane", "Fire", "Frost", "Affliction", "Demonology", "Destruction"}
DAMAGE_SPECS = PURE_DPS_SPECS | {"Arms", "Fury", "Retribution", "Shadow", "Unholy", "Elemental", "Enhancement", "Windwalker", "Balance", "Feral", "Havoc", "Devourer", "Devastation", "Augmentation"}


def primary_only_request(args):
    if getattr(args,"metric","dps") == "hps" or getattr(args, "include_secondary", False) or getattr(args, "role", None) in {"TANK", "HEALER"}:
        return False
    if getattr(args, "spec", None) in HEALERS | TANKS:
        return False
    if getattr(args, "role", None) == "DAMAGER":
        return True
    if getattr(args, "spec", None) in DAMAGE_SPECS:
        return True
    name = getattr(args, "class_name", None)
    return isinstance(name, str) and name.casefold() in PURE_DPS_NAMES


def character_class_name(raw):
    """Resolve WCL's own class IDs through its response, never Blizzard IDs."""
    character = character_data(raw)
    class_id = character.get("classID")
    if type(class_id) is not int or not 0 < class_id <= 1000000:
        return None
    data = raw.get("data")
    game = data.get("gameData") if isinstance(data, dict) else None
    classes = game.get("classes") if isinstance(game, dict) else None
    if not isinstance(classes, list):
        return None
    names = {row["name"].strip().casefold() for row in classes
             if isinstance(row, dict) and type(row.get("id")) is int and row["id"] == class_id
             and isinstance(row.get("name"), str) and row["name"].strip()}
    return next(iter(names)) if len(names) == 1 else None


def primary_only_raw(raw):
    if not isinstance(raw, dict) or PRIMARY_ONLY_MARKER not in raw:
        return False
    if type(raw[PRIMARY_ONLY_MARKER]) is not int or raw[PRIMARY_ONLY_MARKER] != 1:
        raise ProfileError("Invalid primary-only WCL marker", "schema")
    character = character_data(raw)
    if type(character.get("classID")) is not int or not 0 < character["classID"] <= 1000000 or "healing" in character or "damage" not in character:
        raise ProfileError("Invalid primary-only WCL response", "schema")
    return True


def cache_satisfies(raw, args):
    return not primary_only_raw(raw) or primary_only_request(args)


QUERY = """query MPlusLogs($id:Int, $name:String, $slug:String, $region:String, $zone:Int!, $spec:String, $verifyRealm:Boolean! = false, $includeHealing:Boolean! = true) {
  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn currentRequest }
  gameData { classes { id name } }
  worldData @include(if:$verifyRealm) { server(slug:$slug, region:$region) { id } }
  characterData {
    character(id:$id, name:$name, serverSlug:$slug, serverRegion:$region) {
      id name classID level hidden server { id name slug region { slug } }
      damage: zoneRankings(zoneID:$zone, metric:points_and_damage, byBracket:true, specName:$spec)
      healing: zoneRankings(zoneID:$zone, metric:points_and_healing, byBracket:true, specName:$spec) @include(if:$includeHealing)
    }
  }
}"""


def request_json(url, body, headers):
    for key, value in headers.items():
        if isinstance(key, str) and key.casefold() == "authorization":
            # http.client includes rejected header values in ValueError text.
            # Validate before urllib can turn a damaged token into diagnostics.
            if not isinstance(value, str) or any(ord(char) < 32 or ord(char) > 126 for char in value):
                raise APIError("Invalid Warcraft Logs authorization; sign in again", code="auth")
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=45) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not echo request headers, credentials or arbitrary response bodies.
        status, retry = exc.code, retry_seconds(exc.headers.get("Retry-After"))
        if exc.fp is not None:
            exc.close()
        message = f"WCL HTTP {status}; check credentials, API permissions or rate limit"
        if retry:
            message += f"; retry after {int(retry)} seconds"
        raise APIError(message, status, retry) from None
    except (URLError, OSError, HTTPException):
        raise APIError("Could not connect to Warcraft Logs") from None
    except (json.JSONDecodeError, UnicodeError):
        raise APIError("Invalid JSON response from Warcraft Logs; retry later", code="schema") from None
    except ValueError:
        raise APIError("Invalid request to Warcraft Logs; sign in again", code="auth") from None


def access_token(client_id=None, secret=None):
    client_id = client_id or os.environ.get("WCL_CLIENT_ID")
    secret = secret or os.environ.get("WCL_CLIENT_SECRET")
    if not client_id or not secret:
        raise ValueError("Set WCL_CLIENT_ID and WCL_CLIENT_SECRET locally; do not paste secrets into chat")
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    token = request_json(ROOT + "/oauth/token", urlencode({"grant_type": "client_credentials"}).encode(),
                         {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
    if not isinstance(token, dict) or not isinstance(token.get("access_token"), str) or not token["access_token"]:
        raise APIError("WCL did not return an access token", code="schema")
    return token["access_token"]


def fetch(args, token=None, endpoint="client"):
    if endpoint not in {"client", "user"}:
        raise ValueError("Unsupported WCL endpoint")
    token = token or access_token()
    variables = {"id": args.character_id, "name": args.name, "slug": args.server_slug,
                 "region": args.region, "zone": args.zone, "spec": args.spec,
                 "verifyRealm": bool(getattr(args,'verify_realm',False)),
                 "includeHealing": not primary_only_request(args)}
    data = request_json(ROOT + "/api/v2/" + endpoint, json.dumps({"query": QUERY, "variables": variables}).encode(),
                        {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    if not isinstance(data, dict):
        raise APIError("Invalid WCL response",code="schema")
    if data.get("errors"):
        raise APIError("WCL GraphQL error; inspect API schema/query. No export written",
                       rate_limit=rate_limit_data(data),code="schema")
    if not variables["includeHealing"]:
        try:
            character = character_data(data)
            if type(character.get("classID")) is not int or not 0 < character["classID"] <= 1000000:
                raise ProfileError("Unknown class; refresh with both WCL metrics", "schema")
            if (getattr(args,"role",None)!="DAMAGER" and getattr(args,"spec",None) not in DAMAGE_SPECS
                    and character_class_name(data) not in PURE_DPS_NAMES):
                raise ProfileError("Class changed; refresh with both WCL metrics", "schema")
            if "healing" in character or "damage" not in character:
                raise APIError("Invalid primary-only WCL response", code="schema")
            data[PRIMARY_ONLY_MARKER] = 1
            try:
                normalize(data, args)
            except NoSeasonLogs:
                raise ProfileError("No primary measurements; refresh with both WCL metrics", "retry") from None
        except (ValueError, KeyError, TypeError) as exc:
            exc.rate_limit = rate_limit_data(data)
            raise
    return data


def rate_limit_data(raw):
    data = raw.get("data") if isinstance(raw, dict) else None
    return data.get("rateLimitData") if isinstance(data, dict) else None


def numeric(value, maximum=1e12, integer=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ProfileError("Unexpected numeric field in WCL JSON","schema")
    if not math.isfinite(value) or value < 0 or value > maximum or (integer and value % 1):
        raise ProfileError("Numeric field outside supported range","schema")
    return int(value) if integer else value


def rankings(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict) or not isinstance(value.get("rankings"), list):
        raise ProfileError("Unknown zoneRankings JSON shape; preserve raw JSON and update the adapter","schema")
    if any(not isinstance(row, dict) or (row.get("encounter") is not None
           and not isinstance(row["encounter"], dict)) for row in value["rankings"]):
        raise ProfileError("Unknown zoneRankings row shape; expected an object","schema")
    return value


def throughput_rankings(value, label):
    """Normalize WCL maps; missing measurements may be null or an empty array."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            raise ProfileError(f"Unknown {label} throughputRankings shape; expected a JSON object","schema") from None
    if value is None or (isinstance(value, list) and not value):
        return {}
    if not isinstance(value, dict):
        raise ProfileError(f"Unknown {label} throughputRankings shape; expected an object","schema")
    return value


HEALERS={"Holy","Discipline","Restoration","Mistweaver","Preservation"}
TANKS={"Blood","Protection","Guardian","Brewmaster","Vengeance"}

def logged_specs(raw):
    """Include logged alternatives absent from the best dungeon ranking rows."""
    character=raw['data']['characterData']['character']
    found=set()
    for key in ('damage','healing','performance'):
        if character.get(key) is None: continue
        data=rankings(character[key])
        stars=data.get('allStars')
        for row in (stars if isinstance(stars,list) else [])+data['rankings']:
            if not isinstance(row,dict): continue
            for field in ('spec','bestSpec'):
                spec=row.get(field)
                if isinstance(spec,str) and spec and spec!='All specs': found.add(spec)
    return sorted(found)

def character_data(raw):
    data = raw.get("data") if isinstance(raw, dict) else None
    characters = data.get("characterData") if isinstance(data, dict) else None
    if not isinstance(characters, dict) or "character" not in characters or raw.get("errors"):
        raise ProfileError("Invalid WCL character response; no profile cached","schema")
    character = characters["character"]
    if character is not None and not isinstance(character, dict):
        raise ProfileError("Invalid WCL character response; no profile cached","schema")
    if not character:
        raise NoProfile("Character not found; absence is not a zero parse", "missing")
    if character.get("hidden"):
        raise NoProfile("Rankings hidden: Warcraft Logs denied access to this character's logs", "hidden")
    return character


def validate_identity(raw, args):
    """A historical WCL lookup must not label a renamed/transfer target as the request."""
    character = character_data(raw)
    folded = lambda value: unicodedata.normalize("NFC", value).casefold()
    name = getattr(args, "name", None)
    if name and (not isinstance(character.get("name"), str) or folded(character["name"]) != folded(name)):
        raise ProfileError("Character name changed; request the current character identity", "missing")
    server = character.get("server")
    region = server.get("region") if isinstance(server, dict) else None
    actual_region = region.get("slug") if isinstance(region, dict) else None
    if not isinstance(actual_region, str) or folded(actual_region) != folded(args.region):
        raise ProfileError("Character region changed; request the current character identity", "missing")
    requested_slug = getattr(args, "server_slug", None)
    if not requested_slug:
        return  # ID-only rosters do not request a server alias.
    data = raw["data"]
    if "worldData" in data:
        world = data["worldData"]
        requested = world.get("server") if isinstance(world, dict) else None
        requested_id = requested.get("id") if isinstance(requested, dict) else None
        actual_id = server.get("id")
        if type(requested_id) is not int or requested_id <= 0 or type(actual_id) is not int or actual_id <= 0:
            raise ProfileError("Invalid WCL server identity response", "schema")
        same_realm = requested_id == actual_id
    else:
        actual_slug = server.get("slug")
        same_realm = isinstance(actual_slug, str) and folded(actual_slug) == folded(requested_slug)
        if not same_realm and isinstance(actual_slug, str):
            # Legacy caches may use localized realm names instead of canonical
            # WCL slugs. Accept only aliases backed by the bundled realm table.
            import realm_resolver
            mapping = realm_resolver.load_mappings()
            for alias in (requested_slug, getattr(args, "realm", None)):
                if not isinstance(alias, str):
                    continue
                try:
                    same_realm = folded(realm_resolver.resolve(mapping, args.region, alias)) == folded(actual_slug)
                except ValueError:
                    continue
                if same_realm:
                    break
    if not same_realm:
        raise ProfileError("Character realm changed; request the current character identity", "missing")


def score_run(row):
    """WCL's score columns describe bestRank, independently of throughput logs."""
    best = row.get("bestRank")
    if not isinstance(best, dict):
        return None, ""
    level = numeric(best.get("ilvl"), 100, True)
    speed = best.get("speed")
    # Leaderboard speed packs key level and elapsed milliseconds together.
    # Decode the score run, not fastestKill (which can be another run).
    if level is None or type(speed) not in (int, float) or not math.isfinite(speed):
        return level, ""
    duration = level * 40000000 + speed if speed < 0 else speed
    if not 0 < duration < 24 * 3600 * 1000:
        return level, ""
    seconds = int(duration / 1000)
    return level, f"{seconds // 60}:{seconds % 60:02d}"


def normalize(raw, args):
    character = character_data(raw)
    validate_identity(raw, args)
    partial = primary_only_raw(raw)
    if ("damage" in character) != ("healing" in character) and not partial:
        raise ProfileError("Incomplete WCL metric response", "schema")
    dual="damage" in character and "healing" in character
    damage=rankings(character["damage"]) if dual or partial else None
    healing=rankings(character["healing"]) if dual else None
    if dual and not damage['rankings'] and not healing['rankings']:
        raise NoSeasonLogs("Публичные логи M+ не найдены")
    role=getattr(args,"role",None)
    if role not in {"HEALER","TANK","DAMAGER"}:
        specs={}
        for row in (damage or rankings(character.get("performance")))["rankings"]:
            spec=row.get("bestSpec") or row.get("spec")
            if spec: specs[spec]=specs.get(spec,0)+(numeric(row.get("totalKills")) or 0)
        spec=args.spec or (max(specs,key=specs.get) if specs else None)
        role="DAMAGER" if partial or character_class_name(raw) in PURE_DPS_NAMES else "HEALER" if spec in HEALERS or args.metric=="hps" else "TANK" if spec in TANKS else "DAMAGER"
    metric="hps" if role=="HEALER" else "dps"
    if partial and role != "DAMAGER":
        raise ProfileError("Secondary metric requires a full WCL profile", "schema")
    performance=(healing if metric=="hps" else damage) if dual or partial else rankings(character.get("performance"))
    spec_counts={}
    for row in performance["rankings"]:
        logged_spec=row.get("bestSpec") or row.get("spec")
        if isinstance(logged_spec,str) and logged_spec:
            spec_counts[logged_spec]=spec_counts.get(logged_spec,0)+(numeric(row.get("totalKills")) or 0)
    primary_spec=args.spec or (min(spec_counts,key=lambda spec:(-spec_counts[spec],spec)) if spec_counts else None)
    secondary=(damage if metric=="hps" else healing) if dual else None
    other=throughput_rankings(secondary.get("throughputRankings") if secondary else None,"secondary")
    throughput = throughput_rankings(performance.get("throughputRankings"),"primary")
    if "throughputRankings" not in performance:
        raise ValueError("M+ throughputRankings missing; refresh using points_and_damage/points_and_healing")
    if not throughput and not other:
        # zoneRankings also contains leaderboard scores from runs with no
        # uploaded combat log. Those scores cannot supply DPS/HPS measurements.
        raise NoSeasonLogs("Публичные логи M+ не найдены")
    server = character.get("server") or {}
    if not isinstance(server, dict) or not isinstance(server.get("region") or {}, dict):
        raise ValueError("Invalid WCL server response")
    region = (server.get("region") or {}).get("slug", args.region)
    if not isinstance(region, str):
        raise ValueError("Invalid WCL region response")
    region = region.lower()
    if region not in {"eu", "us", "kr", "tw", "cn"}:
        raise ValueError("Unknown region")
    dungeons = []
    for r in performance["rankings"]:
        encounter = r.get("encounter") or {}
        if not encounter.get("name"):
            raise ValueError("Encounter name missing; unknown WCL JSON shape")
        t = throughput.get(str(encounter.get("id")), {})
        if not isinstance(t,dict): raise ValueError("Unknown M+ throughput row shape")
        level, elapsed = score_run(r)
        if level is None:
            level = numeric(t.get("best_level"),100,True)
        second=other.get(str(encounter.get("id")),{})
        if not isinstance(second,dict): raise ValueError("Unknown secondary M+ throughput row")
        score_spec = r.get("bestSpec") or args.spec
        if not isinstance(score_spec, str) or not 0 < len(score_spec) <= 80:
            score_spec = None
        dungeon_stars = r.get("allStars")
        dungeon_rank = numeric(dungeon_stars.get("rank"),100000000,True) if isinstance(dungeon_stars,dict) else None
        dungeons.append({"name": encounter["name"], "level": level, "time": elapsed, "scoreSpec": score_spec,
                         "runs": numeric(r.get("totalKills"), 10000000, True),
                         "amount": numeric(t.get("best_per_second_amount")),
                         "best": numeric(t.get("best_historical_percentile"), 100),
                         "median": numeric(t.get("median_historical_percentile"), 100),
                         "points": numeric(r.get("bestAmount")), "rank": dungeon_rank,
                         "otherLevel":numeric(second.get("best_level"),100,True),
                         "otherAmount":numeric(second.get("best_per_second_amount")),
                         "otherBest":numeric(second.get("best_historical_percentile"),100),
                         "otherMedian":numeric(second.get("median_historical_percentile"),100)})
    stars = performance.get("allStars", [])
    ranks_by_spec = {}
    for star in stars if isinstance(stars, list) else []:
        if not isinstance(star, dict): continue
        spec, rank = star.get("spec"), numeric(star.get("rank"), 100000000, True)
        if isinstance(spec, str) and 0 < len(spec) <= 80 and rank and rank > 0:
            if spec not in ranks_by_spec:
                ranks_by_spec[spec] = rank
            elif ranks_by_spec[spec] != rank:
                # WCL can return conflicting allStars rows for the same spec.
                # Omit the ambiguous rank, rather than inventing a best position
                # or making otherwise usable dungeon logs fail import.
                ranks_by_spec[spec] = None
    spec_ranks = [{"spec": spec, "rank": rank} for spec, rank in ranks_by_spec.items() if rank is not None]
    points = numeric(stars[0].get("points")) if isinstance(stars, list) and len(stars) == 1 and isinstance(stars[0], dict) else None
    if isinstance(stars,list) and len(stars)>1 and dungeons and all(d["points"] is not None for d in dungeons):
        # All-specs score combines the best result in each dungeon. Spec totals
        # overlap; neither adding those totals nor choosing one spec is correct.
        points = math.fsum(d["points"] for d in dungeons)
    runs = sum(d["runs"] for d in dungeons) if dungeons and all(d["runs"] is not None for d in dungeons) else None
    return {"region": region, "realm": args.realm, "name": character["name"], "zone": args.zone,
            "season": args.season, "spec": args.spec or "All specs", "primarySpec":primary_spec, "metric": metric,"role":role,"dual":dual or partial,
            "secondaryPending":partial,
            "otherBest":numeric(secondary.get("bestPerformanceAverage"),100) if secondary else None,
            "otherMedian":numeric(secondary.get("medianPerformanceAverage"),100) if secondary else None,
            "score": points, "best": numeric(performance.get("bestPerformanceAverage"), 100),
            "median": numeric(performance.get("medianPerformanceAverage"), 100), "runs": runs,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "source": "WCL API: M+ по уровню ключа", "characterID": numeric(character.get("id"), 1000000000, True),
            "realmSlug": server.get("slug", args.server_slug or ""), "dungeons": dungeons, "specRanks": spec_ranks,
            "availableSpecs": logged_specs(raw)}


def line(*values):
    return "\t".join(quote("" if v is None else str(v), safe="-._~") for v in values)


def export(profile, spec_details=True, available_specs=False):
    p = profile
    rows = ["MPL1", line("P", *(p.get(k) for k in ("region", "realm", "name", "zone", "season", "spec", "metric",
                                                  "score", "best", "median", "runs", "updated", "source", "characterID", "realmSlug")))]
    if p.get("dual"):
        rows[1]+= "\t"+"\t".join(quote("" if p.get(k) is None else str(p[k]),safe="-._~") for k in ("role","otherBest","otherMedian"))
    if p.get("primarySpec"):
        rows[1]+="\t"+quote(p["primarySpec"],safe="-._~")
    if p.get("secondaryPending"):
        rows.append(line("M", "dps"))
    if available_specs:
        for spec in p.get("availableSpecs", []):
            rows.append(line("A", spec))
    if spec_details:
        for entry in p.get("specRanks", []):
            rows.append(line("R", entry["spec"], entry["rank"]))
    for d in p["dungeons"]:
        keys=("name", "level", "time", "runs", "amount", "best", "median", "points", "rank")
        if p.get("dual"): keys+=("otherLevel","otherAmount","otherBest","otherMedian")
        if spec_details and d.get("scoreSpec"): keys+=("scoreSpec",)
        rows.append(line("D", *(d.get(k) for k in keys)))
    rows.append("E")
    return "\n".join(rows) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character-id", type=int)
    parser.add_argument("--name")
    parser.add_argument("--server-slug")
    parser.add_argument("--region", default="eu", choices=["eu", "us", "kr", "tw", "cn"])
    parser.add_argument("--realm", required=True, help="Realm name exactly as displayed in WoW (e.g. Гордунни)")
    parser.add_argument("--zone", type=int, default=55)
    parser.add_argument("--season", default="Midnight M+ Season 2")
    parser.add_argument("--spec", help="WCL spec slug, e.g. Guardian; omitted = all specs")
    parser.add_argument("--metric", default="dps", choices=["dps", "hps"])
    parser.add_argument("--role",choices=["HEALER","TANK","DAMAGER"],help="Current group role; otherwise inferred from logged specs")
    parser.add_argument("--raw-input", type=Path, help="Convert a previously saved GraphQL response without network")
    parser.add_argument("--output", type=Path, default=Path("profile.mpl"))
    parser.add_argument("--raw-output", type=Path, default=Path("profile.wcl.json"))
    args = parser.parse_args()
    if args.zone != 55:
        parser.error("This addon version supports zone 55; update Data.lua for a new season")
    if not args.raw_input and not args.character_id and not (args.name and args.server_slug):
        parser.error("Use --character-id or --name and --server-slug")
    try:
        if args.raw_input:
            raw = json.loads(args.raw_input.read_text(encoding="utf-8-sig"))
        else:
            raw = fetch(args)
            args.raw_output.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        profile = normalize(raw, args)
        args.output.write_text(export(profile), encoding="utf-8")
        print(f"Exported {profile['name']}-{profile['realm']}: {len(profile['dungeons'])} dungeons -> {args.output}")
        print("Paste this .mpl into /mpl import in WoW. Missing API fields appear as a dash.")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
