"""Original header compatibility and switching through the production renderer."""
import unittest

import test_profile_appearance as appearance


class OriginalHeaderTests(unittest.TestCase):
    setUp = appearance.ProfileAppearanceTests.setUp

    def render(self, style):
        self.assertTrue(self.mpl.ApplyAppearanceStyle(style))
        self.mpl.RenderProfileStats(self.panel)

    def test_original_preset_restores_the_old_header_without_new_duplicates(self):
        self.render('original')
        panel = self.panel
        self.assertEqual(self.mpl.AppearanceValue('headerLayout'), 'original')
        self.assertEqual(panel.title.text, 'MPlusLogs — Warcraft Logs')
        self.assertTrue(panel.character.shown)
        self.assertTrue(panel.specButton.shown)
        self.assertIsNotNone(panel.currentSpec.points.TOPRIGHT)
        self.assertIsNotNone(panel.specButton.points.TOPRIGHT)
        self.assertGreaterEqual(-panel.specButton.points.TOPRIGHT[2],
                                -panel.currentSpec.points.TOPRIGHT[2]+panel.currentSpec.height)
        self.assertEqual(panel.scoreValue.fontSize, 30)
        self.assertTrue(panel.scoreValue.shown)
        self.assertFalse(panel.ratingGroup.shown)
        self.assertFalse(panel.extraLogsButton.shown)
        self.assertTrue(panel.logScope is None or not panel.logScope.shown)
        self.assertTrue(all(not field.shown for field in panel.summaryLabels.values()))
        self.assertGreater(panel.currentSpec.backdropColor[4], 0)
        self.assertGreater(-panel.headerViewport.points.TOPLEFT[2], 240)
        self.assertLess(-panel.context.points.TOPLEFT[2], -panel.headerViewport.points.TOPLEFT[2])

    def test_switching_back_restores_modern_geometry_and_palettes(self):
        panel = self.panel

        def geometry():
            fields = [panel.title, panel.currentSpec, panel.scoreLabel, panel.scoreValue,
                      panel.summary, panel.logScope, panel.headerViewport, panel.context]
            return tuple((tuple(field.points.TOPLEFT.values()) if field.points.TOPLEFT else None,
                          field.width, field.height, field.shown) for field in fields if field is not None)

        before = geometry()
        self.mpl.SetAppearanceValue('buttonColor', self.lua.table_from([.2, .3, .4, 1]))
        self.render('original')
        self.render('classic')
        self.assertEqual(geometry(), before)
        self.assertFalse(panel.character.shown)
        self.assertFalse(panel.specButton.shown)
        self.assertFalse(panel.contextFill.shown)
        self.assertEqual(panel.currentSpec.backdropColor[4], 0)
        self.assertEqual(panel.scoreValue.fontSize, 16)
        self.assertEqual([panel.specButton.backdropColor[i] for i in range(1, 4)], [.2, .3, .4])
        self.assertTrue(all(not tile.shown for i, tile in panel.appearanceBackdropParts.items() if i > 4))

    def test_original_header_survives_profile_save_export_and_import(self):
        self.render('original')
        self.assertTrue(self.mpl.CreateAppearanceTheme('Old header'))
        self.assertTrue(self.mpl.SaveAppearanceEdit())
        exported = self.mpl.ExportAppearance(False)
        self.render('clean')
        self.assertTrue(self.mpl.ImportAppearance(exported))
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(self.mpl.AppearanceValue('headerLayout'), 'original')
        self.assertTrue(self.panel.character.shown)
        self.assertTrue(self.panel.specButton.shown)
        self.assertTrue(self.panel.logScope is None or not self.panel.logScope.shown)

    def test_original_style_keeps_explicit_rating_size(self):
        self.render('original')
        self.mpl.SetAppearanceValue('size_rating', 24)
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(self.panel.scoreValue.fontSize, 24)
        self.assertEqual(self.mpl.AppearanceValue('headerLayout'), 'original')

    def test_original_selector_still_opens_the_current_themed_menu(self):
        self.render('original')
        appearance.ProfileAppearanceTests.capture_specialization_menu(self)
        panel = self.panel
        before = (panel.width, panel.height, panel.headerViewport.points.TOPLEFT[2])
        panel.specButton.scripts.OnClick(panel.specButton)
        self.assertTrue(panel.specMenu.shown)
        self.assertTrue(self.lua.eval('rawequal')(panel.specMenu.activeAnchor, panel.specButton))
        self.assertEqual(sum(entry.kind == 'radio' for entry in panel.specMenu.entries.values()), 3)
        self.assertEqual((panel.width, panel.height, panel.headerViewport.points.TOPLEFT[2]), before)

    def test_character_font_override_belongs_to_the_correct_visible_field(self):
        self.render('original')
        self.mpl.SetAppearanceValue('size_character', 24)
        self.mpl.RenderProfileStats(self.panel)
        self.assertTrue(self.panel.character.shown)
        self.assertEqual(self.panel.character.fontSize, 24)
        self.assertNotEqual(self.panel.title.fontSize, 24)
        self.mpl.SetAppearanceValue('headerLayout', 'modern')
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.panel.character.shown)
        self.assertEqual(self.panel.title.fontSize, 24)

    def test_original_preview_keeps_its_explicit_fictional_title(self):
        self.render('original')
        sample = self.mpl.ShowAppearancePreview()
        self.assertEqual(sample.title.text, self.mpl.L['MPlusLogs — Appearance preview'])
        self.assertEqual(sample.character.text, self.mpl.L['Sample character — fictional data'])
        self.assertTrue(sample.character.shown)

    def test_original_season_surface_has_no_gaps_or_double_root_fill(self):
        self.render('original')
        self.mpl.SetAppearanceValue('surfaceOpacity', .5)
        profile = self.panel.profile
        for loaded in (True, False, True):
            self.panel.profile = profile if loaded else None
            for season in (True, False, True):
                self.mpl.SetAppearanceValue('showSeason', season)
                self.mpl.RenderProfileStats(self.panel)
                panel = self.panel
                regions = [(1, 1, panel.width-1, 1+panel.titleFill.height)]
                if panel.contextFill.shown:
                    x, y = panel.contextFill.points.TOPLEFT.values()
                    regions.append((x, -y, x+panel.contextFill.width, -y+panel.contextFill.height))
                if loaded:
                    x, y = panel.headerViewport.points.TOPLEFT.values()
                    bottom = -y+panel.headerViewport.height+panel.scroll.height
                    regions.append((x, -y, x+panel.viewportWidth, bottom))
                for tile in panel.appearanceBackdropParts.values():
                    if tile.shown:
                        x, y = tile.points.TOPLEFT.values()
                        regions.append((x, -y, x+tile.width, -y+tile.height))
                        self.assertAlmostEqual(tile.fillColor[4], .5)
                xs = sorted({r[i] for r in regions for i in (0, 2)})
                ys = sorted({r[i] for r in regions for i in (1, 3)})
                for left, right in zip(xs, xs[1:]):
                    for top, bottom in zip(ys, ys[1:]):
                        x, y = (left+right)/2, (top+bottom)/2
                        self.assertEqual(sum(l<x<r and t<y<b for l,t,r,b in regions), 1,
                                         (loaded, season, x, y))


if __name__ == '__main__':
    unittest.main()
