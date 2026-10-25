"""Measured text expands columns and keeps headers, rows and groups aligned."""
import unittest

import test_addon
from test_localization import LOCALES


METRIC_MOCK = test_addon.MOCK.replace(
    'function methods:GetText() return self.text or "" end', '''
    function methods:GetText() return self.text or "" end
    function methods:SetColorTexture(r,g,b,a) self.fillColor={r,g,b,a} end
    function methods:SetWordWrap(value) self.wordWrap=value end
    function methods:SetNonSpaceWrap(value) self.nonSpaceWrap=value end
    function methods:GetUnboundedStringWidth()
        local text=tostring(self.text or ""):gsub("|c%x%x%x%x%x%x%x%x",""):gsub("|r","")
        local _,characters=text:gsub("[^\\128-\\191]","")
        return characters*7
    end
''').replace(
    'function methods:CreateTexture() return newFrame() end', '''
    function methods:CreateTexture(_, layer)
        local texture=newFrame(); texture.layer=layer; return texture
    end
''')


class ProfileLayoutTests(unittest.TestCase):
    def test_search_drawer_preserves_table_space_and_focus_across_redraws(self):
        _, mpl = self.runtime("enUS")
        panel = mpl.panel
        height = panel.height
        bottom = panel.scroll.points.BOTTOMRIGHT[2]
        self.assertFalse(panel.lookup.shown)
        self.assertFalse(panel.lookupDivider.shown)
        panel.searchButton.scripts.OnClick()
        self.assertTrue(panel.lookup.shown)
        self.assertTrue(panel.lookupDivider.shown)
        self.assertTrue(panel.lookup.focused)
        self.assertEqual(panel.height, height + 44)
        self.assertEqual(panel.scroll.points.BOTTOMRIGHT[2], bottom + 44)
        panel.metricTabs.hps.scripts.OnClick()
        self.assertTrue(panel.lookup.shown)
        self.assertEqual(panel.height, height + 44)
        panel.lookup.scripts.OnEscapePressed(panel.lookup)
        self.assertFalse(panel.lookup.shown)
        self.assertFalse(panel.lookup.focused)
        self.assertEqual(panel.height, height)

    def test_search_enter_uses_existing_navigation_and_applicant_collapses_drawer(self):
        lua, mpl = self.runtime("enUS")
        panel = mpl.panel
        height = panel.height
        panel.searchButton.scripts.OnClick()
        panel.lookup.SetText(panel.lookup, "  Alice-Area 52  ")
        lua.execute('local MPL=...; MPL.ShowProfile=function(name) lookupName=name end', mpl)
        panel.lookup.scripts.OnEnterPressed()
        self.assertEqual(lua.globals().lookupName, "Alice-Area 52")
        self.assertFalse(panel.lookup.focused)
        panel.applicant = lua.table_from({"groupSize": 1})
        mpl.ValidateApplicant = lua.eval('function() return true end')
        mpl.UpdateProfileInvite()
        mpl.RenderProfileStats(panel)
        self.assertFalse(panel.lookup.shown)
        self.assertFalse(panel.searchButton.shown)
        self.assertTrue(panel.inviteButton.shown)
        self.assertEqual(panel.height, height)
        panel.applicant = False
        mpl.UpdateProfileInvite()
        self.assertTrue(panel.searchButton.shown)
        self.assertFalse(panel.lookup.shown)

    def runtime(self, locale="ruRU"):
        lua = test_addon.LuaRuntime(unpack_returned_tuples=True)
        lua.execute(METRIC_MOCK)
        mpl = lua.table()
        test_addon.load_locales(lua, mpl, locale)
        for name in ("Data.lua", "Snapshot.lua", "UI.lua"):
            lua.execute("return assert(loadstring(...))",
                        (test_addon.ROOT / name).read_text(encoding="utf-8"))("MPlusLogs", mpl)
        lua.execute("MPlusLogsDB={profiles={},companionIntroDismissed=true}")
        mpl.ShowProfile("Киндрих", "Гордунни", None, True)
        return lua, mpl

    def assert_fits(self, panel):
        total = sum(panel.widths.values())
        self.assertEqual(panel.width, total + 60)
        for element in (panel.tableHeader, panel.content, panel.scroll,
                        panel.contextFill, panel.staleBanner):
            self.assertEqual(element.width, total)
        for i in range(1, 10):
            heading = panel.headings[i]
            self.assertFalse(heading.wordWrap)
            self.assertFalse(heading.nonSpaceWrap)
            self.assertGreaterEqual(heading.width, heading.GetUnboundedStringWidth(heading))
            self.assertEqual(panel.sortButtons[i].points.TOPLEFT[1], panel.columns[i] + 1)
        for group in (panel.primaryGroup, panel.secondaryGroup):
            self.assertGreaterEqual(group.width, group.GetUnboundedStringWidth(group))
        for row in panel.rows.values():
            self.assertEqual(row.width, total)
            self.assertEqual(row.background.width, total)
            self.assertEqual(row.bottomLine.width, total)
            self.assertEqual(row.rightLine.points.TOPLEFT[1], total - 1)
            if not row.shown:
                continue
            for i in range(1, 10):
                cell = row.cells[i]
                self.assertFalse(cell.wordWrap)
                self.assertGreaterEqual(cell.width, cell.GetUnboundedStringWidth(cell))
                self.assertEqual(cell.points.TOPLEFT[1], panel.columns[i] + (30 if i == 1 else 6))
                self.assertEqual(row.columnLines[i].points.TOPLEFT[1], panel.columns[i])

    def test_old_grid_is_used_even_with_obsolete_saved_design_preferences(self):
        lua, mpl = self.runtime("enUS")
        panel = mpl.panel
        panel.stale = False
        current_widths = list(panel.widths.values())
        for saved_preference in (True, False):
            lua.globals().MPlusLogsDB.options = lua.table_from({"legacyDesign": saved_preference})
            mpl.RenderProfileStats(panel)
            self.assert_fits(panel)
            height, header = 26, 40
            self.assertEqual(panel.tableHeader.height, header)
            self.assertEqual(panel.height, 656)
            self.assertEqual(panel.content.height, 8 * height)
            self.assertEqual(panel.scroll.points.TOPLEFT[2], -254 - header)
            available = panel.height + panel.scroll.points.TOPLEFT[2] - 145
            self.assertGreaterEqual(available, panel.content.height)
            self.assertEqual(panel.source.points.TOPLEFT[2], -522)
            self.assertEqual(panel.widths[1], current_widths[0])
            for index, row in panel.rows.items():
                self.assertEqual(row.height, height)
                self.assertEqual(row.points.TOPLEFT[2], -(index - 1) * height)
                self.assertEqual(row.bottomLine.points.TOPLEFT[2], 1 - height)
                self.assertEqual(row.icon.width, 20)
                self.assertEqual(row.scoreSpecIcon.width, 16)
                for cell in row.cells.values():
                    self.assertEqual(-cell.points.TOPLEFT[2] + cell.height / 2, height / 2)
                self.assertTrue(all(line.height == height for line in row.columnLines.values()))
                lines = [*row.columnLines.values(), row.rightLine, row.bottomLine]
                show_grid = index % 2 == 1
                for line in lines:
                    self.assertEqual(line.shown, show_grid)
                    self.assertEqual(list(line.fillColor.values()), [0.20] * 3 + [1])
                self.assertEqual(row.shade, 0.018 if index % 2 == 0 else 0)
            self.assertEqual(list(panel.widths.values()), current_widths)

    def test_locales_metrics_sort_and_banner_stay_aligned(self):
        for locale in LOCALES:
            with self.subTest(locale=locale):
                _, mpl = self.runtime(locale)
                panel = mpl.panel
                for metric in ("dps", "hps"):
                    panel.viewMetric = metric
                    mpl.RenderProfileStats(panel)
                    self.assert_fits(panel)
                    self.assertEqual(panel.headings[4].text, mpl.L["Runs"])
                    self.assertEqual(panel.headings[6].text, mpl.L["Rank"])
                    self.assertEqual(panel.metricHeading.text, mpl.L["Best HPS" if metric == "hps" else "Best DPS"])
                    panel.sortButtons[1].scripts.OnClick()
                    self.assert_fits(panel)
                    self.assertEqual(panel.sortColumn, 1)
                panel.stale = True
                mpl.RenderProfileStats(panel)
                offset = panel.staleBanner.height + 4
                self.assertEqual(panel.height, 656 + offset)
                self.assertEqual(panel.scroll.points.TOPLEFT[2], -294 - offset)
                self.assertEqual(panel.source.points.TOPLEFT[2], -522 - offset)
                self.assert_fits(panel)

    def test_all_locales_fit_dps_hps_and_swapped_percentile_headings(self):
        for locale in LOCALES:
            with self.subTest(locale=locale):
                _, mpl = self.runtime(locale)
                self.assert_fits(mpl.panel)
                mpl.panel.metricTabs.hps.scripts.OnClick()
                self.assert_fits(mpl.panel)
                mpl.SetOption("percentile", "median")
                mpl.RenderProfileStats(mpl.panel)
                self.assert_fits(mpl.panel)

    def test_proportions_density_centered_titles_and_row_grid(self):
        _, mpl = self.runtime("enUS")
        panel = mpl.panel
        self.assertEqual(panel.tableHeader.height, 40)
        self.assertEqual(panel.content.height, 8 * 26)
        self.assertGreater(panel.widths[1] / panel.tableWidth, 0.38)
        self.assertLess(panel.widths[1] / panel.tableWidth, 0.5)
        self.assertEqual(panel.tableWidth, 880)
        for i in range(1, 10):
            heading, button = panel.headings[i], panel.sortButtons[i]
            center = button.points.TOPLEFT[1] + heading.points.TOPLEFT[1] + heading.width / 2
            self.assertEqual(center, panel.columns[i] + panel.widths[i] / 2)
        for row in panel.rows.values():
            self.assertEqual(row.height, 26)
            self.assertEqual(row.background.layer, "BACKGROUND")
            self.assertEqual(row.rightLine.layer, "ARTWORK")
            self.assertEqual(row.bottomLine.layer, "ARTWORK")
            for line in row.columnLines.values():
                self.assertEqual(line.layer, "ARTWORK")

    def test_long_row_values_and_group_labels_expand_their_columns(self):
        lua, mpl = self.runtime()
        panel = mpl.panel
        original = [panel.widths[i] for i in range(1, 10)]
        name = "A very long dungeon name that needs additional horizontal space"
        panel.profile.dungeons = lua.table_from([lua.table_from({
            "name": name, "level": 20, "time": "1:12:34", "runs": 123456789012,
            "points": 123456789012, "rank": 123456789012,
            "amount": 123456789012345, "best": 100, "median": 100,
        })])
        panel.primaryGroup.SetText(panel.primaryGroup, "Score " * 35)
        mpl.RenderProfileStats(panel)
        self.assertGreater(panel.widths[1], original[0])
        self.assertGreater(panel.widths[4], original[3])
        self.assertGreater(panel.widths[5] + panel.widths[6], original[4] + original[5])
        self.assert_fits(panel)
        panel.sortButtons[4].scripts.OnClick()
        self.assertEqual(panel.rows[1].dungeonName, name)
        self.assert_fits(panel)

    def test_metric_heading_resize_moves_columns_and_player_tabs_without_growth_on_redraw(self):
        lua, mpl = self.runtime()
        panel = mpl.panel
        panel.groupPlayers = lua.table_from([
            lua.table_from({"name": "Киндрих", "realm": "Гордунни"}),
            lua.table_from({"name": "Alice", "realm": "Area 52"}),
        ])
        mpl.RenderPlayerTabs(panel)
        mpl.L["Best HPS"] = "A much longer healing performance heading"
        panel.metricTabs.hps.scripts.OnClick()
        self.assert_fits(panel)
        self.assertEqual(panel.playerTabs[1].width, panel.tableWidth / 2 - 4)
        self.assertEqual(panel.playerTabs[2].points.BOTTOMLEFT[3], 20 + panel.tableWidth / 2)
        width = panel.width
        for _ in range(3):
            mpl.RenderProfileStats(panel)
            self.assertEqual(panel.width, width)
        panel.metricTabs.dps.scripts.OnClick()
        self.assertLess(panel.width, width)
        self.assert_fits(panel)


if __name__ == "__main__":
    unittest.main()
