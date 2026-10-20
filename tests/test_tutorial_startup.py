"""Login stays quiet; manual guide requests still work through combat."""
import unittest
import test_screenshot_transport as transport_tests
from test_addon import ROOT


class TutorialStartupTests(unittest.TestCase):
    def setUp(self):
        transport_tests.ReplyTests.setUp(self)
        self.lua.execute('''
            eventFrames={}
            local original=CreateFrame
            function CreateFrame(...)
                local f=original(...); eventFrames[#eventFrames+1]=f; return f
            end
            local MPL=...
            MPL.RequestTutorial=function() requested=(requested or 0)+1 end
            MPL.TryPendingTutorial=function() retried=(retried or 0)+1 end
            MPL.ShowTutorial=function() manuallyOpened=(manuallyOpened or 0)+1 end
        ''',self.mpl)
        self.lua.execute('return assert(loadstring(...))',
                         (ROOT/'Integration.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)

    def fire(self,event):
        frame=self.lua.globals().eventFrames[1]
        frame.scripts.OnEvent(frame,event)

    def test_login_never_requests_or_opens_tutorial(self):
        self.fire('PLAYER_LOGIN')
        self.assertIsNone(self.lua.globals().requested)
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
        self.assertIsNone(self.lua.globals().requested)
        self.assertIsNone(self.lua.globals().manuallyOpened)

    def test_leaving_combat_retries_deferred_tutorial(self):
        self.fire('PLAYER_REGEN_ENABLED')
        self.assertEqual(self.lua.globals().retried,1)
        self.fire('GROUP_ROSTER_UPDATE')
        self.assertEqual(self.lua.globals().retried,1)

    def test_slash_command_reopens_tutorial(self):
        self.lua.globals().SlashCmdList.MPLUSLOGS('tutorial')
        self.assertEqual(self.lua.globals().manuallyOpened,1)

    def test_slash_command_previews_companion_intro(self):
        self.lua.globals().SlashCmdList.MPLUSLOGS('testintro')
        self.assertTrue(self.mpl.downloadWindow.companionHint.shown)
        self.assertTrue(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertIsNone(self.lua.globals().manuallyOpened)

    def test_toc_loads_tutorial_after_dialog_helper_before_startup(self):
        files=(ROOT/'MPlusLogs.toc').read_text(encoding='utf-8').splitlines()
        self.assertLess(files.index('UI.lua'),files.index('TutorialSteps.lua'))
        self.assertLess(files.index('TutorialSteps.lua'),files.index('Tutorial.lua'))
        for path in (ROOT/'Locales/Tutorial').glob('*.lua'):
            name=path.relative_to(ROOT).as_posix()
            self.assertLess(files.index('TutorialSteps.lua'),files.index(name))
            self.assertLess(files.index(name),files.index('Tutorial.lua'))
        self.assertLess(files.index('Tutorial.lua'),files.index('Integration.lua'))


if __name__=='__main__': unittest.main()
