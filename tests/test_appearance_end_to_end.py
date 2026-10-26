"""Editor -> appearance state -> actual profile constructor/render integration.

Uses the production UI constructor and renderers with mocked WoW frame objects.
It does not establish real font glyph coverage, GPU blending or protected UI behavior.
"""
import unittest

from test_addon import ROOT, LuaRuntime, load_locales
from test_profile_appearance import MOCK as PROFILE_MOCK


MOCK=PROFILE_MOCK.replace(
    'function methods:SetText(text) self.text = text end', '''
    function methods:SetText(text)
        self.text=text
        if self.scripts.OnTextChanged then self.scripts.OnTextChanged(self,false) end
    end
    function methods:GetScript(name) return self.scripts[name] end
    function methods:SetChecked(value) self.checked=value end
    function methods:GetChecked() return self.checked==true end
    function methods:GetScale() return self.scale or 1 end
    ''').replace(
    'function methods:Hide() self.shown = false end', '''
    function methods:Hide()
        local shown=self.shown; self.shown=false
        if shown and self.scripts.OnHide then self.scripts.OnHide(self) end
    end
    ''').replace(
    'function methods:Show() self.shown = true end', '''
    function methods:Show()
        local shown=self.shown; self.shown=true
        if not shown and self.scripts.OnShow then self.scripts.OnShow(self) end
    end
    ''').replace(
    'function methods:HookScript(name, callback) self.scripts[name] = callback end', '''
    function methods:HookScript(name,callback)
        local old=self.scripts[name]
        self.scripts[name]=function(...) if old then old(...) end; callback(...) end
    end
    ''').replace('function methods:GetFrameLevel() return 1 end', '''
    function methods:GetFrameLevel() return self.frameLevel or 1 end
    function methods:SetFrameLevel(level) self.frameLevel=level end
    ''')


class AppearanceEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.mpl=self.lua.table()
        load_locales(self.lua,self.mpl)
        self.lua.execute('UIParent:SetSize(1920,1080); MPlusLogsDB={profiles={},companionIntroDismissed=true}')
        for name in ('Data.lua','Snapshot.lua','Appearance.lua','AppearancePresets.lua','DungeonNames.lua',
                     'ProfileAppearance.lua','UI.lua','TutorialProfile.lua','TutorialSteps.lua','Settings.lua',
                     'AppearanceSettings.lua','Integration.lua'):
            self.lua.execute('return assert(loadstring(...))',(ROOT/name).read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.mpl.ShowProfile('Киндрих','Гордунни',None,True)
        self.panel=self.mpl.panel
        self.show_profile=self.mpl.ShowProfile
        self.lua.execute('''
            local MPL=...
            MPL.ShowProfile=function() error("appearance editor must not navigate") end
            MPL.ShowDownload=function() error("appearance editor must not download") end
            MPL.SendRequest=function() error("appearance editor must not request logs") end
        ''',self.mpl)

    @staticmethod
    def click(control):
        control.scripts.OnClick(control)

    def test_inherited_size_sliders_match_rendered_fonts(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.fonts)
        samples={'title':self.panel.title,'character':self.panel.character,
                 'summary':self.panel.summary,'rating':self.panel.scoreValue,
                 'header':self.panel.headings[1],'dungeon':self.panel.rows[1].cells[1],
                 'numbers':self.panel.rows[1].cells[2],'secondary':self.panel.source,
                 'button':self.panel.loadButton.caption,'warning':self.panel.staleBanner.message}
        for base in (10,14):
            self.mpl.SetAppearanceValue('fontSize',base)
            for role,sample in samples.items():
                row=editor.rows['size_'+role]
                self.assertEqual(row.slider.value,sample.fontSize,role)
                self.assertEqual(float(row.control.text),sample.fontSize,role)

    def test_editor_geometry_and_fonts_stay_fixed_while_profile_sizes_change(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.fonts)
        row=editor.rows.size_button

        def geometry():
            return (editor.width,editor.height,editor.scale,editor.title.mplAppliedFontSize,
                    row.height,row.label.mplAppliedFontSize,row.control.width,row.control.height,
                    row.control.mplAppliedFontSize,row.slider.width,row.slider.height,
                    row.slider.points.TOPLEFT[1],row.slider.points.TOPLEFT[2],
                    row.reset.width,row.reset.height,row.reset.caption.mplAppliedFontSize,
                    editor.save.height,editor.save.caption.mplAppliedFontSize,
                    editor.sectionButtons.fonts.height)

        original=geometry()
        profile_size=self.panel.rows[1].cells[2].fontSize
        for key,new_value in (('fontSize',24),('size_secondary',28),('size_button',30),
                              ('size_title',32),('scale',.7),('borderThickness',0)):
            with self.subTest(setting=key):
                self.mpl.SetAppearanceValue(key,new_value)
                self.assertEqual(geometry(),original)
        self.assertGreater(self.panel.rows[1].cells[2].fontSize,profile_size)
        self.assertEqual(self.panel.loadButton.caption.fontSize,30)
        self.assertEqual(self.panel.scale,.7)
        self.assertEqual(row.slider.value,30)
        self.assertEqual(float(row.control.text),30)

    def test_editor_defaults_use_readable_fonts_and_larger_targets(self):
        self.lua.execute('function CreateFont(name) return CreateFrame("Font",name) end')
        editor=self.mpl.OpenAppearanceSettings()
        self.assertEqual(editor.title.fontSize,20)
        self.assertEqual(editor.search.fontSize,14)
        self.assertEqual(editor.save.caption.fontSize,14)
        self.assertGreaterEqual(editor.save.height,32)
        self.assertGreaterEqual(editor.search.height,32)
        for section in editor.sectionButtons.values():
            self.assertEqual(section.caption.fontSize,14)
            self.assertGreaterEqual(section.height,40)
            self.assertGreaterEqual(section.width,220)
        for state in ('normalFontObject','highlightFontObject','disabledFontObject'):
            self.assertEqual(editor.save[state].fontSize,14)
        for control in (editor.resetSection,editor.resetAll,editor.undo,editor.save,editor.cancel):
            self.assertGreaterEqual(control.width,control.caption.GetUnboundedStringWidth(control.caption)+24)
        for name in ('fonts','colors','profiles','table'):
            self.click(editor.sectionButtons[name])
            for row in editor.rows.values():
                if row.shown:
                    self.assertEqual(row.label.fontSize,14)
                    self.assertGreaterEqual(row.control.height,32)
                    self.assertLessEqual(-row.label.points.TOPLEFT[2]+row.label.height,
                                         -row.control.points.TOPLEFT[2])
        row=editor.rows.backgroundColor
        self.assertLessEqual(row.control.width,row.hex.points.TOPLEFT[1])
        self.assertLessEqual(row.hex.points.TOPLEFT[1]+row.hex.width,row.hint.points.TOPLEFT[1])
        self.assertLessEqual(row.hint.points.TOPLEFT[1]+row.hint.GetUnboundedStringWidth(row.hint),
                             row.reset.points.TOPLEFT[1])
        row=editor.extras.profiles
        for control in (row.create,row.rename,row.delete):
            self.assertGreaterEqual(control.width,control.caption.GetUnboundedStringWidth(control.caption)+24)
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,900,600)
        self.mpl.ApplyAppearanceToEditor(editor)
        self.assertLessEqual(editor.width*editor.scale,900)
        self.assertLessEqual(editor.height*editor.scale,600)

    def test_role_slider_keeps_its_value_after_release_and_reopening(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.fonts)
        slider=editor.rows.size_button.slider
        slider.scripts.OnMouseDown(slider)
        for value in (11,12,13,14):
            slider.scripts.OnValueChanged(slider,value)
        slider.scripts.OnMouseUp(slider)
        self.assertEqual(slider.value,14)
        self.assertEqual(float(editor.rows.size_button.control.text),14)
        self.assertEqual(self.panel.loadButton.caption.fontSize,14)
        self.click(editor.save)
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.fonts)
        self.assertEqual(editor.rows.size_button.slider.value,14)
        self.assertEqual(float(editor.rows.size_button.control.text),14)

    def test_editor_keeps_using_the_profile_palette(self):
        editor=self.mpl.OpenAppearanceSettings()
        original_height=editor.height
        self.mpl.SetAppearanceValue('backgroundColor',self.lua.table_from([.2,.3,.4,1]))
        self.mpl.SetAppearanceValue('surfaceOpacity',.5)
        color=editor.appearanceBodyFill.fillColor
        self.assertEqual(tuple(color.values()),(.2,.3,.4,.5))
        self.assertEqual(editor.height,original_height)

    def test_actual_slider_updates_existing_profile_and_cancel_preserves_new_data(self):
        editor=self.mpl.OpenAppearanceSettings()
        row=self.panel.rows[1]
        old_height=row.height
        self.panel.viewMetric='hps'; self.panel.selectedSpec='Guardian'; self.panel.inviteSent=True
        self.panel.lookup.SetText(self.panel.lookup,'Alice-Area 52')
        self.panel.lookupExpanded=True; self.panel.lookup.SetFocus(self.panel.lookup)
        editor.rows.fontSize.slider.scripts.OnValueChanged(editor.rows.fontSize.slider,24)
        self.assertEqual(row.height,34)
        self.assertEqual(self.panel.viewMetric,'hps')
        self.assertTrue(self.panel.inviteSent)
        self.assertEqual(self.panel.lookup.text,'Alice-Area 52')
        self.assertTrue(self.panel.lookup.focused)
        self.panel.profile.score=4444
        self.click(editor.cancel)
        self.assertEqual(row.height,old_height)
        self.assertEqual(self.panel.profile.score,4444)
        self.assertFalse(editor.shown)

    def test_actual_color_picker_changes_row_layers_and_cancels_one_color(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.lua.execute('''
            ColorPickerFrame=CreateFrame("Frame")
            function ColorPickerFrame:SetupColorPickerAndShow(options) self.options=options; self:Show() end
            function ColorPickerFrame:GetColorRGB() return .2,.4,.6 end
            function ColorPickerFrame:GetColorAlpha() return .5 end
        ''')
        self.click(editor.sectionButtons.colors)
        self.click(editor.rows.backgroundColor.control)
        picker=self.lua.globals().ColorPickerFrame
        picker.options.swatchFunc()
        color=self.panel.rows[1].background.fillColor
        self.assertAlmostEqual(color[1],.2)
        self.assertAlmostEqual(color[4],.5)
        self.mpl.SetAppearanceValue('fontSize',14)
        picker.options.cancelFunc()
        self.assertEqual(self.panel.rows[1].background.fillColor[1],0)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),14)
        self.click(editor.cancel)

    def test_save_then_reopen_uses_saved_theme_without_rebuilding_profile(self):
        panel_id=self.lua.eval('tostring')(self.panel)
        editor=self.mpl.OpenAppearanceSettings()
        number=editor.rows.fontSize.control
        number.SetText(number,'14'); number.SetFocus(number)
        self.click(editor.save)
        self.assertEqual(self.panel.rows[1].cells[2].fontSize,14)
        self.assertEqual(self.lua.eval('tostring')(self.panel),panel_id)
        editor=self.mpl.OpenAppearanceSettings()
        self.assertEqual(editor.rows.fontSize.control.text,'14')
        self.click(editor.closeButton)
        self.assertEqual(self.panel.rows[1].cells[2].fontSize,14)

    def test_sample_uses_actual_profile_constructor_and_isolated_actions(self):
        self.panel.profile=False
        self.panel.Hide(self.panel)
        editor=self.mpl.OpenAppearanceSettings()
        sample=self.mpl.appearancePreview
        self.assertTrue(sample.shown)
        self.assertNotEqual(self.lua.eval('tostring')(sample),self.lua.eval('tostring')(self.panel))
        self.assertEqual(sample.name,'Preview')
        self.assertIsNone(sample.loadButton.scripts.OnClick)
        self.assertIsNone(sample.rows[1].scripts.OnMouseUp)
        self.assertIsNone(sample.lookup.scripts.OnEnterPressed)
        self.assertGreater(editor.GetFrameLevel(editor),sample.GetFrameLevel(sample))
        editor.rows.fontSize.slider.scripts.OnValueChanged(editor.rows.fontSize.slider,24)
        self.assertEqual(sample.rows[1].height,34)
        self.assertIsNone(sample.rows[1].scripts.OnMouseUp)
        self.click(editor.cancel)
        self.assertEqual(sample.rows[1].height,26)

    def test_hidden_loaded_profile_reopens_and_updates_without_sample(self):
        profile_id=self.lua.eval('tostring')(self.panel.profile)
        self.panel.Hide(self.panel)
        editor=self.mpl.OpenAppearanceSettings()
        self.assertTrue(self.panel.shown)
        self.assertIsNone(self.mpl.appearancePreview)
        self.assertEqual(self.lua.eval('tostring')(self.panel.profile),profile_id)
        editor.rows.fontSize.slider.scripts.OnValueChanged(editor.rows.fontSize.slider,24)
        self.assertEqual(self.panel.rows[1].height,34)
        self.click(editor.cancel)
        self.assertEqual(self.panel.rows[1].height,26)

    def test_visible_appearance_button_opens_editor_directly_and_cancels_preview(self):
        self.assertTrue(self.panel.appearanceButton.shown)
        self.assertEqual(self.panel.appearanceButton.caption.text,'Оформление')
        self.click(self.panel.appearanceButton)
        self.assertTrue(self.mpl.appearanceEditor.shown)
        self.assertIsNone(self.mpl.appearanceSettingsMenu)
        self.mpl.SetAppearanceValue('fontSize',16)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),16)
        self.click(self.mpl.appearanceEditor.cancel)
        self.assertEqual(self.mpl.AppearanceValue('fontSize'),10)
        self.assertFalse(self.mpl.appearanceEditor.shown)

    def test_header_controls_leave_room_for_translated_appearance_label(self):
        self.panel.appearanceButton.caption.SetText(self.panel.appearanceButton.caption,'Fensterdarstellung anpassen')
        self.mpl.RenderProfileStats(self.panel)
        settings=self.panel.settingsButton
        appearance=self.panel.appearanceButton
        self.assertGreaterEqual(appearance.width,appearance.caption.GetUnboundedStringWidth(appearance.caption)+20)
        self.assertLessEqual(appearance.points.TOPRIGHT[1],settings.points.TOPRIGHT[1]-settings.width-8)

    def test_narrow_header_wraps_appearance_settings_and_tutorial_below_title(self):
        self.lua.execute('''
            local MPL=...
            local button=CreateFrame("Button",nil,MPL.panel)
            button.caption=button:CreateFontString()
            button.caption:SetText("Open the full MPlusLogs guide")
            button:SetSize(220,22); button:Show()
            MPL.panel.tutorialButton=button
        ''',self.mpl)
        self.mpl.SetAppearanceValue('verticalLayout',True)
        for column in ('time','runs','points','rank','rate','best','median'):
            self.mpl.SetAppearanceValue('column_'+column+'_visible',False)
        for size in (10,24):
            self.mpl.SetAppearanceValue('fontSize',size)
            self.mpl.RenderProfileStats(self.panel)
            buttons=[self.panel.settingsButton,self.panel.appearanceButton,self.panel.tutorialButton]
            for index,button in enumerate(buttons):
                x,y=button.points.TOPRIGHT.values()
                self.assertGreaterEqual(-y,36)
                self.assertGreaterEqual(self.panel.width+x-button.width,20)
                self.assertLessEqual(-y+button.height,self.panel.appearanceTitleBand-7)
                for other in buttons[index+1:]:
                    other_x,other_y=other.points.TOPRIGHT.values()
                    if y==other_y:
                        self.assertLessEqual(other_x,x-button.width-8)

    def test_real_header_buttons_open_appearance_and_settings_directly(self):
        self.click(self.panel.appearanceButton)
        self.assertTrue(self.mpl.appearanceEditor.shown)
        self.click(self.mpl.appearanceEditor.cancel)
        self.lua.execute('''
            Settings={VarType={Boolean="boolean",String="string",Number="number"}}
            function Settings.RegisterVerticalLayoutCategory()
                return {GetID=function() return 97 end},{AddInitializer=function() end}
            end
            function Settings.RegisterProxySetting() return {} end
            function Settings.CreateCheckbox() end
            function Settings.CreateDropdown() end
            function Settings.CreateElementInitializer() return {} end
            function Settings.RegisterAddOnCategory() end
            function Settings.OpenToCategory(id) openedCategory=id end
            function CreateSettingsListSectionHeaderInitializer() return {} end
        ''')
        self.click(self.panel.settingsButton)
        self.assertEqual(self.lua.globals().openedCategory,97)

    def test_target_menu_opens_cached_accented_character_with_party_tabs(self):
        self.mpl.ShowProfile=self.show_profile
        self.lua.execute('''
            local MPL=...
            local profile=MPL.CopyAppearanceValue(MPL.panel.profile)
            profile.name="Papazêll"; profile.realm="Kazzak"; profile.spec="All specs"
            profile.class="HUNTER"; profile.best=48; profile.median=47.6; profile.runs=90
            MPlusLogsDB.profiles[MPL.Key(profile.name,profile.realm)]=profile
            function UnitFullName(unit)
                if unit=="target" then return "Papazêll","Kazzak" end
                return "Киндрих","Гордунни"
            end
            profileMenuParty={
                {name="Киндрих",realm="Гордунни"},{name="Papazêll",realm="Kazzak"}
            }
            MPL.IsProfileStale=function() return false,"25.10.2026" end
            MPL.FilterFreshProfiles=function() return {},0 end
            eventFrames={}
            local original=CreateFrame
            function CreateFrame(...)
                local frame=original(...); eventFrames[#eventFrames+1]=frame; return frame
            end
        ''',self.mpl)
        self.lua.execute('return assert(loadstring(...))',(ROOT/'Integration.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.lua.execute('''
            local MPL=...
            MPL.CollectParty=function() return profileMenuParty end
            eventFrames[1].scripts.OnEvent(eventFrames[1],"PLAYER_LOGIN")
            local root={}
            function root:CreateDivider() end
            function root:CreateButton(_,callback) self.callback=self.callback or callback end
            Menu.callbacks.MENU_UNIT_TARGET(nil,root,{unit="target"})
            assert(root.callback,"Target profile menu entry missing")
            root.callback()
        ''',self.mpl)
        self.assertTrue(self.panel.shown)
        self.assertEqual(self.panel.name,'Papazêll')
        self.assertEqual(self.panel.realm,'Kazzak')
        self.assertEqual(self.panel.profile.runs,90)
        self.assertEqual(len(self.panel.playerTabs),2)


if __name__=='__main__':
    unittest.main()
