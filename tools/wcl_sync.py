"""Fetch public WCL profiles and export data-only MPL1 files. Python 3.10+, stdlib only."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = "https://www.warcraftlogs.com"


class APIError(ValueError):
    """Safe upstream error with machine-readable status and retry timing."""
    def __init__(self, message, status=None, retry_after=0, rate_limit=None):
        super().__init__(message)
        self.status, self.retry_after, self.rate_limit = status, retry_after, rate_limit


class NoProfile(ValueError):
    """A valid response explicitly says there is no usable public profile."""


def retry_seconds(value):
    try:
        return max(0, min(86400, float(value)))
    except (ValueError, TypeError):
        try:
            return max(0, min(86400, parsedate_to_datetime(value).timestamp() - time.time()))
        except (ValueError, TypeError, OverflowError):
            return 0
QUERY = """query MPlusLogs($id:Int, $name:String, $slug:String, $region:String, $zone:Int!, $spec:String) {
  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }
  characterData {
    character(id:$id, name:$name, serverSlug:$slug, serverRegion:$region) {
      id name hidden server { name slug region { slug } }
      damage: zoneRankings(zoneID:$zone, metric:points_and_damage, byBracket:true, specName:$spec)
      healing: zoneRankings(zoneID:$zone, metric:points_and_healing, byBracket:true, specName:$spec)
    }
  }
}"""


def request_json(url, body, headers):
    req = Request(url, data=body, headers=headers, method="POST")
    try:
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
    except URLError:
        raise APIError("Could not connect to Warcraft Logs") from None


def access_token(client_id=None, secret=None):
    client_id = client_id or os.environ.get("WCL_CLIENT_ID")
    secret = secret or os.environ.get("WCL_CLIENT_SECRET")
    if not client_id or not secret:
        raise ValueError("Set WCL_CLIENT_ID and WCL_CLIENT_SECRET locally; do not paste secrets into chat")
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    token = request_json(ROOT + "/oauth/token", urlencode({"grant_type": "client_credentials"}).encode(),
                         {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
    if not token.get("access_token"):
        raise ValueError("WCL did not return an access token")
    return token["access_token"]


def fetch(args, token=None, endpoint="client"):
    if endpoint not in {"client", "user"}:
        raise ValueError("Unsupported WCL endpoint")
    token = token or access_token()
    variables = {"id": args.character_id, "name": args.name, "slug": args.server_slug,
                 "region": args.region, "zone": args.zone, "spec": args.spec}
    data = request_json(ROOT + "/api/v2/" + endpoint, json.dumps({"query": QUERY, "variables": variables}).encode(),
                        {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    if not isinstance(data, dict):
        raise APIError("Invalid WCL response")
    if data.get("errors"):
        raise APIError("WCL GraphQL error; inspect API schema/query. No export written",
                       rate_limit=(data.get("data") or {}).get("rateLimitData"))
    return data


def numeric(value, maximum=1e12, integer=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("Unexpected numeric field in WCL JSON")
    if not math.isfinite(value) or value < 0 or value > maximum or (integer and value % 1):
        raise ValueError("Numeric field outside supported range")
    return int(value) if integer else value


def rankings(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict) or not isinstance(value.get("rankings"), list):
        raise ValueError("Unknown zoneRankings JSON shape; preserve raw JSON and update the adapter")
    return value


def throughput_rankings(value, label):
    """Normalize WCL maps; missing measurements may be null or an empty array."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            raise ValueError(f"Unknown {label} throughputRankings shape; expected a JSON object") from None
    if value is None or (isinstance(value, list) and not value):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Unknown {label} throughputRankings shape; expected an object")
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
        for row in data.get('allStars',[])+data['rankings']:
            for field in ('spec','bestSpec'):
                spec=row.get(field)
                if isinstance(spec,str) and spec and spec!='All specs': found.add(spec)
    return sorted(found)

