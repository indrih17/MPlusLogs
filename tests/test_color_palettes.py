"""Palette transactions, readable solid surfaces and real editor callbacks.

Contrast measurements exclude player opacity, game rendering and WCL's own
semantic percentile colors, which the palette does not change.
"""
import unittest

import test_addon_appearance as state_tests
import test_appearance_end_to_end as editor_tests


class ColorPaletteTests(unittest.TestCase):
    setUp = state_tests.AppearanceTests.setUp
    table = state_tests.AppearanceTests.table

    def test_every_palette_is_complete_and_changes_only_colors(self):
        self.mpl.SetAppearanceValue('fontSize', 17)
        self.mpl.SetAppearanceValue('surfaceOpacity', .9)
        self.mpl.SetAppearanceValue('semanticColors', False)
        before = self.mpl.CopyAppearanceValue(self.mpl.GetAppearance())
        for name in self.mpl.AppearanceColorPresetOrder.values():
            with self.subTest(palette=name):
                self.assertTrue(self.mpl.ApplyAppearanceColorPreset(name))
                theme = self.mpl.GetAppearance()
                self.assertEqual(self.mpl.GetAppearanceColorPresetID(), name)
                preset = self.mpl.AppearanceColorPresets[name]
                for field in self.mpl.AppearanceFields.values():
                    if field.kind == 'color':
                        self.assertEqual([theme[field.key][i] for i in range(1, 5)],
                                         [preset.colors[field.key][i] for i in range(1, 5)])
                    else:
                        self.assertEqual(theme[field.key], before[field.key], field.key)
                self.assertTrue(theme.legacyLayout)
                self.assertTrue(theme.legacyCenteredHeadings)
                self.assertEqual(list(theme.columnOrder.values()), list(before.columnOrder.values()))

    def test_palette_is_one_undo_step_and_cancel_preserves_saved_theme(self):
        self.mpl.SetAppearanceValue('fontSize', 17)
        self.mpl.ApplyAppearanceColorPreset('midnight')
        self.mpl.UndoAppearanceEdit()
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'classic')
        self.assertEqual(self.mpl.GetAppearance().fontSize, 17)
        self.mpl.ApplyAppearanceColorPreset('emerald')
        self.mpl.CancelAppearanceEdit()
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'classic')
        self.assertEqual(self.lua.globals().MPlusLogsDB.appearance.activeTheme, 'classic')

    def test_custom_colors_save_and_export_detection_do_not_mutate_presets(self):
        self.mpl.ApplyAppearanceColorPreset('copper')
        exported = self.mpl.ExportAppearance(False)
        self.mpl.SaveAppearanceEdit()
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'copper')
        self.mpl.SetAppearanceValue('accentColor', self.table([.1, .2, .3, 1]))
        self.assertIsNone(self.mpl.GetAppearanceColorPresetID())
        self.assertTrue(self.mpl.ImportAppearance(exported))
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'copper')
        self.assertAlmostEqual(self.mpl.AppearanceColorPresets.copper.colors.accentColor[1], 192/255)
        self.assertEqual(self.mpl.AppearancePresets.classic['values'].accentColor[1], .64)

    def test_unknown_palette_and_full_theme_store_do_not_change_state(self):
        self.assertFalse(self.mpl.ApplyAppearanceColorPreset('missing')[0])
        self.assertFalse(self.mpl.IsAppearanceEditing())
        for i in range(30):
            self.mpl.CreateAppearanceTheme('Theme '+str(i))
        self.mpl.SelectAppearanceTheme('classic')
        self.assertFalse(self.mpl.ApplyAppearanceColorPreset('midnight')[0])
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'classic')

    def test_dark_palettes_have_readable_primary_secondary_and_button_text(self):
        def luminance(color):
            components = [color[i]/12.92 if color[i] <= .04045 else
                          ((color[i]+.055)/1.055)**2.4 for i in range(1, 4)]
            return sum(a*b for a, b in zip(components, (.2126, .7152, .0722)))

        def contrast(first, second):
            high, low = sorted((luminance(first), luminance(second)), reverse=True)
            return (high+.05)/(low+.05)

        for name in self.mpl.AppearanceColorPresetOrder.values():
            if name == 'classic':
                continue
            colors = self.mpl.AppearanceColorPresets[name].colors
            for fg in ('textColor', 'mutedColor', 'buttonTextColor', 'numberColor', 'dungeonColor', 'rateColor'):
                for bg in ('backgroundColor', 'titleBackgroundColor', 'headerColor', 'stripeColor',
                           'buttonColor', 'hoverColor', 'selectedColor'):
                    with self.subTest(palette=name, foreground=fg, background=bg):
                        self.assertGreaterEqual(contrast(colors[fg], colors[bg]), 4.5)
            self.assertGreaterEqual(contrast(colors.warningTextColor, colors.warningColor), 4.5)

    def test_alternative_palettes_keep_black_surfaces_and_restrained_tints(self):
        defaults=self.mpl.AppearanceDefaults
        for name in self.mpl.AppearanceColorPresetOrder.values():
            if name=='classic':
                continue
            colors=self.mpl.AppearanceColorPresets[name].colors
            with self.subTest(palette=name):
                for key in ('backgroundColor','rowColor'):
                    self.assertEqual([colors[key][i] for i in range(1,4)],[0,0,0])
                for key in ('titleBackgroundColor','headerColor','buttonColor','stripeColor',
                            'hoverColor','selectedColor'):
                    rgb=[colors[key][i] for i in range(1,4)]
                    self.assertLessEqual(max(rgb),64/255,key)
                    self.assertLessEqual(max(rgb)-min(rgb),16/255,key)
                accent=[colors.accentColor[i] for i in range(1,4)]
                self.assertLessEqual(max(accent)-min(accent),40/255)
                for key in ('rateColor','ratingColor','warningColor','warningTextColor','disabledColor'):
                    self.assertEqual([colors[key][i] for i in range(1,5)],
                                     [defaults[key][i] for i in range(1,5)],key)


