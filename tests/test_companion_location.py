"""Exercise AddOns protection and copying a live, locked Windows executable."""
import importlib.machinery
import importlib.util
import base64
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import companion_location as location


class LocationTests(unittest.TestCase):
    def test_path_boundaries_and_case(self):
        for path in (r'C:\WoW\Interface\AddOns', r'D:\WOW\INTERFACE\ADDONS\MPlusLogs\app.exe'):
            self.assertTrue(location.inside_addons(path))
        for path in (r'C:\AddOns\app.exe', r'C:\WoW\Interface\AddOns-old\app.exe', r'C:\Programs\Companion'):
            self.assertFalse(location.inside_addons(path))

    def test_copy_only_payload_and_preserve_existing_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / 'Interface/AddOns/MPlusLogs'
            (source / '_internal').mkdir(parents=True)
            (source / '_internal/companion-build.json').write_text('{"version":"1.0.0"}')
            (source / location.EXECUTABLE).write_bytes(b'fixture')
            shutil.copy2(ROOT / 'realm-slugs.json', source / 'realm-slugs.json')
            (source / 'licenses').mkdir()
            (source / 'licenses/LICENSE.txt').write_text('license fixture')
            (source / 'UI.lua').write_text('addon')
            (source / 'settings.json').write_text('private')
            destination = base / 'Programs/Companion'
            copied = location.copy_runtime(source / location.EXECUTABLE, destination)
            self.assertTrue(copied.is_file())
            self.assertEqual({path.name for path in destination.iterdir()},
                             {location.EXECUTABLE, '_internal', 'realm-slugs.json', 'licenses'})
            import realm_resolver
            mappings = realm_resolver.load_mappings(destination / 'realm-slugs.json')
            self.assertEqual(realm_resolver.resolve(mappings, 'eu', 'Гордунни'), 'gordunni')
            self.assertEqual((destination / 'licenses/LICENSE.txt').read_text(), 'license fixture')
            with self.assertRaises(FileExistsError):
                location.copy_runtime(source / location.EXECUTABLE, destination)
            self.assertEqual((source / 'UI.lua').read_text(), 'addon')
            self.assertTrue((source / location.EXECUTABLE).exists())
            with self.assertRaises(ValueError):
                location.copy_runtime(source / location.EXECUTABLE, source / 'nested')

    def test_safe_directory_does_not_overwrite_other_installation(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, LOCALAPPDATA=temporary):
            expected = Path(temporary) / 'Programs/MPlusLogs Companion'
            self.assertEqual(location.safe_directory(), expected)
            expected.mkdir(parents=True)
            self.assertEqual(location.safe_directory(), expected.with_name('MPlusLogs Companion 2'))

    def test_guard_precedes_main_and_retail_watcher(self):
        loader = importlib.machinery.SourceFileLoader('location_gui_test', str(ROOT / 'tools/companion_gui.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        gui = importlib.util.module_from_spec(spec)
        loader.exec_module(gui)
        for arguments in ([], ['--background'], ['--watch-retail']):
            with patch.object(sys, 'argv', ['Companion', *arguments]), patch.object(location, 'guard', return_value=True), \
                    patch.object(gui.windows, 'SingleInstance') as instance, patch.object(gui.tk, 'Tk') as window:
                gui.main()
                instance.assert_not_called()
                window.assert_not_called()

    def test_declining_transfer_exits_without_copying_or_launching(self):
        import windows_integration
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, 'executable', r'C:\WoW\Interface\AddOns\MPlusLogs\MPlusLogs-Companion.exe'), \
                patch.object(windows_integration, 'SingleInstance', return_value=Mock(primary=True)) as instance, \
                patch('tkinter.Tk') as window, patch('tkinter.messagebox.askyesno', return_value=False), \
                patch.object(location.local_settings, 'load', return_value={'language': 'enUS'}), \
                patch.object(location, 'safe_directory', return_value=Path(r'C:\Programs\Companion')), \
                patch.object(location, 'copy_runtime') as copy:
            self.assertTrue(location.guard())
            copy.assert_not_called()
            window.return_value.destroy.assert_called_once()
            instance.return_value.close.assert_called_once()

    def test_only_one_concurrent_relocation_prompt(self):
        import windows_integration
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, 'executable', r'C:\WoW\Interface\AddOns\MPlusLogs\MPlusLogs-Companion.exe'), \
                patch.object(windows_integration, 'SingleInstance', return_value=Mock(primary=False)), \
                patch('tkinter.Tk') as window:
            self.assertTrue(location.guard())
            window.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows process and registry integration')
    def test_locked_executable_relocation_and_owned_startup(self):
        import winreg
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler.is_file():
            self.skipTest('Requires the Windows .NET Framework compiler')
        registry = 'Software\\MPlusLogsRelocationTest-' + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as temporary:
            # Spaces and apostrophes exercise PowerShell and Windows argument quoting.
            base = Path(temporary) / "relocation user's folder"
            source = base / 'Interface/AddOns/MPlusLogs'
            (source / '_internal').mkdir(parents=True)
            (source / '_internal/companion-build.json').write_text('{"version":"1.0.0"}')
            (source / 'realm-slugs.json').write_text('{}')
            code = base / 'Fixture.cs'
            code.write_text('class Fixture { static void Main(string[] args) { if(args[0]=="hold") '
                            'System.Threading.Thread.Sleep(60000); else System.IO.File.WriteAllText(args[0], "started"); } }')
            old = source / location.EXECUTABLE
            subprocess.run([str(compiler), '/nologo', '/out:' + str(old), str(code)], check=True, capture_output=True)
            parent = subprocess.Popen([str(old), 'hold'])
            watcher = subprocess.Popen([str(old), 'hold'])
            helper = None
            try:
                time.sleep(0.2)
                with self.assertRaises(PermissionError):
                    old.unlink()
                new = location.copy_runtime(old, base / 'Programs/Companion')
                marker = base / 'new process started.txt'
                alias = base / 'old program junction'
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(source)], check=True, capture_output=True)
                alias_executable = alias / location.EXECUTABLE
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, registry) as key:
                    winreg.SetValueEx(key, 'MPlusLogs Companion', 0, winreg.REG_SZ, f'"{alias_executable}" --background')
                    winreg.SetValueEx(key, 'MPlusLogs Retail Launcher', 0, winreg.REG_SZ, f'{old} --watch-retail')
                    winreg.SetValueEx(key, 'Other program', 0, winreg.REG_SZ, 'other.exe --background')
                shortcuts = base / 'shortcuts'
                shortcuts.mkdir()
                link = shortcuts / 'Companion.lnk'
                unrelated = shortcuts / 'Other.lnk'
                def literal(value):
                    return "'" + str(value).replace("'", "''") + "'"
                setup_links = (
                    "$shell = New-Object -ComObject WScript.Shell; "
                    f"$link = $shell.CreateShortcut({literal(link)}); $link.TargetPath = {literal(alias_executable)}; $link.Save(); "
                    f"$other = $shell.CreateShortcut({literal(unrelated)}); $other.TargetPath = 'C:\\other.exe'; $other.Save(); "
                )
                script = location.relocation_script(old, new, parent.pid, [str(marker)], base, [shortcuts])
                report = base / 'shortcuts.json'
                script = setup_links + script + (
                    "; $shell = New-Object -ComObject WScript.Shell; "
                    f"$links = @($shell.CreateShortcut({literal(link)}).TargetPath, $shell.CreateShortcut({literal(unrelated)}).TargetPath); "
                    f"[IO.File]::WriteAllText({literal(report)}, ($links | ConvertTo-Json))"
                )
                script = script.replace('Software\\Microsoft\\Windows\\CurrentVersion\\Run', registry)
                encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
                helper = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertFalse(marker.exists())
                parent.terminate()
                parent.wait(timeout=10)
                stdout, stderr = helper.communicate(timeout=30)
                self.assertEqual(helper.returncode, 0, (stdout + stderr).decode(errors='replace'))
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue(marker.exists())
                watcher.wait(timeout=10)
                self.assertFalse((base / 'relocation-error.txt').exists())
                old.unlink()  # The AddOns executable is now unlocked, even though the new copy ran.
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry) as key:
                    self.assertEqual(winreg.QueryValueEx(key, 'MPlusLogs Companion')[0], f'"{new}" --background')
                    self.assertEqual(winreg.QueryValueEx(key, 'MPlusLogs Retail Launcher')[0], f'"{new}" --watch-retail')
                    self.assertEqual(winreg.QueryValueEx(key, 'Other program')[0], 'other.exe --background')
                targets = json.loads(report.read_text())
                self.assertEqual(Path(targets[0]).resolve(), new.resolve())
                self.assertEqual(targets[1], r'C:\other.exe')
            finally:
                for process in (parent, watcher, helper):
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, registry)
                except FileNotFoundError:
                    pass
