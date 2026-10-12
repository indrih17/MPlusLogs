"""Companion palettes and Windows application-theme detection."""
import ctypes
from ctypes import wintypes
from tkinter import ttk

PALETTES = {
    "light": {"background":"#f8f6fc", "text":"#21172f", "muted":"#51435f", "control":"#eee8f7", "hover":"#e2d5f5", "accent":"#7c3aed", "border":"#8c789f"},
    "dark": {"background":"#19151f", "text":"#faf7ff", "muted":"#d8cfe6", "control":"#3c334b", "hover":"#514162", "accent":"#7c3aed", "border":"#8f7da4"},
}


def system_theme():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value else "dark"
    except OSError:
        return "light"


def titlebar(window, dark):
    """Best-effort DWM titlebar; client-area theming works on older Windows too."""
    try:
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetParent.argtypes = [wintypes.HWND]
        user.GetParent.restype = wintypes.HWND
        hwnd = user.GetParent(window.winfo_id()) or window.winfo_id()
        user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        style = user.GetWindowLongPtrW(hwnd, -16)
        if style & 0x10000:
            user.SetWindowLongPtrW(hwnd, -16, style & ~0x10000)
            user.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        value = ctypes.c_int(bool(dark))
        if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)) != 0:
            dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
        palette = PALETTES["dark" if dark else "light"]
        for attribute, color in ((35,palette["background"]),(36,palette["text"])):
            red, green, blue = (int(color[index:index+2],16) for index in (1,3,5))
            colorref = wintypes.DWORD(red | green << 8 | blue << 16)
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(colorref), ctypes.sizeof(colorref))
    except (OSError, AttributeError):
        pass


def apply(root, mode, settings=None):
    palette = PALETTES[mode]
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=palette["background"], foreground=palette["text"], font=("Segoe UI",10))
    style.configure("TFrame", background=palette["background"])
    style.configure("TLabel", background=palette["background"], foreground=palette["text"])
    style.configure("Muted.TLabel", foreground=palette["muted"])
    style.configure("TButton", background=palette["control"], foreground=palette["text"], borderwidth=1,
                    bordercolor=palette["border"], lightcolor=palette["border"], darkcolor=palette["border"], padding=(12,8))
    style.map("TButton", background=[("pressed",palette["accent"]),("active",palette["hover"])],
              foreground=[("disabled",palette["muted"]),("pressed","#ffffff")], bordercolor=[("focus",palette["accent"])])
    style.configure("TMenubutton", background=palette["control"], foreground=palette["text"], padding=(12,8),
                    bordercolor=palette["border"], lightcolor=palette["border"], darkcolor=palette["border"], arrowcolor=palette["text"], borderwidth=1)
    style.map("TMenubutton", background=[("active",palette["hover"])])
    style.configure("TCheckbutton", background=palette["background"], foreground=palette["text"],
                    indicatorbackground=palette["control"], indicatorforeground="#ffffff",
                    indicatorbordercolor=palette["border"], indicatormargin=(0,0,8,0), indicatorsize=16)
    style.map("TCheckbutton", background=[("active",palette["background"])],
              indicatorbackground=[("selected",palette["accent"])], indicatorforeground=[("selected","#ffffff")])
    style.layout("Theme.TRadiobutton", [("Button.border", {"sticky":"nswe", "children":[
        ("Button.focus", {"sticky":"nswe", "children":[("Button.padding", {"sticky":"nswe", "children":[
            ("Button.label", {"sticky":"nswe"})]})]})]})])
    style.configure("Theme.TRadiobutton", background=palette["control"], foreground=palette["text"],
                    bordercolor=palette["border"], lightcolor=palette["border"], darkcolor=palette["border"],
                    borderwidth=1, padding=(12,9), anchor="center", focuscolor=palette["text"])
    style.map("Theme.TRadiobutton", background=[("selected",palette["accent"]),("active",palette["hover"])],
              foreground=[("selected","#ffffff")], bordercolor=[("selected",palette["accent"])],
              lightcolor=[("selected",palette["accent"])], darkcolor=[("selected",palette["accent"])])
    root.configure(background=palette["background"])
    titlebar(root, mode == "dark")
    if settings and settings.winfo_exists():
        settings.configure(background=palette["background"])
        titlebar(settings, mode == "dark")
