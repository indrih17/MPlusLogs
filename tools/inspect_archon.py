"""Read local Archon DB metadata and decode one character; no Lua execution or network."""
import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import re


class Reader:
    def __init__(self, content, lookup):
        self.content, self.lookup, self.pos = content, lookup, 0

    def integer(self, count=1):
        end = self.pos + count
        if end > len(self.content):
            raise ValueError("Truncated Archon record")
        result = int.from_bytes(self.content[self.pos:end], "little")
        self.pos = end
        return result

    def string(self):
        index = self.integer(2)
        if index:
            return self.lookup[index - 1]
        count = self.integer()
        end = self.pos + count
        if end > len(self.content):
            raise ValueError("Truncated inline string")
        result = self.content[self.pos:end].decode("utf-8")
        self.pos = end
        return result

    def rankings(self):
        result = {"spec": self.string(), "progressKilled": self.integer(),
                  "progressPossible": self.integer(), "bestAverage": self.integer(2) / 100,
                  "allStarRank": self.integer(3), "allStarPoints": self.integer(2)}
        encounters = []
        for _ in range(self.integer()):
            encounters.append({"encounterID": self.integer(4), "kills": self.integer(2),
                               "best": self.integer(), "isHidden": self.integer() == 1})
        result["encounters"] = encounters
        return result


def decode(encoded, lookup):
    r = Reader(base64.b64decode(encoded, validate=True), lookup)
    if r.integer() != 4:
        raise ValueError("Unsupported Archon format")
    result = {"isSubscriber": r.integer() == 1, "sections": []}
    count = r.integer()
    if count == 0:
        result["summary"] = {"zoneID": r.integer(2), "difficultyID": r.integer(),
                             "sizeID": r.integer(), "progressKilled": r.integer(),
                             "progressPossible": r.integer(), "totalKills": r.integer(2)}
    else:
        for _ in range(count):
            section = {"zoneID": r.integer(2), "difficultyID": r.integer(), "sizeID": r.integer(),
                       "partitionID": r.integer() - 128, "totalKills": r.integer(2)}
            spec_count = r.integer()
            section["anySpec"] = r.rankings()
            section["perSpec"] = [r.rankings() for _ in range(spec_count - 1)]
            result["sections"].append(section)
    if r.integer() == 1:
        result["mainCharacter"] = {"zoneID": r.integer(2), "difficultyID": r.integer(), "sizeID": r.integer(),
                                   "progressKilled": r.integer(), "progressPossible": r.integer(),
                                   "totalKills": r.integer(2), "spec": r.string(), "bestAverage": r.integer(2) / 100}
    result["progressOnly"] = r.integer() == 1
    if r.pos != len(r.content):
        raise ValueError("Unexpected trailing bytes; Archon format may have changed")
    return result


def inspect(directory, name, realm):
    files = sorted(directory.glob("db_*.lua"))
    zones, dates, matches = Counter(), Counter(), []
    for file in files:
        text = file.read_text(encoding="utf-8-sig")
        metadata = re.search(r"local provider = \{([^\n]*?)data=\{", text)
        if not metadata:
            raise ValueError(f"Unknown metadata format: {file.name}")
        header = metadata.group(1)
        zone = int(re.search(r"zone=(\d+)", header).group(1))
        date = re.search(r"date='([^']+)'", header).group(1)
        server = re.search(r'''realm=(["'])(.*?)\1''', header).group(2)
        zones[zone] += 1
        dates[date] += 1
        if server != realm:
            continue
        match = re.search(r"(?:[='.])" + re.escape(name) + r":([A-Za-z0-9+/]+={0,2})[.]", text)
        if match:
            lookup_text = re.search(r"local lookup = \{([^\n]+)\}", text).group(1)
            lookup = re.findall(r"'([^']*)'", lookup_text)
            matches.append({"file": file.name, "date": date, "realm": server, "name": name,
                            "decoded": decode(match.group(1), lookup)})
    return {"source": str(directory), "files": len(files), "zonesByProviderMetadata": dict(zones),
            "dates": dict(dates), "character": matches,
            "note": "Archon local snapshot only. This export contains raid data, not M+ logs."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[2] / "ArchonTooltip/DB")
    parser.add_argument("--name", default="Киндрих")
    parser.add_argument("--realm", default="Гордунни")
    parser.add_argument("--output", type=Path, default=Path("archon-inspection.json"))
    args = parser.parse_args()
    result = inspect(args.directory, args.name, args.realm)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"character", "source"}}, ensure_ascii=True))
    print(f"Decoded character records: {len(result['character'])}; output: {args.output}")
