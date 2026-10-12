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
import companion_version

ROOT = Path(__file__).resolve().parents[1]


def version():
    return re.search(r"^## Version: (\d+\.\d+\.\d+)$", (ROOT / "MPlusLogs.toc").read_text(), re.M)[1]


def addon(output, release_version, source_root=None):
    root = ROOT if source_root is None else Path(source_root)
    toc = (root / "MPlusLogs.toc").read_text(encoding="utf-8")
    files = [line.strip() for line in toc.splitlines() if line.strip() and not line.startswith("#")]
    with zipfile.ZipFile(output / f"MPlusLogs-{release_version}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(root / "MPlusLogs.toc", "MPlusLogs/MPlusLogs.toc")
        for name in files:
            path = (root / name).resolve()
            if (not path.is_relative_to(root.resolve()) or not path.is_file() or path.suffix.lower() not in {".lua", ".xml"}
                or any(part.startswith(".") for part in Path(name).parts)):
                raise ValueError(f"Invalid TOC file: {name}")
            # Ship the demo explicitly via /mpl demo, without a real user's snapshot.
            if name == "Snapshot.lua":
                archive.writestr("MPlusLogs/Snapshot.lua", "local _, MPL = ...\nMPL.snapshots = {}\n")
            else:
                archive.write(path, "MPlusLogs/" + name.replace("\\", "/"))
        archive.write(root / "packaging/ADDON-README.txt", "MPlusLogs/README.txt")
        archive.write(root / "LICENSE", "MPlusLogs/LICENSE")
        for path in sorted((root / "assets/dungeons").glob("*.tga")):
            archive.write(path, "MPlusLogs/assets/dungeons/" + path.name)
        archive.write(root / "assets/dungeons/README.md", "MPlusLogs/assets/dungeons/README.md")
        archive.write(root / "assets/mpluslogs-icon.tga", "MPlusLogs/assets/mpluslogs-icon.tga")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-only", action="store_true")
    parser.add_argument("--skip-addon", action="store_true")
    parser.add_argument("--iscc", type=Path)
    args = parser.parse_args()
    output = ROOT / "release-output"
    output.mkdir(exist_ok=True)
    release_version = version()
    if not args.skip_addon:
        addon(output, release_version)
    if not args.addon_only:
        companion_release = companion_version.version()
        build_metadata = ROOT / "tools/companion-build.json"
        build_metadata.write_text(json.dumps({"version": companion_release}), encoding="utf-8")
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
            "--name", "MPlusLogs-Companion", "--paths", str(ROOT / "tools"), "--hidden-import", "retail_launcher",
            "--hidden-import", "release_smoke", "--icon", str(ROOT / "tools/assets/mpluslogs.ico"),
            "--add-data", f"{ROOT / 'tools/assets'};assets",
            "--add-data", f"{ROOT / 'tools/companion_locales'};companion_locales",
            "--add-data", f"{ROOT / 'tools/oauth_client.json'};.",
            "--add-data", f"{build_metadata};.",
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
        with zipfile.ZipFile(output / f"MPlusLogs-Companion-{companion_release}-Windows-x64.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(internal.parent.rglob("*")):
                if path.is_file():
                    archive.write(path, "MPlusLogs-Companion/" + path.relative_to(internal.parent).as_posix())
            archive.write(ROOT / "packaging/COMPANION-README.txt", "MPlusLogs-Companion/README.txt")
        if args.iscc:
            subprocess.run([str(args.iscc.resolve()), f"/DAppVersion={companion_release}", str(ROOT / "packaging/companion.iss")], check=True)
            installer = output / f"MPlusLogs-Companion-{companion_release}-Setup.exe"
            manifest = {"schema": 1, "version": companion_release, "size": installer.stat().st_size,
                "sha256": hashlib.sha256(installer.read_bytes()).hexdigest(),
                "url": f"https://github.com/indrih17/MPlusLogs/releases/download/companion-v{companion_release}/{installer.name}"}
            (output / "companion-update.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    artifacts = sorted(list(output.glob("*.zip")) + list(output.glob("*.exe")))
    (output / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts), encoding="utf-8")


if __name__ == "__main__":
    main()
