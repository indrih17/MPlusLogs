"""Specialization history, recruitment context, and local-only profile switching."""
import copy
import sys
import unittest
from types import SimpleNamespace

import test_addon
from test_addon import ROOT, api_fixture
sys.path.insert(0, str(ROOT / "tools"))
import wcl_sync as wcl
import build_database as builder


class SpecProfileTests(unittest.TestCase):
    setUp = test_addon.AddonTests.setUp

    def export(self, spec="Guardian", role=None, best=62, date="2026-10-12 04:00 UTC"):
        raw = api_fixture()
        args = SimpleNamespace(realm="Гордунни", region="eu", zone=55, season="test",
                               spec=spec, role=role, metric="dps", server_slug=None)
        profile = wcl.normalize(raw, args)
        profile.update(best=best, updated=date)
        return wcl.export(profile)

    def transport(self):
        self.lua.execute("return assert(loadstring(...))", (ROOT / "Transport.lua").read_text(encoding="utf-8"))("MPlusLogs", self.mpl)
        self.lua.execute("timers={}; C_Timer={After=function(_,fn) timers[#timers+1]=fn end}")

    def profile(self, spec=None, role=None):
        return self.mpl.GetProfile("Киндрих", "Гордунни", spec, role)[0]

    def test_imports_preserve_legacy_and_other_specializations(self):
        self.mpl.Import(self.export())
        self.mpl.Import(self.export("Feral", best=88))
        self.assertEqual(self.profile("Guardian").best, 62)
        self.assertEqual(self.profile("Feral").best, 88)
        self.mpl.SelectSpec("Киндрих", "Гордунни", "Guardian")
        self.assertEqual(self.profile().spec, "Guardian")
        self.mpl.SelectSpec("Киндрих", "Гордунни", "Balance")
        self.assertIsNone(self.profile())
        # Changing selection does not discard either stored profile.
        self.assertEqual(self.profile("Feral").best, 88)

    def test_multi_spec_import_and_bundle_keep_both_profiles(self):
        text = self.export() + self.export("Feral").removeprefix("MPL1\n")
        self.assertEqual(self.mpl.Import(text), 2)
        self.assertEqual(self.profile("Guardian").spec, "Guardian")
        self.assertEqual(self.profile("Feral").spec, "Feral")
        self.assertIsNone(self.mpl.Parse(self.export() + self.export().removeprefix("MPL1\n"))[0])
        first = wcl.normalize(api_fixture(), SimpleNamespace(realm="Гордунни", region="eu", zone=55,
                              season="test", spec="Guardian", metric="dps", server_slug=None))
        second = copy.deepcopy(first); second["spec"] = "Feral"
        code = builder.bundle([first, second])
        self.lua.execute("return assert(loadstring(...))", code)("MPlusLogs", self.mpl)
        self.mpl.LoadBundle()
        self.assertEqual(self.profile("Feral").spec, "Feral")

    def test_legacy_saved_profile_migrates_without_overwrite(self):
        parsed = self.mpl.Parse(self.export())
        key = self.mpl.Key("Киндрих", "Гордунни")
        self.lua.globals().MPlusLogsDB.profiles[key] = parsed[key]
        self.mpl.Import(self.export("Feral"))
        self.assertEqual(self.profile("Guardian").spec, "Guardian")

    def test_spec_auto_selection_follows_candidate_and_applied_role(self):
        self.mpl.Import(self.export()); self.mpl.Import(self.export("Feral"))
        self.mpl.RecordApplicant("Киндрих-Гордунни", "TANK", 104, "DRUID")
        self.assertEqual(self.profile().spec, "Guardian")
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", 103, "DRUID")
        self.assertEqual(self.profile().spec, "Feral")
        self.mpl.RecordApplicant("Киндрих-Гордунни", "TANK", 103, "DRUID")
        self.assertEqual(self.profile().spec, "All specs")  # Never label Feral as tank data.
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", None, "DRUID")
        self.assertEqual(self.mpl.SelectedSpec("Киндрих", "Гордунни"), "All specs")

    def test_known_spec_missing_is_requested_instead_of_using_fresh_all_specs(self):
        self.mpl.Import(self.export(None))
        self.mpl.RecordApplicant("Киндрих-Гордунни", "TANK", 104, "DRUID")
        players = self.lua.table_from([self.lua.table_from({"name":"Киндрих", "realm":"Гордунни", "spec":"Guardian", "role":"TANK"})])
        pending, skipped = self.mpl.FilterFreshProfiles(players)
        self.assertEqual(len(pending), 1); self.assertEqual(skipped, 0)
        self.transport()
        _, request = self.mpl.SendBatchRequest(players)
        self.assertIn("\tdps\tGuardian\tTANK\n", request)

    def test_download_selected_missing_spec_and_reject_wrong_response(self):
        self.transport()
        self.mpl.SelectSpec("Киндрих", "Гордунни", "Feral")
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.assertFalse(self.mpl.panel.profile)
        self.mpl.ShowDownload("Киндрих", "Гордунни", None)
        self.assertEqual(self.mpl.pendingReply.spec, "Feral")
        count, error = self.mpl.ReceiveReply("MPLS1\n" + self.mpl.pendingReply.id + "\n" + self.export(), True)
        self.assertIsNone(count); self.assertIn("специализац", error)
        count, _ = self.mpl.ReceiveReply("MPLS1\n" + self.mpl.pendingReply.id + "\n" + self.export("Feral"), True)
        self.assertEqual(count, 1); self.assertEqual(self.mpl.panel.profile.spec, "Feral")

    def test_dungeon_tooltip_uses_selected_dungeon_and_best_result_key(self):
        self.mpl.Import(self.export())
        tooltip = self.lua.globals().GameTooltip
        self.mpl.AddTooltip(tooltip, "Киндрих-Гордунни", None, "Den of Nalorakk")
        lines = [tooltip.lines[i][1] for i in range(1, len(tooltip.lines)+1)]
        self.assertIn("Den of Nalorakk", lines)
        self.assertIn("Ключ лучшего результата", lines)
        self.assertNotIn("Altar of Fangs", lines)
        self.assertIn("Залогированные прохождения", lines)

    def test_missing_dungeon_does_not_show_other_dungeon_numbers(self):
        self.mpl.Import(self.export())
        tooltip = self.lua.globals().GameTooltip
        self.mpl.AddDungeonTooltip(tooltip, self.profile(), "dps", False, "Murder Row")
        self.assertEqual(tooltip.lines[2][1], "Нет загруженных логов этого подземелья")
        self.assertEqual(len(tooltip.lines), 2)

    def test_listing_resolution_uses_map_ids_and_refuses_ambiguous_activities(self):
        self.lua.execute('''
            C_LFGList.GetActiveEntryInfo=function() return {activityIDs={1}} end
            C_LFGList.GetActivityInfoTable=function(id)
                return {isMythicPlusActivity=true,mapID=id==1 and 1754 or 1763,fullName="localized"}
            end
            C_ChallengeMode={GetMapUIInfo=function(id)
                return "localized dungeon",id,1800,nil,nil,id==249 and 1754 or (id==250 and 1763 or 9999)
            end}
        ''')
        self.assertEqual(self.mpl.ListedDungeon(), "Kings' Rest")
        self.assertIsNone(self.mpl.ListedDungeon(self.lua.table_from([1, 2])))
        self.lua.execute("combat=true")
        self.assertIsNone(self.mpl.ListedDungeon())

    def test_selector_keeps_saved_profiles_and_restores_automatic_selection(self):
        self.transport()
        self.mpl.Import(self.export()); self.mpl.Import(self.export("Feral"))
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", 103, "DRUID")
        self.lua.execute('''
            MenuUtil={CreateContextMenu=function(_,builder)
                radioOptions={}
                local root={CreateTitle=function() end,CreateRadio=function(_,label,checked,select)
                    radioOptions[label]={checked=checked,select=select}
                end}
                builder(nil,root)
            end}
        ''')
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.mpl.panel.specButton.scripts.OnClick()
        choices=self.lua.globals().radioOptions
        self.assertTrue(choices["Автоматически"].checked())
        self.assertIsNone(choices.Guardian)  # Tank spec is excluded for a DPS applicant.
        self.assertIsNotNone(choices.Balance)
        choices.Balance.select()
        self.assertFalse(self.mpl.panel.profile)
        self.assertEqual(self.profile("Feral").best, 62)
        self.mpl.panel.specButton.scripts.OnClick()
        choices=self.lua.globals().radioOptions
        self.assertTrue(choices.Balance.checked())
        choices["Автоматически"].select()
        self.assertEqual(self.mpl.panel.profile.spec, "Feral")

    def test_all_specs_profiles_for_different_roles_do_not_overwrite_each_other(self):
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance"); char["healing"]=copy.deepcopy(char["damage"])
        for role in ("TANK", "DAMAGER"):
            args=SimpleNamespace(realm="Гордунни",region="eu",zone=55,season="test",
                                 spec=None,role=role,metric="dps",server_slug=None)
            self.mpl.Import(wcl.export(wcl.normalize(raw,args)))
        self.assertEqual(self.profile("All specs","TANK").role,"TANK")
        self.assertEqual(self.profile("All specs","DAMAGER").role,"DAMAGER")


if __name__ == "__main__":
    unittest.main()
