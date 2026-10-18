"""Windows tray, per-session single instance and opt-in per-user startup. Stdlib only."""
import ctypes
from ctypes import wintypes as wt
from pathlib import Path
import subprocess
import sys
import threading
from companion_i18n import tr

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "MPlusLogs Companion"
RETAIL_WATCHER_NAME = "MPlusLogs Retail Launcher"


def startup_args(mode="--background"):
    if getattr(sys, "frozen", False):
        args = [sys.executable, mode]
    else:
        runtime = Path(sys.executable).with_name("pythonw.exe")
        args = [str(runtime), str(Path(__file__).with_name("companion_gui.pyw")), mode]
    return args


def startup_command(mode="--background"):
    return subprocess.list2cmdline(startup_args(mode))


def retail_autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RETAIL_WATCHER_NAME)
            return value == startup_command("--watch-retail")
    except FileNotFoundError:
        return False


def set_retail_autostart(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RETAIL_WATCHER_NAME, 0, winreg.REG_SZ, startup_command("--watch-retail"))
        else:
            try:
                winreg.DeleteValue(key, RETAIL_WATCHER_NAME)
            except FileNotFoundError:
                pass


def instance_running(namespace="Singleton"):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
    kernel.OpenMutexW.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    handle = kernel.OpenMutexW(0x100000, False, rf"Local\MPlusLogs.Companion.{namespace}.v1")
    if handle:
        kernel.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == 5  # An inaccessible existing mutex still means a running app.


def ensure_retail_watcher():
    if retail_autostart_enabled() and not instance_running("RetailWatcher"):
        subprocess.Popen(startup_args("--watch-retail"), creationflags=subprocess.CREATE_NO_WINDOW)


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value == startup_command()
    except FileNotFoundError:
        return False