def normalize(raw, args):
    data = raw.get("data") if isinstance(raw, dict) else None
    characters = data.get("characterData") if isinstance(data, dict) else None
    if not isinstance(characters, dict) or "character" not in characters or raw.get("errors"):
        raise ValueError("Invalid WCL character response; no profile cached")
    character = characters["character"]
    if character is not None and not isinstance(character, dict):
        raise ValueError("Invalid WCL character response; no profile cached")
    if not character:
        raise NoProfile("Character not found; absence is not a zero parse")
    if character.get("hidden"):
        raise NoProfile("Rankings hidden: Warcraft Logs denied access to this character's logs")
    dual="damage" in character and "healing" in character
    damage=rankings(character["damage"]) if dual else None
    healing=rankings(character["healing"]) if dual else None
    if dual and not damage['rankings'] and not healing['rankings']:
        raise NoProfile("Публичные логи M+ не найдены")
    role=getattr(args,"role",None)
    if role not in {"HEALER","TANK","DAMAGER"}:
        specs={}
        for row in (damage or rankings(character.get("performance")))["rankings"]:
            spec=row.get("bestSpec") or row.get("spec")
            if spec: specs[spec]=specs.get(spec,0)+(numeric(row.get("totalKills")) or 0)
        spec=args.spec or (max(specs,key=specs.get) if specs else None)
        role="HEALER" if spec in HEALERS or args.metric=="hps" else "TANK" if spec in TANKS else "DAMAGER"
    metric="hps" if role=="HEALER" else "dps"
    performance=(healing if metric=="hps" else damage) if dual else rankings(character.get("performance"))
    logged_specs={}
    for row in performance["rankings"]:
        logged_spec=row.get("bestSpec") or row.get("spec")
        if isinstance(logged_spec,str) and logged_spec:
            logged_specs[logged_spec]=logged_specs.get(logged_spec,0)+(numeric(row.get("totalKills")) or 0)
    primary_spec=args.spec or (min(logged_specs,key=lambda spec:(-logged_specs[spec],spec)) if logged_specs else None)
    secondary=(damage if metric=="hps" else healing) if dual else None
    other=throughput_rankings(secondary.get("throughputRankings") if secondary else None,"secondary")
    throughput = throughput_rankings(performance.get("throughputRankings"),"primary")
    if "throughputRankings" not in performance:
        raise ValueError("M+ throughputRankings missing; refresh using points_and_damage/points_and_healing")
    if not throughput and not other:
        # zoneRankings also contains leaderboard scores from runs with no
        # uploaded combat log. Those scores cannot supply DPS/HPS measurements.
        raise NoProfile("Публичные логи M+ не найдены")
    server = character.get("server") or {}
    region = (server.get("region") or {}).get("slug", args.region).lower()
    if region not in {"eu", "us", "kr", "tw", "cn"}:
        raise ValueError("Unknown region")
    dungeons = []
    for r in performance["rankings"]:
        encounter = r.get("encounter") or {}
        if not encounter.get("name"):
            raise ValueError("Encounter name missing; unknown WCL JSON shape")
        t = throughput.get(str(encounter.get("id")), {})
        if not isinstance(t,dict): raise ValueError("Unknown M+ throughput row shape")
        level = numeric(t.get("best_level"),100,True)
        second=other.get(str(encounter.get("id")),{})
        if not isinstance(second,dict): raise ValueError("Unknown secondary M+ throughput row")
        score_spec = r.get("bestSpec") or args.spec
        if not isinstance(score_spec, str) or not 0 < len(score_spec) <= 80:
            score_spec = None
        dungeons.append({"name": encounter["name"], "level": level, "time": "", "scoreSpec": score_spec,
                         "runs": numeric(r.get("totalKills"), 10000000, True),
                         "amount": numeric(t.get("best_per_second_amount")),
                         "best": numeric(t.get("best_historical_percentile"), 100),
                         "median": numeric(t.get("median_historical_percentile"), 100),
                         "points": numeric(r.get("bestAmount")), "rank": None,
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
    points = numeric(stars[0].get("points")) if isinstance(stars, list) and len(stars) == 1 else None
    runs = sum(d["runs"] for d in dungeons) if dungeons and all(d["runs"] is not None for d in dungeons) else None
    return {"region": region, "realm": args.realm, "name": character["name"], "zone": args.zone,
            "season": args.season, "spec": args.spec or "All specs", "primarySpec":primary_spec, "metric": metric,"role":role,"dual":dual,
            "otherBest":numeric(secondary.get("bestPerformanceAverage"),100) if secondary else None,
            "otherMedian":numeric(secondary.get("medianPerformanceAverage"),100) if secondary else None,
            "score": points, "best": numeric(performance.get("bestPerformanceAverage"), 100),
            "median": numeric(performance.get("medianPerformanceAverage"), 100), "runs": runs,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "source": "WCL API: M+ по уровню ключа", "characterID": numeric(character.get("id"), 1000000000, True),
            "realmSlug": server.get("slug", args.server_slug or ""), "dungeons": dungeons, "specRanks": spec_ranks}


def line(*values):
    return "\t".join(quote("" if v is None else str(v), safe="-._~") for v in values)


def export(profile, spec_details=True):
    p = profile
    rows = ["MPL1", line("P", *(p.get(k) for k in ("region", "realm", "name", "zone", "season", "spec", "metric",
                                                  "score", "best", "median", "runs", "updated", "source", "characterID", "realmSlug")))]
    if p.get("dual"):
        rows[1]+= "\t"+"\t".join(quote("" if p.get(k) is None else str(p[k]),safe="-._~") for k in ("role","otherBest","otherMedian"))
    if p.get("primarySpec"):
        rows[1]+="\t"+quote(p["primarySpec"],safe="-._~")
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
