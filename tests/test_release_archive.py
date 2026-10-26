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
import export_release_source
from upload_curseforge import validate_archive

class ArchiveTests(unittest.TestCase):
    def make_source_fixture(self, root):
        for name in ('Settings.xml', 'LICENSE', 'CODE-SIGNING.md', '.gitignore',
                     'realm-slugs.json', 'Start-Companion.vbs', 'AGENTS.md', 'CHANGELOG.md',
                     'packaging/ADDON-README.txt', 'packaging/README-public.md',
                     'assets/dungeons/README.md', 'experiments/wcl-points-and-damage.json'):
            path=root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('Fixture public source\n',encoding='utf-8')
        (root/'MPlusLogs.toc').write_text('Main.lua\nLocales/Tutorial/deDE.lua\n',encoding='utf-8')
        (root/'Main.lua').write_text('local _, MPL = ...\n',encoding='utf-8')
        (root/'assets/mpluslogs-icon.tga').write_bytes(b'fixture icon')
        tutorial=root/'Locales/Tutorial'
        tutorial.mkdir(parents=True)
        translation='local _, MPL = ...\nMPL.RegisterTutorialLocale("deDE", {title="Anleitung"})\n'
        (tutorial/'deDE.lua').write_text(translation,encoding='utf-8',newline='\n')
        for name in ('tokens.json', 'private.txt', 'unsupported.lua', '.private.lua'):
            (tutorial/name).write_text('Excluded private fixture',encoding='utf-8')
        (tutorial/'nested').mkdir()
        (tutorial/'nested/esES.lua').write_text(translation,encoding='utf-8')
        return translation

    def test_only_supported_tutorial_translations_are_allowlisted(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-tutorial-locales-') as folder:
            root=Path(folder)
            translation=self.make_source_fixture(root)
            build_release.addon(root,'test',source_root=root)
            with zipfile.ZipFile(root/'MPlusLogs-test.zip') as archive:
                tutorial_names={name for name in archive.namelist() if '/Locales/Tutorial/' in name}
                self.assertEqual(tutorial_names,{'MPlusLogs/Locales/Tutorial/deDE.lua'})
                self.assertEqual(archive.read('MPlusLogs/Locales/Tutorial/deDE.lua').decode('utf-8'),translation)
            with patch.object(export_release_source,'ROOT',root):
                entries={entry['path']:entry for entry in export_release_source.entries()}
            tutorial_names={name for name in entries if name.startswith('Locales/Tutorial/')}
            self.assertEqual(tutorial_names,{'Locales/Tutorial/deDE.lua'})
            entry=entries['Locales/Tutorial/deDE.lua']
            self.assertEqual(entry['encoding'],'utf-8')
            self.assertEqual(entry['content'],translation)

    def test_real_addon_archive_excludes_development_files(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-zip-') as folder:
            output=Path(folder)
            build_release.addon(output,'test')
            archive=output/'MPlusLogs-test.zip'
            validate_archive(archive)
            with zipfile.ZipFile(archive) as z:
                self.assertIn('MPlusLogs/Settings.lua',z.namelist())
                self.assertIn('MPlusLogs/Tutorial.lua',z.namelist())
                self.assertIn('MPlusLogs/TutorialSteps.lua',z.namelist())
                self.assertIn('MPlusLogs/TutorialProfile.lua',z.namelist())
                for name in ('Appearance.lua','AppearancePresets.lua','DungeonNames.lua',
                             'ProfileAppearance.lua','AppearanceSettings.lua'):
                    self.assertIn('MPlusLogs/'+name,z.namelist())
                entries={entry['path']:entry for entry in export_release_source.entries()}
                for locale in ('deDE','esES','esMX','frFR','itIT','koKR','ptBR','zhCN','zhTW'):
                    name=f'Locales/Tutorial/{locale}.lua'
                    source=(ROOT/name).read_text(encoding='utf-8')
                    self.assertEqual(z.read('MPlusLogs/'+name),(ROOT/name).read_bytes())
                    self.assertEqual(entries[name]['content'],source)
                self.assertIn('MPlusLogs/assets/mpluslogs-icon.tga',z.namelist())
                toc=z.read('MPlusLogs/MPlusLogs.toc').decode('utf-8')
                self.assertIn(r'## IconTexture: Interface\AddOns\MPlusLogs\assets\mpluslogs-icon.tga',toc)
                self.assertNotIn('MPlusLogs/.git/config',z.namelist())
                for name in export_release_source.LIBRARY_FILES:
                    self.assertIn('MPlusLogs/'+name,z.namelist())
                    self.assertEqual(z.read('MPlusLogs/'+name),(ROOT/name).read_bytes())
                    self.assertEqual(entries[name]['content'],(ROOT/name).read_text(encoding='utf-8-sig'))

    def test_library_export_is_explicit_and_not_a_recursive_glob(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-public-libs-') as folder:
            root=Path(folder)
            self.make_source_fixture(root)
            for name in export_release_source.LIBRARY_FILES:
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('Public vendored file\n',encoding='utf-8')
            for name in ('libs/private.lua','libs/tokens.json',
                         'libs/LibSharedMedia-3.0/private.lua',
                         'libs/LibSharedMedia-3.0/fonts/private.ttf'):
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('Must not leave workspace',encoding='utf-8')
            with patch.object(export_release_source,'ROOT',root):
                names={entry['path'] for entry in export_release_source.entries()}
            self.assertEqual({name for name in names if name.startswith('libs/')},
                             set(export_release_source.LIBRARY_FILES))

    def test_vendored_library_cannot_ship_without_its_notice(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-library-notices-') as folder:
            root=Path(folder)
            self.make_source_fixture(root)
            source='libs/LibSharedMedia-3.0/LibSharedMedia-3.0.lua'
            path=root/source
            path.parent.mkdir(parents=True)
            path.write_text('-- library fixture',encoding='utf-8')
            (root/'MPlusLogs.toc').write_text(source+'\n',encoding='utf-8')
            (root/'libs/README.md').write_text('Library provenance',encoding='utf-8')
            with self.assertRaises(FileNotFoundError):
                build_release.addon(root,'test',source_root=root)

    def test_windows_line_endings_are_preserved_in_archive_and_normalized_in_export(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-crlf-') as folder:
            root=Path(folder)
            translation=self.make_source_fixture(root)
            windows=translation.replace('\n','\r\n').encode('utf-8')
            (root/'Locales/Tutorial/deDE.lua').write_bytes(windows)
            build_release.addon(root,'test',source_root=root)
            with zipfile.ZipFile(root/'MPlusLogs-test.zip') as archive:
                self.assertEqual(archive.read('MPlusLogs/Locales/Tutorial/deDE.lua'),windows)
            with patch.object(export_release_source,'ROOT',root):
                entries={entry['path']:entry for entry in export_release_source.entries()}
            self.assertEqual(entries['Locales/Tutorial/deDE.lua']['content'],translation)

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
