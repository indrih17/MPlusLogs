"""Validate portable payloads and replace only Companion-owned files with rollback."""
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

EXECUTABLE = 'MPlusLogs-Companion.exe'
OWNED = (EXECUTABLE, '_internal', 'realm-slugs.json', 'licenses', 'README.txt', 'COMPANION-README.txt')
MAX_EXPANDED = 1024 * 1024 * 1024


def prepare(archive, data):
    archive = Path(archive)
    if archive.stat().st_size != data['size'] or hashlib.sha256(archive.read_bytes()).hexdigest() != data['sha256']:
        raise ValueError('Portable archive changed after download')
    stage = Path(tempfile.mkdtemp(prefix='MPlusLogs-portable-update-'))
    try:
        total, seen = 0, set()
        with zipfile.ZipFile(archive) as package:
            if len(package.infolist()) > 10000:
                raise ValueError('Too many archive entries')
            for entry in package.infolist():
                path = PurePosixPath(entry.filename)
                parts = path.parts
                key = entry.filename.rstrip('/').casefold()
                if (not parts or parts[0] != 'MPlusLogs-Companion' or path.is_absolute()
                        or any(part in ('.', '..') or ':' in part or part.endswith((' ', '.')) for part in parts)
                        or '\\' in entry.filename or key in seen
                        or stat.S_ISLNK(entry.external_attr >> 16)
                        or (len(parts) > 1 and parts[1] not in OWNED)
                        or (len(parts) > 2 and parts[1] not in ('_internal', 'licenses'))
                        or any(part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                            *('COM' + str(i) for i in range(1, 10)), *('LPT' + str(i) for i in range(1, 10))}
                               for part in parts)):
                    raise ValueError('Unsafe portable archive entry')
                seen.add(key)
                total += entry.file_size
                if total > MAX_EXPANDED:
                    raise ValueError('Expanded portable archive is too large')
                destination = stage.joinpath(*parts)
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(entry) as source, destination.open('xb') as output:
                        shutil.copyfileobj(source, output)
        payload = stage / 'MPlusLogs-Companion'
        build = json.loads((payload / '_internal/companion-build.json').read_text(encoding='utf-8'))
        if not isinstance(build, dict) or build.get('version') != data['version'] or build.get('portable') is not True or not (payload / EXECUTABLE).is_file():
            raise ValueError('Wrong portable build')
        for name in OWNED:
            path = payload / name
            if path.exists() and path.is_dir() != (name in ('_internal', 'licenses')):
                raise ValueError('Wrong portable payload layout')
        return payload
    except Exception as exc:
        shutil.rmtree(stage)
        if isinstance(exc, (zipfile.BadZipFile, RuntimeError, NotImplementedError, KeyError, EOFError)):
            raise ValueError('Invalid portable ZIP') from exc
        raise


def script(payload, data, executable, parent_pid, result_root, archive=None):
    executable = Path(executable).resolve()
    app = executable.parent
    if executable.name != EXECUTABLE or not (app / '_internal').is_dir():
        raise ValueError('Not a portable Companion folder')
    # Refuse links in managed trees; rollback must never traverse outside the app.
    for name in OWNED:
        path = app / name
        paths = [path, *path.rglob('*')] if path.is_dir() else [path]
        if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in paths):
            raise ValueError('Linked portable runtime cannot be updated')
    temporary = Path(tempfile.gettempdir()).resolve()
    cleanup = [Path(payload).resolve().parent]
    if archive is not None:
        folder = Path(archive).resolve().parent
        if folder.parent == temporary and folder.name.startswith('MPlusLogs-update-'):
            cleanup.append(folder)
    config = {'payload': str(Path(payload).resolve()), 'app': str(app), 'executable': str(executable),
              'pid': int(parent_pid), 'results': str(Path(result_root).resolve()),
              'version': data['version'], 'owned': OWNED, 'temporary': str(temporary),
              'cleanup': [str(folder) for folder in cleanup if folder.parent == temporary and
                          folder.name.startswith(('MPlusLogs-portable-update-', 'MPlusLogs-update-'))]}
    encoded = base64.b64encode(json.dumps(config).encode()).decode('ascii')
    return "$c = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')) | ConvertFrom-Json;\n" + HELPER


