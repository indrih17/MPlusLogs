"""Tutorial profiles use the production layout without touching live state."""
import unittest
import test_screenshot_transport as transport_fixture


class TutorialProfileTests(unittest.TestCase):
    def setUp(self):
        transport_fixture.ReplyTests.setUp(self)
        self.lua.execute('return assert(loadstring(...))',
            (transport_fixture.ROOT/'TutorialProfile.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)

    def test_actual_profile_table_metrics_and_spec_switches(self):
        frame=self.mpl.ShowTutorialProfile()
        self.assertEqual(len(frame.headings),9)
        self.assertEqual(len(frame.rows),8)
        self.assertEqual(frame.selectedSpec,'Guardian')
        self.assertEqual(frame.rows[1].cells[1].text,"Kings' Rest")
        self.assertIn('94',frame.rows[1].cells[8].text)
        self.assertIn('|c',frame.rows[1].cells[8].text)
        dps=frame.rows[1].cells[7].text
        frame.metricTabs.hps.scripts.OnClick()
        self.assertEqual(frame.viewMetric,'hps')
        self.assertEqual(frame.metricHeading.text,'Лучший HPS')
        self.assertNotEqual(frame.rows[1].cells[7].text,dps)
        frame.specButton.scripts.OnClick()
        self.assertEqual(frame.selectedSpec,'Restoration')
        self.assertIn('951',frame.rows[1].cells[7].text)

    def test_demo_interactions_preserve_live_profile_request_and_saved_state(self):
        self.lua.execute('''
            local MPL=...
            MPL.panel={sentinel=true}
            livePanel=MPL.panel
            savedProfiles=MPlusLogsDB.profiles
            MPlusLogsDB.options={percentile="best"}; savedOptions=MPlusLogsDB.options
        ''',self.mpl)
        self.mpl.SendRequest('Alice','Area 52','dps','')
        self.lua.globals().livePending=self.mpl.pendingReply
        self.lua.execute('''
            local MPL=...
            local function forbidden() error("Tutorial called production action") end
            MPL.SendRequest=forbidden; MPL.SendBatchRequest=forbidden
            MPL.ShowDownload=forbidden; MPL.CopyURL=forbidden
            MPL.ShowProfile=forbidden; MPL.SelectSpec=forbidden
        ''',self.mpl)
        frame=self.mpl.ShowTutorialProfile()
        frame.metricTabs.hps.scripts.OnClick()
        frame.specButton.scripts.OnClick()
        frame.loadButton.scripts.OnClick()
        self.assertIsNone(frame.loadButton.scripts.OnUpdate)
        self.assertIsNone(frame.wclButton.scripts.OnClick)
        self.assertIsNone(frame.lookupButton.scripts.OnClick)
        self.assertIsNone(frame.lookup.scripts.OnEnterPressed)
        for row in frame.rows.values():
            self.assertIsNone(row.scripts.OnMouseUp)
            self.assertIsNone(row.scoreSpecIcon.scripts.OnMouseUp)
        self.assertTrue(self.lua.eval('''function(MPL)
            return MPL.panel==livePanel and MPL.pendingReply==livePending
                and MPlusLogsDB.profiles==savedProfiles
                and MPlusLogsDB.options==savedOptions
                and not MPlusLogsDB.companionReplySeen
        end''')(self.mpl))

    def test_combat_does_not_create_profile(self):
        self.lua.execute('combat=true')
        self.assertIsNone(self.mpl.ShowTutorialProfile())
        self.assertIsNone(self.mpl.tutorialProfile)

    def test_actual_spec_menu_selects_only_the_local_sample(self):
        self.lua.execute('''
            choices={}
            MenuUtil={CreateContextMenu=function(owner,build)
                local root={CreateRadio=function(_,label,selected,choose)
                    choices[#choices+1]={label=label,selected=selected,choose=choose}
                end}
                build(owner,root)
            end}
        ''')
        frame=self.mpl.ShowTutorialProfile()
        frame.specButton.scripts.OnClick()
        choices=self.lua.globals().choices
        self.assertEqual(len(choices),2)
        self.assertTrue(choices[1].selected())
        choices[2].choose()
        self.assertEqual(frame.selectedSpec,'Restoration')
        self.assertTrue(choices[2].selected())
        self.assertIsNone(self.lua.globals().MPlusLogsDB.selectedSpecs)


if __name__=='__main__': unittest.main()
