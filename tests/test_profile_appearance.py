"""Integrated appearance rendering with measured text; no game requests.

Models frame geometry and callbacks, not actual glyph coverage or GPU blending.
"""
import unittest

from test_addon import ROOT, LuaRuntime, load_locales
from test_profile_layout import METRIC_MOCK


MOCK = METRIC_MOCK.replace('return characters*7', 'return characters*7*(self.fontSize or 10)/10').replace('local function newFrame()', 'local function newFrame() frameCount=(frameCount or 0)+1').replace(
    'return methods[k] or function() end end',
    'return methods[k] or (type(k)=="string" and k:match("^[A-Z]") and function() end or nil) end',
).replace('function methods:CreateFontString() return newFrame() end', '''
    function methods:CreateFontString(_,_,template)
        local field=newFrame()
        field.font="Fonts\\\\FRIZQT___CYR.TTF"
        field.fontSize=template and template:find("Small") and 10 or 12
        field.fontFlags=""
        return field
    end
    function methods:GetScript(name) return self.scripts[name] end
    function methods:GetFont() return self.font or "Fonts\\\\FRIZQT___CYR.TTF",self.fontSize or 10,self.fontFlags or "" end
    function methods:SetFont(path,size,flags) self.font=path; self.fontSize=size; self.fontFlags=flags; return true end
    function methods:GetVerticalScroll() return self.verticalScroll or 0 end
    function methods:SetVerticalScroll(value) self.verticalScroll=value end
    function methods:SetHorizontalScroll(value) self.horizontalScroll=value end
    function methods:SetParent(parent) self.parent=parent end
    function methods:SetValue(value)
        self.value=value
        if self.scripts.OnValueChanged then self.scripts.OnValueChanged(self,value) end
    end
    function methods:SetScale(value) self.scale=value end
    function methods:GetScale() return self.scale or 1 end
    function methods:SetShadowColor(r,g,b,a) self.shadowColor={r,g,b,a} end
    function methods:SetShadowOffset(x,y) self.shadowOffset={x,y} end
    function methods:SetNormalFontObject(object)
        self.normalFontObject=object
        if type(object)=="table" and self.caption then self.caption:SetFont(object:GetFont()) end
    end
    function methods:SetHighlightFontObject(object) self.highlightFontObject=object end
    function methods:SetDisabledFontObject(object) self.disabledFontObject=object end
    function methods:GetStringHeight() return 14 end
    function methods:SetBackdropColor(r,g,b,a) self.backdropColor={r,g,b,a} end
    function methods:SetBackdropBorderColor(r,g,b,a) self.borderColor={r,g,b,a} end
    function methods:SetSnapToPixelGrid(value) self.snapToPixelGrid=value end
    function methods:SetTexelSnappingBias(value) self.texelSnappingBias=value end
    function methods:SetJustifyH(value) self.justifyH=value end
''')


# WoW hooks append to a constructor's script rather than replacing it.
MOCK=MOCK.replace('function methods:HookScript(name, callback) self.scripts[name] = callback end', '''
    function methods:HookScript(name,callback)
        local previous=self.scripts[name]
        self.scripts[name]=function(...)
            if previous then previous(...) end
            callback(...)
        end
    end
''')


class ProfileAppearanceTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.mpl=self.lua.table()
        load_locales(self.lua,self.mpl)
        self.lua.execute('''
            UIParent:SetSize(1920,1080); MPlusLogsDB={profiles={},companionIntroDismissed=true}
            function CreateFont(name) return CreateFrame("Font",name) end
        ''')
        for name in ('Data.lua','Snapshot.lua','Appearance.lua','AppearancePresets.lua',
                     'DungeonNames.lua','ProfileAppearance.lua','UI.lua','Integration.lua'):
            self.lua.execute('return assert(loadstring(...))',(ROOT/name).read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.mpl.ShowProfile('Киндрих','Гордунни',None,True)
        self.panel=self.mpl.panel
        self.show_profile=self.mpl.ShowProfile
        self.lua.execute('local MPL=...; MPL.ShowProfile=function() error("appearance must not navigate") end; MPL.ShowDownload=function() error("appearance must not request") end',self.mpl)

    def set(self,key,value):
        if isinstance(value,(dict,list)):
            value=self.lua.table_from(value,recursive=True)
        result=self.mpl.SetAppearanceValue(key,value)
        self.assertTrue(result[0] if isinstance(result,tuple) else result)

    def assert_table_first_header(self):
        panel=self.panel
        top=lambda field:-field.points.TOPLEFT[2]
        bottom=lambda field:top(field)+field.height
        self.assertFalse(panel.character.shown)
        self.assertTrue(panel.title.shown)
        self.assertEqual(panel.character.height,0)
        self.assertEqual(panel.title.text,panel.character.text)
        self.assertEqual(panel.currentSpec.points.TOPLEFT[1],panel.title.points.TOPLEFT[1])
        self.assertEqual(top(panel.currentSpec),panel.appearanceTitleBand+12)
        identity_bottom=bottom(panel.currentSpec)
        self.assertEqual(panel.ratingGroup.shown,panel.scoreValue.shown)
        if panel.scoreValue.shown:
            group=panel.ratingGroup
            if panel.appearanceCompact:
                self.assertEqual(panel.scoreLabel.justifyH,'CENTER')
                self.assertEqual(panel.scoreValue.justifyH,'CENTER')
                self.assertEqual(panel.scoreLabel.points.TOPLEFT[1],panel.scoreValue.points.TOPLEFT[1])
                self.assertEqual(panel.scoreValue.points.TOPLEFT[1],group.points.TOPLEFT[1]+8)
                self.assertEqual(top(panel.scoreLabel),top(group)+5)
                self.assertGreaterEqual(top(panel.scoreValue),bottom(panel.scoreLabel)+2)
                self.assertLessEqual(bottom(panel.scoreValue),bottom(group)-5)
            else:
                self.assertEqual(panel.scoreLabel.justifyH,'LEFT')
                self.assertEqual(panel.scoreValue.justifyH,'LEFT')
                self.assertEqual(panel.scoreLabel.points.TOPLEFT[1],group.points.TOPLEFT[1]+8)
                self.assertEqual(panel.scoreValue.points.TOPLEFT[1],panel.scoreLabel.points.TOPLEFT[1]+panel.scoreLabel.width+8)
                self.assertAlmostEqual(top(panel.scoreLabel)+panel.scoreLabel.height/2,
                                       top(panel.scoreValue)+panel.scoreValue.height/2)
                self.assertLessEqual(bottom(panel.scoreValue),bottom(group)-6)
            if group.points.TOPLEFT[1]>panel.character.points.TOPLEFT[1]:
                self.assertEqual(group.points.TOPLEFT[1],panel.character.points.TOPLEFT[1]+panel.character.width+24)
                if panel.appearanceCompact:
                    self.assertEqual(top(group),top(panel.currentSpec))
                else:
                    expected_y=max(panel.appearanceTitleBand+6,top(panel.currentSpec)+(panel.currentSpec.height-group.height)/2)
                    self.assertEqual(top(group),expected_y)
            else:
                self.assertGreaterEqual(top(group),bottom(panel.currentSpec)+12)
            identity_bottom=max(identity_bottom,bottom(group))
        table_top=top(panel.headerViewport)
        self.assertIsNone(panel.logScope)
        metric_tabs=[panel.metricTabs[metric] for metric in ('dps','hps')]
        self.assertTrue(all(tab.shown for tab in metric_tabs))
        metric_top=min(top(tab) for tab in metric_tabs)
        metric_bottom=max(bottom(tab) for tab in metric_tabs)
        for tab in metric_tabs:
            self.assertGreaterEqual(tab.points.TOPLEFT[1],20)
            self.assertLessEqual(tab.points.TOPLEFT[1]+tab.width,20+panel.viewportWidth+1e-7)
            self.assertAlmostEqual(top(tab)+tab.height/2,top(metric_tabs[0])+metric_tabs[0].height/2)
        self.assertLessEqual(metric_tabs[0].points.TOPLEFT[1]+metric_tabs[0].width+8,
                             metric_tabs[1].points.TOPLEFT[1])
        offset=panel.staleBanner.height+4 if panel.staleBanner.shown else 0
        if panel.appearanceMetricInline:
            self.assertFalse(panel.appearanceCompact)
            self.assertGreaterEqual(metric_tabs[0].points.TOPLEFT[1],
                                    panel.currentSpec.points.TOPLEFT[1]+panel.currentSpec.width+24)
            if panel.ratingGroup.shown:
                self.assertGreaterEqual(metric_tabs[0].points.TOPLEFT[1],
                                        panel.ratingGroup.points.TOPLEFT[1]+panel.ratingGroup.width+24)
        else:
            self.assertGreaterEqual(metric_top,identity_bottom+8)
        identity_bottom=max(identity_bottom,metric_bottom)
        self.assertGreaterEqual(table_top-offset,identity_bottom+6)
        self.assertLessEqual(table_top-offset-identity_bottom,16)
        table_bottom=bottom(panel.scroll)
        stats_bottom=table_bottom
        for caption,value in zip(panel.summaryLabels.values(),(panel.summary,panel.medianSummary,panel.runSummary)):
            if caption.shown:
                self.assertTrue(value.shown)
                self.assertGreaterEqual(top(caption),table_bottom+8)
                if top(value)>=bottom(caption):
                    self.assertEqual(caption.points.TOPLEFT[1],value.points.TOPLEFT[1])
                    self.assertGreaterEqual(top(value),bottom(caption)+2)
                else:
                    self.assertLessEqual(caption.points.TOPLEFT[1]+caption.width+8,value.points.TOPLEFT[1])
                    self.assertAlmostEqual(top(caption)+caption.height/2,top(value)+value.height/2)
                stats_bottom=max(stats_bottom,bottom(caption),bottom(value))
                self.assertLessEqual(value.points.TOPLEFT[1]+value.width,20+panel.viewportWidth+1e-7)
        for value in (panel.summary,panel.medianSummary,panel.runSummary):
            if value.shown:
                self.assertGreaterEqual(top(value),table_bottom+8)
                stats_bottom=max(stats_bottom,bottom(value))
        if panel.specRanks.shown:
            self.assertGreaterEqual(top(panel.specRanks),table_bottom+8)
            stats_bottom=max(stats_bottom,bottom(panel.specRanks))
            for entry in panel.specRankEntries.values():
                if entry.shown:
                    self.assertGreaterEqual(top(entry),table_bottom+8)
                    stats_bottom=max(stats_bottom,bottom(entry))
                    self.assertLessEqual(entry.points.TOPLEFT[1]+entry.width,20+panel.viewportWidth+1e-7)
        self.assertFalse(panel.contextFill.shown)
        for field in (panel.context,panel.source,panel.note,panel.footer):
            if field.shown:
                self.assertGreaterEqual(top(field),stats_bottom+8)
        actions_top=panel.height-panel.wclButton.points.BOTTOMLEFT[2]-panel.wclButton.height
        self.assertGreaterEqual(actions_top,stats_bottom+8)
        name=panel.currentSpec.name
        natural_right=panel.currentSpec.points.TOPLEFT[1]+name.points.TOPLEFT[1]+name.width
        self.assertEqual(panel.extraLogsButton.points.TOPLEFT[1],natural_right+8)
        self.assertEqual((panel.extraLogsButton.width,panel.extraLogsButton.height),(24,24))
        if panel.appearanceMetricInline:
            self.assertLessEqual(panel.extraLogsButton.points.TOPLEFT[1]+panel.extraLogsButton.width,
                                 metric_tabs[0].points.TOPLEFT[1])
        else:
            self.assertLessEqual(bottom(panel.extraLogsButton),metric_top)
        self.assertFalse(panel.specButton.shown)

    def capture_specialization_menu(self):
        self.lua.execute('''
            local MPL=...
            MenuUtil={CreateContextMenu=function() error("Use the themed specialization menu") end}
            MPL.ProfileSpecs=function() return {"Guardian","Restoration"} end
            MPL.MainProfileSpec=function() return "Guardian" end
            MPL.GetProfile=function(_,_,spec)
                if spec=="All specs" or spec=="Guardian" then return MPL.panel.profile end
            end
        ''',self.mpl)

    def test_builtin_themes_keep_footer_clear_of_the_table_and_actions(self):
        for theme in self.mpl.AppearancePresetOrder.values():
            with self.subTest(theme=theme):
                self.mpl.SelectAppearanceTheme(theme)
                self.mpl.RenderProfileStats(self.panel)
                panel=self.panel
                table_bottom=-panel.scroll.points.TOPLEFT[2]+panel.scroll.height
                footer_fields=(panel.source,panel.note,panel.footer) if self.mpl.AppearanceValue('headerLayout')=='original' else (panel.context,panel.source,panel.note,panel.footer)
                fields=[field for field in footer_fields if field.shown]
                actions_top=panel.height-panel.wclButton.points.BOTTOMLEFT[2]-panel.wclButton.height
                if fields:
                    if self.mpl.AppearanceValue('headerLayout')=='original':
                        self.assertEqual(-fields[0].points.TOPLEFT[2]-table_bottom,8)
                    else:
                        self.assertGreaterEqual(-fields[0].points.TOPLEFT[2]-table_bottom,8)
                        self.assert_table_first_header()
                    last=fields[-1]
                    self.assertEqual(actions_top-(-last.points.TOPLEFT[2]+last.height),8)
                elif self.mpl.AppearanceValue('headerLayout')=='original':
                    self.assertLessEqual(actions_top-table_bottom,8)
                else:
                    self.assert_table_first_header()
                self.assertEqual(panel.note.shown,self.mpl.AppearanceValue('showNotes'))
                self.assertFalse(panel.footer.shown)

    def test_lower_actions_clear_operational_footer_with_search_or_applicant(self):
        for applicant,expanded in ((False,True),(True,False)):
            self.panel.applicant=self.lua.table_from({'groupSize':1}) if applicant else None
            self.panel.lookupExpanded=expanded
            self.panel.footer.SetText(self.panel.footer,'A recoverable download error')
            self.mpl.RenderProfileStats(self.panel)
            panel=self.panel
            self.assertTrue(panel.footer.shown)
            footer_bottom=-panel.footer.points.TOPLEFT[2]+panel.footer.height
            for button,anchor in ((panel.wclButton,'BOTTOMLEFT'),(panel.loadButton,'BOTTOMRIGHT')):
                button_top=panel.height-button.points[anchor][2]-button.height
                self.assertGreaterEqual(button_top-footer_bottom,8)

    def test_summary_and_ranks_move_below_table_without_moving_rating(self):
        panel=self.panel
        panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        for vertical in (False,True):
            self.set('verticalLayout',vertical)
            for compact in (False,True):
                self.set('compactSummary',compact)
                for metric in ('dps','hps'):
                    with self.subTest(vertical=vertical,compact=compact,metric=metric):
                        panel.metricTabs[metric].scripts.OnClick(panel.metricTabs[metric])
                        self.assert_table_first_header()
                        rating_position=tuple(panel.ratingGroup.points.TOPLEFT.values())
                        table_position=tuple(panel.headerViewport.points.TOPLEFT.values())
                        self.set('showSummary',False)
                        self.set('showSpecRanks',False)
                        self.assertEqual(tuple(panel.ratingGroup.points.TOPLEFT.values()),rating_position)
                        self.assertEqual(tuple(panel.headerViewport.points.TOPLEFT.values()),table_position)
                        self.assertFalse(panel.summary.shown)
                        self.assertFalse(panel.specRanks.shown)
                        self.set('showSummary',True)
                        self.set('showSpecRanks',True)
                        self.assert_table_first_header()

    def test_metric_tabs_join_identity_row_and_wrap_before_statistics(self):
        panel=self.panel
        self.assertTrue(panel.appearanceMetricInline)
        self.assert_table_first_header()
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,540,1080)
        self.mpl.RenderProfileStats(panel)
        self.assertFalse(panel.appearanceMetricInline)
        self.assert_table_first_header()
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,1920,1080)
        self.set('verticalLayout',True)
        self.assertFalse(panel.appearanceMetricInline)
        self.assert_table_first_header()
        self.set('verticalLayout',False)
        self.assertTrue(panel.appearanceMetricInline)
        self.assert_table_first_header()

    def test_blank_footer_is_hidden_without_reserved_line_and_operational_message_restores(self):
        panel=self.panel
        self.set('showNotes',False)
        self.assertTrue(panel.note.text)
        self.assertEqual(panel.footer.text,'')
        self.assertFalse(panel.note.shown)
        self.assertFalse(panel.footer.shown)
        original=panel.height
        panel.footer.SetText(panel.footer,'Retry available')
        self.mpl.RenderProfileStats(panel)
        self.assertTrue(panel.footer.shown)
        self.assertGreater(panel.height,original)
        panel.footer.SetText(panel.footer,'')
        self.mpl.RenderProfileStats(panel)
        self.assertFalse(panel.footer.shown)
        self.assertEqual(panel.height,original)

    def test_builtin_themes_preserve_classic_summary_except_compact(self):
        for theme in ('classic','clean','table','large','compact','minimal','classic'):
            self.mpl.SelectAppearanceTheme(theme)
            self.mpl.RenderProfileStats(self.panel)
            self.assertEqual(self.mpl.AppearanceValue('compactSummary'),theme=='compact')
            self.assertEqual(self.panel.medianSummary.shown,theme!='compact')
            self.assertTrue(self.panel.runSummary.shown)
            self.assertTrue(self.mpl.AppearanceValue('legacyLayout'))
            self.assertTrue(self.mpl.AppearanceValue('legacyCenteredHeadings'))
            self.assertEqual(self.mpl.AppearanceValue('maxRows'),8)
            self.assertEqual(self.mpl.AppearanceValue('levelDigits'),'natural')

    def test_clean_and_table_preserve_rendered_classic_geometry(self):
        panel=self.panel
        def geometry():
            fields=(panel.scoreLabel,panel.scoreValue,panel.summary,panel.medianSummary,
                    panel.runSummary,panel.headerViewport,panel.scroll,panel.source,
                    panel.note,panel.footer)
            return (panel.width,panel.height,panel.tableWidth,panel.appearanceRanksY,
                    tuple(panel.widths.values()),
                    tuple((field.points.TOPLEFT[1],field.points.TOPLEFT[2],field.height)
                          for field in fields),
                    tuple(row.height for row in panel.rows.values()))
        classic=geometry()
        for theme in ('clean','table','classic'):
            with self.subTest(theme=theme):
                self.mpl.SelectAppearanceTheme(theme)
                self.mpl.RenderProfileStats(panel)
                self.assertEqual(geometry(),classic)
                self.assertTrue(all(heading.justifyH=='CENTER' for heading in panel.headings.values()))
                self.assertEqual(panel.tableOutline.shown,theme=='table')
                if theme!='classic':
                    self.assertTrue(all(row.bottomLine.shown for row in panel.rows.values()))
                    self.assertTrue(all(row.rightLine.shown==(theme=='table') for row in panel.rows.values()))

    def test_large_preset_grows_fonts_without_hiding_classic_content(self):
        panel=self.panel
        fields=(panel.title,panel.character,panel.summary,panel.headings[1],panel.rows[1].cells[1])
        original=[field.fontSize for field in fields]
        original_height=panel.height
        original_header=panel.tableHeader.height
        self.mpl.SelectAppearanceTheme('large')
        self.mpl.RenderProfileStats(panel)
        for field,size in zip(fields,original):
            self.assertEqual(field.fontSize,size+4)
        self.assertGreater(panel.height,original_height)
        self.assertGreater(panel.tableHeader.height,original_header)
        self.assertGreaterEqual(panel.rows[1].height,panel.rows[1].icon.height+6)
        self.assertTrue(panel.medianSummary.shown)
        self.assertTrue(panel.runSummary.shown)
        self.assertTrue(panel.source.shown)
        self.assertTrue(panel.note.shown)
        self.assertTrue(all(width>0 for width in panel.widths.values()))

    def test_dungeon_icons_follow_reordered_column_across_refreshes(self):
        for order in (
            ['time','level','dungeon','runs','points','rank','rate','best','median'],
            ['level','time','runs','points','rank','rate','best','median','dungeon'],
            ['dungeon','level','time','runs','points','rank','rate','best','median'],
        ):
            self.set('columnOrder',order)
            for show_icons in (True,False,True):
                self.set('showDungeonIcons',show_icons)
                self.mpl.RenderProfileStats(self.panel)
                for row in self.panel.rows.values():
                    self.assertEqual(row.icon.shown,show_icons)
                    if show_icons:
                        left=self.panel.columns[1]
                        icon_x=row.icon.points.TOPLEFT[1]
                        name_x=row.cells[1].points.TOPLEFT[1]
                        self.assertGreaterEqual(icon_x,left)
                        self.assertLessEqual(icon_x+row.icon.width,name_x)
                        self.assertLessEqual(icon_x+row.icon.width,left+self.panel.widths[1])

    def test_compact_preset_reduces_space_and_preserves_classic_data(self):
        panel=self.panel
        original_height=panel.height
        original_row_height=panel.rows[1].height
        original_cells=tuple(tuple(cell.text for cell in row.cells.values()) for row in panel.rows.values())
        self.mpl.SelectAppearanceTheme('compact')
        self.mpl.RenderProfileStats(panel)
        self.assertLess(panel.height,original_height)
        self.assertLess(panel.rows[1].height,original_row_height)
        self.assertEqual(tuple(tuple(cell.text for cell in row.cells.values()) for row in panel.rows.values()),original_cells)
        self.assertTrue(all(width>0 for width in panel.widths.values()))
        self.assertTrue(panel.source.shown)
        self.assertTrue(panel.note.shown)
        self.assertIn(' / ',panel.summary.text)

    def test_minimal_preset_keeps_main_columns_and_classic_names(self):
        panel=self.panel
        original_name=panel.rows[1].cells[1].text
        self.mpl.SelectAppearanceTheme('minimal')
        self.mpl.RenderProfileStats(panel)
        for column in ('dungeon','level','rate','best','median'):
            self.assertGreater(panel.widths[self.mpl.ProfileColumnIndex(column)],0)
        for column in ('time','runs','points','rank'):
            index=self.mpl.ProfileColumnIndex(column)
            self.assertEqual(panel.widths[index],0)
            self.assertFalse(panel.sortButtons[index].shown)
            self.assertFalse(panel.rows[1].cells[index].shown)
        self.assertEqual(panel.rows[1].cells[1].text,original_name)
        self.assertFalse(panel.source.shown)
        self.assertFalse(panel.note.shown)
        self.assertFalse(panel.context.shown)
        self.assertFalse(panel.primaryGroup.shown)
        self.assertFalse(panel.secondaryGroup.shown)

    def test_classic_fits_measured_columns_and_draws_full_grid(self):
        self.assertEqual(self.panel.tableWidth,sum(self.panel.widths.values()))
        self.assertEqual(self.panel.width,self.panel.tableWidth+60)
        self.assertFalse(self.panel.horizontalBar.shown)
        self.assertEqual(self.panel.rows[1].height,26)
        for i,row in self.panel.rows.items():
            self.assertTrue(row.bottomLine.shown)
            self.assertTrue(all(line.shown for line in row.columnLines.values()))
        self.assertEqual(self.panel.rows[1].cells[1].text,'Altar of Fangs')

    def test_classic_header_groups_identity_filters_and_statistics(self):
        panel=self.panel
        self.assertFalse(self.mpl.AppearanceValue('compactSummary'))
        self.assertEqual(self.mpl.AppearanceValue('levelDigits'),'natural')
        self.assertGreaterEqual(panel.tableWidth,780)
        self.assert_table_first_header()
        self.assertTrue(all(caption.shown for caption in panel.summaryLabels.values()))
        self.assertTrue(all(heading.justifyH=='CENTER' for heading in panel.headings.values()))
        self.assertTrue(all(row.cells[2].alpha==1 for row in panel.rows.values()))
        self.assertEqual(panel.currentSpec.backdropColor[4],0)
        self.assertEqual(panel.currentSpec.borderColor[4],0)
        table_bottom=-panel.headerViewport.points.TOPLEFT[2]+panel.headerViewport.height+panel.scroll.height
        self.assertGreaterEqual(-panel.source.points.TOPLEFT[2],table_bottom+8)
        self.assertTrue(panel.note.shown)
        self.assertFalse(panel.footer.shown)
        self.assertTrue(panel.note.text)
        self.assertEqual(panel.footer.text,'')

    def test_classic_layout_survives_copy_save_export_and_import(self):
        self.assertTrue(self.mpl.CreateAppearanceTheme('My classic'))
        self.assertTrue(self.mpl.SaveAppearanceEdit())
        exported=self.mpl.ExportAppearance(False)
        self.mpl.SelectAppearanceTheme('clean')
        self.assertTrue(self.mpl.ImportAppearance(exported))
        self.mpl.RenderProfileStats(self.panel)
        self.assertTrue(self.mpl.AppearanceValue('legacyLayout'))
        self.assertTrue(self.mpl.AppearanceValue('legacyCenteredHeadings'))
        self.assertTrue(self.panel.medianSummary.shown)
        self.assertTrue(self.panel.runSummary.shown)
        self.assert_table_first_header()

    def test_reset_theme_and_table_restore_historical_classic(self):
        self.set('column_best_align','LEFT')
        self.assertFalse(self.mpl.AppearanceValue('legacyCenteredHeadings'))
        self.mpl.ResetAppearance('table')
        self.mpl.RenderProfileStats(self.panel)
        self.assertTrue(all(heading.justifyH=='CENTER' for heading in self.panel.headings.values()))
        self.set('compactSummary',True)
        self.set('levelDigits','aligned')
        self.mpl.ResetAppearance()
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.mpl.AppearanceValue('compactSummary'))
        self.assertEqual(self.mpl.AppearanceValue('levelDigits'),'natural')
        self.assertTrue(self.mpl.AppearanceValue('legacyLayout'))
        self.assert_table_first_header()

    def test_profile_refresh_preserves_external_window_scale(self):
        self.panel.SetScale(self.panel,1.3)
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(self.panel.GetScale(self.panel),1.3)
        self.set('rowHeight',30)
        self.assertEqual(self.panel.GetScale(self.panel),1.3)
        self.set('scale',0.85)
        self.assertEqual(self.panel.GetScale(self.panel),0.85)

    def test_column_alignment_applies_to_heading_and_cells_after_refresh(self):
        for percentile in ('best','median'):
            self.mpl.SetOption('percentile',percentile)
            for column in ('best','median'):
                index=self.mpl.ProfileColumnIndex(column)
                for alignment in ('LEFT','CENTER','RIGHT'):
                    self.set('column_'+column+'_align',alignment)
                    self.mpl.RenderProfileStats(self.panel)
                    self.assertEqual(self.panel.headings[index].justifyH,alignment)
                    cell=self.panel.rows[1].cells[index]
                    self.assertEqual(cell.justifyH,alignment)
                    self.assertGreater(cell.width,cell.GetUnboundedStringWidth(cell))

    def test_column_alignment_positions_aligned_level_digits(self):
        self.set('levelDigits','aligned')
        for alignment in ('LEFT','CENTER','RIGHT'):
            self.set('column_level_align',alignment)
            row=self.panel.rows[1]
            cell=row.cells[2]
            start={'LEFT':0,'CENTER':(cell.width-row.levelDigitWidth)/2,
                   'RIGHT':cell.width-row.levelDigitWidth}[alignment]
            first=row.levelDigits[1]
            self.assertIsNotNone(first.points.TOPLEFT)
            self.assertEqual(first.points.TOPLEFT[3],max(0,start))

    def test_group_profile_tabs_keep_caption_for_appearance_and_open_without_error(self):
        self.panel.groupPlayers=self.lua.table_from([
            {'name':'Papazêll','realm':'Kazzak'},
            {'name':'Киндрих','realm':'Гордунни'},
        ],recursive=True)
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(len(self.panel.playerTabs),2)
        for tab in self.panel.playerTabs.values():
            self.assertIsNotNone(tab.caption)
            self.assertTrue(tab.shown)
            self.assertGreaterEqual(tab.height,tab.caption.mplAppliedFontSize+10)
        self.set('size_button',18)
        for tab in self.panel.playerTabs.values():
            self.assertEqual(tab.caption.fontSize,18)

    def test_aligned_levels_never_draw_the_whole_number_under_digit_slots(self):
        self.panel.profile.dungeons=self.lua.table_from([
            {'name':'Fifteen','level':15}, {'name':'Sixteen','level':16},
            {'name':'Nineteen','level':19}, {'name':'Repeated ones','level':111},
        ],recursive=True)
        for shadow in (True,False):
            for semantic in (True,False):
                self.set('fontShadow',shadow)
                self.set('semanticColors',semantic)
                for mode in ('aligned','natural','aligned'):
                    self.set('levelDigits',mode)
                    for row in self.panel.rows.values():
                        if not row.shown:
                            continue
                        cell=row.cells[2]
                        digits=[digit for digit in row.levelDigits.values() if digit.shown]
                        if mode=='aligned':
                            self.assertFalse(cell.shown,'Whole-number glyphs overlap aligned digits')
                            self.assertEqual(cell.shadowColor[4],0,'Hidden whole number must leave no shadow')
                            self.assertEqual(''.join(digit.text for digit in digits),str(cell.text))
                            self.assertTrue(all(digit.shadowColor[4]==0 for digit in digits))
                        else:
                            self.assertTrue(cell.shown)
                            self.assertEqual(cell.alpha,1)
                            self.assertFalse(digits)

    def test_empty_warning_gettext_nil_during_profile_render(self):
        # WoW can return nil for an empty FontString; the shared mock returns "".
        self.lua.execute('''
            local field=...
            field.GetText=function(self)
                if self.text==nil or self.text=="" then return nil end
                return self.text
            end
        ''',self.panel.staleBanner.message)
        self.panel.stale=False
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.panel.staleBanner.shown)
        self.assertEqual(self.panel.staleBanner.message.text,'')
        self.set('warningTextColor',[.2,.4,.6,1])
        self.panel.stale=True
        self.mpl.RenderProfileStats(self.panel)
        self.assertTrue(self.panel.staleBanner.shown)
        self.assertIn('|cff336699',self.panel.staleBanner.message.text)
        self.assertIn('Данные устарели',self.panel.staleBanner.message.text)
        self.panel.stale=False
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.panel.staleBanner.shown)
        self.assertEqual(self.panel.staleBanner.message.text,'')

    def test_hiding_columns_reduces_real_window_and_removes_grid_and_headers(self):
        self.set('verticalLayout',True)
        original=self.panel.width
        for column in ('time','runs','points','rank','rate','best','median'):
            self.set('column_'+column+'_visible',False)
        self.assertLess(self.panel.width,original)
        self.assertEqual(self.panel.widths[3],0)
        self.assertFalse(self.panel.sortButtons[3].shown)
        self.assertFalse(self.panel.rows[1].cells[3].shown)
        self.assertFalse(self.panel.rows[1].columnLines[3].shown)
        self.assertFalse(self.panel.primaryGroup.shown)
        self.assertFalse(self.panel.secondaryGroup.shown)

    def test_each_hidden_column_releases_horizontal_window_space_and_restores(self):
        original=self.panel.width
        for column in ('level','time','runs','points','rank','rate','best','median'):
            with self.subTest(column=column):
                self.set('column_'+column+'_visible',False)
                self.assertLess(self.panel.width,original)
                self.assertFalse(self.panel.appearanceCompact)
                self.assertEqual(self.panel.width,self.panel.tableWidth+60)
                self.set('column_'+column+'_visible',True)
                self.assertEqual(self.panel.width,original)

    def test_hidden_columns_shrink_to_controls_minimum_without_header_overlap(self):
        previous=self.panel.width
        for column in ('time','runs','points','rank','rate','best','median','level'):
            self.set('column_'+column+'_visible',False)
            self.assertLessEqual(self.panel.width,previous)
            previous=self.panel.width
        self.assertLess(self.panel.width,800)
        self.assertFalse(self.panel.appearanceCompact)
        self.assert_table_first_header()

    def test_all_themes_default_to_horizontal_header(self):
        for theme in self.mpl.AppearancePresetOrder.values():
            with self.subTest(theme=theme):
                self.mpl.SelectAppearanceTheme(theme)
                self.assertFalse(self.panel.appearanceCompact)
                self.assertGreaterEqual(self.panel.viewportWidth,620)
                if self.mpl.AppearanceValue('headerLayout')=='original':
                    self.assertTrue(self.panel.character.shown)
                    self.assertEqual(self.panel.title.text,'MPlusLogs — Warcraft Logs')
                    self.assertIsNotNone(self.panel.currentSpec.points.TOPRIGHT)
                    self.assertTrue(self.panel.specButton.shown)
                    self.assertFalse(self.panel.extraLogsButton.shown)
                    self.assertFalse(self.panel.ratingGroup.shown)
                    if self.panel.logScope is not None:
                        self.assertFalse(self.panel.logScope.shown)
                    self.assertTrue(all(not label.shown for label in self.panel.summaryLabels.values()))
                    self.assertTrue(self.panel.contextFill.shown)
                else:
                    self.assert_table_first_header()

    def test_vertical_layout_is_explicit_and_reversible_on_narrow_screen(self):
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,700,1080)
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.panel.appearanceCompact)
        original=self.panel.height
        self.assert_table_first_header()
        self.set('verticalLayout',True)
        self.assertTrue(self.panel.appearanceCompact)
        self.assert_table_first_header()
        self.assertFalse(self.panel.specButton.shown)
        self.assertEqual(-self.panel.currentSpec.points.TOPLEFT[2],self.panel.appearanceTitleBand+12)
        self.set('verticalLayout',False)
        self.assertFalse(self.panel.appearanceCompact)
        self.assertEqual(self.panel.height,original)
        self.assert_table_first_header()

    def test_full_grid_is_continuous_and_independent_of_stripes(self):
        self.set('gridMode','full'); self.set('striped',False)
        for row in self.panel.rows.values():
            self.assertTrue(row.bottomLine.shown)
            self.assertTrue(row.rightLine.shown)
            self.assertTrue(all(line.shown for line in row.columnLines.values()))
        self.set('gridMode','none')
        self.assertTrue(all(not row.bottomLine.shown for row in self.panel.rows.values()))

    def test_natural_digits_hide_old_slots_and_restore_whole_number(self):
        self.set('levelDigits','natural')
        row=self.panel.rows[1]
        self.assertEqual(row.cells[2].alpha,1)
        self.assertTrue(row.cells[2].shown)
        self.set('levelDigits','aligned')
        self.assertEqual(row.cells[2].alpha,0)
        self.set('levelDigits','natural')
        self.assertEqual(row.cells[2].alpha,1)
        self.assertTrue(all(not digit.shown for digit in row.levelDigits.values()))
        self.set('levelDigits','aligned')
        self.assertEqual(row.cells[2].alpha,0)

    def test_runtime_preserves_navigation_focus_scroll_and_invitation(self):
        self.panel.viewMetric='hps'; self.panel.selectedSpec='Guardian'; self.panel.inviteSent=True
        self.panel.lookupExpanded=True; self.panel.lookup.SetText(self.panel.lookup,'Alice-Area 52')
        self.panel.lookup.SetFocus(self.panel.lookup)
        self.panel.sortButtons[2].scripts.OnClick()
        self.set('rowColor',[.1,.2,.3,.5])
        self.assertEqual(self.panel.viewMetric,'hps')
        self.assertEqual(self.panel.selectedSpec,'Guardian')
        self.assertTrue(self.panel.inviteSent)
        self.assertEqual(self.panel.sortColumn,2)
        self.assertEqual(self.panel.lookup.text,'Alice-Area 52')
        self.assertTrue(self.panel.lookup.focused)

    def test_alias_language_changes_only_display_and_preserves_url(self):
        row=self.panel.rows[3]
        original=row.dungeonName; url=row.url
        self.lua.execute('function GetLocale() return "ruRU" end')
        self.set('dungeonLanguage','client')
        self.assertEqual(row.dungeonName,original)
        self.assertEqual(row.url,url)
        self.assertEqual(row.cells[1].text,'Гробница королей')
        self.mpl.SetDungeonAlias(249,'Короли'); self.set('dungeonFormat','custom')
        self.assertEqual(row.cells[1].text,'Короли')
        self.assertEqual(row.dungeonName,original)

    def test_cancel_restores_style_and_alias_without_reverting_profile_data(self):
        self.set('levelDigits','aligned')
        self.mpl.SetDungeonAlias(249,'Changed')
        self.panel.profile.score=4999
        self.mpl.CancelAppearanceEdit()
        self.assertEqual(self.mpl.AppearanceValue('levelDigits'),'natural')
        self.assertIsNone(self.mpl.GetDungeonAlias(249))
        self.assertEqual(self.panel.profile.score,4999)

    def test_reordered_columns_keep_stable_semantics_and_sorting(self):
        self.set('columnOrder',['dungeon','best','level','median','rate','rank','time','points','runs'])
        self.assertLess(self.panel.columns[8],self.panel.columns[2])
        self.panel.sortButtons[8].scripts.OnClick()
        self.assertEqual(self.panel.sortId,'best')
        self.mpl.SetOption('percentile','median')
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(self.panel.headings[8].text,self.mpl.L['Best %'])
        self.assertEqual(self.panel.sortId,'best')

    def test_font_reapplication_is_absolute_and_large_icons_fit(self):
        self.set('fontSize',18); self.set('iconSize',36)
        row=self.panel.rows[1]
        size=row.cells[1].fontSize
        for _ in range(10): self.mpl.ApplyAppearanceToViews()
        self.assertEqual(row.cells[1].fontSize,size)
        self.assertGreaterEqual(row.height,row.icon.height)
        self.assertGreaterEqual(row.height,row.cells[1].height)

    def test_number_formats_preserve_source_precision_and_missing_values(self):
        self.set('numericFormat','full'); self.set('thousandsSeparator','comma')
        text=self.mpl.FormatAppearanceCell(7,'value',self.lua.table_from({'amount':203830}),self.lua.table_from({'metric':'dps'}),'dps')
        self.assertEqual(text,'203,830')
        self.set('percentPrecision',1)
        self.assertIn('99.9',self.mpl.FormatAppearancePercent(99.96))
        self.assertEqual(self.mpl.FormatAppearancePercent(None),'—')

    def test_sample_is_separate_and_real_actions_are_disabled(self):
        sample=self.mpl.ShowAppearancePreview()
        self.assertNotEqual(sample,self.panel)
        self.assertIsNone(sample.loadButton.scripts.OnClick)
        self.assertIsNone(sample.rows[1].scripts.OnMouseUp)
        self.set('gridMode','full')
        self.assertTrue(sample.rows[2].bottomLine.shown)
        self.assertIsNone(sample.rows[1].scripts.OnMouseUp)

    def test_screen_limit_has_synchronized_horizontal_scrolling(self):
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,700,1080)
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(self.panel.width,680)
        self.assertTrue(self.panel.horizontalBar.shown)
        self.panel.horizontalBar.SetValue(self.panel.horizontalBar,100)
        self.assertEqual(self.panel.scroll.horizontalScroll,100)
        self.assertEqual(self.panel.headerViewport.horizontalScroll,100)
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,1920,1080)
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.panel.horizontalBar.shown)
        self.assertEqual(self.panel.scroll.horizontalScroll,0)
        self.assertEqual(self.panel.headerViewport.horizontalScroll,0)

    def test_width_grows_and_shrinks_with_content_and_font_sizes(self):
        original=self.panel.width
        self.set('column_dungeon_label','A much longer dungeon heading that needs more room than the default')
        self.assertGreater(self.panel.width,original)
        self.assertEqual(self.panel.width,self.panel.tableWidth+60)
        self.set('column_dungeon_label','')
        self.assertEqual(self.panel.width,original)
        self.set('size_header',28)
        self.assertGreater(self.panel.width,original)
        self.set('size_header',0)
        self.assertEqual(self.panel.width,original)

    def test_wide_content_uses_available_screen_instead_of_old_maximum(self):
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,2560,1080)
        self.set('column_dungeon_label','W'*120)
        self.set('column_rate_label','W'*120)
        self.assertGreater(self.panel.width,1500)
        self.assertEqual(self.panel.width,self.panel.tableWidth+60)
        self.assertFalse(self.panel.horizontalBar.shown)

    def test_live_palette_does_not_allocate_frames_and_transparency_keeps_text_visible(self):
        before=self.lua.globals().frameCount
        for i in range(50): self.set('surfaceOpacity',i/50)
        self.assertEqual(self.lua.globals().frameCount,before)
        self.assertEqual(self.panel.backdropColor[4],0)
        self.assertAlmostEqual(self.panel.rows[1].background.fillColor[4],.98)
        self.assertNotEqual(self.panel.rows[1].cells[1].alpha,.98)

    def test_zero_window_border_does_not_create_tiny_edge_or_white_backdrop(self):
        self.lua.execute('''
            local panel=...
            function panel:SetBackdrop(info)
                self.appliedBackdrop=info
                -- Blizzard resets backdrop colors before calculating UVs.
                self:SetBackdropColor(1,1,1,1)
                if info and info.edgeFile then
                    assert(info.edgeSize>=1,"Texture:SetTexCoord(): unsafe tiny border")
                end
            end
            function panel:SetBackdropBorderColor(r,g,b,a) self.borderColor={r,g,b,a} end
        ''',self.panel)
        self.set('surfaceOpacity',.9)
        for thickness in (0,1,3,0,2,0):
            with self.subTest(thickness=thickness):
                self.set('borderThickness',thickness)
                backdrop=self.panel.appliedBackdrop
                self.assertIsNotNone(backdrop)
                self.assertEqual(backdrop.edgeFile is None,thickness==0)
                self.assertEqual(self.panel.backdropColor[4],0)
                self.assertEqual(self.panel.borderColor[4],0 if thickness==0 else 1)
                self.assertAlmostEqual(self.panel.rows[1].background.fillColor[4],.9)
                self.assertAlmostEqual(self.panel.contextFill.fillColor[4],.99)

    def test_surface_tiles_meet_without_gaps_or_double_opacity(self):
        self.set('surfaceOpacity',.5)
        for header_layout in ("modern","original"):
            self.set("headerLayout",header_layout)
            for vertical in (False,True):
                self.set('verticalLayout',vertical)
                for season in (False,True):
                    self.set('showSeason',season)
                    with self.subTest(header_layout=header_layout,vertical=vertical,season=season):
                        panel=self.panel
                        headings=[panel.contextFill,panel.tableDecor[1]]
                        for surface in headings:
                            self.assertAlmostEqual(surface.fillColor[4],.75)
                            self.assertFalse(surface.snapToPixelGrid)
                            self.assertEqual(surface.texelSnappingBias,0)
                        surfaces=[panel.titleFill,panel.appearanceEmptyFill,panel.rows[1].background]
                        surfaces.extend(panel.appearanceBackdropParts.values())
                        for surface in surfaces:
                            self.assertFalse(surface.snapToPixelGrid)
                            self.assertEqual(surface.texelSnappingBias,0)
                            self.assertAlmostEqual(surface.fillColor[4],.5)
                        # The table has its own header/row fills. Treat that
                        # reserved rectangle as one region for the outer tiling.
                        regions=[(1,1,panel.width-1,1+panel.titleFill.height)]
                        if panel.contextFill.shown:
                            x,y=panel.contextFill.points.TOPLEFT.values()
                            regions.append((x,-y,x+panel.contextFill.width,-y+panel.contextFill.height))
                        x,y=panel.headerViewport.points.TOPLEFT.values()
                        bottom=-y+panel.headerViewport.height+panel.scroll.height
                        regions.append((x,-y,x+panel.viewportWidth,bottom))
                        for tile in panel.appearanceBackdropParts.values():
                            if tile.shown:
                                x,y=tile.points.TOPLEFT.values()
                                regions.append((x,-y,x+tile.width,-y+tile.height))
                        xs=sorted({r[i] for r in regions for i in (0,2)})
                        ys=sorted({r[i] for r in regions for i in (1,3)})
                        for left,right in zip(xs,xs[1:]):
                            for top,bottom in zip(ys,ys[1:]):
                                x,y=(left+right)/2,(top+bottom)/2
                                self.assertEqual(sum(l<x<r and t<y<b for l,t,r,b in regions),1)

    def test_background_has_no_holes_or_overlap_across_profile_states(self):
        panel=self.panel
        full=panel.profile
        short=self.mpl.CopyAppearanceValue(full)
        short.dungeons=self.lua.table_from([full.dungeons[1],full.dungeons[2]])
        empty=self.mpl.CopyAppearanceValue(full)
        empty.dungeons=self.lua.table()
        self.set('surfaceOpacity',.5)
        for header_layout in ("modern","original"):
            self.set("headerLayout",header_layout)
            for vertical,screen_width,screen_height in ((False,1920,1080),(True,1920,1080),
                                                       (False,700,620),(True,700,620)):
                self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,screen_width,screen_height)
                self.set('verticalLayout',vertical)
                for season in (False,True):
                    self.set('showSeason',season)
                    for state,profile in (('missing',None),('short',short),('empty',empty),
                                          ('full',full),('missing-again',None),('full-again',full)):
                        with self.subTest(header_layout=header_layout,vertical=vertical,season=season,state=state,screen=(screen_width,screen_height)):
                            panel.profile=profile
                            self.mpl.RenderProfileStats(panel)
                            regions=[(1,1,panel.width-1,1+panel.titleFill.height)]
                            if panel.contextFill.shown:
                                x,y=panel.contextFill.points.TOPLEFT.values()
                                regions.append((x,-y,x+panel.contextFill.width,-y+panel.contextFill.height))
                            for tile in panel.appearanceBackdropParts.values():
                                if tile.shown:
                                    x,y=tile.points.TOPLEFT.values()
                                    regions.append((x,-y,x+tile.width,-y+tile.height))
                            x,y=panel.headerViewport.points.TOPLEFT.values()
                            header_top=-y
                            scroll_top=header_top+panel.headerViewport.height
                            scroll_bottom=scroll_top+panel.scroll.height
                            if panel.tableDecor[1].shown:
                                regions.append((x,header_top,x+panel.viewportWidth,scroll_top))
                            for index,row in panel.rows.items():
                                if row.shown:
                                    top=scroll_top+(index-1)*row.height
                                    bottom=min(scroll_bottom,top+row.height)
                                    if bottom>top:
                                        regions.append((x,top,x+panel.viewportWidth,bottom))
                            if panel.appearanceEmptyFill.shown:
                                regions.append((x,scroll_bottom-panel.appearanceEmptyFill.height,
                                                x+panel.viewportWidth,scroll_bottom))
                            xs=sorted({1,panel.width-1}|{r[i] for r in regions for i in (0,2)})
                            ys=sorted({1,panel.height-1}|{r[i] for r in regions for i in (1,3)})
                            for left,right in zip(xs,xs[1:]):
                                for top,bottom in zip(ys,ys[1:]):
                                    px,py=(left+right)/2,(top+bottom)/2
                                    self.assertEqual(sum(l<px<r and t<py<b for l,t,r,b in regions),1,
                                                     (state,px,py))

    def test_missing_profile_hides_header_grid_and_horizontal_scroll_then_restores(self):
        panel=self.panel
        profile=panel.profile
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,700,1080)
        for header_layout in ("modern","original"):
            self.set("headerLayout",header_layout)
            for grid in ('full','horizontal','vertical'):
                self.set('gridMode',grid)
                for loaded in (True,False,True):
                    with self.subTest(header_layout=header_layout,grid=grid,loaded=loaded):
                        panel.profile=profile if loaded else None
                        self.mpl.RenderProfileStats(panel)
                        self.assertEqual(panel.headerViewport.shown,loaded)
                        self.assertEqual(panel.horizontalBar.shown,loaded)
                        lines=any(line.shown for line in panel.appearanceHeaderLines.values())
                        self.assertEqual(lines,loaded)
                        if not loaded:
                            self.assertFalse(panel.appearanceEmptyFill.shown)
                            self.assertFalse(panel.tableOutline.shown)

    def test_season_and_table_headings_remain_dense_when_body_is_translucent(self):
        for palette in self.mpl.AppearanceColorPresetOrder.values():
            self.mpl.ApplyAppearanceColorPreset(palette)
            for opacity,heading_alpha in ((0,0),(.5,.75),(.9,.99),(1,1)):
                with self.subTest(palette=palette,opacity=opacity):
                    self.set('surfaceOpacity',opacity)
                    self.assertAlmostEqual(self.panel.contextFill.fillColor[4],heading_alpha)
                    self.assertAlmostEqual(self.panel.tableDecor[1].fillColor[4],heading_alpha)
                    self.assertAlmostEqual(self.panel.titleFill.fillColor[4],opacity)
                    self.assertAlmostEqual(self.panel.rows[1].background.fillColor[4],opacity)
                    self.assertNotEqual(self.panel.context.alpha,opacity)
        # Explicit per-color transparency remains meaningful.
        self.set('surfaceOpacity',.9)
        self.set('titleBackgroundColor',[.1,.2,.3,.5])
        self.set('headerColor',[.2,.3,.4,.6])
        self.assertAlmostEqual(self.panel.contextFill.fillColor[4],.99*.5)
        self.assertAlmostEqual(self.panel.tableDecor[1].fillColor[4],.99*.6)

    def test_removed_spacing_settings_cannot_change_layout(self):
        original=(self.panel.width,self.panel.height,self.panel.headerViewport.points.TOPLEFT[2])
        theme=self.mpl.GetAppearance()
        theme.windowPadding=40
        theme.blockSpacing=18
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual((self.panel.width,self.panel.height,self.panel.headerViewport.points.TOPLEFT[2]),original)
        normalized=self.mpl.NormalizeAppearance(theme)
        for key in ('windowPadding','blockSpacing'):
            self.assertIsNone(normalized[key])
            self.assertFalse(self.mpl.SetAppearanceValue(key,18)[0])

    def test_table_border_and_compact_summary_have_visible_effect(self):
        original=self.panel.headerViewport.points.TOPLEFT[2]
        self.set('tableBorder',True)
        self.assertEqual(self.panel.headerViewport.points.TOPLEFT[1],20)
        self.assertEqual(self.panel.headerViewport.points.TOPLEFT[2],original)
        self.assertTrue(self.panel.tableOutline.shown)
        self.assertEqual(self.panel.tableOutline.width,self.panel.viewportWidth)
        self.set('compactSummary',True)
        self.assertFalse(self.panel.medianSummary.shown)
        self.assertTrue(self.panel.runSummary.shown)
        self.assertIn(' / ',self.panel.summary.text)

    def test_compact_summary_never_increases_window_height(self):
        for vertical in (False,True):
            self.set('verticalLayout',vertical)
            self.set('compactSummary',False)
            original=self.panel.height
            rating_y=self.panel.scoreValue.points.TOPLEFT[2]
            rating_x=self.panel.scoreValue.points.TOPLEFT[1]
            self.set('compactSummary',True)
            self.assertLessEqual(self.panel.height,original)
            self.assertEqual(self.panel.scoreValue.points.TOPLEFT[2],rating_y)
            self.assertEqual(self.panel.scoreValue.points.TOPLEFT[1],rating_x)
            self.assertTrue(all(not caption.shown for caption in self.panel.summaryLabels.values()))
            summary=self.panel.summary; rating=self.panel.scoreValue
            self.assertGreaterEqual(-summary.points.TOPLEFT[2],-rating.points.TOPLEFT[2]+rating.height)

    def test_vertical_identity_stays_above_filters_and_summary_wraps_when_needed(self):
        self.set('compactSummary',False)
        self.set('verticalLayout',True)
        self.assert_table_first_header()
        original=self.panel.height
        self.set('size_summary',30)
        self.assertGreater(self.panel.height,original)
        self.assert_table_first_header()
        summary=self.panel.summary
        self.assertEqual(self.panel.summaryLabels[3].points.TOPLEFT[1],20)
        for caption in self.panel.summaryLabels.values():
            self.assertTrue(caption.shown)

    def test_vertical_compact_summary_packs_groups_below_the_table(self):
        self.set('compactSummary',False)
        self.set('verticalLayout',True)
        original=self.panel.height
        self.set('compactSummary',True)
        self.assertLessEqual(self.panel.height,original)
        panel=self.panel
        table_top=-panel.headerViewport.points.TOPLEFT[2]
        for field in (panel.scoreLabel,panel.scoreValue):
            self.assertLessEqual(-field.points.TOPLEFT[2]+field.height,table_top)
        table_bottom=-panel.scroll.points.TOPLEFT[2]+panel.scroll.height
        self.assertGreaterEqual(-panel.summary.points.TOPLEFT[2],table_bottom+8)

    def test_compact_summary_and_ranks_share_row_below_identity_rating(self):
        self.panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.set('compactSummary',True)
        fields=[self.panel.summary,self.panel.specRanks]
        centers=[-field.points.TOPLEFT[2]+field.height/2 for field in fields]
        self.assertTrue(all(center==centers[0] for center in centers))
        self.assertLessEqual(fields[1].points.TOPLEFT[1]+fields[1].width,fields[0].points.TOPLEFT[1])
        self.assertEqual(self.panel.runSummary.points.TOPLEFT[1],20)
        self.assertEqual(fields[0].points.TOPLEFT[1]+fields[0].width,20+self.panel.viewportWidth)
        self.assertLess(-self.panel.scoreValue.points.TOPLEFT[2]+self.panel.scoreValue.height,-fields[0].points.TOPLEFT[2])
        self.assertTrue(all(not caption.shown for caption in self.panel.summaryLabels.values()))
        entry=self.panel.specRankEntries[1]
        self.assertLessEqual(entry.points.TOPLEFT[1]+entry.width,20+self.panel.viewportWidth)

    def test_compact_groups_wrap_when_large_text_cannot_share_the_row(self):
        self.panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.set('compactSummary',True); self.set('size_summary',30)
        summary=self.panel.summary; rating=self.panel.scoreValue
        self.assertGreaterEqual(-summary.points.TOPLEFT[2],-rating.points.TOPLEFT[2]+rating.height)
        self.assertLessEqual(summary.points.TOPLEFT[1]+summary.width,20+self.panel.viewportWidth)
        self.assertGreaterEqual(-self.panel.context.points.TOPLEFT[2],
                                -summary.points.TOPLEFT[2]+summary.height+8)

    def test_compact_rank_font_height_stays_below_table_and_clear_of_footer(self):
        self.panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.set('compactSummary',True); self.set('showRating',False); self.set('showSummary',True)
        self.set('size_numbers',40)
        entry=self.panel.specRankEntries[1]
        self.assertGreaterEqual(entry.height,entry.number.height)
        table_bottom=-self.panel.scroll.points.TOPLEFT[2]+self.panel.scroll.height
        self.assertGreaterEqual(-entry.points.TOPLEFT[2],table_bottom+8)
        self.assertGreaterEqual(-self.panel.context.points.TOPLEFT[2],
                                -entry.points.TOPLEFT[2]+entry.number.height+8)

    def test_hidden_sections_release_window_space_and_restore(self):
        self.set('compactSummary',False)
        self.panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.mpl.RenderProfileStats(self.panel)
        for vertical in (False,True):
            self.set('verticalLayout',vertical)
            for key in ('showSeason','showSpecRanks','showNotes','showSource'):
                with self.subTest(vertical=vertical,key=key):
                    original=self.panel.height
                    self.set(key,False)
                    self.assertLessEqual(self.panel.height,original)
                    self.set(key,True)
                    self.assertEqual(self.panel.height,original)
            original=self.panel.height
            self.set('showSummary',False)
            # A shared horizontal row is as tall as its remaining rating.
            self.assertLessEqual(self.panel.height,original)
            self.assertTrue(all(not label.shown for label in self.panel.summaryLabels.values()))
            previous=self.panel.height
            self.set('showRating',False)
            self.assertLessEqual(self.panel.height,previous)
            self.set('showRating',True); self.set('showSummary',True)
            self.assertEqual(self.panel.height,original)

    def test_compact_summary_large_font_uses_available_width_and_wrap_height(self):
        self.set('compactSummary',True); self.set('size_summary',18)
        summary=self.panel.summary
        measured=summary.GetUnboundedStringWidth(summary)
        self.assertGreaterEqual(summary.width*summary.height/(summary.fontSize+4),measured)
        self.set('showRating',False)
        self.assertLessEqual(summary.width,self.panel.viewportWidth)
        self.assertGreaterEqual(summary.width,measured)
        self.set('compactSummary',False)
        self.assertEqual(summary.height,22)

    def test_compact_summary_without_profile_does_not_use_stale_geometry(self):
        self.panel.profile=None
        self.set('compactSummary',True)
        self.assertFalse(self.panel.summary.shown)
        self.assertGreater(self.panel.height,0)

    def test_unresolved_group_member_uses_current_layout_after_theme_changes(self):
        self.lua.execute('return assert(loadstring(...))',
                         (ROOT/'SearchGroup.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.mpl.ShowProfile=self.show_profile
        self.mpl.searchGroupWindow=self.lua.table_from({
            'resultID':42,'selected':1,'players':[{'name':'Mihihi','class':'MAGE','loaded':False}],
        },recursive=True)
        for theme,vertical in (('compact',False),('minimal',True),('classic',False),('original',False)):
            with self.subTest(theme=theme,vertical=vertical):
                self.mpl.SelectAppearanceTheme(theme)
                self.set('verticalLayout',vertical)
                self.mpl.OpenSearchGroupProfile(1)
                for redraw in (False,True):
                    if redraw:
                        self.mpl.ApplyAppearanceToViews()
                    panel=self.mpl.panel
                    self.assertFalse(panel.currentSpec.shown)
                    self.assertFalse(panel.specButton.shown)
                    self.assertFalse(panel.extraLogsButton.shown)
                    self.assertIsNotNone(panel.loadButton.points.BOTTOMRIGHT)
                    self.assertIsNone(panel.loadButton.points.BOTTOMLEFT)
                    self.assertEqual(panel.emptyMessage.width,panel.viewportWidth)
                    self.assertEqual(panel.emptyMessage.points.TOPLEFT[1],20)
                    self.assertEqual(panel.loadButton.text,self.mpl.L['Load group logs'])
                self.mpl.searchGroupWindow.players[1].candidates=self.lua.table_from([
                    {'name':'Mihihi','realm':'Silvermoon'},
                    {'name':'Mihihi','realm':'Draenor'},
                ],recursive=True)
                self.mpl.OpenSearchGroupProfile(1)
                self.mpl.ApplyAppearanceToViews()
                previous_bottom=-panel.emptyMessage.points.TOPLEFT[2]+panel.emptyMessage.height
                for button in panel.searchChoices.values():
                    self.assertEqual(button.width,panel.viewportWidth)
                    self.assertEqual(button.points.TOPLEFT[1],20)
                    self.assertGreaterEqual(-button.points.TOPLEFT[2],previous_bottom)
                    previous_bottom=-button.points.TOPLEFT[2]+button.height
                self.assertLess(previous_bottom,panel.height-60)
                self.mpl.searchGroupWindow.players[1].candidates=None
        self.show_profile('Киндрих','Гордунни',None,True)
        self.mpl.SelectAppearanceTheme('compact')
        self.assertTrue(panel.profile)
        self.assertTrue(panel.currentSpec.shown)
        self.assertTrue(panel.extraLogsButton.shown)
        self.assertFalse(panel.emptyMessage.shown)
        self.assertTrue(all(not button.shown for button in panel.searchChoices.values()))

    def test_other_specialization_arrow_toggles_themed_menu_without_requests(self):
        panel=self.panel
        self.capture_specialization_menu()
        self.lua.execute('''
            local MPL=...
            MPL.SendRequest=function() error("opening a menu must not request logs") end
            MPL.SendBatchRequest=function() error("opening a menu must not request a batch") end
        ''',self.mpl)
        profile_id=self.lua.eval('tostring')(panel.profile)
        selected=panel.selectedSpec; metric=panel.viewMetric
        geometry=(panel.width,panel.height,tuple(panel.headerViewport.points.TOPLEFT.values()))
        self.assertFalse(panel.specButton.shown)
        self.assertTrue(panel.extraLogsButton.shown)
        for shown in (True,False,True,False,True):
            panel.extraLogsButton.scripts.OnClick(panel.extraLogsButton)
            menu=panel.specMenu
            self.assertEqual(menu.IsShown(menu),shown)
            if shown:
                self.assertTrue(self.lua.eval('rawequal')(menu.activeAnchor,panel.extraLogsButton))
                title=next(entry for entry in menu.entries.values() if entry.kind=='title')
                self.assertEqual(title.text,self.mpl.L['Выбрать специализацию логов'])
            self.assertFalse(panel.specButton.shown)
            self.assertEqual((panel.width,panel.height,tuple(panel.headerViewport.points.TOPLEFT.values())),geometry)
            self.assertEqual(self.lua.eval('tostring')(panel.profile),profile_id)
            self.assertEqual(panel.selectedSpec,selected)
            self.assertEqual(panel.viewMetric,metric)
            self.assert_table_first_header()
        entries=[entry for entry in menu.entries.values() if entry.kind!='title']
        self.assertEqual([entry.kind for entry in entries],['radio','radio','radio','divider','button'])
        for entry,spec in zip(entries[:3],('All specs','Guardian','Restoration')):
            self.assertIn(self.mpl.SpecLabel(spec,panel['class']),entry.text)
            self.assertEqual(entry.selected(),selected==spec)
            self.assertIsNotNone(entry.button)
        self.assertEqual(entries[4].text,self.mpl.L['Find other specializations'])

    def test_specialization_menu_repeat_click_closes_and_reopen_reuses_popup(self):
        self.capture_specialization_menu()
        panel=self.panel
        button=panel.extraLogsButton
        button.scripts.OnClick(button)
        menu=panel.specMenu
        self.assertTrue(menu.IsShown(menu))
        button.scripts.OnClick(button)
        self.assertFalse(menu.IsShown(menu))
        button.scripts.OnClick(button)
        self.assertTrue(menu.IsShown(menu))
        self.assertTrue(self.lua.eval('rawequal')(menu,panel.specMenu))

    def test_specialization_menu_uses_palette_and_drawn_selection_marker(self):
        self.capture_specialization_menu()
        self.set('buttonColor',[.11,.14,.17,1])
        self.set('borderColor',[.31,.34,.37,1])
        self.set('selectedColor',[.21,.24,.27,1])
        self.set('hoverColor',[.41,.44,.47,1])
        self.set('accentColor',[.61,.64,.67,1])
        button=self.panel.extraLogsButton
        button.scripts.OnClick(button)
        menu=self.panel.specMenu
        self.assertEqual(list(menu.backdropColor.values()),[.11,.14,.17,1])
        self.assertEqual(list(menu.borderColor.values()),[.31,.34,.37,1])
        radios=[entry for entry in menu.entries.values() if entry.kind=='radio']
        for entry in radios:
            row=entry.button
            self.assertEqual(row.marker.shown,entry.selected())
            self.assertEqual(row.marker.width,3)
            self.assertEqual(list(row.marker.fillColor.values()),[.61,.64,.67,1])
            self.assertEqual(list(row.backdropColor.values()),
                             [.21,.24,.27,1] if entry.selected() else [.11,.14,.17,1])
        row=radios[1].button
        row.scripts.OnEnter(row)
        self.assertEqual(list(row.backdropColor.values()),[.41,.44,.47,1])
        row.scripts.OnLeave(row)
        self.assertEqual(list(row.backdropColor.values()),[.11,.14,.17,1])

    def test_specialization_menu_closes_on_outside_click_escape_and_combat(self):
        self.capture_specialization_menu()
        button=self.panel.extraLogsButton
        def open_menu():
            button.scripts.OnClick(button)
            menu=self.panel.specMenu
            self.assertTrue(menu.IsShown(menu))
            return menu
        menu=open_menu()
        self.lua.execute('''
            local menu,anchor=...
            menu.IsMouseOver=function() return false end
            anchor.IsMouseOver=function() return true end
        ''',menu,button)
        menu.scripts.OnEvent(menu,'GLOBAL_MOUSE_DOWN')
        self.assertTrue(menu.IsShown(menu))
        self.lua.execute('local anchor=...; anchor.IsMouseOver=function() return false end',button)
        menu.scripts.OnEvent(menu,'GLOBAL_MOUSE_DOWN')
        self.assertFalse(menu.IsShown(menu))
        menu=open_menu()
        menu.scripts.OnKeyDown(menu,'ESCAPE')
        self.assertFalse(menu.IsShown(menu))
        menu=open_menu()
        menu.scripts.OnEvent(menu,'PLAYER_REGEN_DISABLED')
        self.assertFalse(menu.IsShown(menu))

    def test_specialization_menu_reanchors_before_toggling_the_new_anchor(self):
        panel=self.panel
        self.capture_specialization_menu()
        panel.extraLogsButton.scripts.OnClick(panel.extraLogsButton)
        menu=panel.specMenu
        panel.specButton.scripts.OnClick(panel.specButton)
        self.assertTrue(menu.IsShown(menu))
        self.assertTrue(self.lua.eval('rawequal')(menu.activeAnchor,panel.specButton))
        panel.specButton.scripts.OnClick(panel.specButton)
        self.assertFalse(menu.IsShown(menu))

    def test_specialization_menu_loads_only_after_an_explicit_choice(self):
        self.capture_specialization_menu()
        self.lua.execute('''
            local MPL=...
            profileShows=0; downloadShows=0
            MPL.ShowProfile=function() profileShows=profileShows+1 end
            MPL.ShowDownload=function(name,realm,profile,applicant,batch,refresh)
                downloadShows=downloadShows+1; downloadRefresh=refresh
            end
        ''',self.mpl)
        panel=self.panel
        def choose(spec):
            panel.extraLogsButton.scripts.OnClick(panel.extraLogsButton)
            entry=next(entry for entry in panel.specMenu.entries.values()
                       if entry.kind=='radio' and self.mpl.SpecLabel(spec,panel['class']) in entry.text)
            entry.button.scripts.OnClick(entry.button)
            self.assertFalse(panel.specMenu.IsShown(panel.specMenu))
        self.assertEqual(self.lua.globals().downloadShows,0)
        choose('Guardian')
        self.assertEqual(self.mpl.SelectedSpec('Киндрих','Гордунни'),'Guardian')
        self.assertEqual(self.lua.globals().profileShows,1)
        self.assertEqual(self.lua.globals().downloadShows,0)
        choose('Restoration')
        self.assertEqual(self.mpl.SelectedSpec('Киндрих','Гордунни'),'Restoration')
        self.assertEqual(self.lua.globals().downloadShows,1)
        panel.extraLogsButton.scripts.OnClick(panel.extraLogsButton)
        entry=next(entry for entry in panel.specMenu.entries.values() if entry.kind=='button')
        entry.button.scripts.OnClick(entry.button)
        self.assertFalse(panel.specMenu.IsShown(panel.specMenu))
        self.assertEqual(self.mpl.SelectedSpec('Киндрих','Гордунни'),'Restoration')
        self.assertEqual(self.lua.globals().downloadShows,2)
        self.assertTrue(self.lua.globals().downloadRefresh)
        self.assertFalse(panel.specButton.shown)

    def test_preview_arrow_with_disabled_callback_does_not_open_a_real_menu(self):
        self.capture_specialization_menu()
        sample=self.mpl.ShowAppearancePreview()
        self.assertIsNone(sample.specButton.GetScript(sample.specButton,'OnClick'))
        sample.extraLogsButton.scripts.OnClick(sample.extraLogsButton)
        self.assertFalse(sample.specMenu)
        self.assertFalse(sample.specButton.shown)

    def test_metric_tabs_switch_without_redundant_scope_label_and_follow_profile_visibility(self):
        panel=self.panel
        panel.currentSpec.name.SetText(panel.currentSpec.name,'Fire')
        panel.selectedSpec='Guardian'
        panel.profile.spec='All specs'
        for metric in ('dps','hps','dps'):
            panel.metricTabs[metric].scripts.OnClick(panel.metricTabs[metric])
            self.assertEqual(panel.viewMetric,metric)
            self.assertEqual(panel.currentSpec.name.text,'Fire')
            self.assertTrue(all(tab.shown for tab in panel.metricTabs.values()))
            self.assertIsNone(panel.logScope)
        profile=panel.profile
        panel.profile=None
        self.mpl.RenderProfileStats(panel)
        self.assertTrue(all(not tab.shown for tab in panel.metricTabs.values()))
        self.assertIsNone(panel.logScope)
        self.assertTrue(all(not label.shown for label in panel.summaryLabels.values()))
        panel.profile=profile
        self.mpl.RenderProfileStats(panel)
        self.assertTrue(all(tab.shown for tab in panel.metricTabs.values()))
        self.assertIsNone(panel.logScope)
        self.assert_table_first_header()

    def test_extra_logs_icon_stays_small_and_metric_tabs_fit_at_large_fonts(self):
        panel=self.panel
        panel.profile.spec='Restoration'
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,540,1080)
        self.set('size_button',40); self.set('size_secondary',40)
        for _ in range(3):
            self.mpl.RenderProfileStats(panel)
            toggle=panel.extraLogsButton
            self.assertEqual((toggle.width,toggle.height),(24,24))
            self.assertEqual(toggle.caption.text,'')
            self.assertEqual(len(toggle.arrow),4)
            for stroke in toggle.arrow.values():
                self.assertGreater(stroke.width,0)
                self.assertEqual(stroke.height,1)
            self.assert_table_first_header()

    def test_extra_logs_icon_tooltip_explains_specialization_selection(self):
        self.lua.execute('''
            GameTooltip.SetOwner=function(self,owner) self.tooltipOwner=owner end
            GameTooltip.SetText=function(self,text) self.tooltipTitle=text end
            GameTooltip.AddLine=function(self,text) self.tooltipDetail=text end
        ''')
        button=self.panel.extraLogsButton
        button.scripts.OnEnter(button)
        tooltip=self.lua.globals().GameTooltip
        self.assertEqual(tooltip.tooltipTitle,self.mpl.L['Other specialization logs'])
        self.assertEqual(tooltip.tooltipDetail,self.mpl.L['Выбрать специализацию логов'])
        self.assertTrue(tooltip.shown)
        button.scripts.OnLeave(button)
        self.assertFalse(tooltip.shown)
        button.scripts.OnEnter(button)
        button.scripts.OnClick(button)
        self.assertFalse(tooltip.shown)

    def test_summary_pairs_use_natural_width_and_separate_groups_by_twenty_four(self):
        panel=self.panel
        # Short CJK labels catch both artificial minimum widths and distributed whitespace.
        self.mpl.L['Лучший % в среднем:']='甲'
        self.mpl.L['Медианный % в среднем:']='乙'
        self.mpl.L['Прохождения']='丙'
        panel.profile.best=1; panel.profile.median=1; panel.profile.runs=1
        panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.mpl.RenderProfileStats(panel)
        captions=list(panel.summaryLabels.values())
        values=[panel.summary,panel.medianSummary,panel.runSummary]
        for caption,value in zip(captions,values):
            self.assertEqual(caption.width,caption.GetUnboundedStringWidth(caption))
            self.assertEqual(value.points.TOPLEFT[1]-caption.points.TOPLEFT[1]-caption.width,8)
            self.assertEqual(value.width,value.GetUnboundedStringWidth(value)+4)
        right=values[0].points.TOPLEFT[1]+values[0].width
        self.assertEqual(captions[1].points.TOPLEFT[1]-right,24)
        self.assertEqual(captions[2].points.TOPLEFT[1],20)
        self.assertEqual(values[1].points.TOPLEFT[1]+values[1].width,20+panel.viewportWidth)
        self.assertGreater(panel.specRanks.points.TOPLEFT[1],values[2].points.TOPLEFT[1]+values[2].width)
        self.assertLess(panel.specRanks.points.TOPLEFT[1],captions[0].points.TOPLEFT[1])

    def test_summary_labels_hide_for_compact_hidden_summary_and_missing_profile(self):
        profile=self.panel.profile
        for compact,summary,loaded in ((False,True,True),(True,True,True),(False,True,True),
                                       (False,False,True),(False,True,True),(False,True,False),
                                       (False,True,True)):
            with self.subTest(compact=compact,summary=summary,loaded=loaded):
                self.panel.profile=profile if loaded else None
                self.set('compactSummary',compact)
                self.set('showSummary',summary)
                self.mpl.RenderProfileStats(self.panel)
                self.assertTrue(all(label.shown==(loaded and summary and not compact)
                                    for label in self.panel.summaryLabels.values()))
                self.assertEqual(self.panel.summary.shown,loaded and summary)
                self.assertEqual(self.panel.medianSummary.shown,loaded and summary and not compact)
                self.assertEqual(self.panel.runSummary.shown,loaded and summary)

    def test_character_name_and_realm_move_to_title_without_stale_navigation_text(self):
        for name,realm in (('Киндрих','Гордунни'),('Othercharacter','Kazzak'),('Другой','Гордунни')):
            self.show_profile(name,realm,None,True)
            with self.subTest(name=name,realm=realm):
                self.assertEqual(self.panel.title.text,name+' — '+realm)
                self.assertFalse(self.panel.character.shown)
                self.assertEqual(self.panel.character.height,0)
                self.set('showRealm',False)
                self.assertEqual(self.panel.title.text,name)
                self.mpl.RenderProfileStats(self.panel)
                self.assertEqual(self.panel.title.text,name)
                self.set('showRealm',True)
                self.assertEqual(self.panel.title.text,name+' — '+realm)
                self.assertNotIn('MPlusLogs',self.panel.title.text)

    def test_long_character_title_wraps_without_covering_header_controls(self):
        self.panel.character.SetText(self.panel.character,'Оченьдлинноеперсонажноеимя — Очень длинное название игрового мира')
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,700,1080)
        self.set('size_title',30)
        self.mpl.RenderProfileStats(self.panel)
        title=self.panel.title
        self.assertTrue(title.wordWrap)
        line=max(20,title.fontSize+4)
        self.assertGreaterEqual(title.width*title.height/line,title.GetUnboundedStringWidth(title))
        left=title.points.TOPLEFT[1]; top=-title.points.TOPLEFT[2]
        right=left+title.width; bottom=top+title.height
        for control in (self.panel.settingsButton,self.panel.appearanceButton,self.panel.closeButton):
            if control.shown:
                x,y=control.points.TOPRIGHT.values()
                control_left=self.panel.width+x-control.width
                control_top=-y
                control_bottom=control_top+control.height
                if control_top<bottom and control_bottom>top:
                    self.assertGreaterEqual(control_left,right+8)
                else:
                    self.assertGreaterEqual(control_top,bottom+8)
        self.assertGreaterEqual(self.panel.appearanceTitleBand,bottom+8)
        self.assert_table_first_header()

    def test_fictional_preview_title_keeps_full_sample_label_when_realm_is_hidden(self):
        sample=self.mpl.ShowAppearancePreview()
        expected=sample.character.text
        self.assertEqual(sample.title.text,expected)
        self.assertFalse(sample.character.shown)
        self.set('showRealm',False)
        self.assertEqual(sample.title.text,expected)
        self.set('showRealm',True)
        self.assertEqual(sample.title.text,expected)

    def test_tutorial_title_preserves_fictional_character_label(self):
        self.lua.execute('return assert(loadstring(...))',(ROOT/'TutorialProfile.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        sample=self.mpl.ShowTutorialProfile()
        expected=sample.character.text
        self.assertIn('вымышленные данные',expected)
        for show_realm in (False,True,False):
            self.set('showRealm',show_realm)
            self.assertEqual(sample.title.text,expected)
            self.assertFalse(sample.character.shown)

    def test_repeated_render_keeps_header_font_sizes_and_geometry_stable(self):
        for base,summary in ((10,0),(14,0),(14,26),(10,0)):
            self.set('fontSize',base); self.set('size_summary',summary)
            fields=[self.panel.character,self.panel.currentSpec.caption,self.panel.currentSpec.name,
                    self.panel.scoreValue,self.panel.summary,self.panel.medianSummary,
                    self.panel.runSummary,*self.panel.summaryLabels.values()]
            def snapshot():
                return (self.panel.width,self.panel.height,
                        tuple((f.fontSize,f.width,f.height,tuple(f.points.TOPLEFT.values())) for f in fields))
            original=snapshot()
            for _ in range(6):
                self.mpl.RenderProfileStats(self.panel)
                self.assertEqual(snapshot(),original)

    def test_narrow_current_specialization_wraps_without_covering_log_filters(self):
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,540,1080)
        self.panel.currentSpec.name.SetText(self.panel.currentSpec.name,'Танцующий с ветром')
        self.set('size_secondary',40)
        panel=self.panel
        self.assertTrue(panel.currentSpec.name.wordWrap)
        name=panel.currentSpec.name
        self.assertGreaterEqual(name.height/44*name.width,name.GetUnboundedStringWidth(name))
        name_bottom=-name.points.TOPLEFT[2]+name.height
        self.assertGreaterEqual(panel.currentSpec.height,name_bottom)
        self.assertFalse(panel.appearanceMetricInline)
        self.assertGreaterEqual(min(-tab.points.TOPLEFT[2] for tab in panel.metricTabs.values()),
                                -panel.currentSpec.points.TOPLEFT[2]+panel.currentSpec.height+8)
        self.assert_table_first_header()

    def test_legacy_selector_remains_hidden_with_large_localized_metadata(self):
        self.panel.specButton.caption.SetText(self.panel.specButton.caption,'Все специализации')
        self.panel.specButton.detail.SetText(self.panel.specButton.detail,'Выбрать специализацию логов')
        for width in (700,540,380):
            self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,width,1080)
            self.set('size_button',40); self.set('size_secondary',40)
            with self.subTest(width=width):
                self.assertFalse(self.panel.specButton.shown)
                self.assertTrue(callable(self.panel.specButton.GetScript(self.panel.specButton,'OnClick')))
                self.assertEqual((self.panel.extraLogsButton.width,self.panel.extraLogsButton.height),(24,24))
                self.assert_table_first_header()

    def test_narrow_rank_groups_wrap_inside_window_in_full_and_compact_summary(self):
        self.panel.profile.specRanks=self.lua.table_from([
            {'spec':'Guardian','rank':1260},{'spec':'Restoration','rank':999999},
            {'spec':'Balance','rank':888888},{'spec':'Feral','rank':555555},
        ],recursive=True)
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,540,1080)
        self.set('size_numbers',40)
        for compact in (False,True,False):
            self.set('compactSummary',compact)
            with self.subTest(compact=compact):
                table_bottom=-self.panel.scroll.points.TOPLEFT[2]+self.panel.scroll.height
                footer_top=-self.panel.context.points.TOPLEFT[2]
                previous=None
                for entry in self.panel.specRankEntries.values():
                    self.assertTrue(entry.shown)
                    x,y=entry.points.TOPLEFT.values()
                    self.assertGreaterEqual(x,20)
                    self.assertLessEqual(x+entry.width,20+self.panel.viewportWidth+1e-7)
                    self.assertGreaterEqual(-y,table_bottom+8)
                    self.assertLessEqual(-y+entry.height,footer_top-8)
                    if previous:
                        px,py=previous.points.TOPLEFT.values()
                        if y==py:
                            self.assertGreaterEqual(x,px+previous.width+8)
                        else:
                            self.assertGreaterEqual(-y,-py+previous.height+4)
                    previous=entry

    def test_current_specialization_remains_independent_of_selected_log_profile(self):
        self.lua.execute('''
            local MPL=...
            MPL.specs[MPL.Key("Киндрих","Гордунни")]={"Guardian",104,"DRUID"}
        ''',self.mpl)
        for spec in ('All specs','Restoration','All specs'):
            self.mpl.SelectSpec('Киндрих','Гордунни',spec)
            self.show_profile('Киндрих','Гордунни',None,True)
            self.assertEqual(self.panel.currentSpec.name.text,self.mpl.SpecLabel('Guardian','DRUID'))
            self.assertEqual(self.panel.selectedSpec,spec)
            self.assertEqual(self.panel.currentSpec.points.TOPLEFT[1],self.panel.character.points.TOPLEFT[1])
            self.assertEqual(-self.panel.currentSpec.points.TOPLEFT[2],self.panel.appearanceTitleBand+12)

    def test_large_font_roles_reflow_header_and_summary(self):
        self.set('size_header',28); self.set('size_summary',30); self.set('size_secondary',30)
        self.assertGreaterEqual(self.panel.tableHeader.height,72)
        self.assertGreaterEqual(self.panel.currentSpec.height,self.panel.currentSpec.caption.height)
        self.assertGreaterEqual(self.panel.currentSpec.height,self.panel.currentSpec.name.height)
        self.assert_table_first_header()
        fields=[self.panel.runSummary,self.panel.summary,self.panel.medianSummary]
        for first,second in zip(fields,fields[1:]):
            if first.points.TOPLEFT[2]==second.points.TOPLEFT[2]:
                self.assertLessEqual(first.points.TOPLEFT[1]+first.width,second.points.TOPLEFT[1])
            else:
                self.assertGreaterEqual(-second.points.TOPLEFT[2],-first.points.TOPLEFT[2]+first.height)

    def test_full_grid_includes_header_lines_and_palette_survives_hover(self):
        self.set('gridMode','full')
        self.assertTrue(self.panel.appearanceHeaderLines[10].shown)
        for thickness,header_size in ((1,0),(3,28)):
            self.set('gridThickness',thickness); self.set('size_header',header_size)
            panel=self.panel
            first=self.mpl.ProfileColumnIndex(panel.visibleColumnIds[1])
            left=panel.appearanceHeaderLines[first]
            self.assertTrue(left.shown)
            self.assertEqual(tuple(left.points.TOPLEFT.values()),(0,0))
            self.assertEqual(left.height,panel.tableHeader.height)
            right=panel.appearanceHeaderLines[13]
            self.assertTrue(right.shown)
            self.assertEqual(tuple(right.points.TOPLEFT.values()),(panel.tableWidth-thickness,0))
            self.assertEqual(right.height,panel.tableHeader.height)
            for group in panel.appearanceGroups.values():
                if group.shown:
                    center=-group.points.TOPLEFT[2]+group.height/2
                    self.assertEqual(center,panel.tableHeader.height/4)
        self.set('buttonColor',[.2,.3,.4,1])
        self.panel.specButton.scripts.OnLeave(self.panel.specButton)
        self.assertEqual([self.panel.specButton.backdropColor[i] for i in range(1,4)],[.2,.3,.4])

    def test_header_centering_and_side_edges_follow_selected_grid_mode(self):
        panel=self.panel
        for grid in ('horizontal','vertical','none','full','legacy','horizontal'):
            with self.subTest(grid=grid):
                self.set('gridMode',grid)
                first=self.mpl.ProfileColumnIndex(panel.visibleColumnIds[1])
                left,right=panel.appearanceHeaderLines[first],panel.appearanceHeaderLines[13]
                self.assertEqual(left.shown,grid in ('full','vertical'))
                self.assertEqual(right.shown,grid in ('full','vertical'))
                for group in panel.appearanceGroups.values():
                    if group.shown:
                        if grid in ('full','horizontal'):
                            center=-group.points.TOPLEFT[2]+group.height/2
                            self.assertEqual(center,panel.tableHeader.height/4)
                        else:
                            self.assertEqual(group.points.TOPLEFT[2],-5)
                            self.assertEqual(group.height,max(20,group.fontSize+4))

    def test_background_color_inherits_into_default_rows(self):
        self.set('backgroundColor',[.2,.3,.4,1])
        self.assertEqual([self.panel.rows[1].background.fillColor[i] for i in range(1,4)],[.2,.3,.4])

    def test_automatic_percentile_order_keeps_sort_arrow_on_semantic_column(self):
        self.panel.sortButtons[8].scripts.OnClick()
        self.assertEqual(self.panel.sortId,'best')
        self.mpl.SetOption('percentile','median')
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual(self.panel.sortColumn,9)
        self.assertTrue(self.panel.sortButtons[9].arrow.shown)
        self.assertEqual(self.panel.headings[9].text,self.mpl.L['Best %'])

    def test_button_fonts_survive_cooldown_state_updates_and_use_owned_objects(self):
        self.set('size_button',18)
        button=self.panel.loadButton
        self.assertEqual(button.appearanceFonts.normal.fontSize,18)
        self.assertEqual(button.appearanceFonts.highlight.fontSize,18)
        self.assertEqual(button.appearanceFonts.disabled.fontSize,18)
        self.lua.execute('local MPL=...; MPL.ProfileRefreshRemaining=function() return 42 end',self.mpl)
        for _ in range(5): self.mpl.UpdateProfileLoadButton()
        self.assertTrue(self.lua.eval('function(a,b) return a==b end')(button.normalFontObject,button.appearanceFonts.disabled))
        self.assertEqual(button.caption.fontSize,18)
        self.assertEqual(button.disabledFontObject.fontSize,18)


if __name__=='__main__':
    unittest.main()
