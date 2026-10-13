"""Local-only Mythic+ utility history. Stdlib, incremental reads, no HTTP or Lua execution."""
from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading

SCHEMA = 1
REGIONS = {"eu", "us", "kr", "tw", "cn"}
COUNTERS = {"SPELL_INTERRUPT": "interrupts", "SPELL_DISPEL": "dispels", "SPELL_STOLEN": "dispels"}
NAME_EVENTS = {"SPELL_CAST_SUCCESS", "SPELL_DAMAGE", "SPELL_HEAL", "SWING_DAMAGE", "UNIT_DIED", "SPELL_SUMMON", *COUNTERS}
TANKS = {250, 581, 104, 268, 66, 73}
HEALERS = {105, 1468, 270, 65, 256, 257, 264}
STAMP = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))? (\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?$" )


def timestamp(value, year):
    match = STAMP.fullmatch(value)
    if not match:
        raise ValueError("Unsupported combat-log timestamp")
    month, day, explicit_year, hour, minute, second, fraction = match.groups()
    result = datetime(int(explicit_year or year), int(month), int(day), int(hour), int(minute),
                      int(second), int(((fraction or "") + "000000")[:6]))
    return result.isoformat(timespec="microseconds"), explicit_year is None


def identity(full_name):
    """Modern logs append a region after the localized realm: Name-Realm-EU."""
    if not full_name or full_name == "nil":
        return "", "", None
    region = None
    suffix = full_name.rsplit("-", 1)
    if len(suffix) == 2 and suffix[1].lower() in REGIONS:
        full_name, region = suffix[0], suffix[1].lower()
    name, _, realm = full_name.partition("-")
    return name, realm, region


def normalized(value):
    return re.sub(r"[\s\-']", "", value.casefold())


def actor(guid, spec=0):
    return {"guid": guid, "name": "", "realm": "", "spec_id": spec,
            "role": "TANK" if spec in TANKS else "HEALER" if spec in HEALERS else "DAMAGER" if spec else "",
            "interrupts": 0, "deaths": 0, "dispels": 0}


class Parser:
    """Serializable checkpoint state; incomplete snapshots can later become complete."""
    def __init__(self, source, region="eu", year=None, state=None):
        self.source, self.region = str(source), region
        self.year = year or datetime.now().year
        self.pending = None
        self.pets = {}
        self.line = 0
        if state:
            self.year, self.pending, self.pets, self.line = (state[k] for k in ("year", "pending", "pets", "line"))

    def state(self):
        return {"year": self.year, "pending": self.pending, "pets": self.pets, "line": self.line}

    def owner(self, guid):
        visited = set()
        while guid in self.pets and guid not in visited:
            visited.add(guid); guid = self.pets[guid]
        return guid

    def learn(self, guid, full_name, flags):
        if not self.pending or not guid.startswith("Player-"):
            return
        try:
            affiliated = bool(int(flags, 0) & 3)  # mine or party, never nearby players or pets
        except ValueError:
            affiliated = False
        party = self.pending["party"]
        if guid not in party and affiliated and len(party) < 5:
            party[guid] = actor(guid)
        if guid in party:
            name, realm, region = identity(full_name)
            if name:
                party[guid].update(name=name, realm=realm)
            if region:
                self.pending["regions"] = sorted(set(self.pending["regions"] + [region]))

    def snapshot(self, status="in_progress", ended=None, duration=None):
        if not self.pending:
            return None
        run = json.loads(json.dumps(self.pending))
        party = run.pop("party")
        regions = run.pop("regions")
        if regions:
            run["region"] = regions[0] if len(regions) == 1 else ""
        run["id"]=hashlib.sha256(f"{run['region']}|{run['started']}|{run['instance_id']}|{run['map_id']}|{run['level']}".encode()).hexdigest()
        run["status"], run["ended"], run["duration"] = status, ended or "", duration
        roster = set(run.pop("roster"))
        complete = (status == "completed" and len(party) == 5 and set(party) == roster
                    and all(p["name"] and p["realm"] for p in party.values())
                    and run["malformed"] == 0 and run["region"] in REGIONS)
        run["coverage"] = "complete" if complete else "partial"
        run["players"] = sorted(party.values(), key=lambda p: (p["role"], p["name"], p["guid"]))
        run["last_line"] = self.line
        run["sources"] = [{"path": self.source, "first_line": run["first_line"], "last_line": self.line}]
        run["parser_schema"]=SCHEMA
        return run

    def feed(self, line):
        self.line += 1
        parts = line.rstrip("\r\n").split("  ", 1)
        if len(parts) != 2:
            if self.pending and line.strip(): self.pending["malformed"] += 1
            return []
        clock, payload = parts
        event = payload.partition(",")[0]
        if event == "COMBAT_LOG_VERSION" and self.pending:
            # RaiderIO archives emit a format header immediately after the key starts.
            # A later restart (or one after utility events) indicates missing coverage.
            try:
                clock_value,_=timestamp(clock,self.year)
                elapsed=(datetime.fromisoformat(clock_value)-datetime.fromisoformat(self.pending["started"])).total_seconds()
                observed=any(p[k] for p in self.pending["party"].values() for k in ("interrupts","deaths","dispels"))
                if elapsed>5 or elapsed<0 or observed: self.pending["malformed"]+=1
            except ValueError: self.pending["malformed"]+=1
        if event not in NAME_EVENTS | {"CHALLENGE_MODE_START", "CHALLENGE_MODE_END", "COMBATANT_INFO"}:
            return []
        try:
            # COMBATANT_INFO arrays follow specId; only its scalar prefix is needed.
            fields = next(csv.reader([payload.split("[", 1)[0] if event == "COMBATANT_INFO" else payload], strict=True))
            if event == "CHALLENGE_MODE_START":
                started, inferred = timestamp(clock, self.year)
                if self.pending and inferred and started < self.pending["started"]:
                    self.year += 1; started, _ = timestamp(clock, self.year)
                old = self.snapshot("incomplete")
                instance, challenge, level = map(int, fields[2:5])
                if not fields[1] or not 0 < level <= 100 or instance <= 0 or challenge <= 0:
                    raise ValueError("Invalid challenge start")
                self.pending = {"id": hashlib.sha256(f"{self.region}|{started}|{instance}|{challenge}|{level}".encode()).hexdigest(),
                                "dungeon": fields[1], "instance_id": instance, "map_id": challenge, "level": level,
                                "started": started, "region": self.region, "year_inferred": inferred,
                                "party": {}, "roster": [], "regions": [], "malformed": 0, "first_line": self.line}
                return [old] if old else []
            if event == "CHALLENGE_MODE_END" and self.pending:
                ended, _ = timestamp(clock, self.year)
                if int(fields[1]) != self.pending["instance_id"] or int(fields[3]) != self.pending["level"]:
                    self.pending["malformed"] += 1; return []
                if ended < self.pending["started"] and self.pending["year_inferred"]:
                    self.year += 1; ended, _ = timestamp(clock, self.year)
                if ended < self.pending["started"]:
                    raise ValueError("Challenge ends before it starts")
                duration = int(fields[4]) / 1000
                if not 0 < duration <= 86400:
                    raise ValueError("Invalid challenge duration")
                run = self.snapshot("completed" if int(fields[2]) == 1 else "abandoned", ended, duration)
                self.pending = None
                return [run]
            if event == "COMBATANT_INFO" and self.pending:
                guid, spec = fields[1], int(fields[25])
                if not guid.startswith("Player-"):
                    return []
                if guid not in self.pending["roster"]:
                    self.pending["roster"].append(guid)
                if guid not in self.pending["party"] and len(self.pending["party"]) < 5:
                    self.pending["party"][guid] = actor(guid, spec)
                elif guid in self.pending["party"]:
                    self.pending["party"][guid].update(spec_id=spec, role=actor(guid,spec)["role"])
                return []
            if len(fields) < 9:
                raise ValueError("Truncated combat event")
            src, dst = fields[1], fields[5]
            self.learn(src, fields[2], fields[3]); self.learn(dst, fields[6], fields[7])
            if event == "SPELL_SUMMON" and dst.startswith(("Pet-", "Creature-")):
                self.pets[dst] = self.owner(src)
                if len(self.pets) > 2000: self.pets = {dst: self.owner(src)}
            if not self.pending:
                return []
            party = self.pending["party"]
            if event in COUNTERS:
                if len(fields) < 15:
                    raise ValueError("Truncated utility event")
                timestamp(clock,self.year)
                owner = self.owner(src)
                if owner in party: party[owner][COUNTERS[event]] += 1
                elif int(fields[3],0) & 3:
                    self.pending["malformed"] += 1  # An affiliated pet/player has no observed owner/roster entry.
            elif event == "UNIT_DIED" and dst in party:
                party[dst]["deaths"] += 1  # Do not resolve pet death to its owner.
        except (ValueError, IndexError, csv.Error):
            if self.pending: self.pending["malformed"] += 1
        return []


class History:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, started TEXT, region TEXT, data TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, checkpoint TEXT)")
            with db: yield db
        except sqlite3.Error as exc:
            raise ValueError("Could not read or save the local combat-history database") from exc
        finally:
            db.close()

    def save_run(self, db, run):
        if not run: return
        old = db.execute("SELECT data FROM runs WHERE id=?", (run["id"],)).fetchone()
        if old:
            old = json.loads(old[0])
            sources = { (p["path"], p["first_line"]): p for p in old["sources"] + run["sources"] }
            if old["coverage"] == "complete" and run["coverage"] != "complete": run = old
            elif old["status"] != "in_progress" and run["status"] == "in_progress": run = old
            run["sources"] = list(sources.values())[-8:]
        db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?)", (run["id"], run["started"], run["region"], json.dumps(run, ensure_ascii=False)))

    def scan(self, path, region="eu", max_bytes=32 * 1024 * 1024, year=None):
        if region not in REGIONS: raise ValueError("Unsupported combat-log region")
        path = Path(path).resolve()
        with self.lock, self.connect() as db, path.open("rb") as stream:
            stat = path.stat()
            row = db.execute("SELECT checkpoint FROM files WHERE path=?", (str(path),)).fetchone()
            checkpoint = json.loads(row[0]) if row else {}
            size = stat.st_size
            prefix_n = checkpoint.get("prefix_n", min(size,4096))
            prefix = hashlib.sha256(stream.read(prefix_n)).hexdigest()
            valid = (checkpoint.get("inode") == stat.st_ino and checkpoint.get("prefix") == prefix
                     and checkpoint.get("offset",0) <= size and checkpoint.get("region") == region
                     and checkpoint.get("year_override") == year and checkpoint.get("schema")==SCHEMA)
            if checkpoint and not valid:
                previous = Parser(str(path),checkpoint["region"],state=checkpoint["parser"])
                self.save_run(db,previous.snapshot("incomplete"))
                prefix_n=min(size,4096); stream.seek(0); prefix=hashlib.sha256(stream.read(prefix_n)).hexdigest()
            parser = Parser(str(path), region, year or datetime.fromtimestamp(stat.st_mtime).year,
                            checkpoint["parser"] if valid else None)
            offset = checkpoint["offset"] if valid else 0
            stream.seek(offset)
            bound = min(size, offset + max_bytes)
            processed = 0
            while stream.tell() < bound:
                before = stream.tell(); raw = stream.readline()
                if not raw.endswith(b"\n"):
                    stream.seek(before); break  # WoW may still be writing this line.
                for run in parser.feed(raw.decode("utf-8-sig",errors="replace")):
                    self.save_run(db,run)
                processed += 1
            offset = stream.tell()
            self.save_run(db,parser.snapshot())
            checkpoint={"inode":stat.st_ino,"prefix_n":prefix_n,"prefix":prefix,"offset":offset,
                        "region":region,"year_override":year,"schema":SCHEMA,"parser":parser.state()}
            db.execute("INSERT OR REPLACE INTO files VALUES (?,?)", (str(path),json.dumps(checkpoint,ensure_ascii=False)))
            # Bounded local history; pruning never touches the source log.
            db.execute("DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY started DESC LIMIT 2000)")
            return {"lines":processed,"offset":offset,"size":size,"remaining":max(0,size-offset)}

    def runs(self, name=None, realm=None, region=None, limit=100):
        with self.lock, self.connect() as db:
            result=[]
            for data, in db.execute("SELECT data FROM runs ORDER BY started DESC"):
                run=json.loads(data)
                if region and run["region"] != region: continue
                if name and not any(normalized(p["name"]) == normalized(name) and normalized(p["realm"]) == normalized(realm or "") for p in run["players"]): continue
                result.append(run)
            return result[:limit],len(result)


