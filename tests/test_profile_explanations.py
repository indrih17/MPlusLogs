"""Visible profile explanations respond to their appearance switch.

Runs the production renderer with frame geometry mocks, not game fonts.
"""
import unittest
import math

import test_profile_appearance as profiles


class ProfileExplanationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = profiles.ProfileAppearanceTests(methodName='runTest')
        self.fixture.setUp()
        self.lua, self.mpl, self.panel = self.fixture.lua, self.fixture.mpl, self.fixture.panel

    def test_show_notes_changes_visible_explanation_and_releases_its_space(self):
        self.fixture.set('showNotes', True)
        self.assertTrue(self.panel.note.text.strip())
        self.assertTrue(self.panel.note.shown)
        with_notes = self.panel.height
        table_position = tuple(self.panel.headerViewport.points.TOPLEFT.values())
        self.fixture.set('showNotes', False)
        self.assertFalse(self.panel.note.shown)
        self.assertLess(self.panel.height, with_notes)
        self.assertEqual(tuple(self.panel.headerViewport.points.TOPLEFT.values()), table_position)
        self.fixture.set('showNotes', True)
        self.assertTrue(self.panel.note.shown)
        self.assertEqual(self.panel.height, with_notes)

    def test_explanations_survive_metric_and_layout_switches_but_not_missing_profile(self):
        for header in ('modern', 'original'):
            self.fixture.set('headerLayout', header)
            for compact in (False, True):
                self.fixture.set('compactSummary', compact)
                for metric in ('dps', 'hps'):
                    with self.subTest(header=header, compact=compact, metric=metric):
                        self.panel.viewMetric = metric
                        self.mpl.RenderProfileStats(self.panel)
                        self.assertTrue(self.panel.note.text.strip())
                        self.assertTrue(self.panel.note.shown)
        self.panel.profile = None
        self.mpl.RenderProfileStats(self.panel)
        self.assertFalse(self.panel.note.shown)
        self.assertEqual(self.panel.note.text, '')

    def test_large_explanation_wraps_and_stays_clear_of_action_buttons(self):
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,700,1080)
        self.fixture.set('size_secondary', 40)
        note = self.panel.note
        self.assertTrue(note.shown)
        self.assertTrue(note.wordWrap)
        line = max(20, note.fontSize + 4)
        measured = note.GetUnboundedStringWidth(note)
        self.assertGreaterEqual(note.height, math.ceil(measured / note.width) * line)
        note_bottom = -note.points.TOPLEFT[2] + note.height
        action_top = self.panel.height - self.panel.wclButton.points.BOTTOMLEFT[2] - self.panel.wclButton.height
        self.assertGreaterEqual(action_top, note_bottom + 8)
        geometry = (self.panel.height, note.width, note.height, tuple(note.points.TOPLEFT.values()))
        self.mpl.RenderProfileStats(self.panel)
        self.assertEqual((self.panel.height, note.width, note.height, tuple(note.points.TOPLEFT.values())), geometry)

    def test_hiding_summary_does_not_hide_enabled_explanations_or_runtime_guidance(self):
        self.fixture.set('showSummary', False)
        self.assertTrue(self.panel.note.shown)
        self.panel.footer.SetText(self.panel.footer, 'Runtime guidance')
        self.fixture.set('showNotes', False)
        self.assertFalse(self.panel.note.shown)
        self.assertTrue(self.panel.footer.shown)
        self.assertEqual(self.panel.footer.text, 'Runtime guidance')


if __name__ == '__main__':
    unittest.main()
