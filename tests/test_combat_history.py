"""Synthetic combat-log fixtures; no credentials, HTTP calls, or real-player data."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import combat_history as history
import clipboard_protocol
import test_addon


GUIDS=[f"Player-1-{i:08X}" for i in range(1,6)]
NAMES=[f"Player{i}-Gordunni-EU" for i in range(1,6)]


def line(payload,time="12:00:00.0000"):
    return f"10/1/2026 {time}  {payload}\n"


def event(kind,src=0,dst=None):
    source=GUIDS[src] if isinstance(src,int) else src
    destination=dst or "Creature-0-1-1-1-1-1"
    name=NAMES[src] if isinstance(src,int) else "Pet"
    dest_name=NAMES[GUIDS.index(destination)] if destination in GUIDS else "Enemy"
    return f'{kind},{source},"{name}",0x511,0x0,{destination},"{dest_name}",0xa48,0x0,1,"Ability",1,2,"Target ability",1'


def fixture(end=True):
    rows=[line('CHALLENGE_MODE_START,"Test dungeon",2813,587,19,[1,2]')]
    for i,guid in enumerate(GUIDS):
        fields=["COMBATANT_INFO",guid]+["0"]*24
        fields[25]=str([104,264,269,72,259][i])
        rows.append(line(",".join(fields)))
        rows.append(line(event("SPELL_CAST_SUCCESS",i)))
    rows += [line(event("SPELL_INTERRUPT",0)),line(event("SPELL_DISPEL",1)),
             line(event("SPELL_STOLEN",2)),line(event("UNIT_DIED",3,GUIDS[3]))]
    if end: rows.append(line("CHALLENGE_MODE_END,2813,1,19,120000", "12:02:00.0000"))
    return "".join(rows)


class CombatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix=".test-work-history-",dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.log=self.folder/"WoWCombatLog.txt"
        self.store=history.History(self.folder/"history.sqlite3")

    def scan(self,body):
        self.log.write_text(body,encoding="utf-8")
        self.store.scan(self.log,max_bytes=10000000)
        return self.store.runs()[0]

    def test_complete_party_counts_and_query_name_region(self):
        run=self.scan(fixture())[0]
        self.assertEqual(run["coverage"],"complete")
        self.assertEqual(run["duration"],120)
        self.assertEqual(len(run["players"]),5)
        players={p["guid"]:p for p in run["players"]}
        self.assertEqual(players[GUIDS[0]]["interrupts"],1)
        self.assertEqual(players[GUIDS[1]]["dispels"],1)
        self.assertEqual(players[GUIDS[2]]["dispels"],1)
        self.assertEqual(players[GUIDS[3]]["deaths"],1)
        self.assertEqual(self.store.runs("Player1","Gor dunni","eu")[1],1)
        self.assertEqual(self.store.runs("Player1","Gordunni","us")[1],0)

    def test_pet_utility_counts_for_owner_but_pet_deaths_do_not(self):
        pet="Creature-0-1-1-1-123-1"
        summon=line(event("SPELL_SUMMON",1,pet))
        body=fixture(False)+line(event("SPELL_DISPEL",pet))+line(event("UNIT_DIED",1,pet))
        body+=line("CHALLENGE_MODE_END,2813,1,19,120000","12:02:00.0000")
        run=self.scan(summon+body)[0]
        healer=next(p for p in run["players"] if p["guid"]==GUIDS[1])
        self.assertEqual(healer["dispels"],2)
        self.assertEqual(healer["deaths"],0)

    def test_missing_pet_owner_prevents_claiming_complete_totals(self):
        body=fixture().replace(line(event("SPELL_INTERRUPT",0)),line(event("SPELL_INTERRUPT","Pet-1-001")))
        self.assertEqual(self.scan(body)[0]["coverage"],"partial")

    def test_incomplete_line_and_restart_resume_without_double_counting(self):
        body=fixture()
        self.log.write_text(body[:-5],encoding="utf-8")
        self.store.scan(self.log)
        self.assertEqual(self.store.runs()[0][0]["coverage"],"partial")
        with self.log.open("a",encoding="utf-8") as f: f.write(body[-5:])
        restarted=history.History(self.store.path)
        restarted.scan(self.log)
        self.assertEqual(restarted.runs()[0][0]["coverage"],"complete")
        self.assertEqual(restarted.runs()[1],1)
        self.assertEqual(restarted.scan(self.log)["lines"],0)

    def test_rotation_and_duplicate_archive_preserve_history(self):
        self.scan(fixture())
        archive=self.folder/"Archived.txt"; archive.write_text(fixture(),encoding="utf-8")
        self.store.scan(archive)
        self.assertEqual(self.store.runs()[1],1)
        self.assertEqual(len(self.store.runs()[0][0]["sources"]),2)
        self.scan(fixture().replace("12:","13:"))
        self.assertEqual(self.store.runs()[1],2)

    def test_partial_or_malformed_logs_never_become_complete(self):
        self.assertEqual(self.scan(fixture().replace(line("COMBATANT_INFO,"+GUIDS[4]+","+",".join(["0"]*23)+",259"),""))[0]["coverage"],"partial")
        self.assertEqual(self.scan(fixture(False))[0]["coverage"],"partial")
        broken=fixture().replace(line(event("SPELL_INTERRUPT",0)),line("SPELL_INTERRUPT,broken"))
        run=self.scan(broken)[0]
        self.assertEqual(run["coverage"],"partial")
        self.assertGreater(run["malformed"],0)

    def test_no_boundaries_never_invents_a_run(self):
        self.assertEqual(self.scan(line(event("SPELL_INTERRUPT",0))),[])

    def test_export_has_only_requested_runs_and_source_basename(self):
        self.scan(fixture())
        body=history.export(self.store,"eu","Gordunni","Player1")
        self.assertTrue(body.startswith("MPLH1\n"))
        self.assertNotIn(str(self.folder),body)
        self.assertIn("WoWCombatLog.txt",body)
        self.assertEqual(body.count("\nA\t"),5)
        self.assertEqual(history.export(self.store,"eu","Gordunni","Missing").count("\nR\t"),0)

    def test_local_request_never_calls_wcl_and_preserves_envelope(self):
        self.scan(fixture())
        request="MPLS2\n123-1\nMPLC1 history\nMPLHQ1\nQ\teu\tGordunni\tPlayer1\n"
        def forbidden(_): self.fail("Local history must never query WCL")
        reply=clipboard_protocol.reply(request,{},self.folder,forbidden,
            local_history=lambda region,realm,name:history.export(self.store,region,realm,name))
        self.assertIn("batch,dual,history,specprofiles,updater",reply)
        self.assertTrue(reply.startswith("MPLS1\n123-1\n"))
        self.assertTrue(clipboard_protocol.reply(request,{},self.folder,forbidden).startswith("MPLE1\n"))

    def test_old_timestamp_is_explicitly_marked_as_inferred(self):
        parser=history.Parser("old.txt",year=2026)
        runs=[]
        for raw in fixture().replace("/2026 "," ").splitlines(True): runs+=parser.feed(raw)
        self.assertTrue(runs[0]["year_inferred"])

    def test_observed_region_prevents_duplicate_when_source_region_is_corrected(self):
        self.log.write_text(fixture().replace("-EU","-US"),encoding="utf-8")
        self.store.scan(self.log,"eu")
        self.store.scan(self.log,"us")
        self.assertEqual(self.store.runs(region="us")[1],1)

    def test_logging_restart_marks_a_gap_and_blocked_publish_never_touches_git(self):
        body=fixture().replace(line(event("SPELL_INTERRUPT",0)),line("COMBAT_LOG_VERSION,22","12:01:00.0000")+line(event("SPELL_INTERRUPT",0)))
        self.assertEqual(self.scan(body)[0]["coverage"],"partial")
        import publish_changes
        (self.folder/".release-hold").write_text("user hold",encoding="utf-8")
        with patch.object(publish_changes,"ROOT",self.folder),patch.object(sys,"argv",["publish","--summary","test"]), \
             patch.object(publish_changes,"git") as git,patch.object(publish_changes.export_release_source,"entries") as entries:
            with self.assertRaisesRegex(RuntimeError,"hold"): publish_changes.main()
            git.assert_not_called(); entries.assert_not_called()

    def test_archive_format_header_immediately_after_start_is_not_a_gap(self):
        body=fixture().replace(line('CHALLENGE_MODE_START,"Test dungeon",2813,587,19,[1,2]'),
            line('CHALLENGE_MODE_START,"Test dungeon",2813,587,19,[1,2]')+line('COMBAT_LOG_VERSION,22','12:00:01.0000'))
        self.assertEqual(self.scan(body)[0]["coverage"],"complete")

    def test_local_gui_can_render_history_without_an_oauth_session(self):
        import tkinter as tk
        import queue
        import history_ui
        import companion_i18n as i18n
        import appearance
        self.scan(fixture())
        root=tk.Tk(); root.withdraw()
        class App:
            applied_theme="dark"
            config={"combat_log_path":str(self.log),"combat_log_region":"eu"}
            messages=queue.Queue()
            def textvar(_,text): return i18n.TextVar(root,text)
        app=App(); app.root=root
        view=history_ui.LocalHistory(app,self.store.path)
        try:
            view.open(); view.worker.join(timeout=5); view.render(); root.update()
            self.assertEqual(len(view.run_list.get_children()),1)
            self.assertEqual(len(view.party.get_children()),5)
            self.assertNotIn("{source}",view.detail.get())
            self.assertLessEqual(view.body.winfo_reqheight(),view.window.winfo_height())
            for mode in ("dark", "light", "dark"):
                with patch.object(appearance,"titlebar") as titlebar:
                    view.apply_theme(mode); root.update_idletasks()
                    self.assertEqual(view.window.cget("background"),appearance.PALETTES[mode]["background"])
                    titlebar.assert_any_call(view.window,mode=="dark")
            body=view.reply("eu","Gordunni","Player1")
            self.assertTrue(body.startswith("MPLH1\n"))
        finally:
            view.close(); root.destroy()


class AddonHistoryTests(unittest.TestCase):
    def setUp(self):
        test_addon.AddonTests.setUp(self)
        for name in ["History.lua","Transport.lua"]:
            self.lua.execute("return assert(loadstring(...))",(ROOT/name).read_text(encoding="utf-8"))("MPlusLogs",self.mpl)
        self.lua.execute("timers={}; C_Timer={After=function(_,fn) timers[#timers+1]=fn end}")
        parser=history.Parser("WoWCombatLog.txt")
        self.run=[]
        for raw in fixture().splitlines(True): self.run+=parser.feed(raw)
        class Store:
            def runs(_,name,realm,region,limit): return self.run,len(self.run)
        self.body=history.export(Store(),"eu","Gordunni","Player1")

    def test_separate_store_and_group_view_with_observation_count(self):
        result=self.mpl.ParseHistory(self.body)
        self.assertEqual(self.mpl.StoreHistory(result),1)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)
        self.mpl.ShowHistory("Player1","Gordunni")
        self.assertEqual(len(self.mpl.historyWindow.runs),1)
        self.assertIn("1",self.mpl.historyWindow.summary.text)
        self.assertEqual(len(self.mpl.historyWindow.selected.players),5)
        self.assertIn("WoWCombatLog.txt",self.mpl.historyWindow.source.text)

    def test_clipboard_roundtrip_and_foreign_reply_rejected_atomically(self):
        from urllib.parse import quote
        request_id,request=self.mpl.SendHistoryRequest("Player1","Gordunni")
        self.assertIn("MPLC1 history",request)
        meta="MPLV1 1.0.6 batch,dual,history,specprofiles,updater\nMPLB1\n"
        foreign=self.body.replace("\tPlayer1\t","\tPlayer2\t",1)
        count,error=self.mpl.ReceiveReply("MPLS1\n"+request_id+"\n"+meta+quote(foreign,safe=""),True)
        self.assertIsNone(count); self.assertIsNone(self.lua.globals().MPlusLogsDB.localHistory)
        count=self.mpl.ReceiveReply("MPLS1\n"+request_id+"\n"+meta+quote(self.body,safe=""),True)
        self.assertEqual(count,1)
        self.assertEqual(self.mpl.historyWindow.name,"Player1")

    def test_partial_observations_do_not_enter_complete_totals(self):
        partial=self.body.replace("\tcompleted\tcomplete\t","\tincomplete\tpartial\t")
        result=self.mpl.ParseHistory(partial)
        self.mpl.StoreHistory(result)
        runs,n,totals=self.mpl.HistoryRuns("Player1","Gordunni")
        self.assertEqual(len(runs),1); self.assertEqual(n,0)
        self.mpl.ShowHistory("Player1","Gordunni")
        self.assertIn("—",self.mpl.historyWindow.summary.text)

    def test_corrupt_or_duplicate_records_cannot_import(self):
        for body in [self.body[:-2],self.body.replace("\t1\t0\t0\n","\t-1\t0\t0\n",1),
                     self.body+self.body.split("\n",2)[2]]:
            self.assertIsNone(self.mpl.ParseHistory(body)[0])


if __name__=="__main__": unittest.main()
