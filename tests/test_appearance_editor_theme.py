"""Live theme changes reach the real editor and lazily created editor controls.

Mocks cover state, frame colors and font metrics; in-game rendering still needs
visual verification.
"""
import unittest

import test_appearance_end_to_end as integration


class AppearanceEditorThemeTests(unittest.TestCase):
    setUp = integration.AppearanceEndToEndTests.setUp
    click = staticmethod(integration.AppearanceEndToEndTests.click)

    def set(self, key, value):
        if isinstance(value, (dict, list)):
            value = self.lua.table_from(value, recursive=True)
        result = self.mpl.SetAppearanceValue(key, value)
        self.assertTrue(result[0] if isinstance(result, tuple) else result)

    def assert_rgb(self, actual, expected):
        self.assertIsNotNone(actual)
        for index, component in enumerate(expected, 1):
            self.assertAlmostEqual(actual[index], component)

    def test_profile_scale_slider_keeps_editor_readable_and_cancel_restores(self):
        editor = self.mpl.OpenAppearanceSettings()
        editor.rows.scale.slider.scripts.OnValueChanged(editor.rows.scale.slider, 1.2)
        self.assertAlmostEqual(editor.GetScale(editor), 1)
        self.assertAlmostEqual(self.panel.GetScale(self.panel), 1.2)
        self.click(editor.cancel)
        editor = self.mpl.OpenAppearanceSettings()
        self.assertAlmostEqual(editor.GetScale(editor), 1)
        self.assertAlmostEqual(self.panel.GetScale(self.panel), 1)

    def test_editor_text_buttons_and_hover_follow_live_palette(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.set('buttonColor', [.13, .27, .42, 1])
        self.set('textColor', [.84, .73, .62, 1])
        self.set('buttonTextColor', [.56, .67, .78, 1])
        self.set('hoverColor', [.21, .32, .43, 1])
        self.assert_rgb(editor.save.backdropColor, [.13, .27, .42])
        self.assert_rgb(editor.searchLabel.textColor, [.84, .73, .62])
        self.assertIsNotNone(editor.save.caption)
        self.assert_rgb(editor.save.caption.textColor, [.56, .67, .78])
        editor.save.scripts.OnEnter(editor.save)
        self.assert_rgb(editor.save.backdropColor, [.21, .32, .43])
        editor.save.scripts.OnLeave(editor.save)
        self.assert_rgb(editor.save.backdropColor, [.13, .27, .42])
        self.assert_rgb(self.panel.searchButton.backdropColor, [.13, .27, .42])

    def test_opacity_colors_surfaces_without_fading_text_and_cancel_restores(self):
        editor = self.mpl.OpenAppearanceSettings()
        original = list(editor.appearanceBodyFill.fillColor.values())
        self.set('backgroundColor', [.12, .24, .36, .8])
        self.set('titleBackgroundColor', [.18, .28, .38, .6])
        editor.rows.surfaceOpacity.slider.scripts.OnValueChanged(editor.rows.surfaceOpacity.slider, .5)
        self.assert_rgb(editor.appearanceBodyFill.fillColor, [.12, .24, .36])
        self.assertAlmostEqual(editor.appearanceBodyFill.fillColor[4], .4)
        self.assert_rgb(editor.titleFill.fillColor, [.18, .28, .38])
        self.assertAlmostEqual(editor.titleFill.fillColor[4], .3)
        self.assertEqual(editor.backdropColor[4], 0)
        self.assertIn(editor.alpha, (None, 1))
        self.assertIn(editor.searchLabel.alpha, (None, 1))
        self.click(editor.cancel)
        editor = self.mpl.OpenAppearanceSettings()
        self.assertEqual(list(editor.appearanceBodyFill.fillColor.values()), original)

    def test_requested_scale_is_limited_to_screen_without_changing_theme_value(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent, 900, 600)
        self.set('scale', 1.5)
        scale = editor.GetScale(editor)
        self.assertLess(scale, 1.5)
        self.assertLessEqual(editor.GetWidth(editor) * scale, 900)
        self.assertLessEqual(editor.GetHeight(editor) * scale, 600)
        self.assertEqual(self.mpl.AppearanceValue('scale'), 1.5)

    def test_profile_font_settings_preserve_editor_size_and_edit_focus(self):
        editor = self.mpl.OpenAppearanceSettings()
        original = editor.searchLabel.fontSize
        field = editor.rows.fontSize.control
        field.SetText(field, '17')
        field.SetFocus(field)
        self.set('fontSize', 14)
        self.assertEqual(editor.searchLabel.fontSize, original)
        self.assertTrue(field.focused)
        self.assertEqual(field.text, '17')
        self.set('size_button', 17)
        self.assertEqual(editor.save.caption.fontSize, 14)
        self.assertEqual(self.panel.searchButton.caption.fontSize, 17)
        for _ in range(3):
            self.mpl.RefreshAppearanceEditor()
        self.assertEqual(editor.searchLabel.fontSize, original)
        self.assertEqual(editor.save.caption.fontSize, 14)

    def test_new_section_rows_and_dropdown_choices_receive_current_theme(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.set('buttonColor', [.13, .27, .42, 1])
        self.set('textColor', [.84, .73, .62, 1])
        self.click(editor.sectionButtons.fonts)
        control = editor.rows.thousandsSeparator.control
        self.assert_rgb(control.backdropColor, [.13, .27, .42])
        self.assert_rgb(editor.rows.thousandsSeparator.label.textColor, [.84, .73, .62])
        self.click(control)
        menu = editor.choices
        self.assertTrue(menu.shown)
        # Pick an unselected entry: the selected entry intentionally uses its
        # own highlight color.
        unselected = next(button for button in menu.buttons.values()
                          if button.shown and button.choice != menu.current)
        self.assert_rgb(unselected.backdropColor, [.13, .27, .42])
        self.set('buttonColor', [.23, .37, .52, 1])
        self.assert_rgb(unselected.backdropColor, [.23, .37, .52])

    def test_large_editor_fonts_keep_labels_controls_and_buttons_separate(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.set('fontSize', 24)
        row = editor.rows.fontSize
        with self.subTest(element='field label'):
            label_bottom = -row.label.points.TOPLEFT[2] + row.label.GetHeight(row.label)
            input_top = -row.control.points.TOPLEFT[2]
            self.assertLessEqual(label_bottom, input_top)
        with self.subTest(element='save caption'):
            self.assertLessEqual(editor.save.caption.GetHeight(editor.save.caption),
                                 editor.save.GetHeight(editor.save))
        self.click(editor.rows.gridMode.control)
        menu = editor.choices
        previous_bottom = 0
        for button in menu.buttons.values():
            if button.shown:
                with self.subTest(element='choice caption', choice=button.choice):
                    self.assertLessEqual(button.caption.GetHeight(button.caption),
                                         button.GetHeight(button))
                    top = -button.points.TOPLEFT[2]
                    self.assertLessEqual(previous_bottom, top)
                    previous_bottom = top + button.GetHeight(button)

    def test_large_role_fonts_keep_scroll_footer_and_screen_separate(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.set('size_secondary', 40)
        self.set('size_button', 40)
        with self.subTest(element='scroll and footer'):
            scroll_bottom = editor.GetHeight(editor) - editor.scroll.points.BOTTOMRIGHT[2]
            reset_top = -editor.resetSection.points.TOPLEFT[2]
            self.assertLessEqual(scroll_bottom, reset_top)
        with self.subTest(element='status and save'):
            status_bottom = -editor.status.points.TOPLEFT[2] + editor.status.GetHeight(editor.status)
            save_top = -editor.save.points.TOPLEFT[2]
            self.assertLessEqual(status_bottom, save_top)
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent, 900, 600)
        self.set('scale', 1.5)
        with self.subTest(element='screen fit after reflow'):
            self.assertLessEqual(editor.GetHeight(editor) * editor.GetScale(editor), 600)

    def test_large_fonts_keep_theme_profile_and_title_labels_clear(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.set('size_secondary', 40)
        self.set('size_title', 40)
        row = editor.extras.theme
        with self.subTest(element='theme label'):
            label_bottom = -row.label.points.TOPLEFT[2] + row.label.GetHeight(row.label)
            self.assertLessEqual(label_bottom, -row.control.points.TOPLEFT[2])
        with self.subTest(element='title band'):
            title_bottom = -editor.title.points.TOPLEFT[2] + editor.title.GetHeight(editor.title)
            band_bottom = -editor.titleFill.points.TOPLEFT[2] + editor.titleFill.GetHeight(editor.titleFill)
            self.assertLessEqual(title_bottom, band_bottom)
        with self.subTest(element='search label and input'):
            label_bottom = -editor.searchLabel.points.TOPLEFT[2] + editor.searchLabel.GetHeight(editor.searchLabel)
            self.assertLessEqual(label_bottom, -editor.search.points.TOPLEFT[2])
        with self.subTest(element='sidebar search and content'):
            input_right = editor.search.points.TOPLEFT[1] + editor.search.GetWidth(editor.search)
            self.assertLessEqual(input_right, editor.scroll.points.TOPLEFT[1])
            last_section = editor.sectionButtons.profiles
            last_bottom = -last_section.points.TOPLEFT[2] + last_section.GetHeight(last_section)
            self.assertLessEqual(last_bottom, -editor.searchLabel.points.TOPLEFT[2])
        self.click(editor.sectionButtons.profiles)
        row = editor.extras.profiles
        with self.subTest(element='profile name label'):
            label_bottom = -row.label.points.TOPLEFT[2] + row.label.GetHeight(row.label)
            self.assertLessEqual(label_bottom, -row.name.points.TOPLEFT[2])

    def test_transfer_dialog_uses_shared_theme_and_inherits_editor_scale_once(self):
        editor = self.mpl.OpenAppearanceSettings()
        self.set('scale', 1.2)
        self.set('buttonColor', [.13, .27, .42, 1])
        self.set('textColor', [.84, .73, .62, 1])
        self.mpl.ShowAppearanceTransfer(False, False)
        dialog = editor.transfer
        self.assertTrue(dialog.shown)
        self.assert_rgb(dialog.close.backdropColor, [.13, .27, .42])
        self.assert_rgb(dialog.description.textColor, [.84, .73, .62])
        self.assertEqual(dialog.GetScale(dialog), 1)
        self.assertAlmostEqual(editor.GetScale(editor), 1)


if __name__ == '__main__':
    unittest.main()
