"""Opt-in background launcher: detects Retail executable paths, never game memory."""
import ctypes
from ctypes import wintypes as wt
from pathlib import PureWindowsPath
import subprocess
import time
import windows_integration as windows


def is_retail_path(path):
    executable = PureWindowsPath(path)
    return executable.name.casefold() == "wow.exe" and executable.parent.name.casefold() == "_retail_"


class ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize",wt.DWORD),("cntUsage",wt.DWORD),("th32ProcessID",wt.DWORD),
                ("th32DefaultHeapID",ctypes.c_size_t),("th32ModuleID",wt.DWORD),
                ("cntThreads",wt.DWORD),("th32ParentProcessID",wt.DWORD),("pcPriClassBase",wt.LONG),
                ("dwFlags",wt.DWORD),("szExeFile",wt.WCHAR*260)]


def retail_processes():
    kernel = ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD,wt.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.Process32FirstW.argtypes = [wt.HANDLE,ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wt.HANDLE,ctypes.POINTER(ProcessEntry)]
    kernel.OpenProcess.argtypes = [wt.DWORD,wt.BOOL,wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wt.HANDLE,wt.DWORD,wt.LPWSTR,ctypes.POINTER(wt.DWORD)]
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    found = set()
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        valid = kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while valid:
            if entry.szExeFile.casefold() == "wow.exe":
                process = kernel.OpenProcess(0x1000,False,entry.th32ProcessID)
                if process:
                    try:
                        path = ctypes.create_unicode_buffer(32768)
                        size = wt.DWORD(len(path))
                        if kernel.QueryFullProcessImageNameW(process,0,path,ctypes.byref(size)) and is_retail_path(path.value):
                            found.add(entry.th32ProcessID)
                    finally:
                        kernel.CloseHandle(process)
            valid = kernel.Process32NextW(snapshot,ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(snapshot)
    return found


class LaunchState:
    def __init__(self):
        self.previous = set()

    def update(self, processes, companion_running):
        fresh = set(processes) - self.previous
        self.previous = set(processes)
        return bool(fresh) and not companion_running


def watch():
    instance = windows.SingleInstance(namespace="RetailWatcher",notify=False)
    try:
        if not instance.primary:
            return
        state = LaunchState()
        while windows.retail_autostart_enabled():
            try:
                processes = retail_processes()
                previous = set(state.previous)
                if state.update(processes,windows.instance_running()):
                    try:
                        subprocess.Popen(windows.startup_args("--background"),creationflags=subprocess.CREATE_NO_WINDOW)
                    except OSError:
                        state.previous = previous  # Retry a failed launch without losing the game transition.
            except OSError:
                pass  # Temporary enumeration failure must not interpret Retail as a new launch.
            time.sleep(2)
    finally:
        instance.close()
