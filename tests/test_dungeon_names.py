"""Dungeon labels never change canonical WCL identities."""
import unittest

from test_addon import ROOT, MOCK, LuaRuntime, load_locales


class DungeonNamesTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.mpl=self.lua.table()
        load_locales(self.lua,self.mpl,'ruRU')
        self.lua.execute('''
            local MPL=...
            appearance={}; aliases={}
            function MPL.AppearanceValue(key,default)
                local value=appearance[key]; if value==nil then return default end; return value
            end
            function MPL.GetDungeonAlias(id) return aliases[tostring(id)] end
        ''',self.mpl)
        self.lua.execute('return assert(loadstring(...))',(ROOT/'DungeonNames.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)

    def setting(self,key,value):
        self.lua.globals().appearance[key]=value

    def test_default_is_source_english_and_catalog_has_unique_stable_ids(self):
        entries=list(self.mpl.DungeonCatalog.values())
        self.assertEqual(len(entries),8)
        self.assertEqual(len({e.id for e in entries}),8)
        for entry in entries:
            self.assertEqual(self.mpl.DungeonDisplayName(entry.canonical),entry.canonical)
            self.assertEqual(self.mpl.DungeonInfo(entry.id).canonical,entry.canonical)

    def test_explicit_russian_works_on_english_client_and_does_not_mutate_identity(self):
        self.lua.execute('function GetLocale() return "enUS" end')
        self.setting('dungeonLanguage','ruRU')
        entry=self.mpl.DungeonInfo('Murder Row')
        self.assertEqual(self.mpl.DungeonDisplayName(entry.canonical),'Закоулок душегубов')
        self.assertEqual(entry.canonical,'Murder Row')
        self.assertEqual(entry.id,587)
        self.assertEqual(self.mpl.DungeonTooltipNames(entry.canonical),('Закоулок душегубов','Murder Row'))

    def test_client_language_uses_client_api_then_bundled_fallback(self):
        self.setting('dungeonLanguage','client')
        self.lua.execute('C_ChallengeMode={GetMapUIInfo=function(id) return id==587 and "Client local name" or nil end}')
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'Client local name')
        self.assertEqual(self.mpl.DungeonDisplayName('Kings\' Rest'),'Гробница королей')
        self.lua.execute('C_ChallengeMode.GetMapUIInfo=function() error("not ready") end')
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'Закоулок душегубов')

    def test_secret_or_unavailable_client_name_is_not_used(self):
        self.setting('dungeonLanguage','client')
        self.lua.execute('C_ChallengeMode={GetMapUIInfo=function() return {secret=true} end}')
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'Закоулок душегубов')
        self.lua.execute('function GetLocale() return "koKR" end')
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'Murder Row')

    def test_alias_is_used_only_in_custom_mode_and_tooltip_keeps_full_name(self):
        self.lua.globals().aliases['587']='My row'
        self.setting('dungeonLanguage','ruRU')
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'Закоулок душегубов')
        self.setting('dungeonFormat','custom')
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'My row')
        self.assertEqual(self.mpl.DungeonTooltipNames('Murder Row'),('Закоулок душегубов','Murder Row'))
        self.lua.globals().aliases['587']=''
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'Закоулок душегубов')

    def test_formats_unknown_names_and_untranslated_languages(self):
        self.setting('dungeonLanguage','ruRU')
        self.setting('dungeonFormat','short')
        self.assertEqual(self.mpl.DungeonDisplayName('Den of Nalorakk'),'Налоракк')
        self.setting('dungeonFormat','abbreviation')
        self.assertEqual(self.mpl.DungeonDisplayName('Den of Nalorakk'),'DON')
        self.assertEqual(self.mpl.DungeonDisplayName('Future dungeon'),'Future dungeon')
        self.setting('dungeonLanguage','xxXX')
        self.setting('dungeonFormat','full')
        self.assertEqual(self.mpl.DungeonDisplayName('Kings\' Rest'),"Kings' Rest")

    def test_editor_list_is_fresh_and_uses_full_names_even_with_short_format(self):
        self.setting('dungeonLanguage','ruRU')
        self.setting('dungeonFormat','abbreviation')
        entries=self.mpl.GetAppearanceDungeonList()
        murder=next(e for e in entries.values() if e.id==587)
        self.assertEqual(murder.name,'Закоулок душегубов')
        murder.name='changed copy'
        self.assertEqual(self.mpl.DungeonDisplayName('Murder Row'),'MR')


if __name__=='__main__': unittest.main()
