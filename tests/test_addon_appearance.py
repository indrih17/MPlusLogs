"""Appearance transactions, normalization and data-only theme sharing."""
import unittest

from test_addon import LuaRuntime, MOCK, ROOT


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.lua.execute('MPlusLogsDB={options={tooltips=false},profiles={sentinel={score=123}},companionReplySeen=true}')
        self.mpl = self.lua.table()
        for name in ('Appearance.lua', 'AppearancePresets.lua'):
            self.lua.execute('return assert(loadstring(...))', (ROOT / name).read_text(encoding='utf-8'))('MPlusLogs', self.mpl)
        self.mpl.ApplyAppearanceToViews = self.lua.eval('function() refreshCount=(refreshCount or 0)+1 end')

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def test_builtin_styles_change_only_their_named_classic_features(self):
        expected={
            'clean': {'gridMode':'horizontal'},
            'table': {'gridMode':'full','tableBorder':True},
            'compact': {'rowHeight':22,'iconSize':16,'cellPadding':4,'compactSummary':True},
            'large': {'fontSize':14},
            'minimal': {'showNotes':False,'showSource':False,'showSeason':False,
                        'showSpecRanks':False,'showGroupHeaders':False,
                        'column_time_visible':False,'column_runs_visible':False,
                        'column_rank_visible':False,'column_points_visible':False},
        }
        def plain(value):
            return {key:plain(item) for key,item in value.items()} if hasattr(value,'items') else value
        classic=plain(self.mpl.AppearancePresets.classic['values'])
        for theme,overrides in expected.items():
            with self.subTest(theme=theme):
                self.mpl.SelectAppearanceTheme(theme)
                self.assertEqual(plain(self.mpl.GetAppearance()),dict(classic,**overrides))

    def test_builtin_styles_do_not_share_mutable_colors_or_columns(self):
        classic=self.mpl.AppearancePresets.classic['values']
        clean=self.mpl.AppearancePresets.clean['values']
        clean.gridColor[1]=.75
        clean.columnOrder[1]='best'
        self.assertEqual(classic.gridColor[1],.2)
        self.assertEqual(classic.columnOrder[1],'dungeon')
        self.assertEqual(self.mpl.AppearancePresets.large['values'].gridColor[1],.2)

    def test_fresh_defaults_preserve_unrelated_saved_data(self):
        self.assertEqual(self.mpl.AppearanceDefaults.maxRows, 8)
        self.assertEqual(self.mpl.GetAppearance().maxRows, 8)
        self.assertEqual(self.mpl.GetAppearanceThemeID(), 'classic')
        self.assertEqual(self.mpl.GetAppearance().gridMode, 'legacy')
        self.assertEqual(self.mpl.GetAppearance().levelDigits, 'natural')
        db = self.lua.globals().MPlusLogsDB
        self.assertFalse(db.options.tooltips)
        self.assertTrue(db.companionReplySeen)
        self.assertEqual(db.profiles.sentinel.score, 123)

    def test_saved_russian_dungeon_language_migrates_to_client(self):
        self.lua.execute('MPlusLogsDB.appearance={schemaVersion=1,activeTheme="custom",themes={custom={values={dungeonLanguage="ruRU"}}}}')
        self.assertEqual(self.mpl.GetAppearance().dungeonLanguage, 'client')
        for language in ('client', 'enUS'):
            normalized = self.mpl.NormalizeAppearance(self.table({'dungeonLanguage': language}))
            self.assertEqual(normalized.dungeonLanguage, language)

    def test_legacy_row_limit_is_fixed_to_eight_without_changing_other_settings(self):
        self.lua.execute('MPlusLogsDB.appearance={schemaVersion=2,activeTheme="custom",themes={custom={name="Indrih",values={maxRows=12,fontSize=17}}}}')
        self.mpl.InitAppearance()
        self.assertEqual(self.mpl.GetAppearance().maxRows, 8)
        self.assertEqual(self.mpl.GetAppearance().fontSize, 17)
        self.assertEqual(self.mpl.GetAppearanceProfiles()[1].name, 'Indrih')
        self.assertFalse(self.mpl.SetAppearanceValue('maxRows',12)[0])
        for legacy in (4,12,32):
            self.assertEqual(self.mpl.NormalizeAppearance(self.table({'maxRows':legacy})).maxRows,8)

    def test_false_booleans_survive_save_and_normalization(self):
        self.assertTrue(self.mpl.SetAppearanceValue('showNotes', False))
        self.assertFalse(self.mpl.GetAppearance().showNotes)
        self.mpl.SaveAppearanceEdit()
        self.assertFalse(self.mpl.GetAppearance().showNotes)
        normalized = self.mpl.NormalizeAppearance(self.table({'striped': False, 'showSummary': False}))
        self.assertFalse(normalized.striped)
        self.assertFalse(normalized.showSummary)

    def test_obsolete_width_settings_are_removed_from_saved_and_imported_themes(self):
        obsolete={'widthMode':'fixed','fixedWidth':1274,'minWidth':1600,
                  'maxWidth':520,'classicWidth':True,'column_dungeon_width':24}
        values=dict(obsolete,fontSize=14,column_runs_visible=False)
        self.lua.globals().MPlusLogsDB.appearance=self.table({
            'schemaVersion':1,'activeTheme':'custom','themes':{
                'custom':{'name':'Existing theme','values':values}}})
        normalized=self.mpl.NormalizeAppearance(self.table(values))
        saved=self.mpl.GetAppearance()
        for key in obsolete:
            self.assertIsNone(normalized[key],key)
            self.assertIsNone(saved[key],key)
            self.assertFalse(self.mpl.SetAppearanceValue(key,obsolete[key])[0])
        self.assertEqual(saved.fontSize,14)
        self.assertFalse(saved.column_runs_visible)
        self.assertFalse(any(field.key in obsolete for field in self.mpl.AppearanceFields.values()))

    def test_partial_invalid_theme_clamps_and_discards_unknown_fields(self):
        self.lua.execute('MPlusLogsDB.appearance={schemaVersion=1,activeTheme="custom",themes={custom={name="A",values={rowHeight=200,fontSize=0,scale=0/0,gridMode="garbage",unknown="secret",gridColor={-1,2,0.3,0.5}}}}}')
        theme = self.mpl.GetAppearance()
        self.assertEqual(theme.rowHeight, 48)
        self.assertEqual(theme.fontSize, 9)
        self.assertEqual(theme.scale, 1)
        self.assertEqual(theme.gridMode, 'legacy')
        self.assertIsNone(theme.unknown)
        self.assertEqual([theme.gridColor[i] for i in range(1, 5)], [0, 1, 0.3, 0.5])

    def test_future_schema_is_retained_and_safe_defaults_used(self):
        self.lua.execute('MPlusLogsDB.appearance={schemaVersion=99,novel="preserve"}')
        self.assertEqual(self.mpl.GetAppearance().gridMode, 'legacy')
        self.assertEqual(self.lua.globals().MPlusLogsDB.appearanceFuture.novel, 'preserve')

    def test_draft_changes_do_not_write_saved_state(self):
        self.mpl.BeginAppearanceEdit()
        self.mpl.SetAppearanceValue('gridMode', 'full')
        self.assertEqual(self.mpl.GetAppearance().gridMode, 'full')
        self.assertEqual(self.lua.globals().MPlusLogsDB.appearance.activeTheme, 'classic')
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.appearance.themes), 0)
        self.mpl.CancelAppearanceEdit()
        self.assertEqual(self.mpl.GetAppearance().gridMode, 'legacy')

    def test_save_builtin_creates_personal_copy_without_mutating_preset(self):
        self.mpl.SetAppearanceValue('rowHeight', 31)
        self.mpl.SaveAppearanceEdit()
        self.assertEqual(self.mpl.GetAppearance().rowHeight, 31)
        self.assertEqual(self.mpl.AppearancePresets.classic['values'].rowHeight, 26)
        self.assertFalse(self.mpl.IsAppearanceEditing())

    def test_color_values_are_copied_not_shared(self):
        color = self.table([0.1, 0.2, 0.3, 0.4])
        self.mpl.SetAppearanceValue('gridColor', color)
        color[1] = 0.9
        self.assertAlmostEqual(self.mpl.GetAppearance().gridColor[1], 0.1)
        self.assertAlmostEqual(self.mpl.AppearanceDefaults.gridColor[1], 0.2)

    def test_theme_alias_and_character_scope_operations_share_cancel(self):
        self.mpl.BeginAppearanceEdit()
        theme_id = self.mpl.CreateAppearanceTheme('Personal')
        self.mpl.SetAppearanceCharacterBinding('character')
        self.mpl.SetDungeonAlias(249, 'Короли')
        self.assertTrue(self.mpl.RenameAppearanceTheme(theme_id, 'Renamed'))
        self.assertEqual(self.mpl.GetAppearanceCharacterBinding(), 'character')
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Короли')
        self.mpl.CancelAppearanceEdit()
        self.assertEqual(self.mpl.GetAppearanceThemeID(), 'classic')
        self.assertEqual(self.mpl.GetAppearanceCharacterBinding(), 'account')
        self.assertIsNone(self.mpl.GetDungeonAlias(249))
        self.assertEqual(len(self.mpl.GetAppearanceThemes()), 6)

    def test_theme_delete_clears_bindings_but_can_be_undone(self):
        theme_id = self.mpl.CreateAppearanceTheme('Personal')
        self.mpl.SetAppearanceCharacterBinding('character')
        self.mpl.SaveAppearanceEdit()
        self.assertTrue(self.mpl.DeleteAppearanceTheme(theme_id))
        self.assertEqual(self.mpl.GetAppearanceThemeID(), 'classic')
        self.assertTrue(self.mpl.UndoAppearanceEdit())
        self.assertEqual(self.mpl.GetAppearanceThemeID(), theme_id)

    def test_character_reset_preserves_other_themes_and_account_theme(self):
        theme_id = self.mpl.CreateAppearanceTheme('Shared')
        self.mpl.SetAppearanceValue('rowHeight', 30)
        self.mpl.SaveAppearanceEdit()
        self.mpl.ResetAppearanceForCharacter()
        self.assertEqual(self.mpl.GetAppearanceThemeID(), 'classic')
        self.assertEqual(self.mpl.GetAppearanceState().activeTheme, theme_id)
        self.assertEqual(self.mpl.GetAppearanceState().themes[theme_id]['values'].rowHeight, 30)

    def test_character_reset_closes_editor_before_discarding_draft(self):
        self.mpl.SetAppearanceValue('gridMode', 'full')
        self.lua.execute('''
            local MPL=...
            MPL.appearanceEditor={shown=true}
            function MPL.appearanceEditor:IsShown() return self.shown end
            function MPL.appearanceEditor:Hide()
                self.closedWhileEditing=MPL.IsAppearanceEditing()
                self.shown=false
                MPL.CancelAppearanceEdit()
            end
        ''', self.mpl)
        self.mpl.ResetAppearanceForCharacter()
        self.assertTrue(self.mpl.appearanceEditor.closedWhileEditing)
        self.assertFalse(self.mpl.appearanceEditor.shown)
        self.assertFalse(self.mpl.IsAppearanceEditing())
        self.assertEqual(self.mpl.GetAppearance().gridMode, 'legacy')

    def test_coalesced_refresh_does_not_invoke_profile_navigation(self):
        self.lua.execute('pending={}; C_Timer={After=function(_,fn) pending[#pending+1]=fn end}')
        self.mpl.ShowProfile = self.lua.eval('function() error("must not navigate") end')
        for value in (0.9, 0.8, 0.7):
            self.mpl.SetAppearanceValue('surfaceOpacity', value)
        self.assertEqual(len(self.lua.globals().pending), 1)
        self.assertIsNone(self.lua.globals().refreshCount)
        self.lua.globals().pending[1]()
        self.assertEqual(self.lua.globals().refreshCount, 1)
        self.assertAlmostEqual(self.mpl.GetAppearance().surfaceOpacity, 0.7)

    def test_slider_action_undo_returns_to_drag_start(self):
        self.mpl.BeginAppearanceEdit()
        self.mpl.BeginAppearanceAction()
        for value in (0.9, 0.8, 0.7):
            self.mpl.SetAppearanceValue('surfaceOpacity', value)
        self.mpl.EndAppearanceAction()
        self.mpl.UndoAppearanceEdit()
        self.assertEqual(self.mpl.GetAppearance().surfaceOpacity, 1)

    def test_column_order_has_no_duplicates_or_unknown_ids(self):
        self.mpl.SetAppearanceValue('columnOrder', self.table(['best', 'best', 'garbage', 'dungeon']))
        order = list(self.mpl.GetAppearance().columnOrder.values())
        self.assertEqual(order[:2], ['best', 'dungeon'])
        self.assertEqual(len(order), 9)
        self.assertEqual(len(set(order)), 9)
        self.assertFalse(self.mpl.SetAppearanceValue('column_dungeon_visible', False)[0])

    def test_invalid_setters_do_not_begin_a_draft(self):
        for key, value in [('no_such_field', 0), ('gridMode', 'garbage'), ('fontSize', 'huge'), ('showNotes', 0)]:
            self.assertFalse(self.mpl.SetAppearanceValue(key, value)[0])
        self.assertFalse(self.mpl.IsAppearanceEditing())

    def test_import_export_roundtrip_includes_only_appearance(self):
        self.mpl.SetAppearanceValue('gridMode', 'full')
        self.mpl.SetAppearanceValue('gridColor', self.table([0.11, 0.22, 0.33, 0.44]))
        self.mpl.SetAppearanceValue('columnOrder', self.table(['median', 'dungeon']))
        self.mpl.SetDungeonAlias(249, 'Короли')
        text = self.mpl.ExportAppearance(True)
        self.assertTrue(text.startswith('MPLA1:'))
        for private in ('profiles', 'companionReplySeen', 'sentinel', 'tooltips'):
            self.assertNotIn(private, text)
        self.mpl.CancelAppearanceEdit()
        self.assertTrue(self.mpl.ImportAppearance(text))
        self.assertEqual(self.mpl.GetAppearance().gridMode, 'full')
        self.assertAlmostEqual(self.mpl.GetAppearance().gridColor[4], 0.44)
        self.assertEqual(self.mpl.GetAppearance().columnOrder[1], 'median')
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Короли')

    def test_export_does_not_include_aliases_unless_requested(self):
        self.mpl.SetDungeonAlias(249, 'PRIVATE ALIAS')
        self.assertNotIn('PRIVATE ALIAS', self.mpl.ExportAppearance(False))

    def test_import_rejects_code_and_malformed_or_oversized_data(self):
        for text in ('return os.execute("bad")', 'MPLA1:loadstring("bad")', 'MPLA1:m9999999:', 'MPLA1:s9999:x', 'MPLA1:' + 'a' * 70000):
            self.assertFalse(self.mpl.ImportAppearance(text)[0])
        self.assertFalse(self.mpl.IsAppearanceEditing())

    def test_aliases_reject_control_sequences(self):
        for name in ('hello\nworld', '|cffff0000red', 'a' * 121):
            self.assertFalse(self.mpl.SetDungeonAlias(249, name)[0])
        self.assertFalse(self.mpl.IsAppearanceEditing())

    def test_native_font_returns_role_size_and_preserved_flags(self):
        self.assertEqual(self.mpl.ResolveAppearanceFont('numbers'), (None, 10, None, 'native'))
        self.assertTrue(self.mpl.GetAppearanceFontInfo('numbers').available)
        self.assertEqual(self.mpl.GetAppearanceFontInfo('numbers').actual, 'native')
        self.assertEqual(self.mpl.ResolveAppearanceFont('dungeon')[1], 12)
        self.mpl.SetAppearanceValue('fontOutline', 'none')
        self.assertEqual(self.mpl.ResolveAppearanceFont('numbers')[2], '')
        self.mpl.SetAppearanceValue('size_rating', 35)
        self.assertEqual(self.mpl.ResolveAppearanceFont('rating')[1], 35)

    def test_late_media_registration_and_global_override(self):
        self.lua.execute('''
            media={fonts={},callbacks={}}
            function media:List() local r={}; for k in pairs(self.fonts) do r[#r+1]=k end; return r end
            function media:IsValid(_,key) return self.fonts[key]~=nil end
            function media:Fetch(_,key) return self.fonts[self.override or key] end
            function media:GetGlobal() return self.override end
            function media.RegisterCallback(owner,event,fn) media.callbacks[event]=fn end
            LibStub=function() return media end
        ''')
        self.mpl.SetAppearanceValue('font', 'Requested')
        self.assertIsNone(self.mpl.ResolveAppearanceFont('numbers')[0])
        self.lua.execute('media.fonts.Requested="Interface/Fonts/requested.ttf"; media.callbacks.LibSharedMedia_Registered("LibSharedMedia_Registered","font","Requested")')
        self.assertEqual(self.mpl.ResolveAppearanceFont('numbers')[0], 'Interface/Fonts/requested.ttf')
        self.lua.execute('media.fonts.Forced="Interface/Fonts/forced.ttf"; media.override="Forced"; media.callbacks.LibSharedMedia_SetGlobal("LibSharedMedia_SetGlobal","font","Forced")')
        self.assertEqual(self.mpl.ResolveAppearanceFont('numbers')[0], 'Interface/Fonts/forced.ttf')
        self.assertEqual(self.mpl.GetAppearance().font, 'Requested')
        info=self.mpl.GetAppearanceFontInfo('numbers')
        self.assertEqual(info.requested,'Requested')
        self.assertEqual(info.actual,'Forced')
        self.assertTrue(info.overridden)

    def test_embedded_libraries_work_without_other_addons(self):
        self.lua.execute('''
            function GetLocale() return "ruRU" end
            function securecallfunction(fn,...) return fn(...) end
            strmatch=string.match
            bit={band=function(a,b)
                local result,place=0,1
                while a>0 and b>0 do
                    if a%2==1 and b%2==1 then result=result+place end
                    a=math.floor(a/2); b=math.floor(b/2); place=place*2
                end
                return result
            end}
            C_UIFileAsset={IsKnownFile=function() return true end}
        ''')
        for name in ('libs/LibStub/LibStub.lua', 'libs/CallbackHandler-1.0/CallbackHandler-1.0.lua', 'libs/LibSharedMedia-3.0/LibSharedMedia-3.0.lua'):
            self.lua.execute((ROOT / name).read_text(encoding='utf-8'))
        fonts = self.mpl.GetAppearanceFonts()
        self.assertGreater(len(fonts), 2)
        self.mpl.SetAppearanceValue('font', 'Friz Quadrata TT')
        self.assertEqual(self.mpl.ResolveAppearanceFont('numbers')[0], r'Fonts\FRIZQT___CYR.TTF')
        self.lua.execute(r'LibStub("LibSharedMedia-3.0"):Register("font","Registered later",[[Interface\AddOns\Sample\font.ttf]],2)')
        self.mpl.SetAppearanceValue('font', 'Registered later')
        self.assertEqual(self.mpl.ResolveAppearanceFont('numbers')[0], r'Interface\AddOns\Sample\font.ttf')

    def test_implicit_theme_copy_obeys_theme_count_limit(self):
        for i in range(30):
            self.mpl.CreateAppearanceTheme('Theme ' + str(i))
        self.mpl.SelectAppearanceTheme('classic')
        self.assertFalse(self.mpl.SetAppearanceValue('rowHeight', 31)[0])
        self.assertEqual(self.mpl.GetAppearance().rowHeight, 26)

    def test_custom_styles_precede_builtin_styles_after_save_and_rename(self):
        first = self.mpl.CreateAppearanceTheme('Zebra')
        second = self.mpl.CreateAppearanceTheme('Alpha')
        self.mpl.SaveAppearanceEdit()
        themes = list(self.mpl.GetAppearanceThemes().values())
        self.assertEqual([theme.id for theme in themes[:2]], [second, first])
        self.assertTrue(all(not theme.builtin for theme in themes[:2]))
        self.assertTrue(all(theme.builtin for theme in themes[2:]))
        self.mpl.RenameAppearanceTheme(first, 'Alpha')
        self.mpl.SaveAppearanceEdit()
        themes = list(self.mpl.GetAppearanceThemes().values())
        self.assertEqual([theme.id for theme in themes[:2]], [first, second])
        self.assertTrue(all(theme.builtin for theme in self.mpl.GetAppearancePresets().values()))


if __name__ == '__main__':
    unittest.main()
