"""Upload the allowlisted addon ZIP to Wago using an Actions-only credential.

API contract: https://docs.wago.io/#manual-api-integration
"""
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen
import uuid

from upload_curseforge import validate_archive

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://addons.wago.io/api'


def release_metadata(toc, changelog):
    project = re.search(r'^## X-Wago-ID: ([A-Za-z0-9]{8})$', toc, re.M)
    version = re.search(r'^## Version: (\d+\.\d+\.\d+)$', toc, re.M)
    interfaces = re.search(r'^## Interface: ([0-9, ]+)$', toc, re.M)
    if not project or not version or not interfaces or not changelog.strip():
        raise ValueError('Missing Wago project, addon version, interfaces or changelog')
    values = [int(item.strip()) for item in interfaces[1].split(',')]
    if not values or any(not 100000 <= value <= 999999 for value in values):
        raise ValueError('Wago upload supports this Retail addon only')
    latest = max(values)
    metadata = dict(label=version[1], stability='stable', changelog=changelog,
                    supported_retail_patch=f'{latest // 10000}.{latest // 100 % 100}.{latest % 100}')
    return project[1], metadata


def main():
    token = os.environ.get('WAGO_API_TOKEN')
    if not token:
        raise RuntimeError('Missing GitHub Actions secret WAGO_API_TOKEN')
    project, metadata = release_metadata((ROOT / 'MPlusLogs.toc').read_text(encoding='utf-8'),
                                        (ROOT / 'packaging/RELEASE-NOTES.md').read_text(encoding='utf-8'))
    archive = ROOT / f'release-output/MPlusLogs-{metadata["label"]}.zip'
    validate_archive(archive)
    boundary = 'MPlusLogs' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode()
            + json.dumps(metadata).encode()
            + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{archive.name}"\r\nContent-Type: application/zip\r\n\r\n'.encode()
            + archive.read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json',
               'Content-Type': 'multipart/form-data; boundary=' + boundary}
    with urlopen(Request(f'{BASE}/projects/{project}/version', data=body, headers=headers), timeout=120) as response:
        status = response.status
    # Wago's own packager uses HTTP 200/201 as the receipt. No JSON response
    # schema is documented; requiring a body can misclassify a successful POST.
    if status not in (200, 201):
        raise RuntimeError('Wago did not confirm the upload; inspect Wago before retrying')
    report = dict(project=project, version=metadata['label'], http_status=status, accepted=True)
    (ROOT / 'release-output/wago-upload.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
