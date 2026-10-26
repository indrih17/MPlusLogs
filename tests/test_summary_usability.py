"""Summary help and semantic swatches use production rendering, not pixels."""
import unittest

import test_profile_appearance as profiles


class SummaryUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = profiles.ProfileAppearanceTests(methodName='runTest')
        self.fixture.setUp()
        self.lua, self.mpl, self.panel = self.fixture.lua, self.fixture.mpl, self.fixture.panel
        self.lua.execute('''
            GameTooltip.SetOwner=function(self,owner) self.tooltipOwner=owner end
            GameTooltip.SetText=function(self,text) self.tooltipTitle=text end
            GameTooltip.AddLine=function(self,text) self.tooltipDetail=text end
            GameTooltip.IsOwned=function(self,owner) return self.tooltipOwner==owner end
        ''')

    def hover(self, index):
        help_frame = self.panel.summaryHelp[index]
        self.assertTrue(help_frame.shown)
        help_frame.scripts.OnEnter(help_frame)
        return self.lua.globals().GameTooltip

    def test_short_labels_and_help_move_together_with_table_order(self):
        self.fixture.set('columnOrder', ['dungeon','median','best','level','time','runs','points','rank','rate'])
        for metric in ('dps', 'hps'):
            self.panel.viewMetric = metric
            self.mpl.RenderProfileStats(self.panel)
            self.assertEqual(self.panel.summaryLabels[1].text, metric.upper()+' '+self.mpl.L['Median % (avg)']+':')
            tooltip = self.hover(1)
            self.assertEqual(tooltip.tooltipTitle, self.panel.summaryLabels[1].text)
            self.assertEqual(tooltip.tooltipDetail, self.mpl.L['Average of the median logged percentiles across dungeons.'])
            tooltip = self.hover(2)
            self.assertEqual(tooltip.tooltipDetail, self.mpl.L['Average of the best logged percentiles across dungeons. This is not the best single run.'])
            help_frame = self.panel.summaryHelp[2]
            caption, value = self.panel.summaryLabels[2], self.panel.medianSummary
            self.assertEqual(help_frame.points.TOPLEFT[1], caption.points.TOPLEFT[1])
            self.assertEqual(help_frame.points.TOPLEFT[1]+help_frame.width, value.points.TOPLEFT[1]+value.width)

    def test_compact_help_explains_both_values_and_hides_with_summary(self):
        self.fixture.set('compactSummary', True)
        tooltip = self.hover(1)
        self.assertIn(self.mpl.L['Average of the best logged percentiles across dungeons. This is not the best single run.'], tooltip.tooltipDetail)
        self.assertIn(self.mpl.L['Average of the median logged percentiles across dungeons.'], tooltip.tooltipDetail)
        self.assertIn(self.mpl.L['Best and Median follow the table column order.'], tooltip.tooltipDetail)
        self.assertFalse(self.panel.summaryHelp[2].shown)
        self.assertEqual(self.hover(3).tooltipDetail, self.mpl.L['Number of logged runs in this profile.'])
        self.fixture.set('showSummary', False)
        self.assertTrue(all(not item.shown for item in self.panel.summaryHelp.values()))
        # The geometry mock does not dispatch OnHide automatically.
        self.panel.summaryHelp[3].scripts.OnHide(self.panel.summaryHelp[3])
        self.assertFalse(tooltip.shown)
        self.fixture.set('showSummary', True)
        self.fixture.set('headerLayout', 'original')
        self.assertTrue(all(not item.shown for item in self.panel.summaryHelp.values()))

    def test_help_respects_tooltip_preference_and_current_dungeon_meaning(self):
        self.mpl.SetOption('percentile', 'dungeon_best')
        self.mpl.RenderProfileStats(self.panel)
        tooltip = self.hover(1)
        self.assertEqual(tooltip.tooltipDetail, self.mpl.L['Result for the currently listed dungeon, using the selected main metric.'])
        tooltip.Hide(tooltip)
        self.mpl.SetOption('tooltips', False)
        self.hover(1)
        self.assertFalse(tooltip.shown)

    def test_contrast_palette_reaches_table_summary_and_rank_colors(self):
        profile = self.panel.profile
        profile.best, profile.median = 10, 77
        profile.specRanks = self.lua.table_from([{'spec':'Guardian','rank':123,'rankPercent':10}], recursive=True)
        dungeon = profile.dungeons[1]
        dungeon.best, dungeon.median, dungeon.rankPercent = 10, 77, 55
        self.mpl.ApplyAppearanceColorPreset('contrast')
        self.mpl.RenderProfileStats(self.panel)
        self.assertIn('|cffb8bcc4', self.panel.summary.text)
        self.assertIn('|cffc68eff', self.panel.medianSummary.text)
        self.assertIn('|cffb8bcc4', self.panel.rows[1].cells[8].text)
        for field, hex_color in ((self.panel.rows[1].cells[6], '71a7ff'),
                                 (self.panel.specRankEntries[1].number, 'b8bcc4')):
            for channel, offset in enumerate((0, 2, 4), 1):
                self.assertAlmostEqual(field.textColor[channel], int(hex_color[offset:offset+2],16)/255)
        self.mpl.ApplyAppearanceColorPreset('classic')
        self.mpl.RenderProfileStats(self.panel)
        self.assertIn('|cff666666', self.panel.summary.text)

    def test_colons_and_texture_dividers_separate_visible_summary_groups(self):
        self.panel.profile.specRanks = self.lua.table_from([{'spec':'Guardian','rank':123}], recursive=True)
        self.mpl.RenderProfileStats(self.panel)
        for caption in self.panel.summaryLabels.values():
            self.assertTrue(caption.text.endswith(':'))
            self.assertFalse(caption.text.endswith('::'))
        separators = [item for item in self.panel.summarySeparators.values() if item.shown]
        self.assertEqual(len(separators),2)
        runs, best, median = (self.panel.summaryHelp[index] for index in (3,1,2))
        ranks = self.panel.specRanks
        pairs = ((runs.points.TOPLEFT[1]+runs.width,ranks.points.TOPLEFT[1]),
                 (best.points.TOPLEFT[1]+best.width,median.points.TOPLEFT[1]))
        for divider, (start,end) in zip(separators,pairs):
            self.assertEqual(divider.width,1)
            self.assertGreater(divider.points.TOPLEFT[1],start)
            self.assertLess(divider.points.TOPLEFT[1]+divider.width,end)
            self.assertLessEqual(divider.height,24)
            self.assertAlmostEqual(divider.fillColor[4],.35)
        ranks_end=self.panel.specRankEntries[1].points.TOPLEFT[1]+self.panel.specRankEntries[1].width
        self.assertGreater(best.points.TOPLEFT[1]-ranks_end,48)
        self.assertTrue(all(not (ranks_end<item.points.TOPLEFT[1]<best.points.TOPLEFT[1]) for item in separators))
        self.fixture.set('showSummary',False)
        self.assertTrue(all(not item.shown for item in self.panel.summarySeparators.values()))
        self.fixture.set('showSummary',True)
        self.fixture.set('headerLayout','original')
        self.assertTrue(all(not item.shown for item in self.panel.summarySeparators.values()))

    def test_wrapped_rows_have_no_edge_dividers_and_reuse_existing_textures(self):
        self.panel.profile.specRanks = self.lua.table()
        self.fixture.set('verticalLayout',True)
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,540,1080)
        self.fixture.set('size_secondary',40)
        self.fixture.set('size_summary',40)
        self.assertNotEqual(self.panel.summaryHelp[1].points.TOPLEFT[2],self.panel.summaryHelp[2].points.TOPLEFT[2])
        self.assertTrue(all(not item.shown for item in self.panel.summarySeparators.values()))
        count = len(self.panel.summarySeparators)
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(len(self.panel.summarySeparators),count)

    def test_specialization_name_uses_smaller_base_and_respects_font_preferences(self):
        self.assertEqual(self.panel.currentSpec.name.fontSize,14)
        self.fixture.set('fontSize',12)
        self.assertEqual(self.panel.currentSpec.name.fontSize,16)
        self.fixture.set('size_secondary',17)
        self.assertEqual(self.panel.currentSpec.name.fontSize,17)
        self.fixture.set('fontSize',10)
        self.assertEqual(self.panel.currentSpec.name.fontSize,17)
        self.fixture.set('size_secondary',0)
        self.assertEqual(self.panel.currentSpec.name.fontSize,14)


if __name__ == '__main__':
    unittest.main()
