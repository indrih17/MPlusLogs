"""Raise patch versions for direct main commits; preserve retries of the same tag."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, encoding="utf-8", capture_output=True)


def main():
    toc = ROOT / "MPlusLogs.toc"
    version = re.search(r"^## Version: (.+)$", toc.read_text(encoding="utf-8"), re.M)[1]
    tag = "v" + version
    existing = git("rev-parse", "--verify", "refs/tags/" + tag, check=False)
    if existing.returncode or existing.stdout.strip() == git("rev-parse", "HEAD").stdout.strip():
        return
    versions = [tuple(map(int, match)) for match in re.findall(r"^v(\d+)\.(\d+)\.(\d+)$", git("tag", "--list").stdout, re.M)]
    major, minor, patch = max(versions + [tuple(map(int, version.split(".")))])
    release = f"{major}.{minor}.{patch+1}"
    messages = git("log", tag + "..HEAD", "--format=%s").stdout.splitlines()
    notes = f"## {release}\n\n" + "".join("- " + message + "\n" for message in messages if message.strip())
    toc.write_text(re.sub(r"^## Version: .*", "## Version: " + release, toc.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
    for name in ("packaging/COMPANION-README.txt", "packaging/ADDON-README.txt", "packaging/companion.iss"):
        path = ROOT / name
        path.write_text(re.sub(r"\b\d+\.\d+\.\d+\b", release, path.read_text(encoding="utf-8")), encoding="utf-8")
    (ROOT / "packaging/RELEASE-NOTES.md").write_text(notes, encoding="utf-8")
    path = ROOT / "CHANGELOG.md"
    path.write_text(path.read_text(encoding="utf-8").replace("# Changelog\n", "# Changelog\n\n"+notes,1), encoding="utf-8")
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "MPlusLogs.toc", "CHANGELOG.md", "packaging")
    git("commit", "-m", f"Release metadata {release} [skip ci]")


if __name__ == "__main__": main()