def set_autostart(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


class SingleInstance:
    def __init__(self, namespace="Singleton", notify=True):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
        self.kernel.CreateMutexW.restype = wt.HANDLE
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
        self.kernel.CreateEventW.restype = wt.HANDLE
        self.kernel.SetEvent.argtypes = [wt.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        self.kernel.CloseHandle.argtypes = [wt.HANDLE]
        self.mutex = self.kernel.CreateMutexW(None, False, rf"Local\MPlusLogs.Companion.{namespace}.v1")
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.primary = ctypes.get_last_error() != 183
        event_name = "Show" if namespace == "Singleton" else namespace + ".Show"
        self.event = self.kernel.CreateEventW(None, False, False, rf"Local\MPlusLogs.Companion.{event_name}.v1")
        if not self.event:
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.primary and notify:
            self.kernel.SetEvent(self.event)

    def show_requested(self):
        return self.kernel.WaitForSingleObject(self.event, 0) == 0

    def close(self):
        for name in ("event", "mutex"):
            handle = getattr(self, name, None)
            if handle:
                self.kernel.CloseHandle(handle)
                setattr(self, name, None)


class Tray:
    """Own native message loop; send only queue messages to Tk's main thread."""
    def __init__(self, messages):
        self.messages = messages
        self.hwnd = None
        self.error = None
        self.ready = threading.Event()
        self.cancel_start = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        started = self.ready.wait(5)
        if not started or self.error:
            self.cancel_start.set()
            self.thread.join(timeout=2)
            detail = f" ({self.error})" if self.error else ""
            if not started and not detail:
                detail = " (startup timed out)"
            raise OSError("Не удалось создать значок в трее." + detail)

    def run(self):
        try:
            self._loop()
        except Exception as exc:
            self.error = type(exc).__name__
            self.ready.set()
            self.messages.put(("tray_error", "Значок в трее недоступен. Окно остаётся открытым."))

    def _loop(self):
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        result_type = ctypes.c_ssize_t
        proc_type = ctypes.WINFUNCTYPE(result_type, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

        class WindowClass(ctypes.Structure):
            _fields_ = [("style", wt.UINT), ("proc", proc_type), ("clsExtra", ctypes.c_int),
                        ("wndExtra", ctypes.c_int), ("instance", wt.HINSTANCE), ("icon", wt.HANDLE),
                        ("cursor", wt.HANDLE), ("background", wt.HANDLE), ("menu", wt.LPCWSTR), ("name", wt.LPCWSTR)]

        class Guid(ctypes.Structure):
            _fields_ = [("a", wt.DWORD), ("b", wt.WORD), ("c", wt.WORD), ("d", wt.BYTE * 8)]

        class NotifyIcon(ctypes.Structure):
            _fields_ = [("size", wt.DWORD), ("hwnd", wt.HWND), ("id", wt.UINT), ("flags", wt.UINT),
                        ("message", wt.UINT), ("icon", wt.HANDLE), ("tip", wt.WCHAR * 128),
                        ("state", wt.DWORD), ("stateMask", wt.DWORD), ("info", wt.WCHAR * 256),
                        ("version", wt.UINT), ("title", wt.WCHAR * 64), ("infoFlags", wt.DWORD),
                        ("guid", Guid), ("balloonIcon", wt.HANDLE)]

        user.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        user.DefWindowProcW.restype = result_type
        user.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
        user.CreateWindowExW.restype = wt.HWND
        user.RegisterClassW.argtypes = [ctypes.POINTER(WindowClass)]
        user.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
        user.LoadIconW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
        user.LoadIconW.restype = wt.HANDLE
        user.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
        user.LoadImageW.restype = wt.HANDLE
        user.DestroyIcon.argtypes = [wt.HANDLE]
        user.CreatePopupMenu.restype = wt.HMENU
        user.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
        user.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p]
        user.DestroyMenu.argtypes = [wt.HMENU]
        user.SetForegroundWindow.argtypes = [wt.HWND]
        user.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        user.DestroyWindow.argtypes = [wt.HWND]
        user.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
        user.GetMessageW.restype = ctypes.c_int
        user.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
        user.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
        user.DispatchMessageW.restype = result_type
        user.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
        kernel.GetModuleHandleW.argtypes = [wt.LPCWSTR]
        kernel.GetModuleHandleW.restype = wt.HINSTANCE
        shell.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NotifyIcon)]
        shell.Shell_NotifyIconW.restype = wt.BOOL
        restart_message = user.RegisterWindowMessageW("TaskbarCreated")
        icon_message = 0x8001
        data = NotifyIcon()

        @proc_type
        def proc(hwnd, message, wparam, lparam):
            if message == icon_message + 1:
                data.tip = tr("MPlusLogs — помощник Warcraft Logs")[:127]
                shell.Shell_NotifyIconW(1, ctypes.byref(data))
                return 0
            if message == icon_message + 2:
                title, text = self.notification
                data.title, data.info, data.infoFlags = title[:63], text[:255], 1
                data.flags = 16
                shell.Shell_NotifyIconW(1, ctypes.byref(data))
                data.flags = 1 | 2 | 4
                return 0
            if message == restart_message:
                shell.Shell_NotifyIconW(0, ctypes.byref(data))
                return 0
            if message == icon_message:
                if lparam == 0x405:  # NIN_BALLOONUSERCLICK
                    self.messages.put(("show", None))
                if lparam == 0x202:  # left button up
                    self.messages.put(("show", None))
                elif lparam in (0x205, 0x7B):
                    menu = user.CreatePopupMenu()
                    user.AppendMenuW(menu, 0, 1, tr("Открыть MPlusLogs"))
                    user.AppendMenuW(menu, 0, 3, tr("Выйти"))
                    point = wt.POINT()
                    user.GetCursorPos(ctypes.byref(point))
                    user.SetForegroundWindow(hwnd)
                    command = user.TrackPopupMenu(menu, 0x100 | 0x2, point.x, point.y, 0, hwnd, None)
                    user.DestroyMenu(menu)
                    user.PostMessageW(hwnd, 0, 0, 0)
                    if command:
                        self.messages.put(({1: "show", 3: "exit"}[command], None))
                return 0
            if message == 0x10:
                user.DestroyWindow(hwnd)
                return 0
            if message == 2:
                user.PostQuitMessage(0)
                return 0
            return user.DefWindowProcW(hwnd, message, wparam, lparam)

        instance = kernel.GetModuleHandleW(None)
        name = "MPlusLogsTrayWindow"
        wc = WindowClass()
        wc.proc, wc.instance, wc.name = proc, instance, name
        if not user.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = user.CreateWindowExW(0, name, APP_NAME, 0, 0, 0, 0, 0, None, None, instance, None)
        if not self.hwnd:
            user.UnregisterClassW(name, instance)
            raise ctypes.WinError(ctypes.get_last_error())
        data.size = ctypes.sizeof(data)
        data.hwnd, data.id, data.flags, data.message = self.hwnd, 1, 1 | 2 | 4, icon_message
        custom_icon = user.LoadImageW(None, str(Path(__file__).with_name("assets") / "mpluslogs.ico"), 1,
                                      user.GetSystemMetrics(49), user.GetSystemMetrics(50), 0x10)
        data.icon = custom_icon or user.LoadIconW(None, ctypes.c_void_p(32512))
        data.tip = tr("MPlusLogs — помощник Warcraft Logs")[:127]
        try:
            if self.cancel_start.is_set():
                return
            if not shell.Shell_NotifyIconW(0, ctypes.byref(data)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.ready.set()
            msg = wt.MSG()
            while True:
                received = user.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if received <= 0:
                    if received == -1:
                        raise ctypes.WinError(ctypes.get_last_error())
                    break
                user.TranslateMessage(ctypes.byref(msg))
                user.DispatchMessageW(ctypes.byref(msg))
        finally:
            shell.Shell_NotifyIconW(2, ctypes.byref(data))
            if custom_icon:
                user.DestroyIcon(custom_icon)
            user.DestroyWindow(self.hwnd)
            self.hwnd = None
            user.UnregisterClassW(name, instance)

    def refresh_language(self):
        if self.hwnd:
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
            user.PostMessageW(self.hwnd, 0x8002, 0, 0)

    def notify(self, title, text):
        self.notification = (title, text)
        if self.hwnd:
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
            user.PostMessageW(self.hwnd, 0x8003, 0, 0)

    def close(self):
        if self.hwnd:
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
            user.PostMessageW(self.hwnd, 0x10, 0, 0)
        self.thread.join(timeout=2)
