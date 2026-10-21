"""Compact native numbers preserve WCL display values and source precision."""
import unittest

import test_level_digit_alignment as levels


class NumericFieldAlignmentTests(unittest.TestCase):
    setUp = levels.LevelDigitAlignmentTests.setUp

    def show(self, rows):
        self.panel.profile = self.lua.table_from(dict(metric='dps', spec='All specs', dual=True,
            score=4052, best=74, median=69.8, runs=122, dungeons=rows,
            specRanks=[dict(spec='Assassination', rank=1268, rankPercent=98)]), recursive=True)
        self.panel.viewMetric = 'dps'
        self.mpl.RenderProfileStats(self.panel)

    def test_statistics_keep_whole_native_strings(self):
        self.show([dict(name='Dungeon',level=21,time='31:21',runs=21,points=500.51,
                       rank=121,rankPercent=99,amount=510080,best=90,median=31,flagged=True)])
        row = self.panel.rows[1]
        self.assertEqual(row.cells[3].text,'31:21')
        self.assertEqual(row.cells[7].text,'510.08K')
        self.assertIn('90*|r',row.cells[8].text)
        fields = [row.cells[i] for i in range(3,10)]
        fields.extend((self.panel.scoreValue,self.panel.summary,self.panel.medianSummary,
                       self.panel.runSummary,self.panel.specRankEntries[1].number))
        for field in fields:
            self.assertIsNone(self.lua.eval('rawget')(field,'numericGlyphs'))

    def test_points_are_truncated_but_total_rating_and_source_data_are_unchanged(self):
        points = [500.51054166667,515.00353515625,501.49888257576,500.50582720588,
                  500.6890625,516.5213671875,515.75870833333,501.1243125]
        self.show([dict(name=str(i),points=value) for i,value in enumerate(points)])
        self.panel.profile.score = 4051.61223712539
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(self.panel.scoreValue.text,'4052')
        for row, value, raw in zip(self.panel.rows.values(),points,self.panel.profile.dungeons.values()):
            self.assertEqual(row.cells[5].text,str(int(value)))
            self.assertEqual(raw.points,value)


if __name__ == '__main__':
    unittest.main()
