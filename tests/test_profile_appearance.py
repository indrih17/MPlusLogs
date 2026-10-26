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
    function methods:SetSnapToPixelGrid(value) self.snapToPixelGrid=value end
    function methods:SetTexelSnappingBias(value) self.texelSnappingBias=value end
    function methods:SetJustifyH(value) self.justifyH=value end
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
        self.lua.execute('local MPL=...; MPL.ShowProfile=function() error("appearance must not navigate") end; MPL.ShowDownload=function() error("appearance must not request") end',self.mpl)

    def set(self,key,value):
        if isinstance(value,(dict,list)):
            value=self.lua.table_from(value,recursive=True)
        result=self.mpl.SetAppearanceValue(key,value)
        self.assertTrue(result[0] if isinstance(result,tuple) else result)

    def test_builtin_themes_keep_footer_clear_of_the_table_and_actions(self):
        for theme in ('classic','clean','table','large','compact','minimal'):
            with self.subTest(theme=theme):
                self.mpl.SelectAppearanceTheme(theme)
                self.mpl.RenderProfileStats(self.panel)
                panel=self.panel
                table_bottom=-panel.scroll.points.TOPLEFT[2]+panel.scroll.height
                first=panel.source if self.mpl.AppearanceValue('showSource') else panel.footer
                if not self.mpl.AppearanceValue('showSource') and self.mpl.AppearanceValue('showNotes'):
                    first=panel.note
                gap=-first.points.TOPLEFT[2]-table_bottom
                self.assertEqual(gap,8 if theme=='compact' else 20)
                footer_bottom=-panel.footer.points.TOPLEFT[2]+panel.footer.height
                actions_top=panel.height-panel.wclButton.points.BOTTOMLEFT[2]-panel.wclButton.height
                self.assertEqual(actions_top-footer_bottom,8 if theme=='compact' else 28)

    def test_lower_actions_clear_footer_with_search_or_applicant(self):
        for applicant,expanded in ((False,True),(True,False)):
            self.panel.applicant=self.lua.table_from({'groupSize':1}) if applicant else None
            self.panel.lookupExpanded=expanded
            self.mpl.RenderProfileStats(self.panel)
            panel=self.panel
            footer_bottom=-panel.footer.points.TOPLEFT[2]+panel.footer.height
            for button,anchor in ((panel.wclButton,'BOTTOMLEFT'),(panel.loadButton,'BOTTOMRIGHT')):
                button_top=panel.height-button.points[anchor][2]-button.height
                self.assertGreaterEqual(button_top-footer_bottom,8)

    def test_builtin_themes_preserve_classic_summary_except_compact(self):
        for theme in ('classic','clean','table','large','compact','minimal','classic'):
            self.mpl.SelectAppearanceTheme(theme)
            self.mpl.RenderProfileStats(self.panel)
            self.assertEqual(self.mpl.AppearanceValue('compactSummary'),theme=='compact')
            self.assertEqual(self.panel.medianSummary.shown,theme!='compact')
            self.assertEqual(self.panel.runSummary.shown,theme!='compact')
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

    def test_classic_fits_measured_columns_and_preserves_rows_and_grid(self):
        self.assertEqual(self.panel.tableWidth,sum(self.panel.widths.values()))
        self.assertEqual(self.panel.width,self.panel.tableWidth+60)
        self.assertFalse(self.panel.horizontalBar.shown)
        self.assertEqual(self.panel.rows[1].height,26)
        for i,row in self.panel.rows.items():
            self.assertEqual(row.bottomLine.shown,i%2==1)
        self.assertEqual(self.panel.rows[1].cells[1].text,'Altar of Fangs')

    def test_classic_matches_035_banner_table_and_footer_geometry(self):
        panel=self.panel
        offset=panel.staleBanner.height+4 if panel.staleBanner.shown else 0
        self.assertFalse(self.mpl.AppearanceValue('compactSummary'))
        self.assertEqual(self.mpl.AppearanceValue('levelDigits'),'natural')
        self.assertGreaterEqual(panel.tableWidth,880)
        self.assertEqual((panel.scoreLabel.points.TOPLEFT[1],panel.scoreLabel.points.TOPLEFT[2]),(64,-163))
        self.assertEqual((panel.scoreValue.points.TOPLEFT[1],panel.scoreValue.points.TOPLEFT[2]),(64,-189))
        for field,y in ((panel.summary,159),(panel.medianSummary,181),(panel.runSummary,203)):
            self.assertTrue(field.shown)
            self.assertEqual(field.points.TOPLEFT[1],panel.tableWidth-360)
            self.assertEqual(field.points.TOPLEFT[2],-y)
        self.assertEqual(panel.appearanceRanksY,229)
        self.assertEqual(panel.headerViewport.points.TOPLEFT[2],-254-offset)
        for field,y in ((panel.source,522),(panel.note,542),(panel.footer,562)):
            self.assertEqual(field.points.TOPLEFT[2],-y-offset)
        self.assertEqual(panel.height,656+offset)
        self.assertTrue(all(heading.justifyH=='CENTER' for heading in panel.headings.values()))
        self.assertTrue(all(row.cells[2].alpha==1 for row in panel.rows.values()))

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
        self.assertEqual(self.panel.appearanceRanksY,229)

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
        self.assertEqual(self.panel.appearanceRanksY,229)

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
        character_right=self.panel.character.points.TOPLEFT[1]+self.panel.character.width
        spec_left=self.panel.width+self.panel.currentSpec.points.TOPRIGHT[1]-self.panel.currentSpec.width
        self.assertLessEqual(character_right,spec_left)
        rating_right=self.panel.scoreValue.points.TOPLEFT[1]+self.panel.scoreValue.width
        self.assertLessEqual(rating_right,self.panel.summary.points.TOPLEFT[1])

    def test_all_themes_default_to_horizontal_header(self):
        for theme in self.mpl.AppearancePresetOrder.values():
            with self.subTest(theme=theme):
                self.mpl.SelectAppearanceTheme(theme)
                self.assertFalse(self.panel.appearanceCompact)
                self.assertGreaterEqual(self.panel.viewportWidth,620)
                self.assertIsNotNone(self.panel.currentSpec.points.TOPRIGHT)

    def test_vertical_layout_is_explicit_and_reversible_on_narrow_screen(self):
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,700,1080)
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.panel.appearanceCompact)
        summary_x=self.panel.summary.points.TOPLEFT[1]
        rating_right=self.panel.scoreValue.points.TOPLEFT[1]+self.panel.scoreValue.width
        self.assertLessEqual(rating_right,summary_x)
        self.set('verticalLayout',True)
        self.assertTrue(self.panel.appearanceCompact)
        self.assertIsNotNone(self.panel.currentSpec.points.TOPLEFT)
        self.set('verticalLayout',False)
        self.assertFalse(self.panel.appearanceCompact)

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
        for vertical in (False,True):
            self.set('verticalLayout',vertical)
            for season in (False,True):
                self.set('showSeason',season)
                with self.subTest(vertical=vertical,season=season):
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
                    if season:
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
        self.assertFalse(self.panel.runSummary.shown)
        self.assertIn(' / ',self.panel.summary.text)

    def test_compact_summary_never_increases_window_height(self):
        for vertical in (False,True):
            self.set('verticalLayout',vertical)
            self.set('compactSummary',False)
            original=self.panel.height
            self.set('compactSummary',True)
            self.assertLess(self.panel.height,original)
            if not vertical:
                summary=self.panel.summary; rating=self.panel.scoreValue
                self.assertEqual(-summary.points.TOPLEFT[2]+summary.height/2,
                                 -rating.points.TOPLEFT[2]+rating.height/2)

    def test_vertical_rating_and_summary_share_height_and_wrap_when_needed(self):
        self.set('compactSummary',False)
        self.set('verticalLayout',True)
        panel=self.panel
        rating=panel.scoreLabel; summary=panel.summary
        self.assertEqual(rating.points.TOPLEFT[2],summary.points.TOPLEFT[2])
        self.assertLessEqual(rating.points.TOPLEFT[1]+rating.width,summary.points.TOPLEFT[1])
        self.assertLessEqual(summary.points.TOPLEFT[1]+summary.width,20+panel.viewportWidth)
        info_top=-rating.points.TOPLEFT[2]
        self.assertLessEqual(panel.appearanceRanksY-info_top,70)
        self.set('size_summary',30)
        summary=panel.summary; value=panel.scoreValue
        self.assertGreaterEqual(-summary.points.TOPLEFT[2],-value.points.TOPLEFT[2]+value.height)
        self.assertEqual(summary.points.TOPLEFT[1],20)

    def test_vertical_compact_summary_packs_groups_above_the_table(self):
        self.set('compactSummary',False)
        self.set('verticalLayout',True)
        original=self.panel.height
        self.set('compactSummary',True)
        self.assertLess(self.panel.height,original)
        panel=self.panel
        table_top=-panel.headerViewport.points.TOPLEFT[2]
        for field in (panel.scoreLabel,panel.scoreValue,panel.summary):
            self.assertLessEqual(-field.points.TOPLEFT[2]+field.height,table_top)

    def test_compact_rating_summary_and_ranks_share_one_row(self):
        self.panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.set('compactSummary',True)
        fields=[self.panel.scoreLabel,self.panel.scoreValue,self.panel.summary,self.panel.specRanks]
        centers=[-field.points.TOPLEFT[2]+field.height/2 for field in fields]
        self.assertTrue(all(center==centers[0] for center in centers))
        for first,second in zip(fields,fields[1:]):
            self.assertLessEqual(first.points.TOPLEFT[1]+first.width,second.points.TOPLEFT[1])
        entry=self.panel.specRankEntries[1]
        self.assertLessEqual(entry.points.TOPLEFT[1]+entry.width,20+self.panel.viewportWidth)

    def test_compact_groups_wrap_when_large_text_cannot_share_the_row(self):
        self.panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.set('compactSummary',True); self.set('size_summary',30)
        summary=self.panel.summary; rating=self.panel.scoreValue
        self.assertGreaterEqual(-summary.points.TOPLEFT[2],-rating.points.TOPLEFT[2]+rating.height)
        self.assertLessEqual(summary.points.TOPLEFT[1]+summary.width,20+self.panel.viewportWidth)
        self.assertGreaterEqual(-self.panel.headerViewport.points.TOPLEFT[2],
                                -summary.points.TOPLEFT[2]+summary.height)

    def test_compact_rank_font_height_stays_above_table(self):
        self.panel.profile.specRanks=self.lua.table_from([{'spec':'Guardian','rank':1260}],recursive=True)
        self.set('compactSummary',True); self.set('showRating',False); self.set('showSummary',False)
        self.set('size_numbers',40)
        entry=self.panel.specRankEntries[1]
        self.assertGreaterEqual(entry.height,entry.number.height)
        self.assertGreaterEqual(-self.panel.staleBanner.points.TOPLEFT[2],
                                -entry.points.TOPLEFT[2]+entry.number.height)

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
                    self.assertLess(self.panel.height,original)
                    self.set(key,True)
                    self.assertEqual(self.panel.height,original)
            original=self.panel.height
            self.set('showSummary',False)
            # A shared horizontal row is as tall as its remaining rating.
            self.assertLessEqual(self.panel.height,original)
            if vertical:
                self.assertLess(self.panel.height,original)
            previous=self.panel.height
            self.set('showRating',False)
            self.assertLess(self.panel.height,previous)
            self.set('showRating',True); self.set('showSummary',True)
            self.assertEqual(self.panel.height,original)

    def test_compact_summary_large_font_uses_available_width_and_wrap_height(self):
        self.set('compactSummary',True); self.set('size_summary',18)
        summary=self.panel.summary
        measured=summary.GetUnboundedStringWidth(summary)
        self.assertGreaterEqual(summary.width*summary.height/24,measured)
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

    def test_large_font_roles_reflow_header_and_summary(self):
        self.set('size_header',28); self.set('size_summary',30); self.set('size_warning',30)
        self.assertGreaterEqual(self.panel.tableHeader.height,72)
        self.assertGreaterEqual(self.panel.currentSpec.height,30+12+6)
        first=-self.panel.summary.points.TOPLEFT[2]
        second=-self.panel.medianSummary.points.TOPLEFT[2]
        self.assertGreaterEqual(second-first,self.panel.summary.height)

    def test_full_grid_includes_header_lines_and_palette_survives_hover(self):
        self.set('gridMode','full')
        self.assertTrue(self.panel.appearanceHeaderLines[10].shown)
        self.set('buttonColor',[.2,.3,.4,1])
        self.panel.specButton.scripts.OnLeave(self.panel.specButton)
        self.assertEqual([self.panel.specButton.backdropColor[i] for i in range(1,4)],[.2,.3,.4])

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
