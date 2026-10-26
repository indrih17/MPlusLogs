"""Appearance editor transactions and real control callbacks (offline Lua 5.1).

These mocks model scripts, focus and controls, not the game's rendering/font metrics.
"""
import unittest
from pathlib import Path

from test_addon import MOCK, ROOT, LuaRuntime, load_locales


EDITOR_MOCK = MOCK.replace(
    'function methods:SetText(text) self.text = text end', '''
    function methods:SetText(text)
        self.text=text
        if self.scripts.OnTextChanged then self.scripts.OnTextChanged(self,false) end
    end
    function methods:SetChecked(checked) self.checked=checked end
    function methods:GetChecked() return self.checked==true end
    function methods:SetValue(value)
        self.value=value
        if self.scripts.OnValueChanged then self.scripts.OnValueChanged(self,value) end
    end
    function methods:GetValue() return self.value end
    function methods:SetScale(scale) self.scale=scale end
    function methods:GetScale() return self.scale or 1 end
    function methods:GetScript(name) return self.scripts[name] end
    function methods:Raise() self.raised=(self.raised or 0)+1 end
    function methods:SetColorTexture(r,g,b,a) self.color={r,g,b,a} end
    function methods:SetVertexColor(r,g,b,a) self.vertexColor={r,g,b,a} end
    function methods:GetStringHeight() return 20 end
    function methods:EnableMouseWheel(enabled) self.mouseWheelEnabled=enabled end
    function methods:GetVerticalScroll() return self.scrollOffset or 0 end
    function methods:SetVerticalScroll(offset)
        self.scrollOffset=offset
        if self.scripts.OnVerticalScroll then self.scripts.OnVerticalScroll(self,offset) end
    end
    function methods:SetMinMaxValues(minimum,maximum) self.minimum=minimum; self.maximum=maximum end
    ''').replace(
    'function methods:Hide() self.shown = false end', '''
    function methods:Hide()
        local shown=self.shown; self.shown=false
        if shown and self.scripts.OnHide then self.scripts.OnHide(self) end
    end
    ''').replace(
    'function methods:HookScript(name, callback) self.scripts[name] = callback end', '''
    function methods:HookScript(name,callback)
        local previous=self.scripts[name]
        self.scripts[name]=function(...) if previous then previous(...) end; callback(...) end
    end
    ''').replace('return methods[k] or function() end end',
                 'return methods[k] or (type(k)=="string" and k:match("^[A-Z]") and function() end or nil) end')


class AppearanceEditorTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(EDITOR_MOCK)
        self.mpl=self.lua.table()
        load_locales(self.lua,self.mpl)
        self.lua.execute('''
            MPlusLogsDB={profiles={},options={},companionIntroDismissed=true}
            local MPL=...
            MPL.CreateDialog=function(name,title,width,height)
                local frame=CreateFrame("Frame",name,UIParent,"BackdropTemplate")
                frame:SetSize(width,height)
                frame.title=frame:CreateFontString()
                frame.closeButton=CreateFrame("Button",nil,frame)
                return frame
            end
            MPL.ApplyAppearanceToViews=function() applied=(applied or 0)+1 end
            MPL.ShowProfile=function() error("Editor must not reopen real profile") end
            MPL.ShowAppearancePreview=function() previews=(previews or 0)+1 end
            MPL.GetAppearanceDungeonList=function() return {{id=249,name="Kings' Rest"}} end
        ''',self.mpl)
        for name in ('Appearance.lua','AppearancePresets.lua','AppearanceSettings.lua'):
            self.lua.execute('return assert(loadstring(...))',(ROOT/name).read_text(encoding='utf-8'))('MPlusLogs',self.mpl)

    def open(self):
        return self.mpl.OpenAppearanceSettings()

    def click(self,control):
        control.scripts.OnClick(control)

    def select_section(self,section):
        self.click(self.mpl.appearanceEditor.sectionButtons[section])

    def scroll_editor(self):
        editor=self.open()
        editor.scroll.SetHeight(editor.scroll,300)
        self.select_section('fonts')
        return editor,editor.scroll

    def animate_scroll(self,scroll,frames=120,elapsed=1/60):
        for _ in range(frames):
            callback=scroll.editorScrollDriver.scripts.OnUpdate
            if callback is None:
                break
            callback(scroll.editorScrollDriver,elapsed)

    def test_wheel_animates_small_steps_accumulates_and_reverses(self):
        editor,scroll=self.scroll_editor()
        wheel=scroll.scripts.OnMouseWheel
        wheel(scroll,-1)
        self.assertEqual(scroll.scrollOffset,0)
        self.animate_scroll(scroll,1)
        self.assertGreater(scroll.scrollOffset,0)
        self.assertLess(scroll.scrollOffset,40)
        wheel(scroll,-1)
        self.assertEqual(scroll.editorScrollTarget,80)
        self.animate_scroll(scroll)
        self.assertEqual(scroll.scrollOffset,80)
        self.assertIsNone(scroll.editorScrollDriver.scripts.OnUpdate)
        wheel(scroll,-3)
        self.animate_scroll(scroll,1)
        position=scroll.scrollOffset
        wheel(scroll,1)
        self.animate_scroll(scroll,1)
        self.assertLess(scroll.scrollOffset,position)

    def test_scroll_animation_is_frame_rate_independent_and_clamped(self):
        editor,scroll=self.scroll_editor()
        wheel=scroll.scripts.OnMouseWheel
        wheel(scroll,-1)
        self.animate_scroll(scroll,6,1/60)
        position=scroll.scrollOffset
        scroll.SetVerticalScroll(scroll,0)
        wheel(scroll,-1)
        self.animate_scroll(scroll,3,1/30)
        self.assertAlmostEqual(scroll.scrollOffset,position)
        wheel(scroll,-10000)
        self.animate_scroll(scroll)
        self.assertEqual(scroll.scrollOffset,editor.content.height-scroll.height)
        self.assertEqual(scroll.ScrollBar.value,scroll.scrollOffset)
        wheel(scroll,10000)
        self.animate_scroll(scroll)
        self.assertEqual(scroll.scrollOffset,0)

    def test_drag_reset_hide_and_layout_cancel_or_clamp_pending_scroll(self):
        editor,scroll=self.scroll_editor()
        wheel=scroll.scripts.OnMouseWheel
        wheel(scroll,-3)
        scroll.ScrollBar.SetValue(scroll.ScrollBar,120)
        self.assertEqual(scroll.scrollOffset,120)
        self.assertIsNone(scroll.editorScrollDriver.scripts.OnUpdate)
        wheel(scroll,-3)
        self.select_section('window')
        self.assertEqual(scroll.scrollOffset,0)
        self.assertIsNone(scroll.editorScrollTarget)
        wheel(scroll,-100)
        editor.content.SetHeight(editor.content,400)
        scroll.scripts.OnScrollRangeChanged(scroll,0,100)
        self.assertEqual(scroll.editorScrollTarget,100)
        self.animate_scroll(scroll)
        self.assertEqual(scroll.scrollOffset,100)
        wheel(scroll,1)
        scroll.scripts.OnHide(scroll)
        self.assertIsNone(scroll.editorScrollDriver.scripts.OnUpdate)
        scroll.SetHeight(scroll,500)
        scroll.scripts.OnSizeChanged(scroll)
        self.assertFalse(scroll.ScrollBar.shown)
        self.assertEqual(scroll.scrollOffset,0)

    def test_scroll_thumb_tracks_visible_fraction_and_uses_theme_accent(self):
        editor,scroll=self.scroll_editor()
        self.assertAlmostEqual(editor.scrollThumb.height,max(32,300*300/editor.content.height))
        self.assertEqual(scroll.ScrollBar.maximum,editor.content.height-300)
        self.mpl.SetAppearanceValue('accentColor',self.lua.table_from([.2,.4,.6,1]))
        for index,component in enumerate((.2,.4,.6),1):
            self.assertAlmostEqual(editor.scrollThumb.vertexColor[index],component)

    def pointer_scroll_editor(self, content_height, scale=1):
        editor,scroll=self.scroll_editor()
        editor.content.SetHeight(editor.content,content_height)
        scroll.scripts.OnSizeChanged(scroll)
        # Model the native slider's rendered geometry; mouse input is owned by
        # the editor. Cursor coordinates are physical pixels, bounds are UI units.
        self.lua.execute('''
            local editor,scale=...
            local bar,thumb=editor.scroll.ScrollBar,editor.scrollThumb
            function bar:GetHeight() return editor.scroll:GetHeight() end
            function bar:GetEffectiveScale() return scale end
            function thumb:GetTop()
                local travel=bar:GetHeight()-self:GetHeight()
                return 600-(bar.maximum>0 and travel*bar:GetValue()/bar.maximum or 0)
            end
            function thumb:GetBottom() return self:GetTop()-self:GetHeight() end
            cursorY=0; mouseHeld=true
            function GetCursorPosition() return 0,cursorY end
            function IsMouseButtonDown() return mouseHeld end
        ''',editor,scale)
        return editor,scroll

    def test_track_clicks_above_and_below_thumb_follow_visual_direction(self):
        for content_height in (320,600,3000):
            for scale in (.65,1,1.5):
                with self.subTest(content_height=content_height,scale=scale):
                    editor,scroll=self.pointer_scroll_editor(content_height,scale)
                    bar=scroll.ScrollBar
                    self.assertIsNotNone(bar.editorInput)
                    pointer=bar.editorInput
                    maximum=content_height-300
                    scroll.SetVerticalScroll(scroll,maximum/2)
                    top=editor.scrollThumb.GetTop(editor.scrollThumb)
                    self.lua.globals().cursorY=(editor.scrollThumb.GetBottom(editor.scrollThumb)-1)*scale
                    pointer.scripts.OnMouseDown(pointer,'LeftButton')
                    self.assertGreater(scroll.scrollOffset,maximum/2)
                    self.assertLess(editor.scrollThumb.GetTop(editor.scrollThumb),top)
                    scroll.SetVerticalScroll(scroll,maximum/2)
                    self.lua.globals().cursorY=(top+1)*scale
                    pointer.scripts.OnMouseDown(pointer,'LeftButton')
                    self.assertLess(scroll.scrollOffset,maximum/2)
                    self.assertGreater(editor.scrollThumb.GetTop(editor.scrollThumb),top)

    def test_thumb_grab_does_not_jump_and_drag_uses_available_travel(self):
        for scale in (.65,1,1.5):
            editor,scroll=self.pointer_scroll_editor(320,scale)
            self.assertIsNotNone(scroll.ScrollBar.editorInput)
            pointer=scroll.ScrollBar.editorInput
            scroll.SetVerticalScroll(scroll,10)
            # Grab far from the thumb centre, where the old native handler was used.
            self.lua.globals().cursorY=(editor.scrollThumb.GetBottom(editor.scrollThumb)+2)*scale
            pointer.scripts.OnMouseDown(pointer,'LeftButton')
            self.assertEqual(scroll.scrollOffset,10)
            self.lua.globals().cursorY-=5*scale
            pointer.scripts.OnUpdate(pointer,1/60)
            self.assertAlmostEqual(scroll.scrollOffset,10+5*20/(300-editor.scrollThumb.height))
            self.lua.globals().cursorY+=10*scale
            pointer.scripts.OnUpdate(pointer,1/60)
            self.assertAlmostEqual(scroll.scrollOffset,10-5*20/(300-editor.scrollThumb.height))
            self.lua.globals().cursorY-=10000*scale
            pointer.scripts.OnUpdate(pointer,1/60)
            self.assertEqual(scroll.scrollOffset,20)
            self.lua.globals().cursorY+=20000*scale
            pointer.scripts.OnUpdate(pointer,1/60)
            self.assertEqual(scroll.scrollOffset,0)
            self.lua.globals().mouseHeld=False
            pointer.scripts.OnUpdate(pointer,1/60)
            self.assertIsNone(pointer.scripts.OnUpdate)

    def test_pointer_scroll_cancels_wheel_and_hide_cancels_drag(self):
        editor,scroll=self.pointer_scroll_editor(320)
        self.assertIsNotNone(scroll.ScrollBar.editorInput)
        pointer=scroll.ScrollBar.editorInput
        scroll.scripts.OnMouseWheel(scroll,-1)
        self.lua.globals().cursorY=editor.scrollThumb.GetBottom(editor.scrollThumb)-1
        pointer.scripts.OnMouseDown(pointer,'LeftButton')
        self.assertEqual(scroll.scrollOffset,20)
        self.assertIsNone(scroll.editorScrollTarget)
        self.assertIsNone(scroll.editorScrollDriver.scripts.OnUpdate)
        self.lua.globals().cursorY=editor.scrollThumb.GetTop(editor.scrollThumb)-2
        pointer.scripts.OnMouseDown(pointer,'LeftButton')
        self.assertIsNotNone(pointer.scripts.OnUpdate)
        pointer.scripts.OnHide(pointer)
        self.assertIsNone(pointer.scripts.OnUpdate)
        pointer.scripts.OnMouseDown(pointer,'RightButton')
        self.assertIsNone(pointer.scripts.OnUpdate)
        pointer.scripts.OnMouseDown(pointer,'LeftButton')
        pointer.scripts.OnMouseUp(pointer,'LeftButton')
        self.assertIsNone(pointer.scripts.OnUpdate)
        pointer.scripts.OnMouseDown(pointer,'LeftButton')
        scroll.scripts.OnMouseWheel(scroll,1)
        self.assertIsNone(pointer.scripts.OnUpdate)
        self.animate_scroll(scroll)
        self.lua.globals().cursorY=editor.scrollThumb.GetTop(editor.scrollThumb)-2
        pointer.scripts.OnMouseDown(pointer,'LeftButton')
        self.select_section('window')
        self.assertIsNone(pointer.scripts.OnUpdate)

    def test_field_help_is_localized_and_reachable_from_each_control(self):
        editor=self.open()
        for section in ('window','fonts','colors','table'):
            self.select_section(section)
        tooltip=self.lua.globals().GameTooltip
        help_key='Test appearance explanation'
        self.mpl.L[help_key]='Объяснение настройки для игрока.'
        for key in ('scale','locked','font','backgroundColor','gridMode'):
            row=editor.rows[key]
            row.field.help=help_key
            for name,control in (('row',row),('control',row.control),('reset',row.reset),
                                 ('slider',row.slider),('hex',row.hex)):
                if control is None:
                    continue
                with self.subTest(key=key,control=name):
                    tooltip.lines=self.lua.table()
                    control.scripts.OnEnter(control)
                    self.assertTrue(tooltip.shown)
                    self.assertEqual(tooltip.text,self.mpl.L[row.field.label])
                    self.assertEqual(tooltip.lines[1][1],self.mpl.L[help_key])
                    self.assertTrue(tooltip.lines[1][5])
                    control.scripts.OnLeave(control)
                    self.assertFalse(tooltip.shown)
        # Existing button hover scripts are still called through HookScript.
        self.select_section('fonts')
        row=editor.rows.font
        row.control.scripts.OnEnter(row.control)
        self.assertTrue(row.control.editorHovered)
        row.Hide(row)
        self.assertFalse(tooltip.shown)

    def test_field_without_help_does_not_open_tooltip(self):
        editor=self.open()
        row=editor.rows.font
        row.field.help=None
        tooltip=self.lua.globals().GameTooltip
        tooltip.Hide(tooltip)
        row.control.scripts.OnEnter(row.control)
        self.assertFalse(tooltip.shown)
        self.assertTrue(row.control.editorHovered)

    def test_font_size_controls_show_effective_values_and_reset_to_inheritance(self):
        editor=self.open()
        self.select_section('fonts')
        roles=('title','character','summary','rating','header','dungeon','numbers','secondary','button','warning')
        for role in roles:
            row=editor.rows['size_'+role]
            expected=self.mpl.GetAppearanceFontSize(role)
            self.assertGreater(expected,0)
            self.assertEqual(row.slider.value,expected)
            self.assertEqual(float(row.control.text),expected)
            self.assertNotIn('(0',row.label.text)
            self.assertEqual(self.mpl.AppearanceValue('size_'+role),0)
        self.mpl.SetAppearanceValue('fontSize',14)
        self.assertEqual(editor.rows.size_rating.slider.value,34)
        self.assertEqual(editor.rows.size_summary.slider.value,14)
        rating=editor.rows.size_rating
        rating.slider.scripts.OnValueChanged(rating.slider,35)
        self.assertEqual(self.mpl.AppearanceValue('size_rating'),35)
        self.click(rating.reset)
        self.assertEqual(self.mpl.AppearanceValue('size_rating'),0)
        self.assertEqual(rating.slider.value,34)
        self.assertEqual(float(rating.control.text),34)

    def test_font_slider_drag_does_not_hide_its_row_between_steps(self):
        editor=self.open()
        row=editor.rows.fontSize
        slider=row.slider
        self.lua.execute('''
            local row=...
            row.dragHides=0
            row:HookScript("OnHide",function() row.dragHides=row.dragHides+1 end)
        ''',row)
        slider.scripts.OnMouseDown(slider)
        for size in (11,12,13,14):
            slider.scripts.OnValueChanged(slider,size)
            self.assertEqual(self.mpl.AppearanceValue('fontSize'),size)
            self.assertEqual(row.dragHides,0)
        slider.scripts.OnMouseUp(slider)
        self.assertTrue(row.shown)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),14)
        self.mpl.UndoAppearanceEdit()
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),10)

    def test_dropdown_repeated_click_closes_and_can_reopen(self):
        editor=self.open()
        control=editor.extras.theme.control
        current=self.mpl.GetAppearanceThemeID()
        self.click(control)
        menu=editor.choices
        self.assertIsNone(menu.search)
        self.click(control)
        self.assertFalse(menu.shown)
        self.assertEqual(self.mpl.GetAppearanceThemeID(),current)
        self.click(control)
        self.assertTrue(menu.shown)

    def test_window_section_has_no_padding_or_block_spacing_controls(self):
        editor=self.open()
        self.select_section('window')
        self.assertIsNone(editor.rows.windowPadding)
        self.assertIsNone(editor.rows.blockSpacing)
        self.assertTrue(editor.rows.scale.shown)
        self.assertIsNone(editor.rows.maxRows)
        editor.search.SetText(editor.search,'maxRows')
        self.assertTrue(editor.empty.shown)
        self.assertIsNone(editor.rows.maxRows)

    def test_dropdown_scrollbar_tracks_short_long_and_reused_lists(self):
        editor=self.open()
        self.select_section('fonts')
        self.click(editor.rows.thousandsSeparator.control)
        menu=editor.choices
        # Resolve the two vertical anchors omitted by the frame mock.
        self.lua.execute('''
            local menu=...
            menu.scroll.GetHeight=function() return menu:GetHeight()-24 end
        ''',menu)
        menu.scroll.ScrollBar.Show(menu.scroll.ScrollBar)
        menu.draw()
        self.assertFalse(menu.scroll.ScrollBar.shown)
        self.assertFalse(menu.scroll.mouseWheelEnabled)
        self.assertEqual(menu.scroll.scrollOffset,0)
        menu.options=self.lua.table_from([
            {'value':str(i),'label':'Choice '+str(i)} for i in range(20)
        ],recursive=True)
        menu.draw()
        self.assertTrue(menu.scroll.ScrollBar.shown)
        self.assertTrue(menu.scroll.mouseWheelEnabled)
        menu.scroll.SetVerticalScroll(menu.scroll,100)
        menu.options=self.lua.table_from([{'value':'19','label':'Choice 19'}],recursive=True)
        menu.draw()
        self.assertFalse(menu.scroll.ScrollBar.shown)
        self.assertFalse(menu.scroll.mouseWheelEnabled)
        self.assertEqual(menu.scroll.scrollOffset,0)
        menu.scroll.ScrollBar.Show(menu.scroll.ScrollBar)
        menu.scroll.scripts.OnScrollRangeChanged(menu.scroll,0,0)
        self.assertFalse(menu.scroll.ScrollBar.shown)
        menu.options=self.lua.table()
        menu.draw()
        self.assertFalse(menu.scroll.ScrollBar.shown)
        self.assertFalse(menu.scroll.mouseWheelEnabled)

    def test_dropdown_switches_anchor_and_resets_reused_selection_mark(self):
        editor=self.open()
        self.click(editor.extras.theme.control)
        menu=editor.choices
        selected=menu.buttons[1]
        self.assertEqual(selected.text,self.mpl.L[menu.options[1].label])
        self.assertTrue(selected.selectionMark.shown)
        self.assertFalse(menu.buttons[2].selectionMark.shown)
        self.click(editor.rows.gridMode.control)
        self.assertTrue(menu.shown)
        self.assertEqual(menu.current,self.mpl.AppearanceValue('gridMode'))
        self.click(menu.buttons[2])
        self.assertFalse(menu.shown)
        self.assertEqual(self.mpl.AppearanceValue('gridMode'),menu.options[2].value)

    def test_live_change_and_cancel_restore_persisted_state_without_fetch(self):
        editor=self.open()
        self.assertTrue(editor.shown)
        self.assertEqual(self.lua.globals().previews,1)
        slider=editor.rows.surfaceOpacity.slider
        slider.scripts.OnValueChanged(slider,0.5)
        self.assertEqual(self.mpl.AppearanceValue('surfaceOpacity'),0.5)
        self.assertEqual(self.lua.globals().MPlusLogsDB.appearance.activeTheme,'classic')
        self.click(editor.cancel)
        self.assertFalse(editor.shown)
        self.assertEqual(self.mpl.AppearanceValue('surfaceOpacity'),1)
        self.assertFalse(self.mpl.IsAppearanceEditing())

    def test_combined_columns_follow_reordering_and_cancel_restores_visibility(self):
        editor=self.open()
        self.select_section('table')
        columns=editor.extras.columnOrder
        self.assertFalse(columns.entries[1].visible.enabled)
        self.assertFalse(columns.entries[1].up.enabled)
        self.assertFalse(columns.entries[9].down.enabled)
        self.click(columns.entries[2].down)
        entry=columns.entries[2]
        self.assertEqual(entry.id,'time')
        entry.visible.SetChecked(entry.visible,False)
        self.click(entry.visible)
        self.assertFalse(self.mpl.AppearanceValue('column_time_visible'))
        self.assertTrue(self.mpl.AppearanceValue('column_level_visible'))
        self.select_section('quick')
        self.assertFalse(columns.shown)
        self.assertFalse(bool(editor.rows.column_time_visible and editor.rows.column_time_visible.shown))
        self.select_section('table')
        self.assertTrue(columns.shown)
        self.assertFalse(columns.entries[2].visible.checked)
        self.assertFalse(bool(editor.rows.column_time_visible and editor.rows.column_time_visible.shown))
        self.click(editor.cancel)
        self.assertTrue(self.mpl.AppearanceValue('column_time_visible'))
        self.assertEqual(self.mpl.AppearanceValue('columnOrder')[2],'level')

    def test_save_commits_focused_number_and_close_discards_next_session(self):
        editor=self.open()
        field=editor.rows.fontSize.control
        field.SetText(field,'15'); field.SetFocus(field)
        self.click(editor.save)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),15)
        self.assertFalse(editor.shown)
        editor=self.open()
        editor.rows.fontSize.slider.scripts.OnValueChanged(editor.rows.fontSize.slider,18)
        self.click(editor.closeButton)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),15)

    def test_invalid_number_keeps_editor_open_and_does_not_save(self):
        editor=self.open()
        field=editor.rows.fontSize.control
        field.SetText(field,'nan'); field.SetFocus(field)
        self.click(editor.save)
        self.assertTrue(editor.shown)
        self.assertTrue(editor.status.text)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),10)

    def test_removed_layout_controls_are_absent_from_sections_and_search(self):
        editor=self.open()
        self.select_section('table')
        keys=['cellPadding','column_best_padding','column_median_padding','headerHeight']
        keys.extend('column_'+column+'_label' for column in self.mpl.AppearanceColumns.values())
        keys.extend('column_'+column+'_align' for column in self.mpl.AppearanceColumns.values())
        for key in keys:
            self.assertIsNone(editor.rows[key])
            editor.search.SetText(editor.search,key)
            self.assertIsNone(editor.rows[key])
            self.assertTrue(editor.empty.shown)

    def test_digit_spacing_only_appears_for_aligned_digits_and_keeps_value(self):
        self.mpl.SelectAppearanceTheme('clean')
        self.mpl.SetAppearanceValue('levelDigits','natural')
        editor=self.open()
        self.select_section('fonts')
        self.assertIsNone(editor.rows.digitGap)
        self.click(editor.rows.levelDigits.control)
        self.click(editor.choices.buttons[2])
        self.assertTrue(editor.rows.digitGap.shown)
        editor.rows.digitGap.slider.scripts.OnValueChanged(editor.rows.digitGap.slider,3)
        self.click(editor.rows.levelDigits.control)
        self.click(editor.choices.buttons[1])
        self.assertFalse(editor.rows.digitGap.shown)
        self.assertEqual(self.mpl.AppearanceValue('digitGap'),3)
        editor.search.SetText(editor.search,'digitGap')
        self.assertTrue(editor.empty.shown)
        editor.search.SetText(editor.search,'')
        self.click(editor.rows.levelDigits.control)
        self.click(editor.choices.buttons[2])
        self.assertTrue(editor.rows.digitGap.shown)
        self.assertEqual(editor.rows.digitGap.control.text,'3')

    def test_search_finds_advanced_fields_and_reuses_created_controls(self):
        editor=self.open()
        editor.search.SetText(editor.search,'gridThickness')
        row=editor.rows.gridThickness
        self.assertTrue(row.shown)
        row_id=self.lua.eval('function(t) return tostring(t) end')(row)
        for _ in range(20):
            editor.search.SetText(editor.search,'')
            editor.search.SetText(editor.search,'gridThickness')
        self.assertEqual(self.lua.eval('function(t) return tostring(t) end')(editor.rows.gridThickness),row_id)
        self.assertFalse(editor.rows.fontSize.shown)

    def test_colors_only_scroll_when_visible_controls_overflow(self):
        editor=self.open()
        # The base mock does not resolve the scroll frame's two vertical anchors.
        editor.scroll.SetHeight(editor.scroll,editor.height-86-108)
        editor.scroll.ScrollBar.Show(editor.scroll.ScrollBar)
        self.select_section('colors')
        self.assertGreater(editor.content.height,editor.scroll.height)
        self.assertTrue(editor.scroll.ScrollBar.shown)
        self.assertTrue(editor.scroll.mouseWheelEnabled)
        editor.scroll.SetVerticalScroll(editor.scroll,200)
        self.mpl.RefreshAppearanceEditor()
        self.assertEqual(editor.scroll.scrollOffset,200)

        editor.search.SetText(editor.search,'backgroundColor')
        self.assertFalse(editor.scroll.ScrollBar.shown)
        self.assertFalse(editor.scroll.mouseWheelEnabled)
        self.assertEqual(editor.scroll.scrollOffset,0)

    def test_color_section_and_search_only_offer_overall_palette(self):
        editor=self.open()
        self.select_section('colors')
        expected={'backgroundColor','titleBackgroundColor','headerColor','textColor',
                  'buttonColor','accentColor','borderColor','gridColor'}
        visible={key for key,row in editor.rows.items() if row.shown and row.field.kind=='color'}
        self.assertEqual(visible,expected)
        for key in ('numberColor','missingColor','warningColor','disabledColor','selectedColor'):
            editor.search.SetText(editor.search,key)
            self.assertTrue(editor.empty.shown,key)
        editor.search.SetText(editor.search,'Color')
        visible={key for key,row in editor.rows.items() if row.shown and row.field.kind=='color'}
        self.assertEqual(visible,expected)

    def test_reducing_palette_controls_preserves_saved_specialty_colors(self):
        self.open()
        custom=self.lua.table_from([.11,.22,.33,.44])
        self.mpl.SetAppearanceValue('missingColor',custom)
        self.click(self.mpl.appearanceEditor.save)
        editor=self.open()
        self.select_section('colors')
        self.assertIsNone(editor.rows.missingColor)
        self.assertEqual(list(self.mpl.AppearanceValue('missingColor').values()),[.11,.22,.33,.44])
        exported=self.mpl.ExportAppearance(False)
        self.mpl.SetAppearanceValue('missingColor',self.lua.table_from([1,1,1,1]))
        result=self.mpl.ImportAppearance(exported)
        self.assertTrue(result[0] if isinstance(result,tuple) else result)
        self.assertEqual(list(self.mpl.AppearanceValue('missingColor').values()),[.11,.22,.33,.44])

    def test_search_hides_scrollbar_for_a_single_result(self):
        editor=self.open()
        editor.scroll.SetHeight(editor.scroll,editor.height-86-108)
        editor.scroll.ScrollBar.Show(editor.scroll.ScrollBar)
        editor.search.SetText(editor.search,'surfaceOpacity')
        self.assertTrue(editor.rows.surfaceOpacity.shown)
        self.assertFalse(editor.scroll.ScrollBar.shown)
        self.assertFalse(editor.scroll.mouseWheelEnabled)
        editor.search.SetText(editor.search,'no-such-setting')
        self.assertTrue(editor.empty.shown)
        self.assertFalse(editor.scroll.ScrollBar.shown)

    def test_scroll_visibility_updates_after_viewport_size_and_range_changes(self):
        editor=self.open()
        self.select_section('colors')
        editor.scroll.SetHeight(editor.scroll,300)
        editor.scroll.scripts.OnSizeChanged(editor.scroll)
        self.assertTrue(editor.scroll.ScrollBar.shown)
        self.assertTrue(editor.scroll.mouseWheelEnabled)
        editor.scroll.SetVerticalScroll(editor.scroll,80)
        editor.scroll.SetHeight(editor.scroll,editor.content.height+100)
        editor.scroll.scripts.OnSizeChanged(editor.scroll)
        self.assertFalse(editor.scroll.ScrollBar.shown)
        self.assertEqual(editor.scroll.scrollOffset,0)
        # A later template range update must not bring back the unused scrollbar.
        editor.scroll.ScrollBar.Show(editor.scroll.ScrollBar)
        editor.scroll.scripts.OnScrollRangeChanged(editor.scroll,0,0)
        self.assertFalse(editor.scroll.ScrollBar.shown)

    def test_color_hex_alpha_and_picker_cancel_restore_only_color(self):
        editor=self.open()
        color=editor.rows.backgroundColor
        color.hex.SetText(color.hex,'#33669980')
        color.hex.scripts.OnEnterPressed(color.hex)
        current=self.mpl.AppearanceValue('backgroundColor')
        self.assertAlmostEqual(current[1],0x33/255)
        self.assertAlmostEqual(current[4],0x80/255)
        self.lua.execute('''
            ColorPickerFrame=CreateFrame("Frame")
            function ColorPickerFrame:SetupColorPickerAndShow(options) self.options=options; self:Show() end
            function ColorPickerFrame:GetColorRGB() return .9,.8,.7 end
            function ColorPickerFrame:GetColorAlpha() return .3 end
        ''')
        self.mpl.SetAppearanceValue('fontSize',14)
        self.mpl.OpenAppearanceColorPicker('backgroundColor')
        picker=self.lua.globals().ColorPickerFrame
        self.assertAlmostEqual(picker.options.opacity,0x80/255)
        picker.options.swatchFunc()
        self.assertAlmostEqual(self.mpl.AppearanceValue('backgroundColor')[4],0.3)
        picker.options.cancelFunc()
        self.assertAlmostEqual(self.mpl.AppearanceValue('backgroundColor')[4],0x80/255)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),14)

    def test_stale_picker_callback_cannot_modify_saved_or_new_session(self):
        editor=self.open()
        self.lua.execute('''
            ColorPickerFrame=CreateFrame("Frame")
            function ColorPickerFrame:SetupColorPickerAndShow(options) self.options=options; self:Show() end
            function ColorPickerFrame:GetColorRGB() return .9,.8,.7 end
            function ColorPickerFrame:GetColorAlpha() return .3 end
        ''')
        self.mpl.OpenAppearanceColorPicker('backgroundColor')
        stale=self.lua.globals().ColorPickerFrame.options.swatchFunc
        self.click(editor.cancel)
        self.open()
        stale()
        self.assertEqual(self.mpl.AppearanceValue('backgroundColor')[1],0)

    def test_column_reorder_and_aliases_are_transactional(self):
        editor=self.open()
        self.select_section('table')
        order=editor.extras.columnOrder
        self.click(order.entries[2].down)
        self.assertEqual(self.mpl.AppearanceValue('columnOrder')[2],'time')
        self.select_section('names')
        alias=editor.extras.alias_249.control
        alias.SetText(alias,'Моя гробница'); alias.SetFocus(alias)
        self.click(editor.save)
        self.assertEqual(self.mpl.GetDungeonAlias(249),'Моя гробница')
        self.open(); self.select_section('names')
        alias.SetText(alias,'Другое'); alias.scripts.OnEnterPressed(alias)
        self.click(editor.cancel)
        self.assertEqual(self.mpl.GetDungeonAlias(249),'Моя гробница')

    def test_role_font_list_has_inherit_and_missing_font_visible(self):
        editor=self.open(); self.select_section('fonts')
        self.mpl.SetAppearanceValue('font_numbers','Missing custom font')
        self.mpl.RefreshAppearanceEditor()
        row=editor.rows.font_numbers
        self.assertEqual(row.sample.text,self.mpl.L['Unavailable font; using the game interface font.'])
        self.click(row.control)
        self.assertEqual(editor.choices.options[1].value,'inherit')

    def test_settings_menu_keeps_general_and_appearance_routes_separate(self):
        self.lua.execute('local MPL=...; MPL.OpenSettings=function() generalOpened=true end',self.mpl)
        anchor=self.lua.globals().CreateFrame('Button')
        self.mpl.OpenProfileSettingsMenu(anchor)
        menu=self.mpl.appearanceSettingsMenu
        self.assertTrue(menu.shown)
        self.click(menu.general)
        self.assertTrue(self.lua.globals().generalOpened)
        self.assertFalse(menu.shown)
        self.mpl.OpenProfileSettingsMenu(anchor)
        self.click(menu.appearance)
        self.assertTrue(self.mpl.appearanceEditor.shown)

    def test_import_is_previewed_and_cancel_does_not_persist(self):
        editor=self.open()
        self.mpl.SetAppearanceValue('fontSize',14)
        exported=self.mpl.ExportAppearance(False)
        self.mpl.SetAppearanceValue('fontSize',10)
        self.mpl.ShowAppearanceTransfer(True)
        dialog=editor.transfer
        dialog.input.SetText(dialog.input,exported)
        self.click(dialog.apply)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),14)
        self.assertFalse(dialog.shown)
        self.click(editor.cancel)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),10)

    def test_editor_fits_small_screen_and_initial_preview_stays_behind(self):
        self.lua.execute('''
            UIParent:SetSize(1024,600)
            local MPL=...
            MPL.ShowAppearancePreview=function()
                local preview=MPL.appearancePreview or CreateFrame("Frame")
                MPL.appearancePreview=preview; preview:SetSize(700,700); preview:Show()
                return preview
            end
        ''',self.mpl)
        editor=self.open()
        self.assertLessEqual(editor.scale*650,576)
        self.assertEqual(editor.raised,1)
        self.assertIsNone(self.mpl.appearancePreview.raised)
        self.assertIsNone(editor.preview)
        self.assertIsNone(editor.previewCurrent)

    def test_loaded_profile_is_used_even_when_hidden(self):
        for shown in (False, True):
            with self.subTest(shown=shown):
                self.lua.execute('''
                    local MPL=...
                    MPL.panel=CreateFrame("Frame")
                    MPL.panel.profile={dungeons={{id=249,runs=10}}}
                    MPL.appearancePreview=CreateFrame("Frame")
                    MPL.appearancePreview:Show()
                ''',self.mpl)
                if shown:
                    self.mpl.panel.Show(self.mpl.panel)
                editor=self.open()
                self.assertTrue(self.mpl.panel.shown)
                self.assertFalse(self.mpl.appearancePreview.shown)
                self.assertIsNone(self.lua.globals().previews)
                self.click(editor.cancel)

    def test_visible_profile_without_data_uses_sample(self):
        self.lua.execute('''
            local MPL=...
            MPL.panel=CreateFrame("Frame")
            MPL.panel.profile=false
            MPL.panel:Show()
        ''',self.mpl)
        self.open()
        self.assertEqual(self.lua.globals().previews,1)

    def test_large_screen_places_sample_beside_editor(self):
        self.lua.execute('''
            UIParent:SetSize(1920,1080)
            local MPL=...
            MPL.ShowAppearancePreview=function()
                local preview=MPL.appearancePreview or CreateFrame("Frame")
                MPL.appearancePreview=preview; preview:SetSize(940,700); preview:Show()
                return preview
            end
        ''',self.mpl)
        editor=self.open()
        self.assertIsNotNone(editor.points.LEFT)
        self.assertIsNotNone(self.mpl.appearancePreview.points.RIGHT)
        self.assertEqual(editor.scale,1)

    def test_lsm_global_override_is_reported_without_glyph_claim(self):
        self.lua.execute('''
            local library={}
            library.List=function() return {"Wanted face","Forced face"} end
            library.IsValid=function() return true end
            library.Fetch=function() return "Interface\\\\AddOns\\\\Media\\\\forced.ttf" end
            library.GetGlobal=function() return "Forced face" end
            LibStub=function() return library end
        ''')
        editor=self.open()
        self.mpl.SetAppearanceValue('font','Wanted face')
        self.mpl.RefreshAppearanceEditor()
        self.assertIn('Forced face',editor.rows.font.fontStatus.text)
        self.assertIn(self.mpl.L['LSM override:'],editor.rows.font.fontStatus.text)

    def test_missing_blizzard_picker_is_loaded_on_demand(self):
        self.open()
        self.lua.execute('''
            C_AddOns={LoadAddOn=function(name)
                loadedPicker=name
                ColorPickerFrame=CreateFrame("Frame")
                function ColorPickerFrame:SetupColorPickerAndShow(options) self.options=options; self:Show() end
            end}
        ''')
        self.mpl.OpenAppearanceColorPicker('backgroundColor')
        self.assertEqual(self.lua.globals().loadedPicker,'Blizzard_ColorPicker')
        self.assertTrue(self.lua.globals().ColorPickerFrame.shown)
        self.assertIsNotNone(self.lua.globals().ColorPickerFrame.options.cancelFunc)

    def test_legacy_picker_remains_active_and_reads_opacity_slider(self):
        editor=self.open()
        self.lua.execute('''
            ColorPickerFrame=CreateFrame("Frame")
            ColorPickerFrame.SetupColorPickerAndShow=false
            ColorPickerFrame.GetColorAlpha=false
            function ColorPickerFrame:GetColorRGB() return .1,.2,.3 end
            OpacitySliderFrame=CreateFrame("Slider")
            OpacitySliderFrame:SetValue(.75)
            ColorPickerFrame:Show()
        ''')
        self.mpl.OpenAppearanceColorPicker('backgroundColor')
        picker=self.lua.globals().ColorPickerFrame
        self.assertIsNotNone(editor.pendingColor)
        picker.opacityFunc()
        self.assertAlmostEqual(self.mpl.AppearanceValue('backgroundColor')[4],.25)
        picker.cancelFunc()
        self.assertEqual(self.mpl.AppearanceValue('backgroundColor')[1],0)

    def test_hide_before_cancel_callback_still_restores_original_color(self):
        editor=self.open()
        self.lua.execute('''
            timers={}
            C_Timer={After=function(_,fn) timers[#timers+1]=fn end}
            ColorPickerFrame=CreateFrame("Frame")
            function ColorPickerFrame:SetupColorPickerAndShow(options) self.options=options; self:Show() end
            function ColorPickerFrame:GetColorRGB() return .1,.2,.3 end
            function ColorPickerFrame:GetColorAlpha() return .5 end
        ''')
        self.mpl.OpenAppearanceColorPicker('backgroundColor')
        picker=self.lua.globals().ColorPickerFrame
        picker.options.swatchFunc()
        picker.Hide(picker)
        picker.options.cancelFunc()
        self.assertEqual(self.mpl.AppearanceValue('backgroundColor')[1],0)
        self.lua.execute('for _,fn in ipairs(timers) do fn() end')
        self.assertIsNone(editor.pendingColor)


if __name__=='__main__':
    unittest.main()
