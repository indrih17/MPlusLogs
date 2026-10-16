"""Every WoW locale renders with complete dictionaries and stable wire data."""
import json
import re
import unittest
from test_addon import ROOT,MOCK,LuaRuntime,load_locales

LOCALES=['enUS','enGB','ruRU','deDE','esES','esMX','frFR','itIT','ptBR','koKR','zhCN','zhTW']
PROTECTED=re.compile(r'\|c[0-9a-fA-F]{8}|\|r|Ctrl\+[ACV]|/reload|/mpl|MPlusLogs|DPS|HPS|WCL|%[0-9.*]*[sdif]')

class LocalizationTests(unittest.TestCase):
    def runtime(self,locale):
        lua=LuaRuntime(unpack_returned_tuples=True); lua.execute(MOCK)
        lua.execute('MPlusLogsDB={profiles={},companionIntroDismissed=true}; C_Timer={After=function(_,fn) fn() end}')
        mpl=lua.table(); load_locales(lua,mpl,locale)
        for file in ['Data.lua','Snapshot.lua','Transport.lua','UI.lua','Integration.lua']:
            lua.execute('return assert(loadstring(...))',(ROOT/file).read_text(encoding='utf-8'))('MPlusLogs',mpl)
        return lua,mpl

    def test_all_locale_dictionaries_are_complete_and_preserve_controls(self):
        keys=json.loads((ROOT/'Locales/catalog.json').read_text(encoding='utf-8'))
        authored=json.loads((ROOT/'Locales/ruRU.json').read_text(encoding='utf-8'))
        for locale in LOCALES:
            with self.subTest(locale=locale):
                _,mpl=self.runtime(locale)
                self.assertEqual(mpl.locale,'enUS' if locale=='enGB' else locale)
                self.assertEqual(len(list(mpl.L.keys())),len(keys))
                for key in keys:
                    translated=mpl.L[key]
                    self.assertIsInstance(translated,str)
                    self.assertTrue(translated.strip())
                    self.assertNotRegex(translated,r'ZX(?:START|END|PH|NEWLINE)')
                    self.assertEqual(sorted(PROTECTED.findall(translated)),sorted(PROTECTED.findall(authored[key])),msg=(locale,key))
                    colors=r'\|c[0-9a-fA-F]{8}|\|r'
                    self.assertEqual(re.findall(colors,translated),re.findall(colors,authored[key]),msg=(locale,key))

    def test_authored_copy_uses_product_name_and_localized_action_labels(self):
        for directory in (ROOT/'Locales',ROOT/'tools/companion_locales'):
            authored=json.loads((directory/'ruRU.json').read_text(encoding='utf-8'))
            for key,text in authored.items():
                self.assertNotRegex(text,r"[Пп]омощник",key)
        _,mpl=self.runtime('enUS')
        self.assertIn('Check Companion updates',mpl.L['Для загрузки этих логов обновите MPlusLogs Companion.'])
        self.assertNotIn('/reload',mpl.L['\nОткройте MPlusLogs Companion, войдите в Warcraft Logs, затем введите /reload и повторите загрузку.'])

    def test_profile_download_and_wire_identity_in_every_locale(self):
        for locale in LOCALES:
            with self.subTest(locale=locale):
                lua,mpl=self.runtime(locale)
                mpl.ShowProfile('Киндрих','Гордунни')
                original=mpl.panel.profile
                original_spec=original.spec
                original_source=original.source
                mpl.ShowDownload('Киндрих','Гордунни',original)
                self.assertEqual(mpl.downloadWindow.phase,'copy')
                self.assertIn(mpl.L['Запрос: Ctrl+A выделить, Ctrl+C скопировать'],mpl.downloadWindow.status.text)
                self.assertEqual(original.spec,original_spec)
                self.assertEqual(original.source,original_source)
                self.assertEqual(mpl.pendingReply.spec,'')
                self.assertNotIn(mpl.T('All specs'),mpl.downloadWindow.request)
                self.assertEqual(mpl.Key('Киндрих','Гордунни'),'eu:гордунни:киндрих:55')

    def test_unknown_client_locale_falls_back_to_english(self):
        _,mpl=self.runtime('xxXX')
        self.assertEqual(mpl.locale,'enUS')
        self.assertEqual(mpl.L['Пригласить'],'Invite')
        # Missing entries in a selected dictionary still use the English base.
        _,mpl=self.runtime('koKR')
        self.assertEqual(mpl.L['MPlusLogs: tooltips '],'MPlusLogs: tooltips ')

if __name__=='__main__': unittest.main()
