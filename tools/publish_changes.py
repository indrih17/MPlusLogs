"""Publish a stable tested local snapshot; CI builds and uploads both releases."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import export_release_source
import companion_version
import addon_version
from development_paths import build_tools_dir

ROOT = export_release_source.ROOT
BUILD_TOOLS = build_tools_dir(ROOT)
REPO = BUILD_TOOLS / "repository"
STATE = BUILD_TOOLS / "published-source.json"


def git(*args, capture=False):
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, text=True,
        encoding="utf-8", stdout=subprocess.PIPE if capture else None,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")).stdout


def hashes(entries):
    result = {}
    metadata = {"MPlusLogs.toc", "packaging/COMPANION-README.txt", "packaging/ADDON-README.txt", "packaging/companion.iss"}
    for entry in entries:
        if entry["path"] in {"CHANGELOG.md", "packaging/RELEASE-NOTES.md"}: continue
        content = entry["content"]
        if entry["path"] in metadata:
            content = re.sub(r"\b\d+\.\d+\.\d+\b", "VERSION", content)
        result[entry["path"]] = hashlib.sha256(content.encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--summary", action="append")
    args = parser.parse_args()
    entries = export_release_source.entries()
    current = hashes(entries)
    previous = json.loads(STATE.read_text(encoding="utf-8"))["hashes"] if STATE.exists() else {}
    changed = sorted(key for key in current.keys() | previous.keys() if current.get(key) != previous.get(key))
    latest = max((ROOT / entry["path"]).stat().st_mtime for entry in entries if (ROOT / entry["path"]).exists())
    if args.check_only:
        print(json.dumps({"changed": changed, "stable_seconds": round(time.time()-latest)}, ensure_ascii=True)); return
    if not changed: print("No unpublished source changes"); return
    if not args.summary or any(not item.strip() for item in args.summary):
        parser.error("Provide a meaningful --summary before publishing")
    REPO.parent.mkdir(exist_ok=True)
    if not (REPO / ".git").exists():
        subprocess.run(["git", "clone", "https://github.com/indrih17/MPlusLogs.git", str(REPO)], check=True)
    if git("status", "--porcelain", capture=True).strip():
        raise RuntimeError("Publishing checkout has unfinished changes; inspect them first")
    git("pull", "--ff-only", "origin", "main")
    baseline = addon_version.state(REPO)
    addon_version.prepare(baseline)
    companion_version.prepare()
    entries = export_release_source.entries()
    current = hashes(entries)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT, check=True)
    if hashes(export_release_source.entries()) != current:
        raise RuntimeError("Source changed during validation; wait until editing finishes")
    release = addon_version.version()
    addon_changed = release != baseline["version"] or addon_version.source_hash() != baseline["source_hash"]
    old_companion = json.loads((REPO / "packaging/companion-version.json").read_text(encoding="utf-8"))["version"]
    companion_changed = companion_version.version() != old_companion
    components = (["MPlusLogs " + release] if addon_changed else []) + (["Companion " + companion_version.version()] if companion_changed else [])
    label = " / ".join(components) or "Release tooling"
    notes = f"## {label}\n\n" + "".join(f"- {item.strip()}\n" for item in args.summary)
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").replace("# Changelog\n", "# Changelog\n\n" + notes, 1)
    generated = {"MPlusLogs.toc", "CHANGELOG.md", "packaging/COMPANION-README.txt", "packaging/ADDON-README.txt", "packaging/companion.iss", "packaging/RELEASE-NOTES.md"}
    for entry in entries:
        name, content = entry["path"], entry["content"]
        if name == "MPlusLogs.toc": content = re.sub(r"^## Version: .*", "## Version: " + release, content, flags=re.M)
        if name == "packaging/ADDON-README.txt":
            content = re.sub(r"^MPlusLogs \d+\.\d+\.\d+", "MPlusLogs " + release, content)
        if name == "CHANGELOG.md": content = changelog
        if name == "packaging/RELEASE-NOTES.md":
            content = notes
        path = REPO / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if entry["encoding"] == "base64": path.write_bytes(base64.b64decode(content))
        else: path.write_text(content, encoding="utf-8")
        if name in generated: (ROOT / name).write_text(content, encoding="utf-8")
    for name in previous.keys()-current.keys():
        path = (REPO / name).resolve()
        if not path.is_relative_to(REPO.resolve()): raise ValueError("Invalid prior source path")
        if path.is_file(): path.unlink()
    git("add", "--all")
    git("commit", "-m", f"Release {label}: {args.summary[0].strip()}")
    git("push", "origin", "main")
    STATE.write_text(json.dumps({"version": release, "commit": git("rev-parse", "HEAD", capture=True).strip(),
        "hashes": hashes(export_release_source.entries())}, indent=2), encoding="utf-8")
    print(f"Published source for {label}; follow GitHub Actions for changed components")


if __name__ == "__main__": main()
