import sys
import gc
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import appearance


class AppearanceTests(unittest.TestCase):
    def test_settings_controls_keep_palette_on_hover_and_press(self):
        root = tk.Tk()
        root.withdraw()
        try:
            style = ttk.Style(root)
            radio = ttk.Radiobutton(root, text="Start with Windows")
            check = ttk.Checkbutton(root, text="Sound")
            for mode in ("dark", "light", "dark"):
                appearance.apply(root, mode)
                palette = appearance.PALETTES[mode]
                for widget in (radio, check):
                    for state in (("active",), ("active", "selected"),
                                  ("active", "pressed"), ("disabled", "active")):
                        with self.subTest(mode=mode, widget=widget.winfo_class(), state=state):
                            widget.state(("!active", "!pressed", "!selected", "!disabled"))
                            widget.state(state)
                            self.assertEqual(style.lookup(widget.winfo_class(), "background", widget.state()),
                                             palette["background"])
                            self.assertEqual(style.lookup(widget.winfo_class(), "foreground", widget.state()),
                                             palette["muted"] if "disabled" in state else palette["text"])
        finally:
            root.destroy()

    def tearDown(self):
        # Release destroyed Tcl interpreters on their creating thread before a
        # later GUI test starts the native tray worker and triggers Python GC.
        gc.collect()

    def test_tables_and_readonly_region_follow_theme_switches(self):
        root = tk.Tk()
        root.withdraw()
        try:
            table = ttk.Treeview(root)
            region = ttk.Combobox(root, state="readonly", values=("eu", "us"))
            popup = root.tk.call("ttk::combobox::PopdownWindow", str(region)) + ".f.l"
            table.insert("", "end", values=("Player",))
            style = ttk.Style(root)
            for mode in ("dark", "light", "dark"):
                appearance.apply(root, mode)
                palette = appearance.PALETTES[mode]
                self.assertEqual(style.lookup("Treeview", "fieldbackground"), palette["background"])
                self.assertEqual(style.lookup("Treeview", "foreground"), palette["text"])
                self.assertEqual(style.lookup("Treeview", "background", ("selected",)), palette["accent"])
                self.assertEqual(style.lookup("Treeview", "foreground", ("selected",)), "#ffffff")
                self.assertEqual(style.lookup("TCombobox", "fieldbackground", region.state()), palette["control"])
                self.assertEqual(style.lookup("TCombobox", "foreground", region.state()), palette["text"])
                self.assertEqual(root.tk.call(popup, "cget", "-background"), palette["control"])
        finally:
            root.destroy()
