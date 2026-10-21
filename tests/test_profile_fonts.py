"""Dungeon names enlarge the original game font, retaining regional glyph support."""
import unittest

from test_addon import MOCK, ROOT, LuaRuntime, load_locales


class ProfileFontTests(unittest.TestCase):
    def runtime(self, locale="ruRU", font=r"Fonts\FRIZQT___CYR.TTF"):
        lua = LuaRuntime(unpack_returned_tuples=True)
        mock = MOCK.replace('function methods:CreateFontString() return newFrame() end', '''
            function methods:CreateFontString(_, _, template)
                local child=newFrame()
                child.font=clientFont; child.fontTemplate=template
                child.fontSize=template:find("Small",1,true) and 10 or 12
                child.fontFlags="OUTLINE"
                return child
            end
            function methods:GetFont() return self.font,self.fontSize,self.fontFlags end
            function methods:SetFont(path,size,flags)
                self.font=path; self.fontSize=size; self.fontFlags=flags; return true
            end
        ''')
        lua.execute(mock)
        lua.globals().clientFont = font
        lua.execute("MPlusLogsDB={profiles={},companionIntroDismissed=true}")
        mpl = lua.table()
        load_locales(lua, mpl, locale)
        for name in ("Data.lua", "Snapshot.lua", "UI.lua"):
            lua.execute("return assert(loadstring(...))", (ROOT / name).read_text(encoding="utf-8"))("MPlusLogs", mpl)
        mpl.ShowProfile("Киндрих", "Гордунни", None, True)
        return lua, mpl

    def assert_table_fonts(self, panel, expected):
        fields = [panel.primaryGroup, panel.secondaryGroup, *panel.headings.values()]
        for row in panel.rows.values():
            name = row.cells[1]
            self.assertEqual(name.font, expected)
            self.assertEqual(name.fontSize, 12)
            self.assertEqual(name.fontFlags, "OUTLINE")
            fields.extend(cell for i, cell in row.cells.items() if i != 1)
            fields.extend(row.levelDigits.values())
            for cell in row.cells.values():
                self.assertGreaterEqual(cell.height, cell.fontSize)
                self.assertLessEqual(-cell.points.TOPLEFT[2] + cell.height, row.height)
        for field in fields:
            self.assertEqual(field.fontTemplate, "GameFontHighlightSmall")
            self.assertEqual(field.font, expected)
            self.assertEqual(field.fontSize, 10)
            self.assertEqual(field.fontFlags, "OUTLINE")

    def test_original_table_font_and_cyrillic_compatibility_survive_metric_switch(self):
        for locale in ("ruRU", "enUS", "enGB", "deDE", "esES", "esMX", "frFR", "itIT", "ptBR"):
            with self.subTest(locale=locale):
                _, mpl = self.runtime(locale, r"Fonts\FRIZQT__.TTF")
                self.assert_table_fonts(mpl.panel, r"Fonts\FRIZQT___CYR.TTF")
                mpl.panel.metricTabs.hps.scripts.OnClick()
                self.assert_table_fonts(mpl.panel, r"Fonts\FRIZQT___CYR.TTF")

    def test_regional_and_custom_fonts_keep_their_existing_style(self):
        for locale, font in (("koKR", r"Fonts\2002.TTF"),
                             ("zhCN", r"Fonts\ARKai_T.ttf"),
                             ("zhTW", r"Fonts\bLEI00D.TTF"),
                             ("ruRU", r"Interface\AddOns\Custom\font.ttf")):
            with self.subTest(locale=locale):
                _, mpl = self.runtime(locale, font)
                self.assert_table_fonts(mpl.panel, font)

    def test_tutorial_uses_the_original_table_font(self):
        lua, mpl = self.runtime()
        lua.execute("return assert(loadstring(...))", (ROOT / "TutorialProfile.lua").read_text(encoding="utf-8"))("MPlusLogs", mpl)
        self.assert_table_fonts(mpl.ShowTutorialProfile(), r"Fonts\FRIZQT___CYR.TTF")


if __name__ == "__main__":
    unittest.main()
