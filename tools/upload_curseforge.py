"""Upload only the addon ZIP with a GitHub Actions environment secret."""
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://wow.curseforge.com/api"
PROJECT = 1740700


def main():
    token = os.environ.get("CF_API_TOKEN")
    if not token: raise RuntimeError("Missing GitHub Actions secret CF_API_TOKEN")
    toc = (ROOT / "MPlusLogs.toc").read_text(encoding="utf-8")
    version = re.search(r"^## Version: (.+)$", toc, re.M)[1]
    archive = ROOT / f"release-output/MPlusLogs-{version}.zip"
    with zipfile.ZipFile(archive) as z:
        if any(not name.startswith("MPlusLogs/") or name.lower().endswith((".exe", ".dll", ".py", ".json")) for name in z.namelist()):
            raise ValueError("Unexpected file in addon-only archive")
    headers = {"X-Api-Token": token}
    with urlopen(Request(BASE + "/game/versions", headers=headers), timeout=30) as response:
        available = json.load(response)
    interfaces = re.search(r"^## Interface: (.+)$", toc, re.M)[1].split(",")
    names = [f"{int(item)//10000}.{int(item)//100%100}.{int(item)%100}" for item in interfaces]
    ids = []
    for name in names:
        matching = [item["id"] for item in available if item["name"] == name]
        if len(matching) != 1: raise ValueError(f"Unsupported/ambiguous WoW version: {name}")
        ids.extend(matching)
    metadata = {"changelog": (ROOT / "packaging/RELEASE-NOTES.md").read_text(encoding="utf-8"),
        "changelogType": "markdown", "displayName": "MPlusLogs " + version,
        "gameVersions": ids, "releaseType": "release", "isMarkedForManualRelease": False}
    boundary = "MPlusLogs" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n".encode()
        + json.dumps(metadata).encode() + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{archive.name}\"\r\nContent-Type: application/zip\r\n\r\n".encode()
        + archive.read_bytes() + f"\r\n--{boundary}--\r\n".encode())
    headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    with urlopen(Request(f"{BASE}/projects/{PROJECT}/upload-file", data=body, headers=headers), timeout=120) as response:
        result = json.load(response)
    if not isinstance(result.get("id"), int): raise RuntimeError("CurseForge did not return a file ID")
    report = {"project": PROJECT, "file_id": result["id"], "version": version}
    (ROOT / "release-output/curseforge-upload.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__": main()
