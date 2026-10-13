"""Bounded HTTPS update checks and verified installer downloads. No WCL credentials."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import local_settings

CHANNEL = "https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/companion-update.json"
MAX_INSTALLER = 250 * 1024 * 1024
BUILD = Path(__file__).with_name("companion-build.json")


def last_result():
    path = local_settings.PATH.parent / "update-result.json"
    try:
        if path.stat().st_size > 16384:
            return None
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or type(data.get("success")) is not bool:
            return None
        version_tuple(data.get("expected_version"))
        return data
    except (OSError, ValueError, TypeError):
        return None


def current_version():
    if getattr(sys, "frozen", False):
        return json.loads(BUILD.read_text(encoding="utf-8"))["version"]
    import companion_version
    return companion_version.version()


def local_preview():
    if getattr(sys,"frozen",False):
        return bool(json.loads(BUILD.read_text(encoding="utf-8")).get("preview"))
    return (Path(__file__).resolve().parents[1]/".release-hold").exists()


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Invalid Companion version")
    return tuple(map(int, value.split(".")))


def validate_manifest(data):
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Unsupported update manifest")
    version_tuple(data.get("version"))
    expected = f"https://github.com/indrih17/MPlusLogs/releases/download/companion-v{data['version']}/MPlusLogs-Companion-{data['version']}-Setup.exe"
    if data.get("url") != expected or not re.fullmatch(r"[0-9a-f]{64}", data.get("sha256", "")):
        raise ValueError("Invalid update source or checksum")
    if type(data.get("size")) is not int or not 0 < data["size"] <= MAX_INSTALLER:
        raise ValueError("Invalid installer size")
    return data


def check():
    request = Request(CHANNEL, headers={"User-Agent": "MPlusLogs-Companion", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=20) as response:
        content = response.read(16385)
    if len(content) > 16384:
        raise ValueError("Update manifest is too large")
    data = validate_manifest(json.loads(content))
    return data if version_tuple(data["version"]) > version_tuple(current_version()) else None


def download(data):
    data = validate_manifest(data)
    folder = Path(tempfile.mkdtemp(prefix="MPlusLogs-update-"))
    target = folder / "Setup.exe"
    digest, size = hashlib.sha256(), 0
    try:
        with urlopen(Request(data["url"], headers={"User-Agent": "MPlusLogs-Companion"}), timeout=30) as response, target.open("wb") as output:
            while chunk := response.read(65536):
                size += len(chunk)
                if size > data["size"]:
                    raise ValueError("Installer exceeds advertised size")
                digest.update(chunk)
                output.write(chunk)
        if size != data["size"] or digest.hexdigest() != data["sha256"]:
            raise ValueError("Installer checksum mismatch")
        return target
    except Exception:
        target.unlink(missing_ok=True)
        folder.rmdir()
        raise


def installer_script(target, data, executable, parent_pid, result_root):
    """Persist installer failures and verify the installed build before restarting."""
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"
    directory_arg = '/DIR="' + str(executable.parent) + '"'
    log_arg = '/LOG="' + str(result_root / "update-install.log") + '"'
    installed_build = executable.parent / "_internal/companion-build.json"
    return (
        "$ErrorActionPreference = 'Stop'; "
        f"Wait-Process -Id {parent_pid} -ErrorAction SilentlyContinue; "
        "$code = -1; $installed = ''; $failure = ''; $success = $false; "
        f"try {{ $installer = Start-Process -FilePath {literal(target)} -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NORESTARTAPPLICATIONS','/RESTARTEXITCODE=3010','/CLOSEAPPLICATIONS','/FORCECLOSEAPPLICATIONS','/UPDATECOMPANION=1', {literal(directory_arg)}, {literal(log_arg)}) -PassThru -Wait; "
        "$code = $installer.ExitCode; "
        f"if (Test-Path -LiteralPath {literal(installed_build)}) {{ $installed = (Get-Content -LiteralPath {literal(installed_build)} -Raw | ConvertFrom-Json).version }}; "
        f"$success = $code -eq 0 -and $installed -eq {literal(data['version'])}; "
        "if (!$success) { $failure = 'Installer failed or installed version does not match the update' } "
        "} catch { $failure = $_.Exception.Message } finally { "
        f"$result = @{{success=$success; exit_code=$code; expected_version={literal(data['version'])}; installed_version=$installed; error=$failure; log={literal(result_root / 'update-install.log')}}}; "
        f"[IO.File]::WriteAllText({literal(result_root / 'update-result.json')}, ($result | ConvertTo-Json), [Text.Encoding]::UTF8); "
        f"if (Test-Path -LiteralPath {literal(executable)}) {{ Start-Process -FilePath {literal(executable)} }}; "
        f"Remove-Item -LiteralPath {literal(target)} -ErrorAction SilentlyContinue; "
        f"Remove-Item -LiteralPath {literal(target.parent)} -ErrorAction SilentlyContinue }}"
    )


def launch_installer(target, data, result_root=None):
    """Wait for this process to exit, then install and restart at the same location."""
    if not getattr(sys, "frozen", False):
        raise ValueError("Updates require an installed or portable executable")
    target = Path(target).resolve()
    validate_manifest(data)
    if target.stat().st_size != data["size"] or hashlib.sha256(target.read_bytes()).hexdigest() != data["sha256"]:
        raise ValueError("Installer changed after download")
    executable = Path(sys.executable).resolve()
    result_root = local_settings.PATH.parent if result_root is None else Path(result_root)
    result_root.mkdir(parents=True, exist_ok=True)
    script = installer_script(target, data, executable, os.getpid(), result_root)
    launch_helper(script)


def launch_helper(script):
    """Run a detached helper with the system DLL search path and a fresh frozen environment."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    # PyInstaller's DLL search directory is inherited by external executables.
    # Use Windows' normal search path for the helper/installer, then restore ours.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_ulong, ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    buffer = ctypes.create_unicode_buffer(32768)
    kernel.GetDllDirectoryW(len(buffer), buffer)
    original = buffer.value or None
    if not kernel.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1"))
    finally:
        kernel.SetDllDirectoryW(original)
