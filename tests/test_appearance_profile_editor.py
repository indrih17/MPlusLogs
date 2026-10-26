"""Real editor callbacks for independent profile, style and palette libraries."""
import unittest

import test_appearance_end_to_end as integration


class AppearanceProfileEditorTests(unittest.TestCase):
    setUp = integration.AppearanceEndToEndTests.setUp
    click = staticmethod(integration.AppearanceEndToEndTests.click)

    def choose(self, editor, control, item_id):
        self.click(control)
        for button in editor.choices.buttons.values():
            if button.shown and button.choice == item_id:
                self.click(button)
                return
        self.fail('Choice not found: '+item_id)

    def create_profile(self, editor, name):
        row=editor.extras.profiles
        row.name.SetText(row.name,name)
        self.click(row.create)
        return self.mpl.GetAppearanceProfileID()

    def test_profiles_combine_named_layouts_and_palettes_through_editor(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.profiles)
        self.assertEqual(editor.extras.profile.control.text,self.mpl.L['Default profile'])
        self.assertFalse(editor.extras.profiles.delete.enabled)
        self.choose(editor,editor.extras.theme.control,'compact')
        self.assertEqual(self.mpl.GetAppearance().rowHeight,22)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(),'classic')
        self.click(editor.extras.theme.manage)
        library=editor.extras.styleLibrary
        self.assertFalse(library.rename.enabled)
        library.name.SetText(library.name,'My layout')
        self.click(library.create)
        style_id=self.mpl.GetAppearanceStyleID()
        self.assertTrue(style_id.startswith('style'))
        self.assertEqual(editor.extras.theme.control.text,'My layout')
        self.choose(editor,editor.extras.colorPalette.control,'midnight')
        self.click(editor.extras.colorPalette.manage)
        library=editor.extras.paletteLibrary
        library.name.SetText(library.name,'My palette')
        self.click(library.create)
        palette_id=self.mpl.GetAppearanceColorPresetID()
        self.assertTrue(palette_id.startswith('palette'))
        first=self.create_profile(editor,'Indrih')
        second=self.create_profile(editor,'Other')
        self.choose(editor,editor.extras.theme.control,'large')
        self.choose(editor,editor.extras.colorPalette.control,'emerald')
        self.assertEqual(self.mpl.GetAppearanceProfileID(),second)
        self.choose(editor,editor.extras.profile.control,first)
        self.assertEqual(self.mpl.GetAppearanceStyleID(),style_id)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(),palette_id)
        self.assertEqual(self.mpl.GetAppearance().rowHeight,22)
        self.assertEqual(editor.extras.profile.control.text,'Indrih')
        self.assertEqual(editor.extras.theme.control.text,'My layout')
        self.assertEqual(editor.extras.colorPalette.control.text,'My palette')
        self.click(editor.save)
        self.lua.execute('local MPL=...; MPlusLogsDB=MPL.CopyAppearanceValue(MPlusLogsDB); MPL.InitAppearance()',self.mpl)
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.profiles)
        self.assertEqual(editor.extras.profile.control.text,'Indrih')
        self.assertEqual(editor.extras.theme.control.text,'My layout')
        self.assertEqual(editor.extras.colorPalette.control.text,'My palette')

    def test_named_templates_can_be_renamed_deleted_and_keep_literal_names(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.sectionButtons.profiles)
        self.click(editor.extras.theme.manage)
        row=editor.extras.styleLibrary
        row.name.SetText(row.name,'Classic')
        self.click(row.create)
        self.assertEqual(editor.extras.theme.control.text,'Classic')
        self.click(editor.extras.theme.control)
        self.assertEqual(editor.choices.buttons[1].text,'Classic')
        editor.choices.Hide(editor.choices)
        row.name.SetText(row.name,'Named layout')
        self.click(row.rename)
        self.assertEqual(editor.extras.theme.control.text,'Named layout')
        self.click(row.delete)
        self.assertEqual(self.mpl.GetAppearanceStyleID(),'classic')
        self.assertEqual(self.mpl.GetAppearance().rowHeight,26)
        self.click(editor.extras.colorPalette.manage)
        row=editor.extras.paletteLibrary
        row.name.SetText(row.name,'Palette')
        self.click(row.create)
        row.name.SetText(row.name,'Renamed palette')
        self.click(row.rename)
        self.assertEqual(editor.extras.colorPalette.control.text,'Renamed palette')
        self.click(row.delete)
        self.assertEqual(self.mpl.GetAppearanceColorPresetID(),'classic')

    def test_template_libraries_remain_readable_and_cancel_discards_creation(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.click(editor.extras.theme.manage)
        row=editor.extras.styleLibrary
        row.name.SetText(row.name,'Unsaved style')
        self.click(row.create)
        self.click(editor.sectionButtons.colors)
        self.click(editor.extras.colorPalette.manage)
        row=editor.extras.paletteLibrary
        row.name.SetText(row.name,'Unsaved palette')
        self.click(row.create)
        for name in ('styleLibrary','paletteLibrary'):
            row=editor.extras[name]
            self.assertLessEqual(row.label.height,-row.name.points.TOPLEFT[2])
            self.assertLessEqual(-row.name.points.TOPLEFT[2]+row.name.height,-row.create.points.TOPLEFT[2])
            self.assertGreaterEqual(row.create.width,row.create.caption.GetUnboundedStringWidth(row.create.caption)+24)
        self.click(editor.cancel)
        self.assertTrue(all(entry.builtin for entry in self.mpl.GetAppearanceStyles().values()))
        self.assertTrue(all(entry.builtin for entry in self.mpl.GetAppearancePalettes().values()))

    def test_modified_caption_keeps_original_builtin_and_named_style_after_reload(self):
        editor=self.mpl.OpenAppearanceSettings()
        self.mpl.SetAppearanceValue('fontSize',13)
        self.assertIsNone(self.mpl.GetAppearanceStyleID())
        self.assertEqual(editor.extras.theme.control.text,self.mpl.L['%s (modified)'] % self.mpl.L['Classic'])
        self.click(editor.save)
        self.lua.execute('local MPL=...; MPlusLogsDB=MPL.CopyAppearanceValue(MPlusLogsDB); MPL.InitAppearance()',self.mpl)
        editor=self.mpl.OpenAppearanceSettings()
        self.assertEqual(editor.extras.theme.control.text,self.mpl.L['%s (modified)'] % self.mpl.L['Classic'])
        self.choose(editor,editor.extras.theme.control,'compact')
        self.mpl.SetAppearanceValue('fontSize',15)
        self.assertEqual(editor.extras.theme.control.text,self.mpl.L['%s (modified)'] % self.mpl.L['Compact'])
        style_id=self.mpl.CreateAppearanceStyle('My layout')
        self.assertEqual(editor.extras.theme.control.text,'My layout')
        self.mpl.SetAppearanceValue('rowHeight',35)
        self.assertEqual(self.mpl.GetAppearanceStyleSourceID(),style_id)
        self.assertEqual(editor.extras.theme.control.text,self.mpl.L['%s (modified)'] % 'My layout')
        self.mpl.UndoAppearanceEdit()
        self.assertEqual(editor.extras.theme.control.text,'My layout')

    def test_expanded_libraries_have_themed_panels_padding_and_disclosure_arrows(self):
        editor=self.mpl.OpenAppearanceSettings()
        for section,selector,library in (('quick','theme','styleLibrary'),('colors','colorPalette','paletteLibrary')):
            self.click(editor.sectionButtons[section])
            toggle=editor.extras[selector].manage
            self.assertFalse(toggle.editorExpanded)
            self.assertEqual(len(toggle.strokes),2)
            self.click(toggle)
            panel=editor.extras[library]
            self.assertTrue(toggle.editorExpanded)
            self.assertTrue(toggle.editorSelected)
            self.assertTrue(panel.shown)
            self.assertEqual(panel.editorPanelPadding,12)
            for i in range(1,4):
                self.assertAlmostEqual(panel.backdropColor[i],self.mpl.AppearanceValue('headerColor')[i])
                self.assertAlmostEqual(panel.panelAccent.fillColor[i],self.mpl.AppearanceValue('accentColor')[i])
            self.assertGreaterEqual(panel.label.points.TOPLEFT[1],12)
            self.assertGreaterEqual(-panel.label.points.TOPLEFT[2],12)
            self.assertLessEqual(-panel.create.points.TOPLEFT[2]+panel.create.height,panel.height-12)
            self.mpl.SetAppearanceValue('headerColor',self.lua.table_from([.1,.2,.3,1]))
            self.assertAlmostEqual(panel.backdropColor[2],.2)
            self.click(toggle)
            self.assertFalse(toggle.editorExpanded)
            self.assertFalse(panel.shown)


if __name__ == '__main__':
    unittest.main()
