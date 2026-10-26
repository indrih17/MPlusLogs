"""Profiles own snapshots; named styles and palettes are reusable independent parts."""
import unittest

import test_addon_appearance as state_tests
import test_appearance_persistence as lifecycle_tests


def plain(value):
    return {key:plain(item) for key,item in value.items()} if hasattr(value, 'items') else value


class AppearanceProfileTests(unittest.TestCase):
    setUp = state_tests.AppearanceTests.setUp
    table = state_tests.AppearanceTests.table

    def test_profiles_combine_named_styles_and_palettes_without_sharing_changes(self):
        self.mpl.SetAppearanceValue('rowHeight', 31)
        self.mpl.SetAppearanceValue('fontSize', 16)
        style_id = self.mpl.CreateAppearanceStyle('My layout')
        self.mpl.ApplyAppearanceColorPreset('emerald')
        palette_id = self.mpl.CreateAppearancePalette('Forest')
        self.mpl.SetDungeonAlias(249, 'First name')
        first = self.mpl.CreateAppearanceProfile('First')
        first_values = plain(self.mpl.GetAppearance())
        second = self.mpl.CreateAppearanceProfile('Second')
        self.mpl.ApplyAppearanceStyle('compact')
        self.mpl.SetDungeonAlias(249, 'Second name')
        self.assertEqual(self.mpl.GetAppearance().rowHeight, 22)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), palette_id)
        self.mpl.SelectAppearanceProfile(first)
        self.assertEqual(plain(self.mpl.GetAppearance()), first_values)
        self.assertEqual(self.mpl.GetAppearanceStyleID(), style_id)
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'First name')
        self.mpl.SelectAppearanceProfile(second)
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Second name')
        self.mpl.ApplyAppearanceStyle(style_id)
        self.assertEqual(self.mpl.GetAppearance().rowHeight, 31)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), palette_id)

    def test_style_selection_preserves_colors_and_profile_only_color_options(self):
        self.mpl.ApplyAppearanceColorPreset('copper')
        self.mpl.SetAppearanceValue('surfaceOpacity', .37)
        self.mpl.SetAppearanceValue('semanticColors', False)
        self.mpl.SetDungeonAlias(249, 'Personal name')
        colors = {field.key:plain(self.mpl.GetAppearance()[field.key])
                  for field in self.mpl.AppearanceFields.values() if field.kind == 'color'}
        self.mpl.ApplyAppearanceStyle('large')
        self.assertEqual(self.mpl.GetAppearance().fontSize, 14)
        self.assertEqual(self.mpl.GetAppearance().surfaceOpacity, .37)
        self.assertFalse(self.mpl.GetAppearance().semanticColors)
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Personal name')
        for key, color in colors.items():
            self.assertEqual(plain(self.mpl.GetAppearance()[key]), color)

    def test_template_rename_and_delete_do_not_rewrite_profiles(self):
        self.mpl.SetAppearanceValue('rowHeight', 31)
        style_id = self.mpl.CreateAppearanceStyle('Layout')
        self.mpl.ApplyAppearanceColorPreset('emerald')
        palette_id = self.mpl.CreateAppearancePalette('Palette')
        profile_id = self.mpl.CreateAppearanceProfile('Profile')
        original = plain(self.mpl.GetAppearance())
        self.assertTrue(self.mpl.RenameAppearanceStyle(style_id, 'Renamed layout'))
        self.assertTrue(self.mpl.RenameAppearancePalette(palette_id, 'Renamed palette'))
        self.assertEqual(self.mpl.GetAppearanceStyleID(), style_id)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), palette_id)
        self.assertTrue(self.mpl.DeleteAppearanceStyle(style_id))
        self.assertTrue(self.mpl.DeleteAppearancePalette(palette_id))
        self.assertEqual(self.mpl.GetAppearanceProfileID(), profile_id)
        self.assertEqual(plain(self.mpl.GetAppearance()), original)
        self.assertIsNone(self.mpl.GetAppearanceStyleID())
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'emerald')

    def test_template_lists_put_custom_entries_first_and_do_not_expose_mutable_data(self):
        self.mpl.SetAppearanceValue('rowHeight', 31)
        style_id = self.mpl.CreateAppearanceStyle('Z layout')
        self.mpl.ApplyAppearanceColorPreset('midnight')
        palette_id = self.mpl.CreateAppearancePalette('Z palette')
        styles = self.mpl.GetAppearanceStyles()
        palettes = self.mpl.GetAppearancePalettes()
        self.assertEqual(styles[1].id, style_id)
        self.assertEqual(palettes[1].id, palette_id)
        styles[1]['values'].rowHeight = 48
        palettes[1].colors.accentColor[1] = 0
        self.assertEqual(self.mpl.GetAppearanceStyles()[1]['values'].rowHeight, 31)
        self.assertNotEqual(self.mpl.GetAppearancePalettes()[1].colors.accentColor[1], 0)
        profile_id = self.mpl.CreateAppearanceProfile('Z profile')
        profiles = self.mpl.GetAppearanceProfiles()
        self.assertIn(profile_id, [entry.id for entry in profiles.values()])
        self.assertEqual(profiles[len(profiles)].id, 'classic')
        self.assertEqual(len([entry for entry in profiles.values() if entry.builtin]), 1)

    def test_templates_undo_cancel_and_invalid_requests_are_transactional(self):
        style_id = self.mpl.CreateAppearanceStyle('Layout')
        self.mpl.UndoAppearanceEdit()
        self.assertIsNone(self.mpl.GetAppearanceState().styles[style_id])
        self.mpl.CreateAppearancePalette('Palette')
        self.mpl.CancelAppearanceEdit()
        self.assertEqual(len(self.mpl.GetAppearanceState().palettes), 0)
        self.assertFalse(self.mpl.ApplyAppearanceStyle('missing')[0])
        self.assertFalse(self.mpl.ApplyAppearanceColorPreset('missing')[0])
        self.assertFalse(self.mpl.DeleteAppearanceStyle('classic')[0])
        self.assertFalse(self.mpl.RenameAppearancePalette('classic', 'Renamed')[0])
        self.assertIsNone(self.mpl.CreateAppearanceStyle('')[0])
        self.assertFalse(self.mpl.IsAppearanceEditing())

    def test_profile_export_import_is_standalone_after_templates_are_deleted(self):
        self.mpl.SetAppearanceValue('rowHeight', 31)
        style_id = self.mpl.CreateAppearanceStyle('Layout')
        self.mpl.ApplyAppearanceColorPreset('amethyst')
        palette_id = self.mpl.CreateAppearancePalette('Palette')
        self.mpl.SetDungeonAlias(249, 'Personal name')
        exported = self.mpl.ExportAppearance(True)
        original = plain(self.mpl.GetAppearance())
        self.mpl.DeleteAppearanceStyle(style_id)
        self.mpl.DeleteAppearancePalette(palette_id)
        self.mpl.SelectAppearanceProfile('classic')
        self.mpl.CreateAppearanceProfile('Imported')
        self.assertTrue(self.mpl.ImportAppearance(exported))
        restored = plain(self.mpl.GetAppearance())
        # Lua's existing data-only wire format rounds floating point text.
        for field in self.mpl.AppearanceFields.values():
            if field.kind == 'color':
                for i in range(1, 5):
                    self.assertAlmostEqual(restored[field.key][i], original[field.key][i])
            else:
                self.assertEqual(restored[field.key], original[field.key])
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Personal name')

    def test_import_included_aliases_replace_target_profile_alias_snapshot(self):
        source = self.mpl.CreateAppearanceProfile('Source')
        self.mpl.SetDungeonAlias(249, 'Source name')
        exported = self.mpl.ExportAppearance(True)
        self.mpl.CreateAppearanceProfile('Target')
        self.mpl.SetDungeonAlias(249, 'Target name')
        self.mpl.SetDungeonAlias(999, 'Foreign name')
        self.assertTrue(self.mpl.ImportAppearance(exported))
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Source name')
        self.assertIsNone(self.mpl.GetDungeonAlias(999))
        self.mpl.SelectAppearanceProfile(source)
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Source name')

    def test_import_empty_included_aliases_clear_target_alias_snapshot(self):
        self.mpl.CreateAppearanceProfile('Source')
        exported = self.mpl.ExportAppearance(True)
        self.mpl.CreateAppearanceProfile('Target')
        self.mpl.SetDungeonAlias(999, 'Foreign name')
        self.assertTrue(self.mpl.ImportAppearance(exported))
        self.assertIsNone(self.mpl.GetDungeonAlias(999))

    def test_import_omitted_aliases_preserve_target_alias_snapshot(self):
        self.mpl.CreateAppearanceProfile('Source')
        self.mpl.SetDungeonAlias(249, 'Source name')
        exported = self.mpl.ExportAppearance(False)
        self.mpl.CreateAppearanceProfile('Target')
        self.mpl.SetDungeonAlias(249, 'Target name')
        self.mpl.SetDungeonAlias(999, 'Foreign name')
        self.assertTrue(self.mpl.ImportAppearance(exported))
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Target name')
        self.assertEqual(self.mpl.GetDungeonAlias(999), 'Foreign name')

    def test_v1_profiles_names_bindings_values_and_aliases_migrate_losslessly(self):
        self.lua.execute('''
            MPlusLogsDB.appearance={schemaVersion=1,activeTheme="custom7",
                characterThemes={["Киндрих-Гордунни"]="custom7"},aliases={["249"]="Old name"},
                themes={custom7={name="Indrih",values={fontSize=17,backgroundColor={.1,.2,.3,.9}}}}}
        ''')
        state = self.mpl.InitAppearance()
        self.assertEqual(state.schemaVersion, 2)
        self.assertEqual(self.mpl.GetAppearanceProfileID(), 'custom7')
        self.assertEqual(self.mpl.GetAppearanceProfiles()[1].name, 'Indrih')
        self.assertEqual(self.mpl.GetAppearanceCharacterBinding(), 'character')
        self.assertEqual(self.mpl.GetAppearance().fontSize, 17)
        self.assertEqual(plain(self.mpl.GetAppearance().backgroundColor), {1:.1, 2:.2, 3:.3, 4:.9})
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Old name')
        self.mpl.CreateAppearanceProfile('Other')
        self.mpl.SetDungeonAlias(249, 'New name')
        self.mpl.SelectAppearanceProfile('custom7')
        self.assertEqual(self.mpl.GetDungeonAlias(249), 'Old name')
        self.assertFalse(self.lua.globals().MPlusLogsDB.options.tooltips)

    def test_v1_active_builtin_layout_remains_selectable_as_legacy_profile(self):
        self.lua.execute('MPlusLogsDB.appearance={schemaVersion=1,activeTheme="compact",themes={},aliases={}}')
        self.mpl.InitAppearance()
        self.assertEqual(self.mpl.GetAppearanceProfileID(), 'compact')
        self.assertIn('compact', [entry.id for entry in self.mpl.GetAppearanceProfiles().values()])
        self.assertEqual(self.mpl.GetAppearance().rowHeight, 22)
        self.mpl.SelectAppearanceProfile('classic')
        self.mpl.SaveAppearanceEdit()
        self.assertIn('compact', [entry.id for entry in self.mpl.GetAppearanceProfiles().values()])

    def test_same_values_preserve_explicit_template_identity_and_rename(self):
        first_style = self.mpl.CreateAppearanceStyle('A')
        second_style = self.mpl.CreateAppearanceStyle('B')
        self.assertEqual(self.mpl.GetAppearanceStyleID(), second_style)
        self.mpl.ApplyAppearanceStyle(first_style)
        self.assertEqual(self.mpl.GetAppearanceStyleID(), first_style)
        self.mpl.RenameAppearanceStyle(first_style, 'Z')
        self.assertEqual(self.mpl.GetAppearanceStyleID(), first_style)
        self.mpl.ApplyAppearanceStyle('classic')
        self.assertEqual(self.mpl.GetAppearanceStyleID(), 'classic')
        first_palette = self.mpl.CreateAppearancePalette('A')
        second_palette = self.mpl.CreateAppearancePalette('B')
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), second_palette)
        self.mpl.ApplyAppearanceColorPreset(first_palette)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), first_palette)
        self.mpl.RenameAppearancePalette(first_palette, 'Z')
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), first_palette)
        self.mpl.ApplyAppearanceColorPreset('classic')
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'classic')


