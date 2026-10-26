"""Summary percentiles follow the table's semantic order across layouts.

Uses production rendering with the existing frame/text geometry mock. This
checks label/value associations and placement, not real glyph rasterization.
"""
import re
import unittest

import test_profile_appearance as profile_tests


class SummaryOrderTests(unittest.TestCase):
    def setUp(self):
        self.fixture = profile_tests.ProfileAppearanceTests(methodName='runTest')
        self.fixture.setUp()
        self.lua = self.fixture.lua
        self.mpl = self.fixture.mpl
        self.panel = self.fixture.panel
        profile = self.panel.profile
        profile.best, profile.median = 87.3, 42.1
        profile.otherBest, profile.otherMedian = 76.2, 31.4
        self.original = (profile.best, profile.median, profile.otherBest, profile.otherMedian)

    def set(self, key, value):
        self.fixture.set(key, value)

    @staticmethod
    def plain(text):
        return re.sub(r'\|c[0-9a-fA-F]{8}|\|r', '', text)

    def assert_summary_order(self, first, metric, compact, original):
        panel = self.panel
        expected = [87.3, 42.1] if metric == panel.profile.metric else [76.2, 31.4]
        expected_labels = [self.mpl.L['Лучший % в среднем:'], self.mpl.L['Медианный % в среднем:']]
        if not original:
            expected_labels = [self.mpl.L['Best % (avg)'], self.mpl.L['Median % (avg)']]
        if first == 'median':
            expected.reverse()
            expected_labels.reverse()
        if compact:
            text = self.plain(panel.summary.text)
            caption = 'Median / Best' if first == 'median' else 'Best / Median'
            self.assertIn(metric.upper() + ' ' + caption, text)
            self.assertLess(text.index(str(expected[0])), text.index(str(expected[1])))
        elif original:
            for field, label, value in zip((panel.summary, panel.medianSummary), expected_labels, expected):
                text = self.plain(field.text)
                self.assertIn(metric.upper() + ' ' + label, text)
                self.assertIn(str(value), text)
        else:
            for index, (field, label, value) in enumerate(zip((panel.summary, panel.medianSummary), expected_labels, expected), 1):
                self.assertIn(metric.upper() + ' ' + label.rstrip(': '), panel.summaryLabels[index].text)
                self.assertEqual(self.plain(field.text), str(value))
            first_position = (-panel.summaryLabels[1].points.TOPLEFT[2], panel.summaryLabels[1].points.TOPLEFT[1])
            second_position = (-panel.summaryLabels[2].points.TOPLEFT[2], panel.summaryLabels[2].points.TOPLEFT[1])
            self.assertLess(first_position, second_position)
        self.assertEqual((panel.profile.best, panel.profile.median, panel.profile.otherBest, panel.profile.otherMedian), self.original)

    def render(self, metric):
        self.panel.viewMetric = metric
        self.mpl.RenderProfileStats(self.panel)

    def test_automatic_order_tracks_global_percentile_for_all_header_modes(self):
        for original in (False, True):
            self.set('headerLayout', 'original' if original else 'modern')
            for compact in (False, True):
                self.set('compactSummary', compact)
                for first in ('best', 'median'):
                    self.mpl.SetOption('percentile', first)
                    for metric in ('dps', 'hps'):
                        with self.subTest(original=original, compact=compact, first=first, metric=metric):
                            self.render(metric)
                            self.assert_summary_order(first, metric, compact, original)

    def test_manual_column_order_overrides_global_percentile_for_all_header_modes(self):
        for original in (False, True):
            self.set('headerLayout', 'original' if original else 'modern')
            for compact in (False, True):
                self.set('compactSummary', compact)
                for first in ('best', 'median'):
                    second = 'median' if first == 'best' else 'best'
                    self.set('columnOrder', ['dungeon', first, 'level', 'rate', second, 'time', 'runs', 'rank', 'points'])
                    self.mpl.SetOption('percentile', second)
                    for metric in ('dps', 'hps'):
                        with self.subTest(original=original, compact=compact, first=first, metric=metric):
                            self.render(metric)
                            self.assertLess(self.panel.columns[self.mpl.ProfileColumnIndex(first)], self.panel.columns[self.mpl.ProfileColumnIndex(second)])
                            self.assert_summary_order(first, metric, compact, original)

    def test_hiding_table_percentiles_keeps_summary_order_and_independent_visibility(self):
        self.set('columnOrder', ['dungeon', 'median', 'level', 'best', 'rate', 'rank', 'time', 'points', 'runs'])
        self.mpl.SetOption('percentile', 'best')
        for compact in (False, True):
            self.set('compactSummary', compact)
            for hidden in (('best',), ('median',), ('best', 'median'), ()):
                with self.subTest(compact=compact, hidden=hidden):
                    for column in ('best', 'median'):
                        self.set('column_' + column + '_visible', column not in hidden)
                    self.render('dps')
                    self.assertTrue(self.panel.summary.shown)
                    self.assert_summary_order('median', 'dps', compact, False)
                    self.set('showSummary', False)
                    self.assertFalse(self.panel.summary.shown)
                    self.set('showSummary', True)
                    self.assert_summary_order('median', 'dps', compact, False)

    def test_current_dungeon_primary_summary_remains_explicit_and_does_not_accumulate_text(self):
        self.mpl.ListedDungeon = self.lua.eval('function(name) return function() return name end end')(self.panel.profile.dungeons[1].name)
        self.set('columnOrder', ['dungeon', 'median', 'level', 'best', 'rate', 'rank', 'time', 'points', 'runs'])
        for original in (False, True):
            self.set('headerLayout', 'original' if original else 'modern')
            for compact in (False, True):
                self.set('compactSummary', compact)
                for mode in ('dungeon_dps', 'dungeon_best', 'dungeon_median'):
                    self.mpl.SetOption('percentile', mode)
                    for metric in ('dps', 'hps'):
                        with self.subTest(original=original, compact=compact, mode=mode, metric=metric):
                            self.render(metric)
                            label = self.mpl.PrimaryPercentileLabel(metric)
                            text = self.plain(self.panel.summary.text)
                            if original or compact:
                                self.assertEqual(text.count(label), 1)
                            else:
                                self.assertEqual(self.panel.summaryLabels[1].text, label+':')
                            self.assertLessEqual(text.count(self.mpl.L['Runs'] + ':'), 1)
                            self.render(metric)
                            self.assertEqual(self.plain(self.panel.summary.text), text)

    def test_modern_compact_runs_and_ranks_stay_left_with_percentiles_at_right_edge(self):
        panel = self.panel
        self.set('compactSummary', True)
        for has_ranks in (False, True):
            panel.profile.specRanks = self.lua.table_from(
                [{'spec': 'Guardian', 'rank': 1260}] if has_ranks else [], recursive=True)
            with self.subTest(has_ranks=has_ranks):
                self.render('dps')
                self.assertTrue(panel.runSummary.shown)
                self.assertEqual(panel.runSummary.points.TOPLEFT[1], 20)
                self.assertEqual(panel.summary.points.TOPLEFT[1] + panel.summary.width,
                                 20 + panel.viewportWidth)
                self.assertNotIn(self.mpl.L['Runs'] + ':', self.plain(panel.summary.text))
                self.assertEqual(panel.specRanks.shown, has_ranks)
                if has_ranks:
                    self.assertGreaterEqual(panel.specRanks.points.TOPLEFT[1],
                                            panel.runSummary.points.TOPLEFT[1] + panel.runSummary.width + 24)
                    self.assertLessEqual(panel.specRankEntries[1].points.TOPLEFT[1] + panel.specRankEntries[1].width,
                                         panel.summary.points.TOPLEFT[1] - 24)
                self.fixture.assert_table_first_header()

    def test_modern_compact_hidden_summary_hides_ranks_too(self):
        panel = self.panel
        panel.profile.specRanks = self.lua.table_from([{'spec': 'Guardian', 'rank': 1260}], recursive=True)
        self.set('compactSummary', True)
        self.set('showSummary', False)
        self.render('dps')
        self.assertFalse(panel.summary.shown)
        self.assertFalse(panel.medianSummary.shown)
        self.assertFalse(panel.runSummary.shown)
        self.assertFalse(panel.specRanks.shown)
        self.assertTrue(all(not entry.shown for entry in panel.specRankEntries.values()))
        self.fixture.assert_table_first_header()
        self.set('showSpecRanks', False)
        self.assertFalse(panel.specRanks.shown)
        self.assertTrue(all(not entry.shown for entry in panel.specRankEntries.values()))
        self.fixture.assert_table_first_header()

    def test_all_presets_and_return_to_classic_keep_manual_summary_order(self):
        themes = list(self.mpl.AppearancePresetOrder.values()) + ['classic']
        for theme in themes:
            with self.subTest(theme=theme):
                self.assertTrue(self.mpl.SelectAppearanceTheme(theme))
                self.set('columnOrder', ['dungeon', 'median', 'level', 'best', 'rate', 'rank', 'time', 'points', 'runs'])
                self.mpl.SetOption('percentile', 'best')
                self.render('dps')
                self.assert_summary_order('median', 'dps', self.mpl.AppearanceValue('compactSummary'),
                                          self.mpl.AppearanceValue('headerLayout') == 'original')


if __name__ == '__main__':
    unittest.main()
