"""Help is offered where it is useful, without interrupting the live exchange."""
import unittest

import test_tutorial as tutorial_fixture


class TutorialHelpTests(unittest.TestCase):
    setUp = tutorial_fixture.TutorialTests.setUp
    load = tutorial_fixture.TutorialTests.load
    click = tutorial_fixture.TutorialTests.click
    same = tutorial_fixture.TutorialTests.same
    raw = tutorial_fixture.TutorialTests.raw

    def flush(self):
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')

    def exchange(self, waiting=False, first_use=False):
        self.lua.globals().MPlusLogsDB.companionIntroDismissed = None if first_use else True
        self.mpl.ShowDownload('Alice', 'Area 52', None)
        frame = self.mpl.downloadWindow
        if waiting:
            self.lua.execute('controlHeld=true')
            frame.edit.scripts.OnKeyDown(frame.edit, 'C')
            self.assertEqual(frame.phase, 'waiting')
        return frame

    def snapshot(self, frame):
        return (self.mpl.pendingReply.id, frame.request, frame.phase, frame.revision,
                frame.edit.text)

    def close_guide(self):
        self.click(self.mpl.tutorialWindow.later)

    def test_hiding_help_preserves_active_exchange_and_can_be_reversed(self):
        self.mpl.ShowProfile('Alice', 'Area 52', None, True)
        frame = self.exchange(first_use=True)
        before = self.snapshot(frame)
        self.assertTrue(frame.companionHint.shown)
        self.assertTrue(self.mpl.SetOption('hideTutorial', True))
        self.assertFalse(self.mpl.panel.tutorialButton.shown)
        self.assertFalse(frame.tutorialButton.shown)
        self.assertFalse(frame.companionHint.shown)
        self.assertEqual(self.snapshot(frame), before)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertFalse(self.mpl.CompanionHasReplied())
        self.mpl.SetOption('hideTutorial', False)
        self.assertTrue(self.mpl.panel.tutorialButton.shown)
        self.assertTrue(frame.tutorialButton.shown)
        self.assertTrue(frame.companionHint.shown)
        self.assertEqual(self.snapshot(frame), before)

    def test_saved_preference_hides_help_in_new_windows_but_settings_link_still_opens_guide(self):
        self.mpl.SetOption('hideTutorial', True)
        self.mpl.ShowProfile('Alice', 'Area 52', None, True)
        frame = self.exchange(first_use=True)
        self.assertFalse(self.mpl.panel.tutorialButton.shown)
        self.assertFalse(frame.tutorialButton.shown)
        self.assertFalse(frame.companionHint.shown)
        self.lua.execute('''
            tutorialLink={Button=CreateFrame("Button")}
            MPlusLogsTutorialLinkMixin.Init(tutorialLink)
        ''')
        self.click(self.lua.globals().tutorialLink.Button)
        self.assertTrue(self.mpl.tutorialWindow.shown)
        self.assertTrue(self.mpl.GetOption('hideTutorial'))

    def test_empty_profile_offers_setup_help_only_on_click(self):
        self.mpl.ShowProfile('Alice', 'Area 52', None, True)
        profile = self.mpl.panel
        self.assertTrue(profile.tutorialButton.shown)
        self.assertIsNone(self.mpl.tutorialWindow)
        self.click(profile.tutorialButton)
        self.assertTrue(profile.shown)
        self.assertEqual(self.mpl.tutorialWindow.step, 1)

    def test_loaded_profile_opens_relevant_chapter_and_demo_has_no_help_link(self):
        self.mpl.Import(self.body)
        self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        profile = self.mpl.panel
        self.assertIsNotNone(profile.profile)
        self.click(profile.tutorialButton)
        self.assertEqual(self.mpl.tutorialWindow.step, 5)
        demo = self.mpl.CreateTutorialProfileFrame()
        self.assertIsNone(self.raw(demo, 'tutorialButton'))

    def test_empty_profile_with_companion_history_opens_loading_help(self):
        self.lua.globals().MPlusLogsDB.companionReplySeen=True
        self.mpl.ShowProfile('Alice', 'Area 52', None, True)
        self.click(self.mpl.panel.tutorialButton)
        self.assertEqual(self.mpl.tutorialWindow.step,3)

    def test_profile_help_rechecks_current_profile_when_clicked(self):
        self.mpl.Import(self.body)
        self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        profile = self.mpl.panel
        self.mpl.ShowProfile('Alice', 'Area 52', None, True)
        self.assertTrue(self.same(profile, self.mpl.panel))
        self.click(profile.tutorialButton)
        self.assertEqual(self.mpl.tutorialWindow.step, 3)

    def test_download_help_uses_current_companion_setup_state(self):
        frame = self.exchange(first_use=True)
        self.click(frame.tutorialButton)
        self.assertEqual(self.mpl.tutorialWindow.step, 1)
        self.close_guide()
        self.lua.globals().MPlusLogsDB.companionIntroDismissed = True
        self.click(frame.tutorialButton)
        self.assertEqual(self.mpl.tutorialWindow.step, 3)

    def test_help_preserves_request_and_focus_in_both_exchange_phases(self):
        for waiting in (False, True):
            with self.subTest(waiting=waiting):
                self.setUp()
                frame = self.exchange(waiting=waiting)
                before = self.snapshot(frame)
                self.click(frame.tutorialButton)
                self.assertTrue(frame.shown)
                self.assertFalse(frame.edit.focused)
                self.assertEqual(self.snapshot(frame), before)
                # The original ShowDownload timer and direct refocus attempts
                # must not steal keyboard input from the guide.
                frame.focusInput()
                self.flush()
                self.assertFalse(frame.edit.focused)
                self.assertEqual(self.snapshot(frame), before)
                self.close_guide()
                self.assertTrue(frame.edit.focused)
                self.assertEqual(self.snapshot(frame), before)

    def test_guide_close_does_not_refocus_replaced_or_hidden_request(self):
        for change in ('replace', 'hide'):
            with self.subTest(change=change):
                self.setUp()
                frame = self.exchange()
                self.click(frame.tutorialButton)
                if change == 'replace':
                    self.mpl.ShowDownload('Bob', 'Area 52', None)
                    self.flush()
                    self.assertEqual(frame.name, 'Bob')
                else:
                    frame.Hide(frame)
                self.close_guide()
                self.assertFalse(frame.edit.focused)

    def test_suspended_guide_also_blocks_download_focus(self):
        frame = self.exchange(first_use=True)
        self.click(frame.tutorialButton)
        self.click(self.mpl.tutorialWindow.action)
        self.assertTrue(self.mpl.copy.shown)
        self.assertFalse(self.mpl.tutorialWindow.shown)
        frame.focusInput()
        self.flush()
        self.assertFalse(frame.edit.focused)

    def test_help_is_available_beside_disabled_batch_button_and_tracks_visibility(self):
        self.load('Integration.lua')
        self.lua.execute('''
            LFGListFrame={ApplicationViewer=CreateFrame("Frame")}
            local MPL=...
            groupHelpVisible=true
            MPL.GroupLogsEnabled=function() return groupHelpVisible end
            MPL.CollectApplicants=function() return {} end
            MPL.InstallApplicantLogColumn=function() end
            MPL.RefreshApplicantLogs=function() end
        ''', self.mpl)
        self.mpl.InstallBatchButton()
        self.assertFalse(self.mpl.batchButton.enabled)
        help_button = self.mpl.batchTutorialButton
        self.assertTrue(help_button.shown)
        self.assertEqual(help_button.text, '?')
        self.assertIsNone(self.mpl.tutorialWindow)
        self.click(help_button)
        self.assertEqual(self.mpl.tutorialWindow.step, 2)
        self.lua.globals().groupHelpVisible = False
        self.mpl.UpdateBatchButton()
        self.assertFalse(self.mpl.batchButton.shown)
        self.assertFalse(help_button.shown)
        self.lua.globals().groupHelpVisible = True
        self.mpl.UpdateBatchButton()
        self.assertTrue(help_button.shown)
        self.mpl.SetOption('hideTutorial', True)
        self.assertFalse(help_button.shown)
        self.assertTrue(self.mpl.batchButton.shown)
        self.mpl.UpdateBatchButton()
        self.assertFalse(help_button.shown)
        self.lua.globals().groupHelpVisible = False
        self.mpl.SetOption('hideTutorial', False)
        self.assertFalse(help_button.shown)
        self.lua.globals().groupHelpVisible = True
        self.mpl.UpdateBatchButton()
        self.assertTrue(help_button.shown)

    def test_profile_and_download_help_labels_follow_all_addon_locales(self):
        for locale in tutorial_fixture.LOCALES:
            with self.subTest(locale=locale):
                self.setUp()
                self.mpl.locale = locale
                self.mpl.ShowProfile('Alice', 'Area 52', None, True)
                frame = self.exchange()
                caption = self.mpl.GetTutorialCopy(locale).openGuide
                self.assertEqual(self.mpl.panel.tutorialButton.text, caption)
                self.assertEqual(frame.tutorialButton.text, '?')
                frame.tutorialButton.scripts.OnEnter()
                tooltip = self.lua.globals().GameTooltip
                self.assertEqual(tooltip.lines[len(tooltip.lines)][1], caption)


if __name__ == '__main__':
    unittest.main()
