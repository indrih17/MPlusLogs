"""Version only the normalized contents of the actual shipped addon archive."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import zipfile
import build_release

ROOT = Path(__file__).resolve().parents[1]


def version(root=None):
    root = ROOT if root is None else Path(root)
    return re.search(r"^## Version: (\d+\.\d+\.\d+)$", (root / "MPlusLogs.toc").read_text(encoding="utf-8"), re.M)[1]


def source_hash(root=None):
    root = ROOT if root is None else Path(root)
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix=".addon-version-", dir=ROOT) as folder:
        build_release.addon(Path(folder), "fingerprint", root)
        with zipfile.ZipFile(Path(folder) / "MPlusLogs-fingerprint.zip") as archive:
            for name in sorted(archive.namelist()):
                content = archive.read(name)
                if not name.endswith(".tga"):
                    content = content.replace(b"\r\n", b"\n")
                if name == "MPlusLogs/MPlusLogs.toc":
                    content = re.sub(rb"^## Version: .*", b"## Version: VERSION", content, flags=re.M)
                if name == "MPlusLogs/README.txt":
                    content = re.sub(rb"^MPlusLogs \d+\.\d+\.\d+", b"MPlusLogs VERSION", content)
                digest.update(name.encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def state(root=None):
    root = ROOT if root is None else Path(root)
    path = root / "packaging/addon-version.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": version(root), "source_hash": source_hash(root)}


def prepare(baseline=None):
    data = state() if baseline is None else baseline
    fingerprint, release = source_hash(), version()
    if tuple(map(int, release.split("."))) < tuple(map(int, data["version"].split("."))):
        release = data["version"]
    changed = fingerprint != data["source_hash"]
    if changed and release == data["version"]:
        major, minor, patch = map(int, release.split("."))
        release = f"{major}.{minor}.{patch + 1}"
    desired = {"version": release, "source_hash": fingerprint}
    if changed or not (ROOT / "packaging/addon-version.json").exists() or state() != desired:
        toc = ROOT / "MPlusLogs.toc"
        toc.write_text(re.sub(r"^## Version: .*", "## Version: " + release, toc.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
        readme = ROOT / "packaging/ADDON-README.txt"
        readme.write_text(re.sub(r"^MPlusLogs \d+\.\d+\.\d+", "MPlusLogs " + release, readme.read_text(encoding="utf-8")), encoding="utf-8")
        (ROOT / "packaging/addon-version.json").write_text(json.dumps(desired, indent=2) + "\n", encoding="utf-8")
        return True
    return False
