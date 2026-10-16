"""Portable update selection, archive boundaries, locked runtime swap and rollback."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import companion_update as updates
import portable_update as portable


def package(executable=b'fixture', version='1.0.15', extras=None):
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('MPlusLogs-Companion/MPlusLogs-Companion.exe', executable)
        archive.writestr('MPlusLogs-Companion/_internal/companion-build.json', json.dumps({'version': version, 'portable': True}))
        for name, value in (extras or {}).items():
            archive.writestr(name, value)
    value = content.getvalue()
    return value, {'schema': 1, 'version': version, 'kind': 'portable', 'size': len(value),
        'sha256': hashlib.sha256(value).hexdigest(),
        'url': f'https://github.com/indrih17/MPlusLogs/releases/download/companion-v{version}/MPlusLogs-Companion-{version}-Portable.zip'}


class PortableTests(unittest.TestCase):
    def test_channel_selects_zip_and_never_falls_back_to_setup(self):
        _, data = package()
        channel = dict(data, kind='setup', url=data['url'].replace('Portable.zip', 'Setup.exe'), portable={
            key: data[key] for key in ('url', 'size', 'sha256')})
        with patch.object(updates, 'portable_build', return_value=True), patch.object(updates, 'current_version', return_value='1.0.14'):
            with patch.object(updates, 'urlopen', return_value=io.BytesIO(json.dumps(channel).encode())):
                self.assertEqual(updates.check()['kind'], 'portable')
            del channel['portable']
            with patch.object(updates, 'urlopen', return_value=io.BytesIO(json.dumps(channel).encode())):
                self.assertIsNone(updates.check())
        for changes in ({'url': data['url'].replace('Portable.zip', 'Setup.exe')},
                        {'url': 'https://example.com/archive.zip'}, {'kind': 'unknown'}):
            with self.assertRaises(ValueError):
                updates.validate_manifest(dict(data, **changes))

    def test_rejects_zip_traversal_foreign_files_and_windows_aliases(self):
        for name in ('../outside', 'MPlusLogs-Companion/../outside',
                     'MPlusLogs-Companion/_internal/../../outside',
                     'MPlusLogs-Companion/settings.json',
                     'MPlusLogs-Companion/_internal/file:stream',
                     'MPlusLogs-Companion/_internal/CON.txt',
                     'MPlusLogs-Companion/_internal/trailing. ',
                     'MPlusLogs-Companion/_INTERNAL/evil'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                value, data = package(extras={name: 'evil'})
                archive = Path(temporary) / 'update.zip'
                archive.write_bytes(value)
                with self.assertRaises(ValueError):
                    portable.prepare(archive, data)

    def test_checks_payload_version_and_download_integrity(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'update.zip'
            value, data = package()
            archive.write_bytes(value)
            payload = portable.prepare(archive, data)
            try:
                self.assertTrue((payload / portable.EXECUTABLE).exists())
            finally:
                shutil.rmtree(payload.parent)
            with self.assertRaises(ValueError):
                portable.prepare(archive, dict(data, version='1.0.16'))
            archive.write_bytes(value + b'tampered')
            with self.assertRaises(ValueError):
                portable.prepare(archive, data)

    def test_corrupt_archives_are_reported_as_update_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'update.zip'
            content = b'not a zip'
            archive.write_bytes(content)
            _, data = package()
            data.update(size=len(content), sha256=hashlib.sha256(content).hexdigest())
            with self.assertRaises(ValueError):
                portable.prepare(archive, data)

    def test_portable_never_launches_setup_and_failed_helper_leaves_no_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content, data = package()
            archive = root / 'update.zip'
            archive.write_bytes(content)
            app = root / 'app'
            (app / '_internal').mkdir(parents=True)
            executable = app / portable.EXECUTABLE
            executable.write_bytes(b'old')
            results = root / 'results'
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(executable)), \
                    patch.object(updates, 'portable_build', return_value=True), \
                    patch.object(updates, 'launch_helper', side_effect=OSError('cannot start helper')) as launch:
                payload = portable.prepare(archive, data)
                with patch.object(portable, 'prepare', return_value=payload):
                    with self.assertRaises(OSError):
                        updates.launch_installer(archive, data, result_root=results)
                self.assertFalse(payload.parent.exists())
                launch.reset_mock()
                setup_data = dict(data, kind='setup', url=data['url'].replace('Portable.zip', 'Setup.exe'))
                with self.assertRaises(ValueError):
                    updates.launch_installer(archive, setup_data, result_root=results)
                launch.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows portable update helper')
    def test_locked_runtime_update_and_failed_smoke_rollback_preserve_user_files(self):
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler.exists():
            self.skipTest('Requires Windows .NET compiler')
        with tempfile.TemporaryDirectory(prefix='MPlusLogs-portable-test-') as temporary:
            root = Path(temporary)
            source = root / 'Fixture.cs'
            source.write_text(r'''using System; using System.IO;
class Fixture { static void Main(string[] args) {
if (args.Length > 0 && args[0] == "hold") { System.Threading.Thread.Sleep(60000); return; }
if (args.Length > 1 && args[0] == "--self-test-report") {
  if (File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "_internal", "reject"))) { Environment.Exit(7); }
  File.WriteAllText(args[1], "{\"ok\":true}");
} } }''')
            fixture = root / portable.EXECUTABLE
            subprocess.run([str(compiler), '/nologo', '/out:' + str(fixture), str(source)], check=True, capture_output=True)
            for reject in (False, True):
                app = root / ('failed' if reject else "user's folder")
                app.mkdir()
                (app / '_internal').mkdir()
                (app / '_internal/companion-build.json').write_text('{"version":"1.0.14","portable":true}')
                (app / '_internal/old-only.dll').write_text('old')
                shutil.copy2(fixture, app / portable.EXECUTABLE)
                (app / 'user-notes.txt').write_text('preserve me')
                (app / 'OtherAddon').mkdir()
                (app / 'OtherAddon/OtherAddon.toc').write_text('addon')
                results = root / ('result-failed' if reject else 'result-ok')
                results.mkdir()
                value, data = package(fixture.read_bytes(), extras={
                    'MPlusLogs-Companion/_internal/' + ('reject' if reject else 'new-only.dll'): 'new'})
                archive = root / 'update.zip'
                archive.write_bytes(value)
                payload = portable.prepare(archive, data)
                locked = subprocess.Popen([str(app / portable.EXECUTABLE), 'hold'])
                departed = subprocess.Popen([sys.executable, '-c', 'pass'])
                departed.wait(timeout=10)
                try:
                    with self.assertRaises(PermissionError):
                        (app / portable.EXECUTABLE).unlink()
                    helper = portable.script(payload, data, app / portable.EXECUTABLE, departed.pid, results)
                    encoded = base64.b64encode(helper.encode('utf-16-le')).decode()
                    run = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                        '-EncodedCommand', encoded], capture_output=True, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
                    self.assertEqual(run.returncode, 0, (run.stdout + run.stderr).decode(errors='replace'))
                    result = json.loads((results / 'update-result.json').read_text(encoding='utf-8-sig'))
                    self.assertEqual(result['success'], not reject, result)
                    self.assertFalse(result['rollback_error'], result)
                    self.assertEqual(result['installed_version'], '1.0.14' if reject else '1.0.15')
                    self.assertEqual((app / 'user-notes.txt').read_text(), 'preserve me')
                    self.assertEqual((app / 'OtherAddon/OtherAddon.toc').read_text(), 'addon')
                    self.assertEqual((app / '_internal/old-only.dll').exists(), reject)
                    self.assertEqual((app / '_internal/new-only.dll').exists(), not reject)
                    self.assertFalse(any(app.glob('.portable-update-*')))
                    locked.wait(timeout=5)
                    # The restarted fixture exits immediately, but Windows can
                    # retain its image lock briefly after Start-Process returns.
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            (app / portable.EXECUTABLE).unlink()
                            break
                        except PermissionError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(0.05)
                finally:
                    if locked.poll() is None:
                        locked.kill()
                        locked.wait(timeout=5)
                    if payload.parent.exists():
                        shutil.rmtree(payload.parent)


if __name__ == '__main__':
    unittest.main()
