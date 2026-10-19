"""Exercise real profile labels/tabs with locale-specific WoW font metadata."""
import unittest
from test_addon import MOCK, ROOT, LuaRuntime, load_locales


class CyrillicFontTests(unittest.TestCase):
    def runtime(self, font=r"Fonts\FRIZQT__.TTF", locale="enUS"):
        lua = LuaRuntime(unpack_returned_tuples=True)
        mock = MOCK.replace('function methods:CreateFontString() return newFrame() end', '''
            function methods:CreateFontString(_, _, template)
                local child=newFrame(); child.font=clientFont; child.fontSize=12; child.fontFlags="OUTLINE"
                return child
            end
            function methods:GetFont() return self.font,self.fontSize,self.fontFlags end
            function methods:SetFont(path,size,flags) self.font=path; self.fontSize=size; self.fontFlags=flags; return true end
            function methods:SetFontString(caption) self.caption=caption end
        ''')
        lua.execute(mock)
        lua.globals().clientFont = font
        lua.execute('MPlusLogsDB={profiles={},companionIntroDismissed=true}')
        mpl = lua.table()
        load_locales(lua, mpl, locale)
        for name in ('Data.lua', 'Snapshot.lua', 'UI.lua'):
            lua.execute('return assert(loadstring(...))', (ROOT/name).read_text(encoding='utf-8'))('MPlusLogs', mpl)
        mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        mpl.panel.groupPlayers = lua.table_from([
            lua.table_from({'name':'Киндрих','realm':'Гордунни'}),
            lua.table_from({'name':'Towhee','realm':'TarrenMill'})])
        mpl.RenderPlayerTabs(mpl.panel)
        return lua, mpl

    def test_english_profile_and_player_tabs_use_cyrillic_capable_font(self):
        for locale in ('enUS', 'enGB', 'deDE'):
            with self.subTest(locale=locale):
                _, mpl = self.runtime(locale=locale)
                for field in (mpl.panel.character, mpl.panel.playerTabs[1].caption, mpl.panel.playerTabs[2].caption):
                    self.assertEqual(field.font, r'Fonts\FRIZQT___CYR.TTF')
                    self.assertEqual(field.fontSize, 12)
                    self.assertEqual(field.fontFlags, 'OUTLINE')
                self.assertEqual(mpl.panel.character.text, 'Киндрих — Гордунни')
                self.assertEqual(mpl.panel.playerTabs[1].text, '|cffffd100Киндрих|r')

    def test_existing_russian_asian_and_custom_fonts_are_preserved(self):
        for font in (r'Fonts\FRIZQT___CYR.TTF', r'Fonts\2002.TTF', r'Fonts\ARKai_T.ttf', r'Interface\AddOns\Custom\font.ttf'):
            with self.subTest(font=font):
                _, mpl = self.runtime(font=font)
                self.assertEqual(mpl.panel.character.font, font)
                self.assertEqual(mpl.panel.playerTabs[1].caption.font, font)


if __name__ == '__main__':
    unittest.main()
