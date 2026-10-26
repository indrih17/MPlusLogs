"""Proportional game-font digits must keep the same decimal-place positions."""
import unittest
from unittest.mock import patch

import test_addon


class LevelDigitAlignmentTests(unittest.TestCase):
    def setUp(self):
        mock = test_addon.MOCK.replace('function methods:GetText() return self.text or "" end', '''
            function methods:GetText() return self.text or "" end
            function methods:SetJustifyH(value) self.justifyH=value end
            function methods:GetUnboundedStringWidth()
                local widths={['1']=3,['2']=7,['0']=6}
                local width=0
                for char in tostring(self.text or ""):gmatch('.') do width=width+(widths[char] or 6) end
                return width
            end
        ''')
        with patch.object(test_addon, 'MOCK', mock):
            test_addon.AddonTests.setUp(self)
        self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        self.panel = self.mpl.panel
        self.mpl.AppearanceValue = self.lua.eval('function(key, fallback) if key=="levelDigits" then return "aligned" end; return fallback end')

    def show(self, levels):
        self.panel.profile = self.lua.table_from(dict(metric='dps', spec='All specs',
            dungeons=[dict(name='Dungeon '+str(i), level=level) for i,level in enumerate(levels)]), recursive=True)
        self.panel.viewMetric = 'dps'
        self.mpl.RenderProfileStats(self.panel)

    def leading_digit_center(self, row):
        cell = row.cells[2]
        digits = self.lua.eval('rawget')(row, 'levelDigits')
        if digits:
            digit = digits[1]
            point = digit.points.TOPRIGHT
            self.assertTrue(self.lua.eval('function(a,b) return a==b end')(point[1], cell))
            return cell.width + point[3] - digit.width / 2
        return cell.width - cell.GetUnboundedStringWidth(cell) + 7 / 2

    def test_leading_two_has_the_same_position_in_21_and_22(self):
        self.show([21,22])
        self.assertEqual(self.leading_digit_center(self.panel.rows[1]),
                         self.leading_digit_center(self.panel.rows[2]))
        for row in self.panel.rows.values():
            if row.shown:
                self.assertEqual(row.cells[2].justifyH, 'RIGHT')

    def test_units_start_on_same_vertical_and_have_equal_gap_in_21_and_22(self):
        self.show([21,22])
        def left(row, index):
            digit = row.levelDigits[index]
            start = row.cells[2].width + digit.points.TOPRIGHT[3] - digit.width
            unused = digit.width - digit.GetUnboundedStringWidth(digit)
            if digit.justifyH == 'CENTER':
                start += unused / 2
            elif digit.justifyH == 'RIGHT':
                start += unused
            return start
        first, second = self.panel.rows[1], self.panel.rows[2]
        self.assertEqual(left(first, 2), left(second, 2))
        def gap(row):
            return left(row, 2) - left(row, 1) - row.levelDigits[1].GetUnboundedStringWidth(row.levelDigits[1])
        self.assertEqual(gap(first), gap(second))

    def test_same_digit_step_survives_sort_and_different_number_lengths(self):
        self.show([21,22,1,100])
        for row in self.panel.rows.values():
            if not row.shown:
                continue
            self.assertEqual(row.cells[2].alpha, 0)
            self.assertEqual(row.levelDigitWidth, len(str(row.cells[2].text)) * 7)
            self.assertTrue(all(digit.width == 7 for digit in row.levelDigits.values() if digit.shown))
        self.panel.sortButtons[2].scripts.OnClick()
        self.assertEqual(self.panel.rows[1].cells[2].text, 100)
        self.assertEqual(self.panel.rows[1].levelDigits[1].text, '1')
        self.assertEqual(self.panel.rows[1].levelDigits[3].text, '0')

    def test_reused_row_hides_obsolete_digits_and_restores_missing_value(self):
        self.show([100])
        row = self.panel.rows[1]
        self.show([1])
        self.assertTrue(row.levelDigits[1].shown)
        self.assertFalse(row.levelDigits[2].shown)
        self.assertFalse(row.levelDigits[3].shown)
        self.show([None])
        self.assertEqual(row.cells[2].text, '—')
        self.assertEqual(row.cells[2].alpha, 1)
        self.assertTrue(all(not digit.shown for digit in row.levelDigits.values()))
        self.assertIsNone(self.lua.eval('rawget')(row, 'levelDigitWidth'))

    def test_metric_switch_redraws_native_digits_with_same_cell_positions(self):
        self.show([21])
        row = self.panel.rows[1]
        self.panel.profile.dual = True
        self.panel.profile.dungeons[1].otherLevel = 22
        self.panel.metricTabs.hps.scripts.OnClick()
        self.assertEqual(row.cells[2].text, 22)
        self.assertEqual(''.join(str(digit.text) for digit in row.levelDigits.values() if digit.shown), '22')
        self.assertEqual(row.levelDigitWidth, 14)

    def test_column_expands_to_fit_all_digit_slots(self):
        self.show([111111111111])
        row = self.panel.rows[1]
        self.assertGreaterEqual(row.cells[2].width, row.levelDigitWidth)


if __name__ == '__main__':
    unittest.main()
