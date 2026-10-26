"""Appearance swatches retain semantic tiers and survive palette transactions.

Contrast checks use solid palette RGB surfaces, not the game scene or opacity.
"""
import unittest

import test_addon
import test_addon_appearance as appearance_tests


class PercentilePaletteTests(unittest.TestCase):
    def setUp(self):
        appearance_tests.AppearanceTests.setUp(self)
        test_addon.load_locales(self.lua, self.mpl)
        self.lua.execute('return assert(loadstring(...))',
                         (test_addon.ROOT / 'Data.lua').read_text(encoding='utf-8'))('MPlusLogs', self.mpl)

    table = appearance_tests.AppearanceTests.table

    @staticmethod
    def rgb(hex_color):
        return [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]

    @staticmethod
    def contrast(first, second):
        def luminance(color):
            channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in color]
            return sum(v * w for v, w in zip(channels, (.2126, .7152, .0722)))
        bright, dark = sorted((luminance(first), luminance(second)), reverse=True)
        return (bright + .05) / (dark + .05)

    def test_existing_palettes_retain_wcl_tiers_and_boundaries(self):
        values = (0, 24.99, 25, 49.99, 50, 74.99, 75, 94.99, 95, 98.99, 99, 99.99, 100)
        for palette in self.mpl.AppearanceColorPresetOrder.values():
            if palette == 'contrast':
                continue
            self.mpl.ApplyAppearanceColorPreset(palette)
            for value in values:
                with self.subTest(palette=palette, value=value):
                    self.assertEqual(self.mpl.AppearancePercentColor(value), self.mpl.PercentColor(value))
        for value in (None, '50', False, float('nan')):
            self.assertIsNone(self.mpl.AppearancePercentColor(value))

    def test_high_contrast_brightens_dim_tiers_on_solid_table_surfaces(self):
        self.mpl.SetAppearanceValue('surfaceOpacity', .3)
        self.mpl.ApplyAppearanceColorPreset('contrast')
        theme = self.mpl.GetAppearance()
        for value in (10, 50, 75):
            color = self.mpl.AppearancePercentColor(value)
            self.assertNotEqual(color, self.mpl.PercentColor(value))
            for surface in ('backgroundColor', 'rowColor', 'stripeColor', 'hoverColor'):
                background = [theme[surface][i] for i in range(1, 4)]
                with self.subTest(value=value, surface=surface):
                    self.assertGreaterEqual(self.contrast(self.rgb(color), background), 4.5)
        for value in (25, 49.99, 95, 99, 100):
            self.assertEqual(self.mpl.AppearancePercentColor(value), self.mpl.PercentColor(value))
        self.assertEqual(theme.surfaceOpacity, .3)
        self.assertTrue(theme.semanticColors)

    def test_disabled_semantics_use_number_color_without_changing_swatches(self):
        self.mpl.ApplyAppearanceColorPreset('contrast')
        self.mpl.SetAppearanceValue('numberColor', self.table([.2, .4, .6, .15]))
        before = self.mpl.AppearancePercentColor(10)
        self.mpl.SetAppearanceValue('semanticColors', False)
        for value in (10, 25, 50, 75, 99, 100):
            self.assertEqual(self.mpl.AppearancePercentColor(value), '336699')
        self.mpl.SetAppearanceValue('semanticColors', True)
        self.assertEqual(self.mpl.AppearancePercentColor(10), before)

    def test_palette_swatches_undo_cancel_save_and_export_as_data(self):
        self.mpl.SetAppearanceValue('surfaceOpacity', .4)
        self.mpl.SaveAppearanceEdit()
        self.mpl.ApplyAppearanceColorPreset('contrast')
        colors = [self.mpl.AppearancePercentColor(value) for value in (10, 50, 75)]
        self.mpl.UndoAppearanceEdit()
        self.assertEqual(self.mpl.AppearancePercentColor(10), '666666')
        self.mpl.ApplyAppearanceColorPreset('contrast')
        self.mpl.CancelAppearanceEdit()
        self.assertEqual(self.mpl.AppearancePercentColor(10), '666666')
        self.mpl.ApplyAppearanceColorPreset('contrast')
        exported = self.mpl.ExportAppearance(False)
        self.mpl.SaveAppearanceEdit()
        self.mpl.ApplyAppearanceColorPreset('classic')
        self.assertTrue(self.mpl.ImportAppearance(exported))
        self.assertEqual([self.mpl.AppearancePercentColor(v) for v in (10, 50, 75)], colors)
        self.assertEqual(self.mpl.GetAppearance().surfaceOpacity, .4)
        self.assertTrue(self.mpl.GetAppearance().semanticColors)

    def test_old_theme_values_gain_defaults_without_losing_user_preferences(self):
        normalized = self.mpl.NormalizeAppearance(self.table({'fontSize': 17, 'surfaceOpacity': .2}))
        self.assertEqual(normalized.fontSize, 17)
        self.assertEqual(normalized.surfaceOpacity, .2)
        self.assertEqual(normalized.semanticLowColor[1], 102 / 255)
        self.assertEqual(normalized.semanticRareColor[2], 112 / 255)
        self.assertEqual(normalized.semanticEpicColor[1], 163 / 255)


if __name__ == '__main__':
    unittest.main()