class ColorPaletteEditorTests(unittest.TestCase):
    setUp = editor_tests.AppearanceEndToEndTests.setUp
    click = staticmethod(editor_tests.AppearanceEndToEndTests.click)

    def test_palette_picker_applies_live_colors_and_reuses_other_choice_menus(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.colors)
        row = editor.extras.colorPalette
        self.assertEqual(row.control.text, self.mpl.L['Classic'])
        self.click(row.control)
        menu = editor.choices
        self.assertEqual(len(menu.buttons), 7)
        for choice in menu.buttons.values():
            self.assertTrue(all(swatch.shown for swatch in choice.paletteSwatches.values()))
        self.click(menu.buttons[3])
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'midnight')
        self.assertEqual(row.control.text, self.mpl.L['Midnight blue'])
        self.assertAlmostEqual(self.panel.titleFill.fillColor[1], 17/255)
        self.assertEqual(row.swatches[5].texture.fillColor[1], 157/255)
        self.mpl.SetAppearanceValue('accentColor', self.lua.table_from([.1, .2, .3, 1]))
        self.assertEqual(row.control.text, self.mpl.L['Custom colors'])
        self.click(editor.sectionButtons.fonts)
        self.click(editor.rows.font.control)
        self.assertTrue(all(not swatch.shown for swatch in menu.buttons[1].paletteSwatches.values()))
        self.click(editor.cancel)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'classic')

    def test_palette_names_are_searchable(self):
        editor = self.mpl.OpenAppearanceSettings()
        editor.search.SetText(editor.search, self.mpl.L['Emerald'])
        self.assertTrue(editor.extras.colorPalette.shown)
        self.assertFalse(editor.empty.shown)

    def test_profiles_section_saves_palette_in_selected_custom_profile(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.profiles)
        row = editor.extras.colorPalette
        self.assertTrue(row.shown)
        self.assertLess(-editor.extras.theme.points.TOPLEFT[2], -row.points.TOPLEFT[2])
        self.assertLess(-row.points.TOPLEFT[2], -editor.extras.profiles.points.TOPLEFT[2])
        editor.extras.profiles.name.SetText(editor.extras.profiles.name, 'Indrih')
        self.click(editor.extras.profiles.create)
        theme_id = self.mpl.GetAppearanceThemeID()
        self.click(row.control)
        self.click(editor.choices.buttons[4])  # Emerald
        self.assertEqual(self.mpl.GetAppearanceThemeID(), theme_id)
        self.click(editor.save)
        # Reinitialize from a fresh SavedVariables table, as after /reload.
        self.lua.execute('local MPL=...; MPlusLogsDB=MPL.CopyAppearanceValue(MPlusLogsDB); MPL.InitAppearance()', self.mpl)
        editor = self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.profiles)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'emerald')
        self.assertEqual(editor.extras.colorPalette.control.text, self.mpl.L['Emerald'])
        self.click(editor.extras.profile.control)
        self.assertEqual(editor.choices.buttons[1].choice, theme_id)
        self.mpl.SelectAppearanceTheme('classic')
        self.mpl.RefreshAppearanceEditor()
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'classic')
        self.mpl.SelectAppearanceTheme(theme_id)
        self.mpl.RefreshAppearanceEditor()
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'emerald')
        self.assertEqual(editor.extras.colorPalette.control.text, self.mpl.L['Emerald'])
        self.click(editor.extras.colorPalette.control)
        self.click(editor.choices.buttons[3])  # Midnight, discard this change
        self.click(editor.cancel)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(), 'emerald')


if __name__ == '__main__':
    unittest.main()
