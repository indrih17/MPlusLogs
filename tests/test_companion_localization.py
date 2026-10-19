"""Locale completeness, safe placeholders, language switching and packaged assets."""
import ast
import gc
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "tools"))
import companion_i18n as i18n
import local_settings
import export_release_source


class CompanionLocalizationTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("system")

    def test_all_client_languages_are_complete(self):
        keys = set(json.loads((i18n.DIRECTORY / "catalog.json").read_text(encoding="utf-8")))
        self.assertEqual(len(i18n.LANGUAGES),11)
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                catalog = i18n.catalog(language)
                self.assertEqual(set(catalog),keys)
                for key,text in catalog.items():
                    self.assertTrue(text.strip(),key)
                    self.assertEqual(set(re.findall(r"\{\w+\}",key)),set(re.findall(r"\{\w+\}",text)),key)
                    if language != "ruRU":
                        self.assertFalse(re.search(r"[А-Яа-яЁё]",text),key)
                    self.assertNotIn("ZXPH",text)
                    self.assertEqual(key.count("\n"),text.count("\n"),key)

    def test_system_mapping_english_alias_and_fallback(self):
        self.assertEqual(i18n.tr("Follow Windows", "ruRU"), "Как в Windows")
        self.assertEqual(i18n.tr("Language", "ruRU"), "Язык")
        for name,expected in {"en-GB":"enUS","de-AT":"deDE","pt-PT":"ptBR","zh-HK":"zhTW","fr-CA":"frFR","unsupported":"enUS"}.items():
            self.assertEqual(i18n.normalize(name),expected)
        with patch.object(i18n,"system_language",return_value="deDE"):
            self.assertEqual(i18n.set_language("system"),"deDE")
            self.assertEqual(i18n.tr("Настройки"),"Einstellungen")

    def test_safe_error_rendering_and_source_data_unchanged(self):
        i18n.set_language("enUS")
        self.assertEqual(i18n.tr("Не удалось войти: Сессия Warcraft Logs истекла. Войдите ещё раз."),
                         "Could not sign in: Your Warcraft Logs session expired. Sign in again.")
        self.assertIn("401",i18n.tr("WCL HTTP 401; check credentials, API permissions or rate limit"))
        self.assertEqual(i18n.tr("MPLS1\n1-2\nMPLB1\nexample"),"MPLS1\n1-2\nMPLB1\nexample")
        self.assertEqual(i18n.tr("Киндрих–Гордунни"),"Киндрих–Гордунни")

    def test_export_contains_all_languages_but_no_user_settings(self):
        names = {entry["path"] for entry in export_release_source.entries()}
        for language in i18n.LANGUAGES:
            self.assertIn(f"tools/companion_locales/{language}.json",names)
        self.assertNotIn("settings.json",names)
        self.assertNotIn("companion-status.json",names)

    @unittest.skipUnless(sys.platform=="win32","Windows GUI")
    def test_open_window_changes_language_and_preserves_explicit_sound(self):
        # Run after the test frame and its widget references have been released.
        # Tcl interpreters must be collected on the thread that created them.
        self.addCleanup(gc.collect)
        import tkinter as tk
        loader = importlib.machinery.SourceFileLoader("localized_gui_test",str(ROOT / "tools/companion_gui.pyw"))
        spec = importlib.util.spec_from_loader(loader.name,loader)
        gui = importlib.util.module_from_spec(spec)
        loader.exec_module(gui)
        for saved,sound in (({},True),({"sound":False},False)):
            with patch.object(local_settings,"load",return_value=saved), patch.object(sys,"argv",["test"]), \
                 patch.object(gui.windows,"retail_autostart_enabled",return_value=False), \
                 patch.object(gui.windows,"autostart_enabled",return_value=False):
                root = tk.Tk()
                root.withdraw()
                app = gui.App(root)
                try:
                    app.last_heartbeat = time.time()
                    self.assertEqual(app.sound.get(),sound)
                    app.settings()
                    def descendants(widget):
                        for child in widget.winfo_children():
                            yield child
                            yield from descendants(child)
                    def control(source):
                        return next(widget for widget in descendants(app.settings_window)
                                    if "textvariable" in widget.keys()
                                    and str(widget.cget("textvariable")) in {
                                        str(var) for var in app.textvars if var.source == source})
                    reconnect = control("Переподключить Warcraft Logs")
                    signout = control("Выйти из Warcraft Logs")
                    update = control("Check Companion updates")
                    quit_button = control("Завершить помощник")
                    self.assertEqual(reconnect.master, signout.master)
                    self.assertEqual(update.master, quit_button.master)
                    self.assertNotEqual(reconnect.master, quit_button.master)
                    for source in ("Диагностика", "Тестовый режим без Warcraft Logs", "Проверить связь с аддоном без WCL"):
                        with self.assertRaises(StopIteration):
                            control(source)
                    self.assertFalse(app.mode_diagnostic)
                    app.status.set("Готов к работе. Ожидаю запрос из WoW.")
                    with patch.object(app,"save_preferences"):
                        app.language.set("enUS")
                        app.change_language()
                        self.assertEqual(app.status.get(),"Ready. Waiting for a request from WoW.")
                        self.assertEqual(app.settings_window.title(),"MPlusLogs settings")
                        app.language.set("ruRU")
                        app.change_language()
                        self.assertEqual(app.status.get(),"Готов к работе. Ожидаю запрос из WoW.")
                        self.assertEqual(app.settings_window.title(),"Настройки MPlusLogs")
                finally:
                    app.exit()


if __name__ == "__main__":
    unittest.main()
