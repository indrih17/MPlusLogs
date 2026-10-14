"""Independent group filters across settings, applicant UI and search hooks."""
import unittest

import test_batch

ROOT=test_batch.ROOT


class GroupVisibilityTests(unittest.TestCase):
    options=("showInRaids","showInPvp","showInOtherGroups")
    expected={1:"mythicPlus",2:"showInRaids",3:"showInRaids",
              4:"showInPvp",5:"showInPvp",6:"showInOtherGroups",
              7:"showInOtherGroups",8:"showInOtherGroups",9:"showInOtherGroups",10:"showInPvp"}

    def setUp(self):
        test_batch.BatchTests.setUp(self)
        self.lua.execute('''
            activities={
                [1]={categoryID=2,isMythicPlusActivity=true},
                [2]={categoryID=3,difficultyID=15,isCurrentRaidActivity=true},
                [3]={categoryID=3,difficultyID=9,isCurrentRaidActivity=false},
                [4]={categoryID=4,isPvpActivity=true},
                [5]={categoryID=8},
                [6]={categoryID=6},
                [7]={categoryID=3,difficultyID=0},
                [8]={categoryID=2,isMythicPlusActivity=false},
                [9]={categoryID=121},
                [10]={categoryID=6,isRatedPvpActivity=true},
            }
            listingActivity=1; searchActivity=1
            C_LFGList.GetActivityInfoTable=function(id) return activities[id] end
            C_LFGList.GetActiveEntryInfo=function() return {activityIDs={listingActivity}} end
            C_LFGList.GetSearchResultInfo=function() return {leaderName="Киндрих-Гордунни",activityIDs={searchActivity}} end
        ''')
        self.lua.execute('return assert(loadstring(...))',(ROOT/'Settings.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)

    def choose(self,*enabled):
        for key in self.options:
            self.mpl.SetOption(key,key in enabled)

    def test_only_mythic_plus_is_enabled_by_default(self):
        for activity,key in self.expected.items():
            with self.subTest(activity=activity):
                self.assertEqual(self.mpl.GroupLogsEnabled(self.lua.table_from([activity])),key=="mythicPlus")
        self.lua.execute('MPlusLogsDB.options={showInMythicPlus=false}')
        self.assertTrue(self.mpl.GroupLogsEnabled(self.lua.table_from([1])))
        self.assertFalse(self.mpl.SetOption('showInMythicPlus',False))
        for key in self.options:
            self.assertFalse(self.mpl.GetOption(key))

    def test_each_category_can_be_enabled_alone_or_combined(self):
        for enabled in [(),*( (key,) for key in self.options),("showInRaids","showInOtherGroups")]:
            self.choose(*enabled)
            for activity,key in self.expected.items():
                with self.subTest(enabled=enabled,activity=activity):
                    self.assertEqual(self.mpl.GroupLogsEnabled(self.lua.table_from([activity])),key=="mythicPlus" or key in enabled)
        saved=self.lua.globals().MPlusLogsDB.options
        self.assertIsNone(saved.showInMythicPlus)
        self.assertTrue(saved.showInOtherGroups)
        self.assertTrue(saved.showInRaids)
        self.assertFalse(saved.showInPvp)

    def test_raid_settings_refresh_button_and_column_without_rating_header(self):
        self.mpl.InstallBatchButton()
        viewer=self.lua.globals().LFGListFrame.ApplicationViewer
        self.lua.globals().listingActivity=2
        viewer.RatingColumnHeader.Hide(viewer.RatingColumnHeader)
        self.mpl.UpdateBatchButton()
        self.assertFalse(self.mpl.batchButton.shown)
        self.assertFalse(self.mpl.logColumn.shown)
        self.assertEqual(self.lua.globals().PVEFrame.width,563)
        self.choose('showInRaids')
        self.assertTrue(self.mpl.batchButton.shown)
        self.assertTrue(self.mpl.batchButton.enabled)
        self.assertTrue(self.mpl.logColumn.shown)
        cell=self.mpl.applicantLogCells[self.lua.globals().testRows[1].Members[1]]
        self.assertTrue(cell.shown)
        self.assertEqual(cell.points['LEFT'][3],226)
        self.assertTrue(self.lua.eval('function(a,b) return a==b end')(
            self.mpl.logColumn.points['LEFT'][1],viewer.ItemLevelColumnHeader))
        self.assertEqual(self.lua.globals().PVEFrame.width,653)
        self.mpl.batchButton.scripts.OnClick()
        self.assertTrue(self.mpl.pendingReply.batch)
        self.mpl.SetOption('showInRaids',False)
        self.assertFalse(cell.shown)
        self.assertFalse(self.mpl.batchButton.shown)
        self.assertEqual(self.lua.globals().PVEFrame.width,563)

    def test_unknown_and_secret_activity_data_is_not_displayed(self):
        self.choose(*self.options)
        self.assertFalse(self.mpl.GroupLogsEnabled(self.lua.table_from([999])))
        self.assertFalse(self.mpl.GroupLogsEnabled(self.lua.table_from([])))
        self.assertFalse(self.mpl.GroupLogsEnabled(self.lua.table_from([self.lua.table_from({'secret':True})])))
        for field in ('categoryID','isMythicPlusActivity','isPvpActivity','isRatedPvpActivity','difficultyID'):
            activity=self.lua.table_from({'categoryID':3,'difficultyID':15})
            activity[field]=self.lua.table_from({'secret':True})
            with self.subTest(field=field):
                self.assertIsNone(self.mpl.GroupLogCategory(activity))

    def install_hooks(self):
        self.lua.execute('''
            eventFrames={}
            local original=CreateFrame
            CreateFrame=function(...) local f=original(...); eventFrames[#eventFrames+1]=f; return f end
        ''')
        self.lua.execute('return assert(loadstring(...))',(ROOT/'Integration.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.lua.execute('eventFrames[1].scripts.OnEvent(eventFrames[1],"PLAYER_LOGIN")')

    def test_search_tooltips_and_menus_use_search_category_not_own_listing(self):
        self.install_hooks()
        self.lua.globals().listingActivity=6
        self.choose('showInRaids')
        self.lua.globals().searchActivity=2
        self.lua.execute('''
            owner={resultID=10}
            root={count=0,CreateDivider=function() end,CreateButton=function(self) self.count=self.count+1 end}
            hooks.LFGListSearchEntry_OnEnter(owner)
            Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root)
        ''')
        self.assertGreater(len(self.lua.globals().GameTooltip.lines),0)
        self.assertEqual(self.lua.globals().root.count,3)
        self.lua.execute('''
            searchActivity=6; GameTooltip.lines={}; GameTooltip.mplKey=nil; root.count=0
            hooks.LFGListSearchEntry_OnEnter(owner)
            Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root)
        ''')
        self.assertEqual(len(self.lua.globals().GameTooltip.lines),0)
        self.assertEqual(self.lua.globals().root.count,0)

    def test_disabled_groups_do_not_block_manual_profiles(self):
        self.choose()
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.assertTrue(self.mpl.panel.shown)
        self.assertEqual(self.mpl.panel.name,'Киндрих')


if __name__=='__main__':
    unittest.main()
