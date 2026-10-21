"""The addon version follows its archive, never Companion or development files."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import addon_version


class AddonVersionTests(unittest.TestCase):
    def test_independent_versions_and_idempotent_publication(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            for name, content in {
                "MPlusLogs.toc": "## Version: 0.5.11\nUI.lua\nSnapshot.lua\n",
                "UI.lua": "original", "Snapshot.lua": "private fixture",
                "LICENSE": "license", "packaging/ADDON-README.txt": "MPlusLogs 0.5.11\nInstall addon.\n",
                "assets/dungeons/README.md": "icons", "assets/mpluslogs-icon.tga": "icon"
            }.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            with patch.object(addon_version, "ROOT", root):
                self.assertTrue(addon_version.prepare())
                self.assertEqual(addon_version.version(), "0.5.11")
                self.assertFalse(addon_version.prepare())
                (root / "companion.py").write_text("changed companion")
                (root / "Snapshot.lua").write_text("different private fixture")
                self.assertFalse(addon_version.prepare())
                self.assertEqual(addon_version.version(), "0.5.11")
                (root / "UI.lua").write_text("changed addon")
                self.assertTrue(addon_version.prepare())
                self.assertEqual(addon_version.version(), "0.5.12")
                self.assertFalse(addon_version.prepare())
                (root / "assets/dungeons/new.tga").write_bytes(b"new icon")
                self.assertTrue(addon_version.prepare())
                self.assertEqual(addon_version.version(), "0.5.13")


    def test_version_metadata_and_windows_newlines_do_not_trigger_releases(self):
        original = addon_version.source_hash()
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            import build_release
            import zipfile
            root = Path(folder)
            build_release.addon(root, "copy")
            with zipfile.ZipFile(root / "MPlusLogs-copy.zip") as archive:
                for name in archive.namelist():
                    relative = name.removeprefix("MPlusLogs/")
                    if relative == "README.txt": relative = "packaging/ADDON-README.txt"
                    destination = root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    content = archive.read(name)
                    if not name.endswith(".tga"):
                        content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    destination.write_bytes(content)
            toc = root / "MPlusLogs.toc"
            import re
            toc.write_text(re.sub(r"^## Version: .*", "## Version: 99.0.0", toc.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
            self.assertEqual(addon_version.source_hash(root), original)


if __name__ == "__main__": unittest.main()
