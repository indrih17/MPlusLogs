"""Header clicks sort displayed profile values without changing source profiles."""
import unittest

import test_addon


class ProfileSortingTests(unittest.TestCase):
    setUp = test_addon.AddonTests.setUp

    def show(self, rows, metric="dps"):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        panel = self.mpl.panel
        panel.profile = self.lua.table_from({
            "metric": metric, "spec": "All specs", "characterID": 81818678,
            "dungeons": self.lua.table_from([self.lua.table_from(row) for row in rows]),
        })
        panel.viewMetric = metric
        panel.sortColumn = False
        panel.sortAscending = False
        self.mpl.RenderProfileStats(panel)
        return panel

    def names(self, panel):
        return [row.dungeonName for row in panel.rows.values() if row.shown]

    def click(self, panel, column):
        panel.sortButtons[column].scripts.OnClick()

    def assert_sort_cycle(self, panel, column, descending, ascending):
        for expected, is_ascending in (
            (descending, False), (ascending, True), (descending, False)
        ):
            self.click(panel, column)
            self.assertEqual(self.names(panel), expected)
            self.assertEqual(panel.sortColumn, column)
            self.assertEqual(panel.sortAscending, is_ascending)
            for index in range(1, 10):
                self.assertEqual(panel.sortButtons[index].arrow.shown, index == column)

    def test_arrow_directions_are_reflections_of_the_same_size_and_shape(self):
        panel = self.show([{"name": "A", "level": 1}, {"name": "B", "level": 2}])
        arrow = panel.sortButtons[2].arrow

        def pixels():
            result = set()
            for texture in arrow.stripes.values():
                x, y = texture.points.TOPLEFT[1], texture.points.TOPLEFT[2]
                for dx in range(texture.width):
                    for dy in range(texture.height):
                        result.add((x + dx, y - dy))
            return result

        self.click(panel, 2)
        down = pixels()
        self.click(panel, 2)
        up = pixels()
        self.assertEqual((arrow.width, arrow.height), (7, 4))
        self.assertEqual(len(down), 16)
        self.assertEqual(up, {(x, -3 - y) for x, y in down})
        for shape in (down, up):
            self.assertEqual(max(x for x, _ in shape) - min(x for x, _ in shape) + 1, 7)
            self.assertEqual(max(y for _, y in shape) - min(y for _, y in shape) + 1, 4)

    def test_reopening_profile_resets_sort_but_visible_refresh_preserves_it(self):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        panel = self.mpl.panel
        original = self.names(panel)
        self.click(panel, 1)
        descending = self.names(panel)
        self.assertNotEqual(descending, original)
        self.mpl.ShowProfile("Киндрих-Гордунни", None, None, True)
        self.assertEqual(panel.sortColumn, 1)
        self.assertEqual(self.names(panel), descending)
        panel.Hide(panel)
        self.mpl.ShowProfile("Киндрих-Гордунни", None, None, True)
        self.assertFalse(panel.sortColumn)
        self.assertFalse(panel.sortAscending)
        self.assertEqual(self.names(panel), original)
        self.assertTrue(all(not panel.sortButtons[i].arrow.shown for i in range(1, 10)))
        self.click(panel, 1)
        self.assertFalse(panel.sortAscending)
        self.assertEqual(self.names(panel), descending)

    def test_initial_order_then_name_clicks_and_new_column_start_descending(self):
        panel = self.show([
            {"name": "Beta", "level": 10},
            {"name": "Alpha", "level": 20},
            {"name": "Gamma", "level": 0},
        ])
        self.assertEqual(self.names(panel), ["Beta", "Alpha", "Gamma"])
        self.assertFalse(panel.sortColumn)
        self.assertTrue(all(not panel.sortButtons[i].arrow.shown for i in range(1, 10)))
        self.assert_sort_cycle(panel, 1, ["Gamma", "Beta", "Alpha"], ["Alpha", "Beta", "Gamma"])
        self.click(panel, 1)  # Ascending again, before selecting another column.
        self.click(panel, 2)
        self.assertFalse(panel.sortAscending)
        self.assertEqual(self.names(panel), ["Alpha", "Beta", "Gamma"])

    def test_numeric_columns_keep_zero_and_stable_ties_with_unknown_values_last(self):
        for column, field in ((2, "level"), (4, "runs"), (5, "points"),
                              (6, "rank"), (7, "amount"), (8, "best"), (9, "median")):
            with self.subTest(column=column):
                panel = self.show([
                    {"name": "Middle", field: 9},
                    {"name": "High", field: 20},
                    {"name": "Zero", field: 0},
                    {"name": "Unknown"},
                    {"name": "Tie", field: 9},
                ])
                self.assert_sort_cycle(panel, column,
                    ["High", "Middle", "Tie", "Zero", "Unknown"],
                    ["Zero", "Middle", "Tie", "High", "Unknown"])
                self.assertEqual([panel.profile.dungeons[i].name for i in range(1, 6)],
                                 ["Middle", "High", "Zero", "Unknown", "Tie"])

    def test_duration_sort_uses_seconds_and_keeps_empty_times_last(self):
        panel = self.show([
            {"name": "Ten minutes", "time": "10:00"},
            {"name": "Unknown"},
            {"name": "Under ten", "time": "9:59"},
            {"name": "Over an hour", "time": "1:02:00"},
            {"name": "Empty", "time": ""},
            {"name": "Zero", "time": "0:00"},
        ])
        self.assert_sort_cycle(panel, 3,
            ["Over an hour", "Ten minutes", "Under ten", "Zero", "Unknown", "Empty"],
            ["Zero", "Under ten", "Ten minutes", "Over an hour", "Unknown", "Empty"])

    def test_percentile_columns_follow_the_selected_display_order(self):
        panel = self.show([
            {"name": "Best winner", "best": 90, "median": 10},
            {"name": "Median winner", "best": 20, "median": 80},
        ])
        self.mpl.SetOption("percentile", "median")
        self.mpl.RenderProfileStats(panel)
        self.assert_sort_cycle(panel, 8,
            ["Median winner", "Best winner"], ["Best winner", "Median winner"])
        self.assert_sort_cycle(panel, 9,
            ["Best winner", "Median winner"], ["Median winner", "Best winner"])
        # A display preference change reuses the column and direction.
        self.mpl.SetOption("percentile", "best")
        self.mpl.RenderProfileStats(panel)
        self.assertEqual(panel.sortColumn, 9)
        self.assertFalse(panel.sortAscending)
        self.assertEqual(self.names(panel), ["Median winner", "Best winner"])

    def test_metric_switch_resorts_values_and_hides_unavailable_metadata(self):
        panel = self.show([
            {"name": "DPS winner", "level": 20, "amount": 2000, "best": 90, "median": 80,
             "time": "30:00", "points": 500, "rank": 1,
             "otherLevel": 5, "otherAmount": 100, "otherBest": 10, "otherMedian": 5},
            {"name": "HPS winner", "level": 10, "amount": 1000, "best": 50, "median": 30,
             "time": "10:00", "points": 400, "rank": 2,
             "otherLevel": 9, "otherAmount": 500, "otherBest": 95, "otherMedian": 85},
        ])
        for column in (2, 7, 8, 9):
            with self.subTest(column=column):
                panel.sortColumn = False
                self.click(panel, column)
                self.assertEqual(self.names(panel), ["DPS winner", "HPS winner"])
                panel.metricTabs.hps.scripts.OnClick()
                self.assertEqual(panel.sortColumn, column)
                self.assertFalse(panel.sortAscending)
                self.assertEqual(self.names(panel), ["HPS winner", "DPS winner"])
                panel.metricTabs.dps.scripts.OnClick()
        panel.metricTabs.hps.scripts.OnClick()
        for column in (3, 5, 6):
            with self.subTest(metadata_column=column):
                self.assert_sort_cycle(panel, column,
                    ["DPS winner", "HPS winner"], ["DPS winner", "HPS winner"])
                self.assertEqual([panel.rows[i].cells[column].text for i in (1, 2)], ["—", "—"])

    def test_sorted_row_links_and_invitation_state_stay_with_the_correct_identity(self):
        panel = self.show([
            {"name": "Altar of Fangs", "level": 10},
            {"name": "Ruby Life Pools", "level": 20},
        ])
        panel.applicant = self.lua.table_from({"applicantID": 123, "name": "Киндрих", "realm": "Гордунни"})
        panel.inviteSent = True
        self.click(panel, 2)
        self.assertEqual(panel.applicant.applicantID, 123)
        self.assertTrue(panel.inviteSent)
        row = panel.rows[1]
        self.assertEqual(row.dungeonName, "Ruby Life Pools")
        row.scripts.OnMouseUp(row, "LeftButton")
        self.assertIn("/character/id/81818678?zone=55&boss=112521&metric=points_and_damage",
                      self.mpl.copy.edit.text)
        self.click(panel, 2)
        self.assertEqual(row.dungeonName, "Altar of Fangs")
        row.scripts.OnMouseUp(row, "LeftButton")
        self.assertIn("&boss=12993&", self.mpl.copy.edit.text)
        self.assertTrue(panel.inviteSent)

    def test_redraw_and_replacement_profile_keep_sort_but_missing_profile_hides_headers(self):
        panel = self.show([{"name": "A", "level": 1}, {"name": "B", "level": 2}])
        self.click(panel, 2)
        self.mpl.RenderProfileStats(panel)
        self.assertEqual(self.names(panel), ["B", "A"])
        panel.profile.dungeons = self.lua.table_from([
            self.lua.table_from({"name": "C", "level": 5}),
            self.lua.table_from({"name": "D", "level": 9}),
        ])
        self.mpl.RenderProfileStats(panel)
        self.assertEqual(self.names(panel), ["D", "C"])
        panel.profile = None
        self.mpl.RenderProfileStats(panel)
        self.assertEqual(self.names(panel), [])
        self.assertTrue(all(not panel.sortButtons[i].shown for i in range(1, 10)))

    def test_tutorial_sorting_keeps_live_sort_and_disabled_links_isolated(self):
        self.lua.execute('return assert(loadstring(...))',
            (test_addon.ROOT / "TutorialProfile.lua").read_text(encoding="utf-8"))("MPlusLogs", self.mpl)
        live = self.show([{"name": "A", "level": 1}, {"name": "B", "level": 2}])
        self.click(live, 2)
        tutorial = self.mpl.ShowTutorialProfile()
        self.click(tutorial, 4)
        self.assertEqual(self.names(tutorial)[0], "Voidscar Arena")
        self.assertEqual(live.sortColumn, 2)
        self.assertEqual(self.names(live), ["B", "A"])
        tutorial.specButton.scripts.OnClick()
        self.assertEqual(tutorial.sortColumn, 4)
        self.assertEqual(self.names(tutorial)[0], "Voidscar Arena")
        for row in tutorial.rows.values():
            # The frame mock fabricates no-op methods for unknown fields.
            self.assertIsNone(self.lua.eval('function(frame) return rawget(frame,"url") end')(row))
            self.assertIsNone(row.scripts.OnMouseUp)
            self.assertIsNone(row.scoreSpecIcon.scripts.OnMouseUp)
        tutorial.Hide(tutorial)
        self.mpl.ShowTutorialProfile()
        self.assertFalse(tutorial.sortColumn)
        self.assertFalse(tutorial.sortAscending)
        self.assertEqual(self.names(tutorial)[0], "Kings' Rest")
        self.assertTrue(all(not tutorial.sortButtons[i].arrow.shown for i in range(1, 10)))


if __name__ == "__main__":
    unittest.main()
