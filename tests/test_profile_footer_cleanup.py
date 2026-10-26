"""Optional explanations and live guidance reserve only their visible space."""
import unittest

import test_profile_appearance as appearance


class ProfileFooterCleanupTests(unittest.TestCase):
    setUp = appearance.ProfileAppearanceTests.setUp
    set = appearance.ProfileAppearanceTests.set

    def test_loaded_profile_keeps_source_and_optional_explanation(self):
        panel=self.panel
        self.assertTrue(panel.note.text)
        self.assertEqual(panel.footer.text,'')
        self.assertTrue(panel.note.shown)
        self.assertFalse(panel.footer.shown)
        self.assertTrue(panel.source.shown)
        self.assertIn(panel.profile.source,panel.source.text)

    def test_hidden_note_and_empty_footer_do_not_reserve_rows(self):
        panel=self.panel
        with_notes=panel.height
        self.set('showNotes',False)
        original=panel.height
        self.assertLess(original,with_notes)
        self.set('showNotes',True)
        self.assertEqual(panel.height,with_notes)
        self.set('showNotes',False)
        panel.footer.SetText(panel.footer,'Runtime failure details')
        self.mpl.RenderProfileStats(panel)
        self.assertTrue(panel.footer.shown)
        self.assertEqual(panel.height,original+20)
        panel.footer.SetText(panel.footer,' \n\t ')
        self.mpl.RenderProfileStats(panel)
        self.assertFalse(panel.footer.shown)
        self.assertEqual(panel.height,original)

    def test_season_and_source_share_a_row_at_opposite_edges(self):
        panel=self.panel
        season,source=panel.context,panel.source
        self.assertEqual(season.points.TOPLEFT[2],source.points.TOPLEFT[2])
        self.assertEqual(season.points.TOPLEFT[1],20)
        self.assertEqual(source.justifyH,'RIGHT')
        self.assertAlmostEqual(source.points.TOPLEFT[1]+source.width,20+panel.viewportWidth)
        self.assertLessEqual(season.points.TOPLEFT[1]+season.width+20,source.points.TOPLEFT[1])

    def test_footer_wraps_on_narrow_screen_and_restores_single_row(self):
        panel=self.panel
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,540,1080)
        self.mpl.RenderProfileStats(panel)
        self.assertLess(panel.context.points.TOPLEFT[2]*-1,panel.source.points.TOPLEFT[2]*-1)
        self.assertGreaterEqual(-panel.source.points.TOPLEFT[2],-panel.context.points.TOPLEFT[2]+panel.context.height)
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,1920,1080)
        self.mpl.RenderProfileStats(panel)
        self.assertEqual(panel.context.points.TOPLEFT[2],panel.source.points.TOPLEFT[2])
        original=panel.height
        self.set('showSource',False)
        self.assertEqual(panel.height,original)
        self.set('showSource',True)
        self.assertEqual(panel.height,original)

    def test_runtime_error_remains_visible_when_notes_and_source_are_disabled(self):
        self.set('showNotes',False)
        self.set('showSource',False)
        panel=self.panel
        original=panel.height
        self.mpl.SetProfileFooter(panel,'Could not refresh this profile')
        self.assertTrue(panel.footer.shown)
        self.assertFalse(panel.note.shown)
        self.assertFalse(panel.source.shown)
        self.assertGreater(panel.height,original)

    def test_missing_metric_guidance_shows_and_returns_to_empty_footer(self):
        panel=self.panel
        panel.profile.secondaryPending=True
        panel.profile.metric='dps'
        # WoW FontStrings return nil for an empty string.
        self.lua.execute('''
            local footer=...
            footer.GetText=function(self) return self.text~="" and self.text or nil end
        ''',panel.footer)
        original=panel.height
        panel.metricTabs.hps.scripts.OnClick(panel.metricTabs.hps)
        self.assertEqual(panel.footer.text,self.mpl.L['Healing data loads on request. Click Load HPS.'])
        self.assertTrue(panel.footer.shown)
        self.assertGreater(panel.height,original)
        panel.metricTabs.dps.scripts.OnClick(panel.metricTabs.dps)
        self.assertEqual(panel.footer.text,'')
        self.assertFalse(panel.footer.shown)
        self.assertEqual(panel.height,original)

    def test_cooldown_notice_shows_immediately_and_releases_space_when_expired(self):
        panel=self.panel
        original=panel.height
        self.lua.execute('''
            local MPL=...
            MPL.ProfileNeedsDisplayRefresh=function() return false end
            MPL.UpdateProfileLoadButton=function() return true,61 end
        ''',self.mpl)
        panel.loadButton.scripts.OnClick(panel.loadButton)
        self.assertTrue(panel.footer.shown)
        self.assertTrue(panel.cooldownNotice)
        self.assertGreater(panel.height,original)
        self.lua.execute('local MPL=...; MPL.UpdateProfileLoadButton=function() return false,0 end',self.mpl)
        panel.loadButton.scripts.OnUpdate(panel.loadButton,1)
        self.assertFalse(panel.cooldownNotice)
        self.assertEqual(panel.footer.text,'')
        self.assertFalse(panel.footer.shown)
        self.assertEqual(panel.height,original)

    def test_realm_inference_notice_has_no_leading_empty_line(self):
        self.panel.profile.realmInferred=True
        self.show_profile('Киндрих','Гордунни',None,True)
        self.assertEqual(self.panel.footer.text,self.mpl.L['Match based on name and class; realm not confirmed in game.'])
        self.assertTrue(self.panel.footer.shown)

    def test_multiline_runtime_footer_has_enough_height(self):
        panel=self.panel
        original=panel.height
        self.lua.execute('''
            local footer=...
            footer.GetStringHeight=function(self) return self.text~="" and 54 or 0 end
        ''',panel.footer)
        panel.footer.SetText(panel.footer,'Failure details\nNext action\nRetry information')
        self.mpl.RenderProfileStats(panel)
        self.assertTrue(panel.footer.shown)
        self.assertGreaterEqual(panel.footer.height,54)
        self.assertGreaterEqual(panel.height-original,54)

    def test_search_rescan_upgrade_notice_reveals_an_empty_footer(self):
        panel=self.panel
        original=panel.height
        self.lua.execute('return assert(loadstring(...))',
                         (appearance.ROOT/'SearchGroup.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.lua.execute('local MPL=...; MPL.CompanionSupports=function() return false end',self.mpl)
        self.mpl.ShowSearchGroupLogs(123,True)
        self.assertEqual(panel.footer.text,self.mpl.L['Update Companion to search realms again.'])
        self.assertTrue(panel.footer.shown)
        self.assertGreater(panel.height,original)


if __name__=='__main__':
    unittest.main()
