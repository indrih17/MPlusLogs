"""Independent Companion version, derived from its shipped inputs."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "packaging/companion-version.json"
RUNTIME = ("companion_gui.pyw", "companion_i18n.py", "companion_update.py", "companion_version.py",
           "companion_location.py",
           "clipboard_companion.py", "clipboard_protocol.py", "build_database.py", "realm_resolver.py",
           "wcl_sync.py", "wcl_oauth.py", "local_settings.py", "windows_integration.py", "retail_launcher.py",
           "appearance.py", "release_smoke.py", "requirements.txt", "oauth_client.json", "build_release.py",
           "api_budget.py", "personal_api.py")


def metadata():
    return json.loads(METADATA.read_text(encoding="utf-8"))


def version():
    return metadata()["version"]


def source_hash():
    files = [ROOT / "tools" / name for name in RUNTIME]
    files += [ROOT / name for name in ("realm-slugs.json", "LICENSE", "packaging/companion.iss", "packaging/COMPANION-README.txt")]
    files += list((ROOT / "tools/assets").glob("*")) + list((ROOT / "tools/companion_locales").glob("*.json"))
    digest = hashlib.sha256()
    for path in sorted(files):
        if not path.is_file():
            continue
        content = path.read_bytes()
        if path.suffix not in {".png", ".ico"}:
            content = content.replace(b"\r\n", b"\n")
        if path.name in {"companion.iss", "COMPANION-README.txt"}:
            content = re.sub(rb"\b\d+\.\d+\.\d+\b", b"VERSION", content)
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def prepare():
    data = metadata()
    fingerprint = source_hash()
    if data.get("source_hash") == fingerprint:
        return False
    major, minor, patch = map(int, data["version"].split("."))
    data.update(version=f"{major}.{minor}.{patch + 1}", source_hash=fingerprint)
    METADATA.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for name in ("companion.iss", "COMPANION-README.txt"):
        path = ROOT / "packaging" / name
        path.write_text(re.sub(r"\b\d+\.\d+\.\d+\b", data["version"], path.read_text(encoding="utf-8")), encoding="utf-8")
    return True