class AppearanceProfileReloadTests(unittest.TestCase):
    def test_equal_template_choices_stay_independent_in_profiles_after_reload(self):
        lifecycle = lifecycle_tests.AppearancePersistenceTests()
        lua, mpl = lifecycle.runtime()
        style_a = mpl.CreateAppearanceStyle('A')
        palette_a = mpl.CreateAppearancePalette('A')
        profile_a = mpl.CreateAppearanceProfile('A')
        style_b = mpl.CreateAppearanceStyle('B')
        palette_b = mpl.CreateAppearancePalette('B')
        profile_b = mpl.CreateAppearanceProfile('B')
        # Restore each combination, despite identical materialized values.
        mpl.SelectAppearanceProfile(profile_a)
        mpl.ApplyAppearanceStyle(style_a)
        mpl.ApplyAppearanceColorPreset(palette_a)
        mpl.SelectAppearanceProfile(profile_b)
        lua.globals().FireEvent('PLAYER_LOGOUT')
        _, restored = lifecycle.runtime(lifecycle.saved(lua.globals().MPlusLogsDB))
        for profile, style, palette in ((profile_a, style_a, palette_a), (profile_b, style_b, palette_b)):
            restored.SelectAppearanceProfile(profile)
            self.assertEqual(restored.GetAppearanceStyleID(), style)
            self.assertEqual(restored.GetAppearanceColorPresetID(), palette)

    def test_named_profile_templates_and_aliases_survive_logout_and_fresh_runtime(self):
        lifecycle = lifecycle_tests.AppearancePersistenceTests()
        lua, mpl = lifecycle.runtime()
        mpl.SetAppearanceValue('fontSize', 17)
        style_id = mpl.CreateAppearanceStyle('Readable layout')
        mpl.ApplyAppearanceColorPreset('emerald')
        palette_id = mpl.CreateAppearancePalette('Forest')
        mpl.SetDungeonAlias(249, 'Personal name')
        profile_id = mpl.CreateAppearanceProfile('Indrih')
        lua.globals().FireEvent('PLAYER_LOGOUT')
        _, restored = lifecycle.runtime(lifecycle.saved(lua.globals().MPlusLogsDB))
        self.assertEqual(restored.GetAppearanceState().schemaVersion, 2)
        self.assertEqual(restored.GetAppearanceProfileID(), profile_id)
        self.assertEqual(restored.GetAppearanceStyleID(), style_id)
        self.assertEqual(restored.GetAppearanceColorPresetID(), palette_id)
        self.assertEqual(restored.GetDungeonAlias(249), 'Personal name')
        restored.ApplyAppearanceStyle('classic')
        restored.ApplyAppearanceColorPreset(palette_id)
        self.assertEqual(restored.GetAppearance().fontSize, 10)
        self.assertEqual(restored.GetAppearanceColorPresetID(), palette_id)


if __name__ == '__main__':
    unittest.main()
