"""Specialization history, recruitment context, and local-only profile switching."""
import copy
import sys
import unittest
import tempfile
from pathlib import Path
from urllib.parse import quote
from types import SimpleNamespace

import test_addon
from test_addon import ROOT, api_fixture
sys.path.insert(0, str(ROOT / "tools"))
import wcl_sync as wcl
import build_database as builder
import clipboard_protocol


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

    def test_companion_to_window_imports_each_logged_spec(self):
        self.transport()
        raw=api_fixture(); char=raw['data']['characterData']['character']
        char['damage']=char.pop('performance'); char['healing']=copy.deepcopy(char['damage'])
        # Shape observed in real WCL replies: alternate specs are in allStars,
        # while dungeon ranking rows only contain the best specialization.
        char['damage']['allStars']=[{'spec':'Elemental','points':3774},{'spec':'Enhancement','points':3000}]
        char['damage']['rankings'][0]['spec']='Elemental'
        char['damage']['rankings'][0]['bestSpec']='Elemental'
        char['healing']['allStars']=[]
        calls=[]
        def fetch(args):
            calls.append(args.spec)
            reply=copy.deepcopy(raw)
            if args.spec:
                d=reply['data']['characterData']['character']['damage']
                d['rankings'][0]['spec']=args.spec; d['rankings'][0]['bestSpec']=args.spec
                d['allStars']=[{'spec':args.spec,'points':3774}]
                d['throughputRankings']['12825']['best_per_second_amount']=111111 if args.spec=='Elemental' else 222222
            return reply
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.mpl.ShowDownload('Киндрих','Гордунни',self.mpl.panel.profile)
        request=self.mpl.downloadWindow.request
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-work-') as directory:
            response=clipboard_protocol.reply(request,{'eu':{'гордунни':'gordunni'}},Path(directory),fetch)
            count,error=self.mpl.ReceiveReply(response,True)
        self.assertIsNotNone(count,msg=error)
        self.assertEqual(set(calls),{None,'Elemental','Enhancement'})
        self.assertEqual(self.mpl.panel.specButton.text,'Все специализации')
        self.assertEqual(self.mpl.panel.profile.spec,'All specs')
        self.assertEqual(self.mpl.panel.profile.dungeons[1].amount,168110)
        self.assertEqual(set(self.mpl.ProfileSpecs('Киндрих','Гордунни').values()),{'Elemental','Enhancement'})
        self.mpl.SelectSpec('Киндрих','Гордунни','Enhancement')
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.assertEqual(self.mpl.panel.specButton.text,'Enhancement')
        self.assertEqual(self.mpl.panel.profile.dungeons[1].amount,222222)

    def test_expanded_download_rejects_legacy_companion_and_foreign_character(self):
        self.transport()
        self.mpl.ShowDownload('Киндрих','Гордунни',None)
        request_id=self.mpl.pendingReply.id
        count,error=self.mpl.ReceiveReply('MPLS1\n'+request_id+'\n'+self.export(),True)
        self.assertIsNone(count)
        self.assertIn('Companion',error)
        raw=api_fixture(); raw['data']['characterData']['character']['name']='Foreign'
        args=SimpleNamespace(realm='Гордунни',region='eu',zone=55,season='test',spec='Feral',metric='dps',server_slug=None)
        response='MPLS1\n'+request_id+'\nMPLV1 1.0.6 specprofiles\n'+self.export()+wcl.export(wcl.normalize(raw,args)).removeprefix('MPL1\n')
        count,error=self.mpl.ReceiveReply(response,True)
        self.assertIsNone(count)
        self.assertIn('не подходит выбранному персонажу',error)

    def test_leaderboard_only_reply_opens_normal_no_logs_profile(self):
        self.transport()
        raw=api_fixture(); char=raw['data']['characterData']['character']
        char['damage']=char.pop('performance')
        char['damage']['throughputRankings']=[]
        char['healing']=copy.deepcopy(char['damage'])
        self.mpl.ShowDownload('Киндрих','Гордунни',None)
        request=self.mpl.downloadWindow.request
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-work-') as directory:
            response=clipboard_protocol.reply(request,{'eu':{'гордунни':'gordunni'}},Path(directory),lambda _:raw)
            self.assertTrue(response.startswith('MPLE1\n'))
            cached=builder.read_cache(next(Path(directory).glob('*.json')))
            self.assertTrue(cached['negative'])
            self.assertNotIn('refresh_error',cached)
            edit=self.mpl.downloadWindow.edit
            edit.SetText(edit,response); edit.scripts.OnTextChanged(edit,True)
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
        self.assertFalse(self.mpl.downloadWindow.shown)
        self.assertTrue(self.mpl.panel.emptyMessage.shown)
        self.assertNotIn('Companion',self.mpl.panel.emptyMessage.text)

    def test_hidden_and_cooldown_replies_open_normal_empty_profile(self):
        self.transport()
        for name,message in [('Other',"No usable profile: Rankings hidden: Warcraft Logs denied access"), ('Cooldown',"No usable profile: Profile refresh is cooling down; retry after 3182 seconds")]:
            self.mpl.ShowDownload(name,'Thrall',None)
            f=self.mpl.downloadWindow
            response='MPLE1\n'+self.mpl.pendingReply.id+'\n'+quote(message,safe='')
            f.edit.SetText(f.edit,response); f.edit.scripts.OnTextChanged()
            self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
            self.assertFalse(f.shown)
            self.assertTrue(self.mpl.panel.shown)
            self.assertFalse(self.mpl.panel.profile)
            self.assertTrue(self.mpl.panel.emptyMessage.shown)
            self.assertNotIn('Companion',self.mpl.panel.emptyMessage.text)
            self.assertIsNone(self.mpl.pendingReply)

    def test_unexpected_reply_failure_stays_an_error(self):
        self.transport()
        self.mpl.ShowDownload('Other','Thrall',None)
        count,error=self.mpl.ReceiveReply('MPLE1\n'+self.mpl.pendingReply.id+'\n'+quote('Unknown zoneRankings JSON shape',safe=''),True)
        self.assertIsNone(count)
        self.assertIn('JSON shape',error)
        self.assertTrue(self.mpl.downloadWindow.shown)

    def test_known_hidden_reason_survives_reload_and_later_cooldown(self):
        self.transport()
        self.mpl.ShowDownload('Other','Thrall',None)
        self.mpl.ReceiveReply('MPLE1\n'+self.mpl.pendingReply.id+'\n'+quote('Rankings hidden: access denied',safe=''),True)
        self.mpl.profileStates=None  # Only SavedVariables survive an addon reload.
        self.mpl.ShowProfile('Other','Thrall')
        self.assertEqual(self.mpl.panel.emptyMessage.text,self.mpl.L['Логи скрыты в Warcraft Logs.'])
        self.mpl.ShowDownload('Other','Thrall',None)
        self.assertIsNone(self.mpl.pendingReply)
        # A delayed cooldown response must not erase the known access reason.
        self.lua.execute('MPlusLogs.pendingReply={id="late-cooldown",name="Other",realm="Thrall",spec="Arms"}')
        self.mpl.ReceiveReply('MPLE1\n'+self.mpl.pendingReply.id+'\n'+quote('Profile refresh is cooling down; retry after 300 seconds',safe=''),True)
        self.assertEqual(self.mpl.panel.emptyMessage.text,self.mpl.L['Логи скрыты в Warcraft Logs.'])

    def test_unknown_cooldown_describes_request_instead_of_log_access(self):
        self.transport()
        self.mpl.ShowDownload('Other','Thrall',None)
        self.mpl.ReceiveReply('MPLE1\n'+self.mpl.pendingReply.id+'\n'+quote('Profile refresh is cooling down; retry after 300 seconds',safe=''),True)
        self.assertEqual(self.mpl.panel.emptyMessage.text,self.mpl.L['Повторный запрос логов отложен. Его можно отправить позже.'])
        self.assertEqual(self.mpl.panel.specButton.detail.text,'Повторный запрос отложен')

    def live_player(self):
        self.lua.execute('''
            UnitClass=function() return "Death Knight","DEATHKNIGHT" end
            C_SpecializationInfo={
                GetSpecialization=function() return 1 end,
                GetSpecializationInfo=function() return 250,"Blood" end,
            }
        ''')

    def test_live_player_selector_only_contains_own_class(self):
        self.live_player()
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        specs=self.mpl.ProfileSpecs("Киндрих", "Гордунни")
        self.assertEqual(set(specs.values()), set())

    def test_live_spec_is_visible_even_with_all_specs_selected(self):
        self.live_player()
        self.mpl.SelectSpec("Киндрих", "Гордунни", "All specs")
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.assertEqual(self.mpl.panel.currentSpec.name.text, "Blood")
        self.assertEqual(self.mpl.panel.selectedSpec, "All specs")

    def test_unknown_class_does_not_offer_every_class(self):
        specs=self.mpl.ProfileSpecs("Nobody", "Гордунни")
        self.assertEqual(list(specs.values()), [])

    def test_current_spec_badge_uses_game_data_and_clears_for_unknown_character(self):
        self.live_player()
        self.lua.execute('''GetSpecializationInfoByID=function(id)
            if id==250 then return id,"Blood",nil,135770 end
        end''')
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        badge=self.mpl.panel.currentSpec
        self.assertEqual(badge.caption.text,"Текущая специализация")
        self.assertEqual(badge.name.text,"Blood")
        self.assertTrue(badge.icon.shown)
        self.assertEqual(self.mpl.panel.character.text,"Киндрих — Гордунни")
        self.mpl.SelectSpec("Киндрих", "Гордунни", "Feral")
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.assertEqual(badge.name.text,"Blood")
        self.mpl.ShowProfile("Nobody", "Гордунни")
        self.assertEqual(badge.name.text,"—")
        self.assertFalse(badge.icon.shown)

    def test_current_spec_badge_uses_applicant_spec_without_wcl_profile(self):
        self.lua.execute('''GetSpecializationInfoByID=function(id)
            if id==104 then return id,"Страж",nil,132276 end
        end''')
        self.mpl.RecordApplicant("Other-Thrall", "TANK", 104, "DRUID")
        self.mpl.ShowProfile("Other", "Thrall")
        self.assertEqual(self.mpl.panel.currentSpec.name.text,"Страж")
        self.assertTrue(self.mpl.panel.currentSpec.icon.shown)
        self.assertFalse(self.mpl.panel.profile)

    def test_live_player_defaults_to_all_specs_across_spec_changes(self):
        self.live_player()
        self.mpl.Import(self.export(None))
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.assertEqual(self.mpl.panel.selectedSpec, "All specs")
        self.assertEqual(self.mpl.panel.profile.spec, "All specs")
        self.lua.execute('C_SpecializationInfo.GetSpecializationInfo=function() return 252,"Unholy" end')
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.assertEqual(self.mpl.panel.selectedSpec, "All specs")
        self.assertEqual(self.mpl.panel.currentSpec.name.text, "Unholy")

    def test_target_class_is_known_without_inspect_and_cached_spec_is_used(self):
        self.lua.execute('''
            UnitFullName=function(unit)
                if unit=="target" then return "Other","Thrall" end
                return "Киндрих","Гордунни"
            end
            UnitClass=function() return "Mage","MAGE" end
            C_SpecializationInfo={GetInspectSpecialization=function() return 0 end}
        ''')
        self.mpl.ShowProfile("Other", "Thrall")
        specs=self.mpl.ProfileSpecs("Other", "Thrall")
        self.assertEqual(set(specs.values()), set())
        self.assertEqual("Other — Thrall", self.mpl.panel.character.text)
        self.lua.execute('C_SpecializationInfo.GetInspectSpecialization=function() return 63 end')
        self.mpl.ShowProfile("Other", "Thrall")
        self.assertEqual(self.mpl.panel.currentSpec.name.text, "Fire")

    def test_target_badge_requests_inspect_and_updates_when_ready(self):
        self.lua.execute('''
            inspectCalls=0; specReady=false
            UnitExists=function(unit) return unit=="target" end
            UnitFullName=function() return "Other","Thrall" end
            UnitClass=function() return "Mage","MAGE" end
            UnitGUID=function() return "Player-Other" end
            CanInspect=function() return true end
            NotifyInspect=function(unit) inspectCalls=inspectCalls+1; inspectedUnit=unit end
            C_SpecializationInfo={GetInspectSpecialization=function() return specReady and 63 or 0 end}
            GetSpecializationInfoByID=function(id) return id,"Fire",nil,135810 end
            local create=CreateFrame
            CreateFrame=function(...) local f=create(...); lastCreated=f; return f end
        ''')
        self.lua.execute("return assert(loadstring(...))", (ROOT / "Integration.lua").read_text(encoding="utf-8"))("MPlusLogs", self.mpl)
        events=self.lua.globals().lastCreated
        self.mpl.ShowProfile("Other", "Thrall")
        self.assertEqual(self.lua.globals().inspectCalls,1)
        self.assertEqual(self.lua.globals().inspectedUnit,"target")
        self.assertEqual(self.mpl.panel.currentSpec.name.text,"—")
        self.mpl.ShowProfile("Other", "Thrall")
        self.assertEqual(self.lua.globals().inspectCalls,1)
        self.lua.execute('specReady=true')
        events.scripts.OnEvent(events,"INSPECT_READY","Player-Other")
        self.assertEqual(self.mpl.panel.currentSpec.name.text,"Fire")
        self.assertTrue(self.mpl.panel.currentSpec.icon.shown)
        self.lua.execute('specReady=false; combat=true; GetServerTime=function() return 1791777610 end')
        self.mpl.ShowProfile("Other", "Thrall")
        self.assertEqual(self.lua.globals().inspectCalls,1)
        self.lua.execute('combat=false; CanInspect=function() return false end')
        self.mpl.ShowProfile("Other", "Thrall")
        self.assertEqual(self.lua.globals().inspectCalls,1)

    def test_applicant_class_can_be_inferred_from_spec_id(self):
        self.mpl.RecordApplicant("Other-Thrall", "DAMAGER", 252, None)
        specs=self.mpl.ProfileSpecs("Other", "Thrall", "DAMAGER")
        self.assertEqual(set(specs.values()), set())

    def test_localized_shared_slug_uses_character_class(self):
        self.live_player()
        self.lua.execute('''
            C_SpecializationInfo.GetSpecializationInfo=function() return 251,"Frost" end
            GetSpecializationInfoByID=function(id)
                if id==251 then return id,"Лёд" elseif id==64 then return id,"Маг: Лёд" end
            end
        ''')
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.assertEqual(self.mpl.panel.currentSpec.name.text, "Лёд")
        self.assertEqual(self.mpl.panel.specButton.text,"Все специализации")
        self.assertEqual(self.mpl.SpecLabel("Frost","DEATHKNIGHT"),"Лёд")
        self.assertEqual(self.mpl.SpecLabel("Frost","MAGE"),"Маг: Лёд")

    def test_spec_change_event_refreshes_open_profile_and_preserves_metric(self):
        self.live_player()
        self.lua.execute('''
            local create=CreateFrame
            CreateFrame=function(...) local f=create(...); lastCreated=f; return f end
        ''')
        self.lua.execute("return assert(loadstring(...))", (ROOT / "Integration.lua").read_text(encoding="utf-8"))("MPlusLogs", self.mpl)
        events=self.lua.globals().lastCreated
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.mpl.panel.viewMetric="hps"
        self.lua.execute('C_SpecializationInfo.GetSpecializationInfo=function() return 252,"Unholy" end')
        events.scripts.OnEvent(events,"PLAYER_SPECIALIZATION_CHANGED","player")
        self.assertEqual(self.mpl.panel.currentSpec.name.text,"Unholy")
        self.assertEqual(self.mpl.panel.viewMetric,"hps")

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

    def test_all_specs_default_is_independent_of_candidate_spec_and_role(self):
        self.mpl.Import(self.export()); self.mpl.Import(self.export("Feral"))
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance"); char["healing"]=copy.deepcopy(char["damage"])
        for role in ("TANK", "DAMAGER"):
            args=SimpleNamespace(realm="Гордунни",region="eu",zone=55,season="test",
                                 spec=None,role=role,metric="dps",server_slug=None)
            self.mpl.Import(wcl.export(wcl.normalize(raw,args)))
        for role,spec_id in [("TANK",104),("DAMAGER",103),("TANK",103),("DAMAGER",None)]:
            self.mpl.RecordApplicant("Киндрих-Гордунни", role, spec_id, "DRUID")
            self.assertEqual(self.mpl.SelectedSpec("Киндрих", "Гордунни"), "All specs")
            self.assertEqual(self.profile().spec, "All specs")
            self.assertEqual(self.profile().role, role)

    def test_known_spec_missing_is_requested_instead_of_using_fresh_all_specs(self):
        self.mpl.Import(self.export(None))
        self.mpl.RecordApplicant("Киндрих-Гордунни", "TANK", 104, "DRUID")
        self.mpl.SelectSpec("Киндрих", "Гордунни", "Guardian", "TANK")
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
        count, error = self.mpl.ReceiveReply("MPLS1\n" + self.mpl.pendingReply.id + "\nMPLV1 1.0.6 specprofiles\n" + self.export(), True)
        self.assertIsNone(count); self.assertIn("не соответствует запрошенным данным", error)
        count, _ = self.mpl.ReceiveReply("MPLS1\n" + self.mpl.pendingReply.id + "\nMPLV1 1.0.6 specprofiles\n" + self.export("Feral"), True)
        self.assertEqual(count, 1); self.assertEqual(self.mpl.panel.profile.spec, "Feral")

    def test_dungeon_tooltip_uses_selected_dungeon_and_best_result_key(self):
        self.mpl.Import(self.export())
        tooltip = self.lua.globals().GameTooltip
        self.mpl.AddTooltip(tooltip, "Киндрих-Гордунни", None, "Den of Nalorakk")
        lines = [tooltip.lines[i][1] for i in range(1, len(tooltip.lines)+1)]
        self.assertNotIn("Den of Nalorakk", lines)
        self.assertIn("[DON] DPS Best / Median", lines)
        self.assertIn("[DON] Ключ лучшего результата", lines)
        self.assertIn("[DON] Залогированные прохождения", lines)
        self.assertIn("DPS Best / Median", lines)
        self.assertNotIn("Altar of Fangs", lines)
        self.assertIn("Залогированные прохождения", lines)

    def test_missing_dungeon_does_not_show_other_dungeon_numbers(self):
        self.mpl.Import(self.export())
        tooltip = self.lua.globals().GameTooltip
        self.mpl.AddDungeonTooltip(tooltip, self.profile("Guardian"), "dps", False, "Murder Row")
        self.assertEqual(tooltip.lines[1][1], "[MR] Нет загруженных логов этого подземелья")
        self.assertEqual(len(tooltip.lines), 1)

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

    def test_selector_keeps_saved_profiles_and_restores_all_specs(self):
        self.transport()
        self.mpl.snapshots=None
        self.mpl.Import(self.export()); self.mpl.Import(self.export("Feral"))
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", 103, "DRUID")
        self.lua.execute('''
            MenuUtil={CreateContextMenu=function(_,builder)
                radioOptions={}
                local root={CreateTitle=function() end,CreateDivider=function() end,CreateButton=function() end,CreateRadio=function(_,label,checked,select)
                    radioOptions[label]={checked=checked,select=select}
                end}
                builder(nil,root)
            end}
        ''')
        self.mpl.ShowProfile("Киндрих", "Гордунни")
        self.mpl.panel.specButton.scripts.OnClick()
        choices=self.lua.globals().radioOptions
        self.assertFalse(choices["Feral — основной — загружено"].checked())
        self.assertIsNotNone(choices["Guardian — загружено"])  # Saved logs from other roles remain selectable.
        self.assertIsNone(choices.Balance)  # No Balance logs have been loaded.
        self.assertTrue(choices["Все специализации"].checked())
        choices["Guardian — загружено"].select()
        self.assertEqual(self.mpl.panel.profile.spec, "Guardian")
        self.assertEqual(self.profile("Feral").best, 62)
        self.mpl.panel.specButton.scripts.OnClick()
        choices=self.lua.globals().radioOptions
        self.assertTrue(choices["Guardian — загружено"].checked())
        choices["Feral — основной — загружено"].select()
        self.assertEqual(self.mpl.panel.profile.spec, "Feral")
        self.mpl.panel.specButton.scripts.OnClick()
        choices=self.lua.globals().radioOptions
        choices["Все специализации"].select()
        self.assertEqual(self.mpl.panel.selectedSpec, "All specs")
        self.assertFalse(self.mpl.panel.profile)
        self.assertTrue(self.mpl.panel.specButton.canSelectSpecs)
        self.mpl.ShowDownload("Киндрих", "Гордунни", None)
        self.assertEqual(self.mpl.pendingReply.spec, "")

    def test_all_specs_profiles_for_different_roles_do_not_overwrite_each_other(self):
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance"); char["healing"]=copy.deepcopy(char["damage"])
        for role in ("TANK", "DAMAGER"):
            args=SimpleNamespace(realm="Гордунни",region="eu",zone=55,season="test",
                                 spec=None,role=role,metric="dps",server_slug=None)
            self.mpl.Import(wcl.export(wcl.normalize(raw,args)))
        self.assertEqual(self.profile("All specs","TANK").role,"TANK")
        self.assertEqual(self.profile("All specs","DAMAGER").role,"DAMAGER")

    def test_aggregate_logs_keep_filter_and_export_main_spec(self):
        raw=api_fixture()
        raw["data"]["characterData"]["character"]["performance"]["rankings"][0]["bestSpec"]="Unholy"
        args=SimpleNamespace(realm="Thrall",region="eu",zone=55,season="test",spec=None,metric="dps",server_slug=None)
        profile=wcl.normalize(raw,args)
        self.assertEqual(profile["spec"],"All specs")
        self.assertEqual(profile["primarySpec"],"Unholy")
        self.mpl.Import(wcl.export(profile))
        self.mpl.SelectSpec("Киндрих","Thrall","All specs")
        self.mpl.ShowProfile("Киндрих","Thrall")
        self.assertEqual(self.mpl.panel.profile.spec,"All specs")
        self.assertEqual(self.mpl.panel.profile.primarySpec,"Unholy")
        self.assertEqual(self.mpl.panel.specButton.text,"Все специализации")
        self.assertEqual(self.mpl.panel.specButton.detail.text,"Выбрать специализацию логов")
        self.assertEqual(set(self.mpl.ProfileSpecs("Киндрих","Thrall").values()),set())

    def test_dual_metric_profile_roundtrips_main_spec(self):
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance"); char["healing"]=copy.deepcopy(char["damage"])
        char["damage"]["rankings"][0]["bestSpec"]="Unholy"
        args=SimpleNamespace(realm="Thrall",region="eu",zone=55,season="test",spec=None,role="DAMAGER",metric="dps",server_slug=None)
        profile=wcl.normalize(raw,args)
        parsed=self.mpl.Parse(wcl.export(profile))
        stored=parsed[self.mpl.Key("Киндрих","Thrall")]
        self.assertEqual(stored.primarySpec,"Unholy")
        self.assertTrue(stored.dual)

    def test_selector_shows_current_log_spec_and_switches_to_another(self):
        self.mpl.Import(self.export("Feral")); self.mpl.Import(self.export("Balance"))
        self.mpl.SelectSpec("Киндрих","Гордунни","Feral","DAMAGER")
        self.mpl.RecordApplicant("Киндрих-Гордунни","DAMAGER",103,"DRUID")
        self.mpl.ShowProfile("Киндрих","Гордунни")
        self.assertEqual(self.mpl.panel.specButton.text,"Feral")
        self.assertEqual(self.mpl.panel.profile.spec,"Feral")
        self.lua.execute('''
            MenuUtil={CreateContextMenu=function(_,builder)
                radioOptions={}
                builder(nil,{CreateTitle=function() end,CreateDivider=function() end,CreateButton=function() end,CreateRadio=function(_,text,checked,select)
                    radioOptions[text]={checked=checked,select=select}
                end})
            end}
        ''')
        self.mpl.panel.specButton.scripts.OnClick()
        choices=self.lua.globals().radioOptions
        self.assertIsNone(choices["Автоматически"])
        self.assertTrue(choices["Feral — основной — загружено"].checked())
        choices["Balance — загружено"].select()
        self.assertEqual(self.mpl.panel.specButton.text,"Balance")
        self.assertEqual(self.mpl.panel.profile.spec,"Balance")

    def test_aggregate_is_default_even_with_saved_main_spec(self):
        self.mpl.Import(self.export("Feral"))
        raw=api_fixture(); raw["data"]["characterData"]["character"]["performance"]["rankings"][0]["bestSpec"]="Feral"
        args=SimpleNamespace(realm="Гордунни",region="eu",zone=55,season="test",spec=None,metric="dps",server_slug=None)
        profile=wcl.normalize(raw,args); profile["updated"]="2026-10-13 00:00 UTC"
        self.mpl.Import(wcl.export(profile))
        self.mpl.ShowProfile("Киндрих","Гордунни")
        self.assertEqual(self.mpl.panel.specButton.text,"Все специализации")
        self.assertEqual(self.mpl.panel.profile.spec,"All specs")

    def test_main_spec_comes_from_applicant_even_without_its_logs(self):
        self.mpl.Import(self.export("Feral"))
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", 102, "DRUID")
        self.assertEqual(self.mpl.MainProfileSpec("Киндрих", "Гордунни"), "Balance")
        self.mpl.SelectSpec("Киндрих", "Гордунни", "Feral")
        self.assertEqual(self.mpl.MainProfileSpec("Киндрих", "Гордунни"), "Balance")
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", 103, "DRUID")
        self.assertEqual(self.mpl.MainProfileSpec("Киндрих", "Гордунни"), "Feral")
        self.assertIsNone(self.mpl.MainProfileSpec("Киндрих", "Гордунни", "HEALER"))

    def test_log_history_does_not_mark_unknown_current_spec_as_main(self):
        self.mpl.Import(self.export("Feral"))
        self.assertIsNone(self.mpl.MainProfileSpec("Киндрих", "Гордунни"))
        self.assertEqual(self.mpl.DefaultProfileSpec("Киндрих", "Гордунни"), "Feral")
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", 103, "DRUID")
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", None, "DRUID")
        self.assertIsNone(self.mpl.MainProfileSpec("Киндрих", "Гордунни"))

    def test_main_spec_setting_switches_between_current_and_saved_logs(self):
        self.mpl.Import(self.export("Feral"))
        self.mpl.Import(self.export("Balance", date="2026-10-13 00:00 UTC"))
        self.mpl.RecordApplicant("Киндрих-Гордунни", "DAMAGER", 103, "DRUID")
        self.assertEqual(self.mpl.MainProfileSpec("Киндрих", "Гордунни"), "Feral")
        self.mpl.SetOption("mainSpec", "logs")
        self.assertEqual(self.mpl.MainProfileSpec("Киндрих", "Гордунни"), "Balance")
        self.assertEqual(self.mpl.SelectedSpec("Киндрих", "Гордунни"), "All specs")
        self.mpl.SelectSpec("Киндрих", "Гордунни", "Feral")
        self.assertEqual(self.mpl.MainProfileSpec("Киндрих", "Гордунни"), "Balance")
        self.mpl.SetOption("mainSpec", "current")
        self.assertEqual(self.mpl.MainProfileSpec("Киндрих", "Гордунни"), "Feral")


if __name__ == "__main__":
    unittest.main()
