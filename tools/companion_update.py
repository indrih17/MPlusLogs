"""Bounded HTTPS update checks and verified installer downloads. No WCL credentials."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

CHANNEL = "https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/companion-update.json"
MAX_INSTALLER = 250 * 1024 * 1024
BUILD = Path(__file__).with_name("companion-build.json")


def current_version():
    if getattr(sys, "frozen", False):
        return json.loads(BUILD.read_text(encoding="utf-8"))["version"]
    import companion_version
    return companion_version.version()


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


def launch_installer(target, data):
    """Wait for this process to exit, then install and restart at the same location."""
    if not getattr(sys, "frozen", False):
        raise ValueError("Updates require an installed or portable executable")
    target = Path(target).resolve()
    validate_manifest(data)
    if target.stat().st_size != data["size"] or hashlib.sha256(target.read_bytes()).hexdigest() != data["sha256"]:
        raise ValueError("Installer changed after download")
    executable = Path(sys.executable).resolve()
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"
    directory_arg = '/DIR="' + str(executable.parent) + '"'
    script = (
        f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
        f"try {{ $installer = Start-Process -FilePath {literal(target)} -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/UPDATECOMPANION=1', {literal(directory_arg)}) -PassThru -Wait }} finally {{ "
        f"if (Test-Path -LiteralPath {literal(executable)}) {{ Start-Process -FilePath {literal(executable)} }}; "
        f"Remove-Item -LiteralPath {literal(target)} -ErrorAction SilentlyContinue; "
        f"Remove-Item -LiteralPath {literal(target.parent)} -ErrorAction SilentlyContinue }}"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                     creationflags=subprocess.CREATE_NO_WINDOW)