def field(value):
    from urllib.parse import quote
    return quote(str(value) if value is not None else "",safe="-_.~ :")


def export(history, region, realm, name):
    if region not in REGIONS or not name or not realm or len(name)>200 or len(realm)>200:
        raise ValueError("Invalid local-history request")
    runs,total=history.runs(name,realm,region,100)
    rows=["MPLH1", "\t".join(map(field,["S",datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),region,realm,name,total,len(runs)]))]
    for run in runs:
        source=run["sources"][-1]
        rows.append("\t".join(map(field,["R",run["id"],run["dungeon"],run["map_id"],run["level"],run["started"],run["ended"],
                      run["duration"],run["status"],run["coverage"],Path(source["path"]).name,source["first_line"],source["last_line"],int(run["year_inferred"])])))
        for p in run["players"]:
            rows.append("\t".join(map(field,["A",p["guid"],p["name"],p["realm"],p["spec_id"],p["role"],p["interrupts"],p["deaths"],p["dispels"]])))
        rows.append("E")
    result="\n".join(rows)+"\n"
    if len(result.encode())>500000: raise ValueError("Local-history reply exceeds 500 KB")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log",type=Path)
    parser.add_argument("--database",type=Path,required=True)
    parser.add_argument("--region",choices=sorted(REGIONS),default="eu")
    parser.add_argument("--year",type=int)
    args=parser.parse_args()
    history=History(args.database)
    while True:
        progress=history.scan(args.log,args.region,year=args.year)
        if not progress["remaining"] or not progress["lines"]: break
    runs,total=history.runs(region=args.region)
    print(json.dumps({"runs":total,"complete_in_latest100":sum(r["coverage"]=="complete" for r in runs),"progress":progress},ensure_ascii=False))


if __name__=="__main__": main()
