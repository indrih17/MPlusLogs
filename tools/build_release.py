"""Build explicitly allowlisted addon and Windows companion release artifacts."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def version():
    return re.search(r"^## Version: (\d+\.\d+\.\d+)$", (ROOT / "MPlusLogs.toc").read_text(), re.M)[1]


def addon(output, release_version):
    toc = (ROOT / "MPlusLogs.toc").read_text(encoding="utf-8")
    files = [line.strip() for line in toc.splitlines() if line.strip() and not line.startswith("#")]
    with zipfile.ZipFile(output / f"MPlusLogs-{release_version}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "MPlusLogs.toc", "MPlusLogs/MPlusLogs.toc")
        for name in files:
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise ValueError(f"Invalid TOC file: {name}")
            # Ship the demo explicitly via /mpl demo, without a real user's snapshot.
            if name == "Snapshot.lua":
                archive.writestr("MPlusLogs/Snapshot.lua", "local _, MPL = ...\nMPL.snapshots = {}\n")
            else:
                archive.write(path, "MPlusLogs/" + name.replace("\\", "/"))
        archive.write(ROOT / "packaging/ADDON-README.txt", "MPlusLogs/README.txt")
        archive.write(ROOT / "LICENSE", "MPlusLogs/LICENSE")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-only", action="store_true")
    parser.add_argument("--iscc", type=Path)
    args = parser.parse_args()
    output = ROOT / "release-output"
    output.mkdir(exist_ok=True)
    release_version = version()
    addon(output, release_version)
    if not args.addon_only:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
            "--name", "MPlusLogs-Companion", "--paths", str(ROOT / "tools"), "--hidden-import", "retail_launcher",
            "--hidden-import", "release_smoke", "--icon", str(ROOT / "tools/assets/mpluslogs.ico"),
            "--add-data", f"{ROOT / 'tools/assets'};assets",
            "--add-data", f"{ROOT / 'tools/oauth_client.json'};.",
            "--add-data", f"{ROOT / 'realm-slugs.json'};.",
            str(ROOT / "tools/companion_gui.pyw")], cwd=ROOT, check=True)
        # In a frozen build modules live in _internal; realm_resolver expects its parent.
        internal = ROOT / "dist/MPlusLogs-Companion/_internal"
        shutil.copy2(ROOT / "realm-slugs.json", internal.parent / "realm-slugs.json")
        notices = internal.parent / "licenses"
        notices.mkdir(exist_ok=True)
        shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python-LICENSE.txt")
        shutil.copy2(ROOT / "LICENSE", notices / "MPlusLogs-LICENSE.txt")
        distribution = importlib.metadata.distribution("pyinstaller")
        for item in distribution.files:
            if item.name in {"COPYING.txt", "LICENSE", "LICENSE.txt"}:
                shutil.copy2(distribution.locate_file(item), notices / ("PyInstaller-" + item.name))
        smoke = output / "companion-smoke.json"
        subprocess.run([str(internal.parent / "MPlusLogs-Companion.exe"), "--self-test-report", str(smoke)], check=True, timeout=30)
        if not json.loads(smoke.read_text())["ok"]:
            raise RuntimeError("Frozen smoke test failed")
        with zipfile.ZipFile(output / f"MPlusLogs-Companion-{release_version}-Windows-x64.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(internal.parent.rglob("*")):
                if path.is_file():
                    archive.write(path, "MPlusLogs-Companion/" + path.relative_to(internal.parent).as_posix())
            archive.write(ROOT / "packaging/COMPANION-README.txt", "MPlusLogs-Companion/README.txt")
        if args.iscc:
            subprocess.run([str(args.iscc.resolve()), f"/DAppVersion={release_version}", str(ROOT / "packaging/companion.iss")], check=True)
    artifacts = sorted(list(output.glob(f"*{release_version}*.zip")) + list(output.glob(f"*{release_version}*.exe")))
    (output / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts), encoding="utf-8")


if __name__ == "__main__":
    main()
