"""Prepare only the components whose shipped inputs changed; retries are stable."""
from pathlib import Path
import subprocess
import addon_version
import companion_version

ROOT = Path(__file__).resolve().parents[1]


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, encoding="utf-8", capture_output=True)


def main():
    addon_changed = addon_version.prepare()
    companion_changed = companion_version.prepare()
    if not addon_changed and not companion_changed:
        return
    components = (["MPlusLogs " + addon_version.version()] if addon_changed else []) + (["Companion " + companion_version.version()] if companion_changed else [])
    label = " / ".join(components)
    notes = "## " + label + "\n\n- Update shipped component inputs.\n"
    (ROOT / "packaging/RELEASE-NOTES.md").write_text(notes, encoding="utf-8")
    path = ROOT / "CHANGELOG.md"
    path.write_text(path.read_text(encoding="utf-8").replace("# Changelog\n", "# Changelog\n\n" + notes, 1), encoding="utf-8")
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "MPlusLogs.toc", "CHANGELOG.md", "packaging")
    git("commit", "-m", "Prepare " + label + " [skip ci]")


if __name__ == "__main__": main()
