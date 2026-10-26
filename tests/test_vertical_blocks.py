"""Vertical layout stacks production profile blocks, not only rating text.

The shared Lua mock measures geometry; it does not model game glyph rendering.
"""
import unittest

import test_profile_appearance as profiles


class VerticalBlockTests(unittest.TestCase):
    def setUp(self):
        self.fixture = profiles.ProfileAppearanceTests(methodName='runTest')
        self.fixture.setUp()
        self.lua, self.mpl, self.panel = self.fixture.lua, self.fixture.mpl, self.fixture.panel
        self.panel.profile.specRanks = self.lua.table_from(
            [{'spec': 'Guardian', 'rank': 123}], recursive=True)
        self.mpl.RenderProfileStats(self.panel)

    @staticmethod
    def top(field):
        return -field.points.TOPLEFT[2]

    def bottom(self, field):
        return self.top(field) + field.height

    def test_vertical_setting_stacks_specialization_rating_and_metric_controls(self):
        self.fixture.set('verticalLayout', True)
        panel = self.panel
        self.assertEqual(panel.ratingGroup.points.TOPLEFT[1], 20)
        self.assertGreaterEqual(self.top(panel.ratingGroup), self.bottom(panel.currentSpec) + 8)
        self.assertEqual(panel.metricTabs.dps.points.TOPLEFT[1], 20)
        self.assertGreaterEqual(self.top(panel.metricTabs.dps), self.bottom(panel.ratingGroup) + 8)

    def test_vertical_footer_stacks_runs_ranks_and_percentile_blocks(self):
        self.fixture.set('verticalLayout', True)
        panel = self.panel
        for compact in (False, True):
            with self.subTest(compact=compact):
                self.fixture.set('compactSummary', compact)
                runs, summary = panel.summaryHelp[3], panel.summaryHelp[1]
                self.assertEqual(runs.points.TOPLEFT[1], 20)
                self.assertEqual(panel.specRanks.points.TOPLEFT[1], 20)
                self.assertGreaterEqual(self.top(panel.specRanks), self.bottom(runs) + 8)
                rank_bottom = max(self.bottom(panel.specRanks),
                                  *(self.bottom(entry) for entry in panel.specRankEntries.values() if entry.shown))
                self.assertEqual(summary.points.TOPLEFT[1], 20)
                self.assertGreaterEqual(self.top(summary), rank_bottom + 8)
                if not compact:
                    median = panel.summaryHelp[2]
                    self.assertEqual(median.points.TOPLEFT[1], 20)
                    self.assertGreaterEqual(self.top(median), self.bottom(summary) + 8)
                self.assertTrue(all(not divider.shown for divider in panel.summarySeparators.values()))

    def test_disabling_vertical_layout_restores_horizontal_geometry(self):
        panel = self.panel
        fields = [panel.currentSpec, panel.ratingGroup, panel.metricTabs.dps,
                  panel.metricTabs.hps, panel.headerViewport, panel.specRanks,
                  panel.summaryHelp[1], panel.summaryHelp[2], panel.summaryHelp[3],
                  panel.context, panel.source]
        def geometry():
            return [(field.points.TOPLEFT[1], field.points.TOPLEFT[2], field.width, field.height)
                    for field in fields], panel.height
        baseline = geometry()
        self.fixture.set('verticalLayout', True)
        self.fixture.set('verticalLayout', False)
        self.assertEqual(geometry(), baseline)

    def test_stacking_keeps_manual_percentile_order_and_reflows_when_blocks_hide(self):
        self.fixture.set('columnOrder', ['dungeon','median','best','level','time','runs','points','rank','rate'])
        self.fixture.set('verticalLayout', True)
        panel = self.panel
        self.assertIn(self.mpl.L['Median % (avg)'], panel.summaryLabels[1].text)
        self.assertIn(self.mpl.L['Best % (avg)'], panel.summaryLabels[2].text)
        self.assertGreaterEqual(self.top(panel.summaryHelp[2]), self.bottom(panel.summaryHelp[1]) + 8)
        previous_height = panel.height
        self.fixture.set('showSpecRanks', False)
        self.assertLess(panel.height, previous_height)
        self.assertGreaterEqual(self.top(panel.summaryHelp[1]), self.bottom(panel.summaryHelp[3]) + 8)
        self.assertFalse(panel.specRanks.shown)
        self.assertTrue(all(not entry.shown for entry in panel.specRankEntries.values()))

    def test_show_summary_hides_entire_statistics_row_without_hiding_metadata_or_actions(self):
        panel = self.panel
        for vertical in (False, True):
            self.fixture.set('verticalLayout', vertical)
            for compact in (False, True):
                with self.subTest(vertical=vertical, compact=compact):
                    self.fixture.set('compactSummary', compact)
                    previous_height = panel.height
                    table_top = panel.headerViewport.points.TOPLEFT[2]
                    identity_position = (panel.currentSpec.points.TOPLEFT[1], panel.currentSpec.points.TOPLEFT[2])
                    retained = [panel.context, panel.source, panel.wclButton,
                                panel.searchButton, panel.loadButton]
                    previous_visibility = [field.shown for field in retained]
                    self.fixture.set('showSummary', False)
                    fields = [panel.summary, panel.medianSummary, panel.runSummary, panel.specRanks,
                              *panel.specRankEntries.values(), *panel.summaryLabels.values(),
                              *panel.summaryHelp.values(), *panel.summarySeparators.values()]
                    self.assertTrue(all(not field.shown for field in fields))
                    self.assertLess(panel.height, previous_height)
                    self.assertEqual(panel.headerViewport.points.TOPLEFT[2], table_top)
                    self.assertEqual((panel.currentSpec.points.TOPLEFT[1], panel.currentSpec.points.TOPLEFT[2]), identity_position)
                    self.assertEqual([field.shown for field in retained], previous_visibility)
                    self.fixture.set('showSummary', True)
                    self.assertTrue(panel.specRanks.shown)


if __name__ == '__main__':
    unittest.main()
