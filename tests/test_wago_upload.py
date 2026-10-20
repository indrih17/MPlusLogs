"""Wago requests use only the validated addon archive and reviewed release notes."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import MagicMock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import upload_wago as wago

TOC = '## Interface: 120007, 120100, 120105\n## Version: 0.5.29\n## X-Wago-ID: qKQgAENx\n'


class WagoTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell is required for the release workflow guard')
    def test_workflow_requires_wago_upload_or_an_existing_receipt(self):
        workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        step = workflow.split('- name: Verify Wago publication credential', 1)[1]
        guard = textwrap.dedent(step.split('run: |', 1)[1].split('      - name:', 1)[0])
        mocks = '''
            function python {
                $global:LASTEXITCODE = [int]$env:MPL_TEST_VERSION_EXIT
                if ($global:LASTEXITCODE -eq 0) { '0.5.29' }
            }
            function gh {
                if ($args[2] -ne 'v0.5.29') { throw 'Unexpected addon tag' }
                $global:LASTEXITCODE = [int]$env:MPL_TEST_RELEASE_EXIT
                $env:MPL_TEST_ASSETS
            }
        '''
        cases = (
            ('configured', 'fixture-only', 0, 0, [], True, 'configured=true'),
            ('new addon without credential', '', 0, 1, [], False, 'Missing WAGO_API_TOKEN'),
            ('CurseForge only', '', 0, 0, ['curseforge-upload.json'], False, 'Missing WAGO_API_TOKEN'),
            ('already on Wago', '', 0, 0, ['wago-upload.json'], True, 'configured=false'),
            ('version failure', '', 1, 0, ['wago-upload.json'], False, 'Addon version inspection failed'),
        )
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.test-wago-guard-') as folder:
            output = Path(folder) / 'outputs.txt'
            for name, token, version_exit, release_exit, assets, succeeds, expected in cases:
                with self.subTest(name=name):
                    output.unlink(missing_ok=True)
                    env = dict(os.environ, WAGO_API_TOKEN=token, GITHUB_OUTPUT=str(output),
                               MPL_TEST_VERSION_EXIT=str(version_exit),
                               MPL_TEST_RELEASE_EXIT=str(release_exit),
                               MPL_TEST_ASSETS=json.dumps({'assets': [{'name': asset} for asset in assets]}))
                    result = subprocess.run(
                        [shutil.which('pwsh'), '-NoProfile', '-NonInteractive', '-Command', mocks + guard],
                        env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
                    self.assertEqual(result.returncode == 0, succeeds, result.stderr)
                    if succeeds:
                        self.assertIn(expected, output.read_text(encoding='utf-8-sig'))
                    else:
                        self.assertIn(expected, result.stderr)

    def response(self, status):
        response = MagicMock()
        response.__enter__.return_value.status = status
        return response

    def test_metadata_uses_version_and_latest_supported_retail_patch(self):
        project, metadata = wago.release_metadata(TOC, 'Reviewed notes')
        self.assertEqual(project, 'qKQgAENx')
        self.assertEqual(metadata, dict(label='0.5.29', stability='stable',
                                       changelog='Reviewed notes', supported_retail_patch='12.1.5'))

    def test_bad_metadata_is_rejected(self):
        for toc, notes in ((TOC.replace('qKQgAENx', '../other'), 'notes'),
                           (TOC.replace('120007, 120100, 120105', '11509'), 'notes'),
                           (TOC, ' '), (TOC.replace('0.5.29', 'bad'), 'notes')):
            with self.subTest(toc=toc), self.assertRaises(ValueError):
                wago.release_metadata(toc, notes)

    def fixture(self):
        folder = tempfile.TemporaryDirectory(dir=ROOT, prefix='.test-wago-')
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        (root / 'packaging').mkdir()
        (root / 'release-output').mkdir()
        (root / 'MPlusLogs.toc').write_text(TOC, encoding='utf-8')
        (root / 'packaging/RELEASE-NOTES.md').write_text('Reviewed notes', encoding='utf-8')
        archive = root / 'release-output/MPlusLogs-0.5.29.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('MPlusLogs/MPlusLogs.toc', TOC)
        return root, archive

    def test_upload_multipart_and_receipt(self):
        root, archive = self.fixture()
        with patch.object(wago, 'ROOT', root), patch.dict(wago.os.environ, WAGO_API_TOKEN='fixture-only'), \
             patch.object(wago, 'urlopen', return_value=self.response(201)) as upload:
            wago.main()
        request = upload.call_args.args[0]
        self.assertEqual(request.full_url, 'https://addons.wago.io/api/projects/qKQgAENx/version')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-only')
        self.assertIn(archive.read_bytes(), request.data)
        self.assertIn(b'"supported_retail_patch": "12.1.5"', request.data)
        receipt = (root / 'release-output/wago-upload.json').read_text()
        self.assertEqual(json.loads(receipt), dict(project='qKQgAENx', version='0.5.29', http_status=201, accepted=True))
        self.assertNotIn('fixture-only', receipt)

    def test_invalid_archive_never_leaves_machine(self):
        root, archive = self.fixture()
        with zipfile.ZipFile(archive, 'a') as z:
            z.writestr('MPlusLogs/tools/settings.json', 'private')
        with patch.object(wago, 'ROOT', root), patch.dict(wago.os.environ, WAGO_API_TOKEN='fixture-only'), \
             patch.object(wago, 'urlopen') as upload, self.assertRaises(ValueError):
            wago.main()
        upload.assert_not_called()

    def test_error_response_does_not_create_receipt(self):
        for status in (202, 400, 500):
            root, _ = self.fixture()
            with patch.object(wago, 'ROOT', root), patch.dict(wago.os.environ, WAGO_API_TOKEN='fixture-only'), \
                 patch.object(wago, 'urlopen', return_value=self.response(status)), self.assertRaises(RuntimeError):
                wago.main()
            self.assertFalse((root / 'release-output/wago-upload.json').exists())

    def test_missing_credential_never_contacts_wago(self):
        with patch.dict(wago.os.environ, {}, clear=True), patch.object(wago, 'urlopen') as upload, self.assertRaises(RuntimeError):
            wago.main()
        upload.assert_not_called()
