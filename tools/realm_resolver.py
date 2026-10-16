"""Resolve localized/normalized WoW realm names without guessing WCL slugs."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def normalized(text):
    return re.sub(r"[\s\-']", "", text.casefold())


def archon_mappings(path):
    mappings = {}
    if not path.exists():
        return mappings
    # Read data records only; do not execute another addon's Lua.
    pattern = re.compile(r'Private\.Realms\[\d+\]\s*=\s*\{\s*name\s*=\s*"([^"]+)",\s*slug\s*=\s*"([^"]+)",\s*region\s*=\s*"([^"]+)",\s*database\s*=\s*"([^"]+)"')
    for name, slug, region, database in pattern.findall(path.read_text(encoding="utf-8-sig")):
        if database == region and region.lower() in {"eu", "us", "kr", "tw", "cn"}:
            mappings.setdefault(region.lower(), {})[name] = slug
    return mappings


def load_mappings(path=None):
    # Local Archon realm metadata is optional; the bundled data works without Archon.
    mappings = archon_mappings(ROOT.parent / "ArchonTooltip/Realms.lua")
    path = path or ROOT / "realm-slugs.json"
    if path.exists():
        custom = json.loads(path.read_text(encoding="utf-8-sig"))
        for region, realms in custom.items():
            mappings.setdefault(region, {}).update(realms)
    return mappings


def resolve(mapping, region, realm):
    names = mapping.get(region, {})
    slug = names.get(realm)
    if slug:
        return slug
    matches = {slug for name, slug in names.items() if normalized(name) == normalized(realm)}
    if len(matches) == 1:
        return matches.pop()
    raise ValueError(f"Unknown/ambiguous realm {region}/{realm}; update realm-slugs.json")


def parse_queue(text, mappings, allow_unresolved=False):
    if len(text.encode("utf-8")) > 500000:
        raise ValueError("Queue is too large")
    from urllib.parse import unquote
    lines = [line for line in text.splitlines() if line]
    if not lines or lines[0] not in {"MPLQ1","MPLQ2"}:
        raise ValueError("Expected MPLQ1 from MPlusLogs")
    entries = []
    for line in lines[1:]:
        parts = [unquote(part) for part in line.split("\t")]
        if len(parts) not in {4, 6, 7} or parts[0] != "Q":
            raise ValueError("Malformed queue entry")
        _, region, realm, name = parts[:4]
        if region not in {"eu", "us", "kr", "tw", "cn"} or not name or not realm:
            raise ValueError("Invalid character identity")
        metric, spec = parts[4:6] if len(parts) >= 6 else ("dps", "")
        role=parts[6] if len(parts)==7 else None
        if role is not None and role not in {"HEALER","TANK","DAMAGER"}: raise ValueError("Invalid role")
        if metric not in {"dps", "hps"}:
            raise ValueError("Invalid metric")
        for value in (realm, name, spec):
            if len(value.encode()) > 200 or any(ord(c) < 32 or c == "|" for c in value):
                raise ValueError("Invalid text in request")
        try: slug=resolve(mappings, region, realm); queue_error=None
        except ValueError as exc:
            if not allow_unresolved: raise
            slug=None; queue_error=str(exc)
        entry={"name": name, "realm": realm, "server_slug": slug,
               "region": region, "metric": metric, "spec": spec or None}
        if role: entry["role"]=role
        if queue_error: entry["queue_error"]=queue_error
        entries.append(entry)
    if not entries or len(entries) > 1000:
        raise ValueError("Expected 1..1000 characters")
    return entries