HELPER = r'''
$ErrorActionPreference = 'Stop'
$app = [IO.Path]::GetFullPath($c.app)
$payload = [IO.Path]::GetFullPath($c.payload)
$work = Join-Path $app ('.portable-update-' + [Guid]::NewGuid().ToString('N'))
$backup = Join-Path $work 'backup'
$log = Join-Path $c.results 'update-install.log'
$resultFile = Join-Path $c.results 'update-result.json'
$success = $false; $failure = ''; $installed = ''; $rollbackError = ''
$moved = @(); $placed = @()
function CheckedChild([string]$root, [string]$name) {
    $full = [IO.Path]::GetFullPath((Join-Path $root $name))
    if (!$full.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escaped update folder' }
    return $full
}
function RemoveOwned([string]$root, [string]$name) {
    $path = CheckedChild $root $name
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}
try {
    New-Item -ItemType Directory -Path $backup | Out-Null
    Wait-Process -Id $c.pid -Timeout 60 -ErrorAction SilentlyContinue
    # The Retail watcher can hold the same runtime open after the main UI exits.
    $session = (Get-Process -Id $PID).SessionId
    Get-Process -Name 'MPlusLogs-Companion' -ErrorAction SilentlyContinue |
        Where-Object { $_.SessionId -eq $session -and $_.Path -eq $c.executable } |
        Stop-Process -Force
    Add-Content -LiteralPath $log -Value 'Portable update: replacing Companion runtime'
    foreach ($name in $c.owned) {
        $old = CheckedChild $app $name
        if (Test-Path -LiteralPath $old) {
            Move-Item -LiteralPath $old -Destination (CheckedChild $backup $name)
            $moved += $name
        }
    }
    foreach ($name in $c.owned) {
        $source = CheckedChild $payload $name
        if (Test-Path -LiteralPath $source) {
            $placed += $name
            Copy-Item -LiteralPath $source -Destination (CheckedChild $app $name) -Recurse
        }
    }
    $installed = (Get-Content -LiteralPath (Join-Path $app '_internal\companion-build.json') -Raw | ConvertFrom-Json).version
    if ($installed -ne $c.version) { throw 'Portable version mismatch' }
    $proof = Join-Path $work 'smoke.json'
    $arguments = '--self-test-report "' + $proof + '"'
    $probe = Start-Process -FilePath $c.executable -ArgumentList $arguments -WindowStyle Hidden -PassThru
    if (!$probe.WaitForExit(30000)) { $probe.Kill(); $probe.WaitForExit(); throw 'Portable self-test timed out' }
    if ($probe.ExitCode -ne 0 -or !(Test-Path -LiteralPath $proof)) { throw 'Portable self-test failed' }
    if (!(Get-Content -LiteralPath $proof -Raw | ConvertFrom-Json).ok) { throw 'Portable self-test rejected the new runtime' }
    $success = $true
} catch {
    $failure = $_.Exception.Message
    try {
        foreach ($name in $placed) { RemoveOwned $app $name }
        foreach ($name in $moved) {
            Move-Item -LiteralPath (CheckedChild $backup $name) -Destination (CheckedChild $app $name)
        }
        $installed = (Get-Content -LiteralPath (Join-Path $app '_internal\companion-build.json') -Raw | ConvertFrom-Json).version
    } catch { $rollbackError = $_.Exception.Message }
} finally {
    $result = @{success=$success; expected_version=$c.version; installed_version=$installed; error=$failure; rollback_error=$rollbackError; log=$log}
    [IO.File]::WriteAllText($resultFile, ($result | ConvertTo-Json), [Text.Encoding]::UTF8)
    Add-Content -LiteralPath $log -Value ($result | ConvertTo-Json -Compress)
    if (!$rollbackError -and (Test-Path -LiteralPath $c.executable)) {
        Start-Process -FilePath $c.executable -WorkingDirectory $app
    }
    # Work is an exclusively created child of this exact app; preserve backups
    # on rollback failure instead of deleting the only recoverable old runtime.
    if (!$rollbackError -and (Test-Path -LiteralPath $work)) {
        if ([IO.Path]::GetDirectoryName($work) -ne $app -or [IO.Path]::GetFileName($work) -notlike '.portable-update-*') { throw 'Unsafe work folder' }
        Remove-Item -LiteralPath $work -Recurse -Force
    }
    if (!$rollbackError) {
        foreach ($folder in $c.cleanup) {
            $full = [IO.Path]::GetFullPath($folder)
            if ([IO.Path]::GetDirectoryName($full) -ne $c.temporary -or
                [IO.Path]::GetFileName($full) -notmatch '^MPlusLogs-(portable-update|update)-') { throw 'Unsafe temporary folder' }
            if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
        }
    }
}
'''
