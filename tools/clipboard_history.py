"""Best-effort removal of exact, processed MPlusLogs requests from Win+V.

Use the Windows WinRT API through built-in Windows PowerShell, without a
runtime download or extra Python packages. Never clear the whole history or
modify the current clipboard. History contents are never logged or saved.
"""
import base64
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.ApplicationModel.DataTransfer.Clipboard, Windows.ApplicationModel.DataTransfer, ContentType=WindowsRuntime]
$null = [Windows.ApplicationModel.DataTransfer.ClipboardHistoryItemsResult, Windows.ApplicationModel.DataTransfer, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await($operation, [Type]$resultType) {
    $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
    if (!$task.Wait(2000)) { throw 'History operation timed out' }
    return $task.Result
}
function Remove-ExactRequest($items, [string]$expected, $readText, $deleteItem) {
    $removed = 0
    foreach ($item in $items) {
        if ($item.Content.Contains('Text')) {
            $text = & $readText $item
            if ([string]::Equals($text, $expected, [StringComparison]::Ordinal)) {
                if (& $deleteItem $item) { $removed++ }
            }
        }
    }
    return $removed
}
# Request text travels over stdin, never as shell code or command arguments.
$expected = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadToEnd().Trim()))
$result = Await ([Windows.ApplicationModel.DataTransfer.Clipboard]::GetHistoryItemsAsync()) ([Windows.ApplicationModel.DataTransfer.ClipboardHistoryItemsResult])
if ($result.Status.ToString() -ne 'Success') { exit 2 }
$read = { param($item) Await ($item.Content.GetTextAsync()) ([string]) }
$delete = { param($item) [Windows.ApplicationModel.DataTransfer.Clipboard]::DeleteItemFromHistory($item) }
$removed = Remove-ExactRequest $result.Items $expected $read $delete
[Console]::Out.Write($removed)
'''


def valid_request(text):
    if not isinstance(text, str) or len(text) > 500000:
        return False
    # Import lazily: the protocol module itself imports the clipboard bridge.
    import clipboard_protocol
    return clipboard_protocol.unwrap_request(text) is not None


def remove_request(text):
    """Return a removal count, or None if history is disabled/unavailable."""
    if sys.platform != "win32" or not valid_request(text):
        return None
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii")],
            input=base64.b64encode(text.encode("utf-8")).decode("ascii"),
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


_requests = queue.Queue(maxsize=32)
_lock = threading.Lock()
_worker = None


def _clean():
    while True:
        text = _requests.get()
        try:
            # History is populated asynchronously by Windows after a copy.
            for attempt in range(3):
                removed = remove_request(text)
                if removed is None or removed > 0:
                    break
                if attempt < 2:
                    time.sleep(0.25)
        except Exception:
            # An optional Windows API must not terminate the cleanup worker.
            pass
        finally:
            _requests.task_done()
            text = None


def forget_request(text):
    """Queue only a recognized request already consumed by Companion."""
    global _worker
    if sys.platform != "win32" or not valid_request(text):
        return
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_clean, name="MPlusLogsClipboardHistory", daemon=True)
            _worker.start()
    try:
        _requests.put_nowait(text)
    except queue.Full:
        pass
