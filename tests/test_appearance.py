import sys
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import appearance


class AppearanceTests(unittest.TestCase):
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
