"""Sibling dialog subtrees must never interleave at the same drawing levels."""
import unittest
from unittest.mock import patch
import test_screenshot_transport as transport_tests


class WindowLayerTests(unittest.TestCase):
    def setUp(self):
        # Model the WoW APIs needed for draw ordering, including inherited child levels.
        mock=transport_tests.MOCK.replace(
            'function methods:Show() self.shown = true end',
            'function methods:Show() local was=self.shown; self.shown=true; if not was and self.scripts.OnShow then self.scripts.OnShow(self) end end')
        mock=mock.replace('function methods:GetFrameLevel() return 1 end', '''
            function methods:GetFrameLevel() local p=rawget(self,"parent"); return rawget(self,"level") or (p and p:GetFrameLevel()+1 or 0) end
            function methods:SetFrameLevel(value) self.level=value end
            function methods:GetFrameStrata() local p=rawget(self,"parent"); return rawget(self,"strata") or (p and p:GetFrameStrata() or "MEDIUM") end
            function methods:SetFrameStrata(value) self.strata=value end
            function methods:GetChildren() return unpack(rawget(self,"children") or {}) end
            function methods:SetBackdropColor(r,g,b,a) self.backdropAlpha=a end
        ''')
        mock=mock.replace('local f = newFrame(); f.parent = parent', '''local f = newFrame(); f.parent = parent
            if parent then parent.children=rawget(parent,"children") or {}; table.insert(parent.children,f) end''')
        with patch.object(transport_tests,'MOCK',mock):
            transport_tests.ReplyTests.setUp(self)
        self.lua.execute('''
            function highestLevel(frame)
                local highest=frame:GetFrameLevel()
                for _,child in ipairs({frame:GetChildren()}) do highest=math.max(highest,highestLevel(child)) end
                return highest
            end
        ''')

    def highest(self,frame):
        return self.lua.globals().highestLevel(frame)

    def test_copy_dialog_covers_download_controls(self):
        self.mpl.ShowDownload('Alice','Area 52',None)
        self.mpl.ShowCompanionDownload()
        self.assertGreater(self.mpl.copy.GetFrameLevel(self.mpl.copy),self.highest(self.mpl.downloadWindow))
        self.assertEqual(self.mpl.copy.backdropAlpha,1)

    def test_every_popup_is_above_all_previous_window_descendants(self):
        self.mpl.Import(self.body)
        self.mpl.ShowProfile('Киндрих','Гордунни',None,True)
        previous=[self.mpl.panel]
        cases=[
            (lambda:self.mpl.ShowDownload('Alice','Area 52',None),'downloadWindow'),
            (self.mpl.ShowCompanionDownload,'copy'),
            (self.mpl.ShowCompanionUpdates,'companionUpdateWindow'),
            (lambda:self.mpl.ShowCompanionIntro(None),'companionIntroWindow'),
            (lambda:self.mpl.ShowStaleNotice('Киндрих','Гордунни',self.mpl.panel.profile,'16.10.2026'),'staleWindow'),
            (self.mpl.ShowRequests,'requestsWindow'),
            (self.mpl.ShowImport,'importWindow'),
            (lambda:self.mpl.ShowBatchResults(self.lua.table(),self.lua.table(),self.lua.table(),0,True),'batchResultsWindow'),
        ]
        for open_window,key in cases:
            with self.subTest(window=key):
                open_window()
                window=self.mpl[key]
                for below in previous:
                    if below.shown:
                        self.assertGreater(window.GetFrameLevel(window),self.highest(below))
                self.assertEqual(window.backdropAlpha,1)
                previous.append(window)

    def test_focus_promotes_dialog_but_main_profile_stays_below_popups(self):
        self.mpl.Import(self.body)
        self.mpl.ShowProfile('Киндрих','Гордунни',None,True)
        self.mpl.ShowDownload('Alice','Area 52',None)
        self.mpl.ShowCompanionDownload()
        download=self.mpl.downloadWindow
        download.scripts.OnMouseDown(download)
        self.assertGreater(download.GetFrameLevel(download),self.highest(self.mpl.copy))
        self.mpl.panel.scripts.OnMouseDown(self.mpl.panel)
        self.assertGreater(download.GetFrameLevel(download),self.highest(self.mpl.panel))
        self.assertGreater(self.mpl.copy.GetFrameLevel(self.mpl.copy),self.highest(self.mpl.panel))

    def test_reopening_and_focusing_reorders_without_level_growth(self):
        self.mpl.ShowDownload('Alice','Area 52',None)
        self.mpl.ShowCompanionDownload()
        for _ in range(30):
            self.mpl.downloadWindow.Hide(self.mpl.downloadWindow)
            self.mpl.ShowDownload('Alice','Area 52',None)
            self.assertGreater(self.mpl.downloadWindow.GetFrameLevel(self.mpl.downloadWindow),self.highest(self.mpl.copy))
            self.mpl.copy.Hide(self.mpl.copy)
            self.mpl.ShowCompanionDownload()
        self.assertLess(self.highest(self.mpl.copy),200)


if __name__=='__main__':unittest.main()
