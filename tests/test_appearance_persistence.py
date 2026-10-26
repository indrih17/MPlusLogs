"""Reload/logout lifecycle with fresh Lua runtimes and copied SavedVariables.

Models event delivery and serialization; it does not launch a WoW client.
"""
import unittest

from test_addon import MOCK, ROOT, LuaRuntime


class AppearancePersistenceTests(unittest.TestCase):
    def runtime(self, saved=None):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(MOCK)
        lua.execute('''
            local create=CreateFrame
            local frames={}
            function CreateFrame(...)
                local f=create(...)
                f.events={}
                function f:RegisterEvent(event) self.events[event]=true end
                frames[#frames+1]=f
                return f
            end
            function FireEvent(event,...)
                for _,f in ipairs(frames) do
                    if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f,event,...) end
                end
            end
        ''')
        lua.globals().MPlusLogsDB = lua.table_from(saved or {}, recursive=True)
        mpl = lua.table()
        for name in ('Appearance.lua', 'AppearancePresets.lua'):
            lua.execute('return assert(loadstring(...))', (ROOT/name).read_text(encoding='utf-8'))('MPlusLogs', mpl)
        lua.globals().FireEvent('ADDON_LOADED', 'MPlusLogs')
        return lua, mpl

    def saved(self, value):
        return {key:self.saved(item) for key,item in value.items()} if hasattr(value,'items') else value

    def test_named_style_survives_reload_without_pressing_save(self):
        lua, mpl = self.runtime()
        mpl.BeginAppearanceEdit()
        mpl.SetAppearanceValue('fontSize', 17)
        mpl.ApplyAppearanceColorPreset('emerald')
        theme_id = mpl.CreateAppearanceTheme('Indrih')
        mpl.ApplyAppearanceToViews = lua.eval('function() error("Do not rebuild UI during logout") end')
        lua.globals().FireEvent('PLAYER_LOGOUT')  # /reload writes SavedVariables here
        _, restored = self.runtime(self.saved(lua.globals().MPlusLogsDB))
        themes = {theme.id:theme.name for theme in restored.GetAppearanceThemes().values()}
        self.assertEqual(themes.get(theme_id), 'Indrih')
        self.assertEqual(restored.GetAppearanceThemeID(), theme_id)
        self.assertEqual(restored.GetAppearance().fontSize, 17)
        self.assertEqual(restored.GetAppearanceColorPresetID(), 'emerald')

    def test_explicit_cancel_before_reload_keeps_previous_saved_style(self):
        lua, mpl = self.runtime()
        original = mpl.CreateAppearanceTheme('Original')
        mpl.SaveAppearanceEdit()
        mpl.CreateAppearanceTheme('Discarded')
        mpl.CancelAppearanceEdit()
        lua.globals().FireEvent('PLAYER_LOGOUT')
        _, restored = self.runtime(self.saved(lua.globals().MPlusLogsDB))
        self.assertEqual(restored.GetAppearanceThemeID(), original)
        self.assertNotIn('Discarded', [theme.name for theme in restored.GetAppearanceThemes().values()])


if __name__ == '__main__':
    unittest.main()
