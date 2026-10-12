"""Offline Companion translations; WoW protocol identifiers are never translated."""
import ctypes
import json
from pathlib import Path
import re
import tkinter as tk

DIRECTORY = Path(__file__).with_name("companion_locales")
LANGUAGES = {"enUS":"English", "ruRU":"Русский", "deDE":"Deutsch", "esES":"Español (España)",
             "esMX":"Español (Latinoamérica)", "frFR":"Français", "itIT":"Italiano", "ptBR":"Português (Brasil)",
             "koKR":"한국어", "zhCN":"简体中文", "zhTW":"繁體中文"}
_catalogs = {}
_language = "enUS"


def normalize(locale):
    value = locale.replace("-", "").replace("_", "").casefold()
    if value in {"engb", "en"}:
        return "enUS"
    exact = next((key for key in LANGUAGES if key.casefold() == value), None)
    if exact:
        return exact
    if value.startswith("zh"):
        return "zhTW" if value in {"zhhk","zhmo","zhhant"} else "zhCN"
    return {"en":"enUS","ru":"ruRU","de":"deDE","es":"esMX","fr":"frFR","it":"itIT","pt":"ptBR","ko":"koKR"}.get(value[:2],"enUS")


def system_language():
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetUserDefaultLocaleName.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        buffer = ctypes.create_unicode_buffer(85)
        if kernel.GetUserDefaultLocaleName(buffer, len(buffer)):
            return normalize(buffer.value)
    except (OSError, AttributeError):
        pass
    return "enUS"


def set_language(language):
    global _language
    _language = system_language() if language == "system" else normalize(language)
    return _language


def catalog(language):
    language = normalize(language)
    if language not in _catalogs:
        _catalogs[language] = json.loads((DIRECTORY / (language + ".json")).read_text(encoding="utf-8"))
    return _catalogs[language]


def tr(text, language=None):
    """Translate fixed text or safe error prefixes, without interpolating arbitrary data."""
    language = _language if language is None else normalize(language)
    base = catalog("enUS")
    selected = catalog(language)
    if text in base:
        return selected.get(text) or base[text]
    if text.startswith("WCL HTTP "):
        match = re.match(r"WCL HTTP (\d+);", text)
        if match:
            return tr("WCL HTTP {code}. Check your sign-in, API permissions or request limit.", language).format(code=match[1])
    # Prefixes are authored separately for concatenated errors; suffix may be OS text.
    for prefix in sorted((key for key in base if key.endswith(": ")), key=len, reverse=True):
        if text.startswith(prefix):
            return tr(prefix, language) + tr(text[len(prefix):], language)
    return text


class TextVar(tk.StringVar):
    """Keep the source text so an open window can switch language immediately."""
    def __init__(self, master, value=""):
        self.source = value
        self.format_values = None
        super().__init__(master=master, value=tr(value))

    def set(self, value):
        self.source = value
        self.format_values = None
        super().set(tr(value))

    def set_format(self, template, **values):
        self.source, self.format_values = template, values
        self.refresh()

    def refresh(self):
        translated = tr(self.source)
        super().set(translated.format(**self.format_values) if self.format_values is not None else translated)
