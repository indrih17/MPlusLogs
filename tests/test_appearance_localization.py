"""Appearance descriptors and editor copy are in complete offline catalogs."""
import ast
import json
import re
import unittest

from test_addon import ROOT,MOCK,LuaRuntime


class AppearanceLocalizationTests(unittest.TestCase):
    def test_generated_descriptor_labels_and_options_are_in_every_catalog(self):
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute(MOCK)
        mpl=lua.table()
        for name in ('Appearance.lua','AppearancePresets.lua'):
            lua.execute('return assert(loadstring(...))',(ROOT/name).read_text(encoding='utf-8'))('MPlusLogs',mpl)
        expected=set()
        for field in mpl.AppearanceFields.values():
            expected.add(field.label)
            self.assertTrue(field.help,field.key)
            expected.add(field.help)
            if field.options:
                expected.update(option.label for option in field.options.values())
        expected.update(preset.name for preset in mpl.AppearancePresets.values())
        expected.update(preset.name for preset in mpl.AppearanceColorPresets.values())
        for name in ('AppearanceSettings.lua','ProfileAppearance.lua','Settings.lua'):
            code=(ROOT/name).read_text(encoding='utf-8')
            expected.update(ast.literal_eval(raw) for raw in re.findall(
                r'L\[((?:"(?:[^"\\]|\\.)*")|(?:\'(?:[^\'\\]|\\.)*\'))\]',code))
            if name=='AppearanceSettings.lua':
                expected.update(ast.literal_eval(raw) for raw in re.findall(
                    r'label\s*=\s*("(?:[^"\\]|\\.)*")',code))
        catalog=set(json.loads((ROOT/'Locales/catalog.json').read_text(encoding='utf-8')))
        self.assertFalse(expected-catalog,sorted(expected-catalog))
        for locale in ('enUS','ruRU','deDE','esES','esMX','frFR','itIT','koKR','ptBR','zhCN','zhTW'):
            with self.subTest(locale=locale):
                data=json.loads((ROOT/'Locales'/f'{locale}.json').read_text(encoding='utf-8'))
                self.assertFalse(expected-set(data),sorted(expected-set(data)))
                for key in expected:self.assertTrue(data[key].strip(),key)

    def test_primary_russian_editor_copy_is_authored(self):
        data=json.loads((ROOT/'Locales/ruRU.json').read_text(encoding='utf-8'))
        for key,text in {
            'Appearance…':'Оформление окна…','Save':'Сохранить','Cancel':'Отмена',
            'Dungeon language':'Язык названий подземелий','Game language':'Язык игры','Full table':'Таблица с сеткой',
            'Background opacity':'Непрозрачность фона (0–1)','Natural spacing':'Обычные цифры',
        }.items():self.assertEqual(data[key],text)


if __name__=='__main__':unittest.main()
