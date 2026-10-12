"""Development Git/cache files must never be shipped to addon users."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_release
from upload_curseforge import validate_archive

class ArchiveTests(unittest.TestCase):
    def test_real_addon_archive_excludes_development_files(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-zip-') as folder:
            output=Path(folder)
            build_release.addon(output,'test')
            archive=output/'MPlusLogs-test.zip'
            validate_archive(archive)
            with zipfile.ZipFile(archive) as z:
                self.assertIn('MPlusLogs/Settings.lua',z.namelist())
                self.assertIn('MPlusLogs/assets/mpluslogs-icon.tga',z.namelist())
                toc=z.read('MPlusLogs/MPlusLogs.toc').decode('utf-8')
                self.assertIn(r'## IconTexture: Interface\AddOns\MPlusLogs\assets\mpluslogs-icon.tga',toc)
                self.assertNotIn('MPlusLogs/.git/config',z.namelist())

    def test_builder_rejects_hidden_git_file_even_if_added_to_toc(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-zip-') as folder:
            root=Path(folder); (root/'.git').mkdir()
            (root/'.git/leak.lua').write_text('private development metadata')
            (root/'MPlusLogs.toc').write_text('.git/leak.lua\n')
            with patch.object(build_release,'ROOT',root), self.assertRaises(ValueError):
                build_release.addon(root,'test')

    def test_uploader_rejects_hidden_or_development_archive_entries(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-zip-') as folder:
            archive=Path(folder)/'test.zip'
            for name in ['MPlusLogs/.git/config','MPlusLogs/.git/leak.lua',
                         'MPlusLogs/.build-tools/repository/config','MPlusLogs/backups/example.lua']:
                with zipfile.ZipFile(archive,'w') as z: z.writestr(name,'test')
                with self.assertRaises(ValueError): validate_archive(archive)

if __name__=='__main__': unittest.main()
