"""Rank cells use their own WCL percentile, independently of DPS and position."""
import unittest
from unittest.mock import patch

import test_addon


class RankColorTests(unittest.TestCase):
    def setUp(self):
        mock = test_addon.MOCK.replace('function methods:GetText() return self.text or "" end', '''
            function methods:GetText() return self.text or "" end
            function methods:SetShadowColor(r,g,b,a) self.shadowColor={r,g,b,a} end
            function methods:SetShadowOffset(x,y) self.shadowOffset={x,y} end
        ''')
        with patch.object(test_addon, "MOCK", mock):
            test_addon.AddonTests.setUp(self)

    def show(self, rows):
        self.mpl.ShowProfile("Киндрих-Гордунни", None, None, True)
        panel = self.mpl.panel
        panel.profile = self.lua.table_from({
            "metric": "dps", "spec": "All specs", "dual": True,
            "dungeons": self.lua.table_from([self.lua.table_from(row) for row in rows]),
        })
        panel.viewMetric = "dps"
        self.mpl.RenderProfileStats(panel)
        return panel

    def assert_color(self, cell, color):
        expected = [int(color[offset:offset + 2], 16) / 255 for offset in (0, 2, 4)]
        for actual, value in zip(cell.textColor.values(), expected):
            self.assertAlmostEqual(actual, value)

    def test_rank_percentile_thresholds_reuse_existing_wcl_palette(self):
        for percentile, color in ((100, "e5cc80"), (99, "e268a8"),
                                  (98.999, "ff8000"), (95, "ff8000"),
                                  (94.999, "a335ee"), (75, "a335ee"),
                                  (74.999, "0070ff"), (50, "0070ff"),
                                  (49.999, "1eff00"), (25, "1eff00"),
                                  (24.999, "666666"), (0, "666666")):
            with self.subTest(percentile=percentile):
                panel = self.show([{"name": "Dungeon", "rank": 2500, "rankPercent": percentile}])
                self.assertEqual(panel.rows[1].cells[6].text, 2500)
                self.assert_color(panel.rows[1].cells[6], color)

    def test_close_ranks_can_have_different_colors_and_dps_does_not_drive_rank_color(self):
        panel = self.show([
            {"name": "Pink", "rank": 2362, "rankPercent": 99.1, "best": 1, "points": 471},
            {"name": "Orange", "rank": 2385, "rankPercent": 98.9, "best": 99, "points": 471},
        ])
        self.assert_color(panel.rows[1].cells[6], "e268a8")
        self.assert_color(panel.rows[2].cells[6], "ff8000")
        panel.sortButtons[6].scripts.OnClick()
        self.assertEqual(panel.rows[1].dungeonName, "Orange")
        self.assert_color(panel.rows[1].cells[6], "ff8000")
        self.assertEqual(panel.rows[2].dungeonName, "Pink")
        self.assert_color(panel.rows[2].cells[6], "e268a8")
        self.assert_color(panel.rows[1].cells[5], "e268a8")

    def test_metric_switch_clears_primary_rank_color_then_restores_it(self):
        panel = self.show([{"name": "Dungeon", "rank": 2990, "rankPercent": 98.7}])
        self.assert_color(panel.rows[1].cells[6], "ff8000")
        panel.metricTabs.hps.scripts.OnClick()
        self.assertEqual(panel.rows[1].cells[6].text, "—")
        self.assert_color(panel.rows[1].cells[6], "e1f2f5")
        panel.metricTabs.dps.scripts.OnClick()
        self.assert_color(panel.rows[1].cells[6], "ff8000")

    def test_old_and_missing_rank_metadata_stay_neutral(self):
        panel = self.show([
            {"name": "Legacy", "rank": 1000, "best": 99},
            {"name": "Missing rank", "rankPercent": 100},
        ])
        self.assertEqual(panel.rows[1].cells[6].text, 1000)
        self.assertEqual(panel.rows[2].cells[6].text, "—")
        for index in (1, 2):
            self.assert_color(panel.rows[index].cells[6], "e1f2f5")

    def test_low_sample_asterisk_follows_best_percentile_and_active_metric(self):
        panel = self.show([
            {"name": "Temple", "best": 11, "median": 11, "flagged": True,
             "otherBest": 28, "otherMedian": 14},
            {"name": "Other", "best": 50, "median": 28,
             "otherBest": 0, "otherMedian": 0, "otherFlagged": True},
        ])
        self.assertIn("11*|r", panel.rows[1].cells[8].text)
        self.assertNotIn("*", panel.rows[1].cells[9].text)
        panel.metricTabs.hps.scripts.OnClick()
        self.assertNotIn("*", panel.rows[1].cells[8].text)
        self.assertIn("0*|r", panel.rows[2].cells[8].text)
        self.assertNotIn("*", panel.rows[2].cells[9].text)
        self.mpl.SetOption("percentile", "median")
        self.mpl.RenderProfileStats(panel)
        self.assertNotIn("*", panel.rows[2].cells[8].text)
        self.assertIn("0*|r", panel.rows[2].cells[9].text)
        panel.sortButtons[1].scripts.OnClick()
        temple = next(row for row in panel.rows.values() if row.dungeonName == "Temple")
        self.assertNotIn("*", temple.cells[9].text)
        panel.metricTabs.dps.scripts.OnClick()
        self.assertIn("11*|r", temple.cells[9].text)

    def test_spec_ranks_have_a_light_caption_and_individual_colors(self):
        panel = self.show([{"name": "Dungeon"}])
        self.lua.execute('GetSpecializationInfoByID=function(id) return id,"Spec",nil,id*10 end')
        panel["class"] = "DRUID"
        panel.profile.specRanks = self.lua.table_from([
            self.lua.table_from({"spec": "Feral", "rank": 48, "rankPercent": 99.8}),
            self.lua.table_from({"spec": "Guardian", "rank": 207, "rankPercent": 99.2}),
            self.lua.table_from({"spec": "Balance", "rank": 1268, "rankPercent": 98.7}),
        ])
        self.mpl.RenderProfileStats(panel)
        self.assertEqual(panel.specRanks.text, "Spec Ranks:")
        self.assert_color(panel.specRanks, "e1f2f5")
        for index, rank, color in ((1, "48", "e268a8"), (2, "207", "e268a8"), (3, "1268", "ff8000")):
            entry = panel.specRankEntries[index]
            self.assertEqual(entry.number.text, rank)
            self.assert_color(entry.number, color)
            self.assertEqual(list(entry.number.shadowOffset.values()), [0.5, 0])
            self.assertTrue(entry.hasIcon)
            self.assertTrue(entry.icon.shown)
        panel.profile.specRanks = self.lua.table()
        self.mpl.RenderProfileStats(panel)
        self.assertFalse(panel.specRanks.shown)
        self.assertTrue(all(not entry.shown for entry in panel.specRankEntries.values()))

    def test_numeric_emphasis_keeps_percentile_colors_and_clears_for_missing_data(self):
        panel = self.show([{"name": "Dungeon", "level": 20, "time": "29:26", "runs": 30,
                            "points": 471, "rank": 2990, "rankPercent": 98.7,
                            "amount": 128040, "best": 50, "median": 28}])
        row = panel.rows[1]
        self.assertEqual(list(row.cells[1].shadowOffset.values()), [0, 0])
        self.assertEqual(row.cells[1].shadowColor[4], 0)
        self.assertEqual(list(row.cells[2].shadowOffset.values()), [0, 0])
        self.assertEqual(row.cells[2].shadowColor[4], 0)
        for digit in row.levelDigits.values():
            self.assertEqual(list(digit.shadowOffset.values()), [0, 0])
            self.assertEqual(digit.shadowColor[4], 0)
        for index in range(3, 10):
            self.assertEqual(list(row.cells[index].shadowOffset.values()), [0.5, 0])
            self.assertEqual(row.cells[index].shadowColor[4], 1)
        for index, color in ((6, "ff8000"), (8, "0070ff"), (9, "1eff00")):
            expected = [int(color[offset:offset + 2], 16) / 255 for offset in (0, 2, 4)]
            self.assertEqual([row.cells[index].shadowColor[channel] for channel in (1, 2, 3)], expected)
        panel.metricTabs.hps.scripts.OnClick()
        self.assertEqual(row.cells[6].text, "—")
        self.assertEqual(list(row.cells[6].shadowOffset.values()), [0, 0])
        self.assertEqual(row.cells[6].shadowColor[4], 0)


if __name__ == "__main__":
    unittest.main()
