"""Real Lua regressions for identity, access state and request boundaries."""
import unittest

import test_batch
import test_name_search


class LuaBoundaryAuditTests(unittest.TestCase):
    setUp = test_batch.BatchTests.setUp

    def test_secret_realm_never_falls_back_to_same_name_on_local_realm(self):
        realm = self.lua.table_from({"secret": True})
        self.assertIsNone(self.mpl.Identity("Alice", realm))
        self.assertIsNone(self.mpl.GetProfile("Alice", realm))

    def test_unit_tooltip_ignores_missing_or_secret_identity_before_recording_role(self):
        # Capture the production event frame while reloading Integration.lua.
        self.lua.execute('''
            local create=CreateFrame
            CreateFrame=function(...) local f=create(...); latestFrame=f; return f end
        ''')
        self.lua.execute("return assert(loadstring(...))",
                         (test_batch.ROOT / "Integration.lua").read_text(encoding="utf-8"))("MPlusLogs", self.mpl)
        self.lua.execute('''
            latestFrame.scripts.OnEvent(latestFrame,"PLAYER_LOGIN")
            MPlusLogs.roles=nil
            UnitGroupRolesAssigned=function() return "HEALER" end
            UnitFullName=function() return nil,nil end
            unitTooltip(GameTooltip)
            UnitFullName=function() return "Alice",{secret=true} end
            unitTooltip(GameTooltip)
        ''')
        self.assertIsNone(self.mpl.roles)
        self.assertEqual(len(self.lua.globals().GameTooltip.lines), 0)

    def test_hidden_state_suppresses_cached_percentiles_in_tooltip(self):
        self.lua.execute('''
            local MPL=...
            MPL.StoreProfiles({{name="Alice",realm="Гордунни",region="eu",spec="All specs",
                role="DAMAGER",metric="dps",dual=true,best=99,median=91,runs=23,
                updated="2026-10-12 04:00 UTC",source="WCL API",season="test",dungeons={}}})
            MPlusLogsDB.profileStates={[MPL.Key("Alice","Гордунни")]=
                {reason="hidden",expires=GetServerTime()+3600}}
        ''', self.mpl)
        self.mpl.AddTooltip(self.lua.globals().GameTooltip, "Alice", "Гордунни")
        lines = [str(value) for row in self.lua.globals().GameTooltip.lines.values()
                 for value in row.values()]
        self.assertIn(self.mpl.L["Логи скрыты в Warcraft Logs."], lines)
        self.assertFalse(any("99%" in value for value in lines))

    def test_batch_request_snapshots_selection_without_mutating_caller(self):
        player = self.lua.table_from(dict(name="Alice", realm="Гордунни", role="HEALER", spec="All specs"))
        players = self.lua.table_from([player])
        self.mpl.SendBatchRequest(players)
        self.assertEqual(player.spec, "All specs")
        player.role = "DAMAGER"
        player.spec = "Arms"
        pending = self.mpl.pendingReply
        self.assertEqual(pending.expected[self.mpl.Key("Alice", "Гордунни")].role, "HEALER")
        self.assertEqual(pending.players[1].role, "HEALER")


class SearchCacheAuditTests(unittest.TestCase):
    setUp = test_name_search.NameSearchTests.setUp

    def test_same_name_cross_realm_members_keep_distinct_tabs_after_roster_update(self):
        self.lua.execute('''
            searchMembers[2]={name="Twin",classFilename="WARRIOR",assignedRole="DAMAGER"}
            searchMembers[3]={name="Twin",classFilename="WARRIOR",assignedRole="DAMAGER"}
            C_LFGList.GetSearchResultInfo=function()
                return {leaderName=leaderName,activityIDs={1},numMembers=3}
            end
            MPlusLogs.ShowSearchGroup(10)
            MPlusLogs.UpdateSearchGroupRoster(10)
        ''')
        players = self.mpl.searchGroupWindow.players
        self.assertFalse(self.lua.eval("rawequal")(players[2], players[3]))
        self.assertEqual(len(players), 3)

    def test_legacy_wrong_metric_profile_does_not_complete_search_group(self):
        self.lua.execute('''
            local MPL=...
            MPL.StoreProfiles({{name="Frákkie",realm="Draenor",region="eu",spec="All specs",
                role="DAMAGER",metric="hps",dual=false,best=99,median=91,runs=23,
                updated="2026-10-12 04:00 UTC",source="WCL API",season="test",dungeons={}}})
            searchMembers={searchMembers[1]}
            C_LFGList.GetSearchResultInfo=function()
                return {leaderName=leaderName,activityIDs={1},numMembers=1}
            end
            MPL.ShowSearchGroup(10)
        ''', self.mpl)
        self.assertTrue(self.mpl.SearchGroupHasPendingProfiles(10))
        self.mpl.BeginSearchGroupRequest()
        self.assertEqual(len(self.mpl.searchGroupWindow.requestPlayers), 1)


if __name__ == "__main__":
    unittest.main()
