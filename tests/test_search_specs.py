"""Search leader metadata reaches the current-specialization badge."""
import unittest
import test_group_visibility

ROOT=test_group_visibility.ROOT


class SearchSpecTests(unittest.TestCase):
    def setUp(self):
        test_group_visibility.GroupVisibilityTests.setUp(self)
        self.lua.execute('''
            leaderName="Frákkie-Draenor"
            C_LFGList.GetSearchResultInfo=function()
                return {leaderName=leaderName,activityIDs={1},numMembers=2}
            end
            searchMembers={
                {isLeader=false,classFilename="SHAMAN",specName="Исцеление",assignedRole="HEALER"},
                {isLeader=true,classFilename="MONK",specName="Танцующий с ветром",assignedRole="DAMAGER"},
            }
            C_LFGList.GetSearchResultPlayerInfo=function(_,index) return searchMembers[index] end
            GetSpecializationInfoByID=function(id)
                if id==269 then return id,"Танцующий с ветром",nil,608953 end
                if id==268 then return id,"Хмелевар",nil,608951 end
                if id==264 then return id,"Исцеление",nil,136052 end
            end
            owner={resultID=10}
            buttons={}
            root={CreateDivider=function() end,
                CreateButton=function(_,label,callback) buttons[#buttons+1]=callback end}
        ''')
        test_group_visibility.GroupVisibilityTests.install_hooks(self)

    def open_leader(self):
        self.lua.execute('buttons={}; Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root); buttons[1]()')

    def test_search_menu_uses_leader_spec_not_first_member_or_wcl_spec(self):
        self.open_leader()
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'Танцующий с ветром')
        self.assertTrue(self.mpl.panel.currentSpec.icon.shown)
        self.assertEqual(self.mpl.panel['class'],'MONK')
        self.assertEqual(self.mpl.roles[self.mpl.Key('Frákkie','Draenor')],'DAMAGER')
        self.assertEqual(self.mpl.panel.selectedSpec,'All specs')
        self.assertFalse(self.mpl.panel.inviteButton.shown)

    def update_listing(self):
        self.lua.execute('eventFrames[1].scripts.OnEvent(eventFrames[1],"LFG_LIST_SEARCH_RESULT_UPDATED",10)')

    def test_direct_leader_api_does_not_depend_on_member_order(self):
        self.lua.execute('''
            C_LFGList.GetSearchResultLeaderInfo=function() return searchMembers[2] end
            C_LFGList.GetSearchResultPlayerInfo=function() error("No roster scan needed") end
        ''')
        self.open_leader()
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'Танцующий с ветром')

    def test_late_listing_spec_updates_open_profile_and_preserves_metric(self):
        self.lua.execute('searchMembers[2].specName=nil')
        self.open_leader()
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'—')
        self.mpl.panel.viewMetric='hps'
        self.lua.execute('searchMembers[2].specName="Хмелевар"; searchMembers[2].assignedRole="TANK"')
        self.update_listing()
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'Хмелевар')
        self.assertTrue(self.mpl.panel.currentSpec.icon.shown)
        self.assertEqual(self.mpl.panel.viewMetric,'hps')

    def test_changed_leader_does_not_relabel_previously_opened_character(self):
        self.open_leader()
        self.lua.execute('leaderName="Replacement-Draenor"; searchMembers[2].specName="Хмелевар"')
        self.update_listing()
        self.assertEqual(self.mpl.panel.name,'Frákkie')
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'Танцующий с ветром')

    def test_missing_leader_and_secret_spec_remain_unknown(self):
        for setup in ('searchMembers[2].isLeader=false',
                      'searchMembers[2].specName={secret=true}',
                      'C_LFGList.GetSearchResultPlayerInfo=nil'):
            with self.subTest(setup=setup):
                self.setUp()
                self.lua.execute(setup)
                self.open_leader()
                self.assertEqual(self.mpl.panel.currentSpec.name.text,'—')
                self.assertFalse(self.mpl.panel.currentSpec.icon.shown)

    def test_localized_spec_name_is_matched_within_the_leaders_class(self):
        self.lua.execute('''
            searchMembers[2]={isLeader=true,classFilename="PRIEST",specName="Holy",assignedRole="HEALER"}
            GetSpecializationInfoByID=function(id)
                if id==65 or id==257 then return id,"Holy",nil,id*10 end
            end
        ''')
        self.open_leader()
        self.assertEqual(self.mpl.panel['class'],'PRIEST')
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'Holy')
        self.assertEqual(self.mpl.specs[self.mpl.Key('Frákkie','Draenor')][3],'PRIEST')

    def test_search_tooltip_records_the_same_leader_metadata(self):
        self.lua.execute('hooks.LFGListSearchEntry_OnEnter(owner)')
        self.mpl.ShowProfile('Frákkie','Draenor')
        self.assertEqual(self.mpl.panel.currentSpec.name.text,'Танцующий с ветром')


if __name__=='__main__':
    unittest.main()
